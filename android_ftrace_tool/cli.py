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
    from .core import (Adb, Ftrace, AdbError, default_log_filename,
                       STORAGE_EVENT_GROUPS, FLOW_PRESET_ORDER, EVENT_BUNDLES,
                       IO_GRAPH_FUNCTIONS, CORRELATION_TRIGGERS)
except ImportError:                       # 직접 실행(python cli.py)인 경우
    from core import (Adb, Ftrace, AdbError, default_log_filename,
                      STORAGE_EVENT_GROUPS, FLOW_PRESET_ORDER, EVENT_BUNDLES,
                      IO_GRAPH_FUNCTIONS, CORRELATION_TRIGGERS)


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
    스토리지 데이터 플로우(앱→F2FS→block→SCSI→UFS/UIC) 관련 ftrace 이벤트 그룹과
    tracer 를 설정한다. '설정완료' 전까지 즉시 enable/disable 한다.

    명령:
      번호 : 그룹 전체 on/off 토글
      f    : read/write/erase 플로우 전체 켜기(프리셋, 앱→UFS/UIC)
      d    : 켜진 그룹의 개별 이벤트 세부 선택(불필요 이벤트 빼기)
      x    : 전체 그룹 보기(고급)  t: tracer  a: 전체 해제  s: 설정완료

    반환: (group_state, tracer)
      group_state: dict { group -> "ALL" | set(개별 이벤트 이름) }
                   "ALL"=그룹 전체, set=일부 이벤트만 켜진 상태.
    """
    banner("2단계: ftrace 옵션 설정 (스토리지 플로우: 앱→F2FS→block→SCSI→UFS/UIC)")
    available = set(ft.list_event_groups())          # 디바이스 지원 그룹 전체
    tracers = ft.list_available_tracers()

    # 카탈로그를 (지원 / 미지원) 으로 분리 (카탈로그 순서 = 플로우 순서)
    options = [(g, d) for g, d in STORAGE_EVENT_GROUPS.items() if g in available]
    missing = [(g, d) for g, d in STORAGE_EVENT_GROUPS.items() if g not in available]

    if not options:
        print("  [경고] 이 디바이스에서 스토리지 관련 이벤트 그룹을 찾지 못했습니다.")
        print("         'x' 로 전체 그룹을 확인할 수 있습니다.")

    group_state = {}                      # group -> "ALL" or set(events)
    current_tracer = "nop"
    show_all = False                      # True 면 전체 그룹 보기(고급)

    def _mark(g):
        st = group_state.get(g)
        if st == "ALL":
            return "[O]"                  # 그룹 전체
        if isinstance(st, set) and st:
            return "[~]"                  # 일부 이벤트만
        return "[ ]"                      # 꺼짐

    while True:
        # 화면에 보여줄 목록(display)과 번호 매핑을 구성한다.
        if show_all:
            display = sorted(available)
            print("\n  ── 전체 이벤트 그룹 (번호=on/off 토글) ──")
            for i, g in enumerate(display, 1):
                print(f"   {i:>3}) {_mark(g)} {g}")
        else:
            display = [g for g, _ in options]
            print("\n  ── 스토리지 플로우 이벤트 그룹 (위→아래 = 앱→UFS) ──")
            for i, (g, d) in enumerate(options, 1):
                print(f"   {i}) {_mark(g)} {g:<11} - {d}")
            for g, d in missing:
                print(f"   --) [X] {g:<11} - {d}  (이 디바이스 미지원)")
        print("     ([O]=그룹전체  [~]=일부 이벤트  [ ]=꺼짐)")

        sync_on = "syscalls" in group_state      # sync 묶음 활성 여부(근사)
        graph_on = (current_tracer == "function_graph")
        corr_on = bool(ft._installed_triggers)   # 흐름 추적 트리거 설치 여부
        print("\n  ── 추가 명령 ──")
        print(f"   f) read/write/erase 플로우 전체 켜기(프리셋)")
        print(f"   y) sync 시스템콜 추적(fsync/sync/...)  [현재: {'ON' if sync_on else 'OFF'}]")
        print(f"   d) 켜진 그룹의 개별 이벤트 세부 선택(빼기)")
        print(f"   g) function_graph I/O 인과 보기(호출 중첩)  [현재: {'ON' if graph_on else 'OFF'}]")
        print(f"   h) 흐름 추적 트리거: block I/O 지연(io_latency 합성)  [현재: {'ON' if corr_on else 'OFF'}]")
        print(f"   t) tracer 설정       (현재: {current_tracer})")
        print(f"   a) 전체 선택 해제")
        print(f"   x) {'스토리지만 보기' if show_all else '전체 그룹 보기(고급)'}")
        print(f"   s) 설정완료 → 다음 단계")
        print(f"   현재 선택: {_summarize_state(group_state)}")

        cmd = ask("\n  선택", "s").strip().lower()

        if cmd == "s":
            if not group_state and current_tracer == "nop":
                cont = ask("  선택된 옵션이 없습니다. 그래도 진행할까요? (y/n)", "n")
                if cont.lower() != "y":
                    continue
            return group_state, current_tracer

        if cmd == "a":
            # 전체 해제 → 디바이스에서도 모두 disable
            for g in list(group_state):
                try:
                    ft.enable_event_group(g, False)
                except AdbError as e:
                    print(f"    [오류] {g} 해제 실패: {e}")
            group_state.clear()
            # 흐름 추적 트리거/합성 이벤트도 함께 정리
            if ft._installed_triggers:
                ft.remove_correlation_presets()
            print("  모든 이벤트 그룹/흐름 추적 트리거를 해제했습니다.")
            continue

        if cmd == "f":
            _apply_flow_preset(ft, group_state, available)
            continue

        if cmd == "y":
            _toggle_event_bundle(ft, group_state, available, "sync_syscalls")
            continue

        if cmd == "d":
            _detail_events(ft, group_state)
            continue

        if cmd == "g":
            current_tracer = _toggle_graph_io(ft, current_tracer)
            continue

        if cmd == "h":
            _toggle_correlation(ft, "block_io_latency")
            continue

        if cmd == "x":
            show_all = not show_all
            continue

        if cmd == "t":
            _choose_tracer(ft, tracers)
            current_tracer = ft.get_tracer()
            continue

        # 숫자 입력 → 현재 화면(display) 기준 해당 그룹 토글(전체 on/off)
        if cmd.isdigit() and 1 <= int(cmd) <= len(display):
            g = display[int(cmd) - 1]
            try:
                if g in group_state:
                    ft.enable_event_group(g, False)
                    del group_state[g]
                    print(f"    [ ] {g} 비활성화됨")
                else:
                    ft.enable_event_group(g, True)
                    group_state[g] = "ALL"
                    print(f"    [O] {g} 활성화됨(전체)")
            except AdbError as e:
                print(f"    [오류] {g} 설정 실패: {e}")
            continue

        print("  올바른 입력이 아닙니다.")


def _summarize_state(group_state):
    """group_state 를 사람이 읽기 좋은 한 줄 요약 문자열로 만든다."""
    if not group_state:
        return "(없음)"
    parts = []
    for g in sorted(group_state):
        st = group_state[g]
        parts.append(g if st == "ALL" else f"{g}({len(st)}개 이벤트)")
    return ", ".join(parts)


def _apply_flow_preset(ft, group_state, available):
    """앱→F2FS→block→SCSI→UFS 플로우 그룹을 한 번에 켠다(디바이스 지원분만)."""
    applied, skipped = [], []
    for g in FLOW_PRESET_ORDER:
        if g not in available:
            skipped.append(g)
            continue
        try:
            ft.enable_event_group(g, True)
            group_state[g] = "ALL"
            applied.append(g)
        except AdbError as e:
            print(f"    [오류] {g} 활성화 실패: {e}")
    if applied:
        print(f"  플로우 프리셋 활성화: {' → '.join(applied)}")
    if skipped:
        print(f"  (미지원으로 제외: {', '.join(skipped)})")


def _toggle_event_bundle(ft, group_state, available, bundle_name):
    """
    개별 이벤트 묶음(예: sync 시스템콜)을 한 번에 켜고/끈다.
    그룹 전체가 아니라 묶음에 정의된 (group, event) 만 핀포인트로 제어하며,
    group_state 의 "부분 이벤트(set)" 모델에 반영한다.
    """
    bundle = EVENT_BUNDLES.get(bundle_name)
    if not bundle:
        print(f"  [오류] 알 수 없는 묶음: {bundle_name}")
        return

    groups_used = sorted({g for g, _ in bundle["events"]})
    # 묶음이 쓰는 그룹이 디바이스에 있는지 확인
    for g in groups_used:
        if g not in available:
            print(f"  [경고] '{g}' 그룹이 없어 '{bundle['desc']}' 를 켤 수 없습니다.")
            return

    # 디바이스에 실제 존재하는 이벤트만 대상으로 한다(커널마다 일부 누락 가능).
    existing = {}
    for g in groups_used:
        try:
            existing[g] = set(ft.list_events_in_group(g))
        except AdbError as e:
            print(f"  [오류] '{g}' 이벤트 목록 조회 실패: {e}")
            return
    target = [(g, e) for g, e in bundle["events"] if e in existing.get(g, set())]
    if not target:
        print("  [경고] 이 디바이스에 해당 이벤트가 없습니다(미지원).")
        return

    # 현재 켜져 있는지 판단(대상이 모두 켜져 있으면 ON 으로 간주)
    def _is_on(g, e):
        st = group_state.get(g)
        return st == "ALL" or (isinstance(st, set) and e in st)
    enable = not all(_is_on(g, e) for g, e in target)

    changed = 0
    for g, e in target:
        st = group_state.get(g)
        if enable and st == "ALL":
            continue                      # 그룹 전체가 이미 켜져 있으면 건드리지 않음
        if not enable and st == "ALL":
            print(f"  [안내] '{g}' 그룹이 전체 ON 상태라 묶음만 끌 수 없습니다."
                  f" 그룹을 끄려면 메뉴에서 '{g}' 를 토글하세요.")
            return
        try:
            ft.enable_event(g, e, enable)
        except AdbError as ex:
            print(f"    [오류] {g}/{e} 설정 실패: {ex}")
            continue
        s = st if isinstance(st, set) else set()
        if enable:
            s.add(e)
            group_state[g] = s
        else:
            s.discard(e)
            if s:
                group_state[g] = s
            else:
                group_state.pop(g, None)
        changed += 1

    print(f"  '{bundle['desc']}' {'켜짐' if enable else '꺼짐'} ({changed}개 이벤트 적용)")


def _toggle_graph_io(ft, current_tracer):
    """(A) function_graph 로 I/O 인과(호출 중첩)를 보는 모드 on/off. 새 tracer 반환."""
    if current_tracer == "function_graph":
        try:
            ft.set_tracer("nop")
            ft.clear_graph_functions()
        except AdbError as e:
            print(f"  [오류] 해제 실패: {e}")
            return current_tracer
        print("  function_graph I/O 보기 해제(tracer=nop)")
        return "nop"

    # function_graph 지원 확인
    if "function_graph" not in ft.list_available_tracers():
        print("  [경고] 이 커널은 function_graph tracer 를 지원하지 않습니다.")
        return current_tracer
    try:
        ft.set_tracer("function_graph")
        applied = ft.set_graph_functions(IO_GRAPH_FUNCTIONS)
    except AdbError as e:
        print(f"  [오류] function_graph 설정 실패: {e}")
        return current_tracer
    if applied:
        print(f"  function_graph I/O 보기 ON — 범위 함수 {len(applied)}개: {', '.join(applied)}")
    else:
        print("  function_graph ON(범위 제한 함수가 없어 전체 호출이 잡혀 로그가 많을 수 있음)")
    print("  ※ 이 모드는 동기 제출 경로의 인과(중첩)를 보여줍니다. 로그 형식이")
    print("    이벤트 방식과 달라 사후 분석 스크립트(analyzer) 대상이 아닙니다.")
    return "function_graph"


def _toggle_correlation(ft, preset_name):
    """(B) hist/synthetic 흐름 추적 트리거 프리셋 on/off (block I/O 지연 → io_latency)."""
    preset = CORRELATION_TRIGGERS[preset_name]
    if ft._installed_triggers:
        ft.remove_correlation_presets()
        print(f"  흐름 추적 트리거 해제: {preset['desc']}")
        return
    try:
        res = ft.apply_correlation_preset(preset_name)
    except AdbError as e:
        print(f"  [경고] 흐름 추적 트리거 설치 실패(커널 미지원 가능): {e}")
        print("        CONFIG_HIST_TRIGGERS / CONFIG_SYNTH_EVENTS 필요. 건너뜁니다.")
        return
    print(f"  흐름 추적 트리거 설치: {preset['desc']}")
    if res:
        print(f"  → 결과는 캡처 로그에 '{res[0]}:{res[1]}' 이벤트로 나타납니다(dev,sector,lat).")


def _detail_events(ft, group_state):
    """켜진 그룹 하나를 골라 개별 이벤트를 세부 토글한다(불필요 이벤트 빼기)."""
    enabled_groups = sorted(group_state)
    if not enabled_groups:
        print("  먼저 그룹을 하나 이상 켜야 세부 선택이 가능합니다.")
        return
    print("\n  세부 선택할 그룹:")
    for i, g in enumerate(enabled_groups, 1):
        print(f"   {i}) {g}")
    sel = ask("  그룹 번호 (엔터=취소)", "")
    if not (sel.isdigit() and 1 <= int(sel) <= len(enabled_groups)):
        return
    group = enabled_groups[int(sel) - 1]

    try:
        events = ft.list_events_in_group(group)
    except AdbError as e:
        print(f"  [오류] 이벤트 목록 조회 실패: {e}")
        return
    if not events:
        print("  이 그룹에 개별 이벤트가 없습니다.")
        return

    # 현재 켜진 이벤트 집합 계산
    st = group_state[group]
    enabled = set(events) if st == "ALL" else set(st)

    # syscalls 처럼 이벤트가 매우 많은 그룹은 전부 나열하면 화면이 폭발한다.
    # 이 경우 현재 켜진 이벤트만 보여줘서(빼기 위주) 다룰 수 있게 한다.
    if len(events) > 50:
        print(f"  ('{group}' 은 이벤트가 {len(events)}개로 많아, 현재 켜진 것만 표시합니다)")
        events = sorted(enabled)
        if not events:
            print("  켜진 개별 이벤트가 없습니다.")
            return

    while True:
        print(f"\n  ── '{group}' 개별 이벤트 (번호=포함/제외 토글) ──")
        for i, ev in enumerate(events, 1):
            mark = "[O]" if ev in enabled else "[ ]"
            print(f"   {i:>3}) {mark} {ev}")
        print("   c) 완료(상위 메뉴로)")
        c = ask("  선택", "c").strip().lower()
        if c == "c":
            break
        if c.isdigit() and 1 <= int(c) <= len(events):
            ev = events[int(c) - 1]
            try:
                if ev in enabled:
                    ft.enable_event(group, ev, False)
                    enabled.discard(ev)
                    print(f"    [ ] {ev} 제외")
                else:
                    ft.enable_event(group, ev, True)
                    enabled.add(ev)
                    print(f"    [O] {ev} 포함")
            except AdbError as e:
                print(f"    [오류] {ev} 설정 실패: {e}")
            continue
        print("  올바른 입력이 아닙니다.")

    # 상태 반영: 전체면 "ALL", 일부면 set, 모두 빠지면 그룹 제거
    if not enabled:
        try:
            ft.enable_event_group(group, False)
        except AdbError:
            pass
        del group_state[group]
        print(f"  '{group}' 의 모든 이벤트가 제외되어 그룹을 껐습니다.")
    elif enabled == set(events):
        group_state[group] = "ALL"
        print(f"  '{group}' 전체 이벤트 포함 상태입니다.")
    else:
        group_state[group] = enabled
        print(f"  '{group}' 에서 {len(enabled)}/{len(events)}개 이벤트만 켜졌습니다.")


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
def run_capture(ft, group_state, tracer, fname):
    """ftrace 로그 캡처를 시작하고 사용자가 멈출 때까지 저장한다."""
    banner("4단계: ftrace 로그 캡처")

    # 파일 상단에 들어갈 메타데이터 헤더
    header = [
        "Android ftrace capture",
        f"tracefs   : {ft.tracefs}",
        f"tracer    : {tracer}",
        f"events    : {_summarize_state(group_state)}",
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
        group_state, tracer = configure_options(ft)
        # 3) 준비 + 파일명
        fname = prepare_capture(ft)
        # 4) 캡처
        run_capture(ft, group_state, tracer, fname)
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
