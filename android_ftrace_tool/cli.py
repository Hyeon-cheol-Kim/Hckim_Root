"""
Android ftrace 로그 도구 - CLI(UI) 계층
========================================
core.py 의 순수 로직을 호출해 대화형 콘솔 UI 를 제공한다.

요구사항 동작 시퀀스:
  1) adb 디바이스 목록 출력 → 선택해 연결
  2) 설정 가능한 ftrace 옵션 + '설정완료' 메뉴 출력
     → '설정완료' 전까지 선택한 옵션을 즉시 enable
  3) 버퍼 최대화 등 준비 작업 + 저장 파일명 입력
  4) ftrace 로그 출력/저장 시작

UI 분리 설계(요구사항 #4):
  이 파일의 모든 화면 출력/입력은 print()/input() 으로 격리되어 있다.
  향후 Windows GUI 로 확장할 때는 이 cli.py 대신 gui.py 를 새로 만들고
  동일한 core.py 함수들을 호출하면 된다. 로직 수정은 필요 없다.
"""

import os
import sys
import time
import argparse

# 패키지/단일 실행 양쪽을 지원하기 위한 import 처리
try:
    from .core import Adb, Ftrace, AdbError, default_log_filename
except ImportError:                       # 직접 실행(python cli.py)인 경우
    from core import Adb, Ftrace, AdbError, default_log_filename


# ── 출력 헬퍼 ──────────────────────────────────────────────────────
def banner(title):
    """섹션 제목을 보기 좋게 출력한다."""
    line = "═" * 60
    print(f"\n{line}\n  {title}\n{line}")


# 연속 EOF 횟수. 입력 스트림이 끝난 상태에서 재프롬프트 루프가 무한히
# 도는 것을 막기 위한 안전장치.
_eof_streak = 0
_EOF_LIMIT = 3


def ask(prompt, default=None):
    """
    입력을 받되 빈 입력이면 default 를 반환한다.

    EOF(Ctrl-D, 파이프 입력 종료) 처리:
      - 처음 몇 번은 default 를 돌려줘 자동화(echo ... | tool)를 지원한다.
      - 연속 EOF 가 _EOF_LIMIT 회를 넘으면 EOFError 를 올려, 같은 기본값을
        반복 반환해 무한 루프에 빠지는 것을 막는다.
    """
    global _eof_streak
    suffix = f" [{default}]" if default is not None else ""
    try:
        val = input(f"{prompt}{suffix}: ").strip()
    except EOFError:
        _eof_streak += 1
        print()
        if _eof_streak >= _EOF_LIMIT:
            raise
        return default if default is not None else "q"
    _eof_streak = 0                       # 정상 입력 시 카운터 리셋
    return val if val else (default if default is not None else "")


# ╔══════════════════════════════════════════════════════════════════╗
# ║ 단계 1) 디바이스 선택                                              ║
# ╚══════════════════════════════════════════════════════════════════╝
def select_device(adb_path):
    """연결된 adb 디바이스를 출력하고 사용자가 하나를 고르게 한다."""
    banner("1단계: adb 디바이스 연결")
    probe = Adb(adb_path=adb_path)
    try:
        devices = probe.list_devices()
    except AdbError as e:
        print(f"[오류] {e}")
        return None

    if not devices:
        print("연결된 디바이스가 없습니다. USB 연결과 'USB 디버깅' 설정을 확인하세요.")
        return None

    print("연결된 디바이스 목록:")
    for i, d in enumerate(devices, 1):
        label = d.model or d.product or "(이름 미상)"
        flag = "" if d.ready else f"  <-- 상태: {d.state} (사용 불가)"
        print(f"  {i}) {d.serial:<24} {label}{flag}")

    while True:
        sel = ask("연결할 디바이스 번호 입력 (q=종료)", "1")
        if sel.lower() == "q":
            return None
        if sel.isdigit() and 1 <= int(sel) <= len(devices):
            chosen = devices[int(sel) - 1]
            if not chosen.ready:
                print(f"  선택한 디바이스 상태가 '{chosen.state}' 라 사용할 수 없습니다.")
                continue
            print(f"  → '{chosen.serial}' ({chosen.model}) 선택됨")
            return chosen.serial
        print("  올바른 번호를 입력하세요.")


# ╔══════════════════════════════════════════════════════════════════╗
# ║ 단계 준비) tracefs 탐지 + root 확보                                ║
# ╚══════════════════════════════════════════════════════════════════╝
def prepare_ftrace(adb):
    """root 권한을 확보하고 tracefs 경로를 탐지한 Ftrace 객체를 반환한다."""
    # ftrace 제어에는 보통 root 권한이 필요하다. adb root 를 시도한다.
    if not adb.is_root():
        print("  root 권한 확보 시도(adb root)...")
        msg = adb.root()
        if msg:
            print(f"    {msg}")
        # root 재시작 후 디바이스가 잠시 끊겼다 붙으므로 wait 한다.
        adb._run(["wait-for-device"], timeout=60, check=False)
        if not adb.is_root():
            print("  [경고] root 권한을 얻지 못했습니다. 일부 명령이 실패할 수 있어")
            print("         'su -c' 우회를 사용합니다.")
            adb.use_su = True

    ft = Ftrace(adb)
    path = ft.detect_tracefs()
    print(f"  tracefs 경로: {path}")
    return ft


# ╔══════════════════════════════════════════════════════════════════╗
# ║ 단계 2) ftrace 옵션 설정                                           ║
# ╚══════════════════════════════════════════════════════════════════╝
def configure_options(ft):
    """
    설정 가능한 이벤트 그룹과 tracer 를 출력하고,
    '설정완료'를 고르기 전까지 토글하며 즉시 enable/disable 한다.
    """
    banner("2단계: ftrace 옵션 설정")
    groups = ft.list_event_groups()
    tracers = ft.list_available_tracers()

    if not groups:
        print("  [경고] 사용 가능한 이벤트 그룹을 찾지 못했습니다.")
    selected = set()                      # 현재 enable 된 그룹 집합
    current_tracer = "nop"

    while True:
        print("\n  ── 이벤트 그룹 (번호 입력 시 on/off 토글) ──")
        for i, g in enumerate(groups, 1):
            mark = "[O]" if g in selected else "[ ]"
            print(f"   {i:>3}) {mark} {g}")

        print("\n  ── 추가 명령 ──")
        print(f"   t) tracer 설정       (현재: {current_tracer})")
        print(f"   a) 전체 선택 해제")
        print(f"   s) 설정완료 → 다음 단계")
        print(f"   현재 선택: {sorted(selected) if selected else '(없음)'}")

        cmd = ask("\n  선택", "s").strip().lower()

        if cmd == "s":
            if not selected and current_tracer == "nop":
                cont = ask("  선택된 옵션이 없습니다. 그래도 진행할까요? (y/n)", "n")
                if cont.lower() != "y":
                    continue
            return selected, current_tracer

        if cmd == "a":
            # 전체 해제 → 디바이스에서도 모두 disable
            for g in list(selected):
                try:
                    ft.enable_event_group(g, False)
                except AdbError as e:
                    print(f"    [오류] {g} 해제 실패: {e}")
            selected.clear()
            print("  모든 이벤트 그룹을 해제했습니다.")
            continue

        if cmd == "t":
            _choose_tracer(ft, tracers)
            current_tracer = ft.get_tracer()
            continue

        # 숫자 입력 → 해당 그룹 토글
        if cmd.isdigit() and 1 <= int(cmd) <= len(groups):
            g = groups[int(cmd) - 1]
            try:
                if g in selected:
                    ft.enable_event_group(g, False)
                    selected.discard(g)
                    print(f"    [ ] {g} 비활성화됨")
                else:
                    ft.enable_event_group(g, True)
                    selected.add(g)
                    print(f"    [O] {g} 활성화됨")
            except AdbError as e:
                print(f"    [오류] {g} 설정 실패: {e}")
            continue

        print("  올바른 입력이 아닙니다.")


def _choose_tracer(ft, tracers):
    """tracer 목록을 보여주고 선택받아 적용한다."""
    if not tracers:
        print("  사용 가능한 tracer 정보가 없습니다.")
        return
    print("\n  ── tracer 선택 ──")
    for i, t in enumerate(tracers, 1):
        print(f"   {i}) {t}")
    sel = ask("  tracer 번호 (엔터=취소)", "")
    if sel.isdigit() and 1 <= int(sel) <= len(tracers):
        t = tracers[int(sel) - 1]
        try:
            ft.set_tracer(t)
            print(f"    tracer = {t} 적용됨")
        except AdbError as e:
            print(f"    [오류] tracer 설정 실패: {e}")


# ╔══════════════════════════════════════════════════════════════════╗
# ║ 단계 3) 준비 작업 + 파일명 입력                                    ║
# ╚══════════════════════════════════════════════════════════════════╝
def prepare_capture(ft):
    """버퍼 최대화 등 준비 작업을 수행하고 저장 파일명을 입력받는다."""
    banner("3단계: 캡처 준비")

    # trace clock 을 mono 로 설정(분석 시 타임스탬프가 일관됨)
    try:
        ft.set_trace_clock("mono")
        print("  trace_clock = mono 설정")
    except AdbError:
        print("  [경고] trace_clock 설정 실패(무시하고 진행)")

    # 버퍼 최대화
    before = ft.get_buffer_size_kb()
    after = ft.maximize_buffer()
    print(f"  ring buffer: {before} KB → {after} KB/CPU 로 최대화")

    # 저장 파일명 입력 (검증 루프)
    default_name = default_log_filename()
    while True:
        fname = ask("  저장할 로그 파일명", default_name)
        ok, result = _validate_filename(fname, default_name)
        if not ok:
            print(f"    [오류] {result}  다시 입력하세요.")
            continue
        fname = result
        # 이미 존재하면 덮어쓰기 확인
        if os.path.exists(fname):
            ow = ask(f"    '{fname}' 파일이 이미 있습니다. 덮어쓸까요? (y/n)", "n")
            if ow.lower() != "y":
                continue
        # 실제 쓰기 가능 여부 확인(디렉터리 권한/존재)
        writable, err = _check_writable(fname)
        if not writable:
            print(f"    [오류] {err}  다시 입력하세요.")
            continue
        break

    print(f"  저장 파일: {fname}")
    return fname


# 파일명에 쓸 수 없는 문자(Windows 호환 포함)
_INVALID_FNAME_CHARS = set('<>:"|?*')


def _validate_filename(fname, default_name):
    """
    파일명을 검증/정규화한다.
    반환: (성공여부, 정규화된 파일명 또는 오류메시지)
    """
    fname = (fname or "").strip().strip('"').strip("'")
    if not fname:
        fname = default_name
    # 경로 구분자는 허용하되, 파일명 자체의 금지문자만 검사한다.
    base = os.path.basename(fname)
    if not base:
        return False, "파일명이 비어 있습니다(디렉터리만 지정됨)."
    bad = _INVALID_FNAME_CHARS & set(base)
    if bad:
        return False, f"파일명에 사용할 수 없는 문자 포함: {''.join(sorted(bad))}"
    if base in (".", ".."):
        return False, "올바른 파일명이 아닙니다."
    if not fname.lower().endswith(".log"):
        fname += ".log"
    return True, fname


def _check_writable(fname):
    """저장 경로에 실제로 파일을 만들 수 있는지(권한/디렉터리) 확인한다."""
    folder = os.path.dirname(os.path.abspath(fname))
    if not os.path.isdir(folder):
        # 폴더가 없으면 만들 수 있는지 시도
        try:
            os.makedirs(folder, exist_ok=True)
        except OSError as e:
            return False, f"저장 폴더를 만들 수 없습니다: {folder} ({e})"
    if not os.access(folder, os.W_OK):
        return False, f"저장 폴더에 쓰기 권한이 없습니다: {folder}"
    return True, ""


# ╔══════════════════════════════════════════════════════════════════╗
# ║ 단계 4) 캡처 실행                                                  ║
# ╚══════════════════════════════════════════════════════════════════╝
def run_capture(ft, selected, tracer, fname):
    """ftrace 로그 캡처를 시작하고 사용자가 멈출 때까지 저장한다."""
    banner("4단계: ftrace 로그 캡처")

    # 파일 상단에 들어갈 메타데이터 헤더
    header = [
        "Android ftrace capture",
        f"tracefs   : {ft.tracefs}",
        f"tracer    : {tracer}",
        f"events    : {', '.join(sorted(selected)) if selected else '(none)'}",
        f"buffer_kb : {ft.get_buffer_size_kb()} KB/CPU",
    ]

    print("  캡처를 시작합니다. 중지하려면 Enter 키를 누르세요...")
    # start_capture 실패(파일 열기/프로세스 실행 등)는 AdbError 로 올라온다.
    session = ft.start_capture(fname, header_lines=header)

    # 캡처 스레드가 곧바로 죽었는지(예: 디바이스 분리, trace_pipe 접근 불가) 확인
    time.sleep(0.3)
    if not session.is_alive() and session.line_count == 0:
        session.stop()
        err = f" ({session.error})" if session.error else ""
        print(f"  [경고] 캡처가 즉시 종료되었습니다{err}.")
        print("         root 권한 또는 trace_pipe 접근 가능 여부를 확인하세요.")

    count = 0
    try:
        # Enter 입력 시까지 대기. 그 사이 백그라운드 스레드가 파일에 기록한다.
        input()
    except (KeyboardInterrupt, EOFError):
        print("\n  (중단 신호 감지) 캡처를 종료합니다...")
    finally:
        # 어떤 경우에도 반드시 캡처를 정지해 디바이스 tracing_on 을 끈다.
        count = session.stop()

    if session.error:
        print(f"  [경고] 캡처 중 오류 발생: {session.error}")
    print(f"  캡처 종료. {count} 줄 저장됨 → {fname}")

    # 정리: 이벤트/트레이서 원복
    cleanup = ask("  디바이스 ftrace 설정을 원복할까요? (y/n)", "y")
    if cleanup.lower() == "y":
        try:
            ft.disable_all_events()
            print("  ftrace 설정을 원복했습니다.")
        except AdbError as e:
            print(f"  [경고] 원복 중 오류(무시): {e}")


# ╔══════════════════════════════════════════════════════════════════╗
# ║ 메인 진입점                                                        ║
# ╚══════════════════════════════════════════════════════════════════╝
def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Android 커널 ftrace 로그 선택/수집/저장 도구")
    parser.add_argument("--adb", default="adb",
                        help="adb 실행 파일 경로 (기본: PATH 의 adb)")
    args = parser.parse_args(argv)

    print("╔" + "═" * 58 + "╗")
    print("║  Android ftrace 로그 수집 도구 (CLI)" + " " * 21 + "║")
    print("╚" + "═" * 58 + "╝")

    try:
        # 1) 디바이스 선택
        serial = select_device(args.adb)
        if not serial:
            print("종료합니다.")
            return 1

        adb = Adb(adb_path=args.adb, serial=serial)

        # 준비) root + tracefs
        ft = prepare_ftrace(adb)
        # 2) 옵션 설정
        selected, tracer = configure_options(ft)
        # 3) 준비 + 파일명
        fname = prepare_capture(ft)
        # 4) 캡처
        run_capture(ft, selected, tracer, fname)
    except AdbError as e:
        print(f"\n[오류] {e}")
        return 1
    except KeyboardInterrupt:
        print("\n사용자 중단으로 종료합니다.")
        return 130
    except EOFError:
        print("\n입력이 종료되어 프로그램을 마칩니다.")
        return 1
    except Exception as e:
        # 예기치 못한 모든 예외를 사용자에게 간결히 알린다(트레이스백 노출 방지).
        print(f"\n[예기치 못한 오류] {type(e).__name__}: {e}")
        return 1

    print("\n완료되었습니다.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
