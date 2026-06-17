"""
Android ftrace 로그 도구 - 핵심 로직 계층 (Core Layer)
======================================================
이 모듈은 **UI 입출력(print/input)을 전혀 포함하지 않는** 순수 로직 계층이다.
adb 통신과 Android 커널 ftrace 제어를 담당하며, 결과를 값으로 반환하거나
콜백을 통해 전달한다.

이렇게 UI 와 분리해 둔 이유(요구사항 #4):
  - 현재는 CLI(cli.py)가 이 core 를 호출한다.
  - 향후 Windows GUI 도구로 확장할 때, GUI 코드가 동일한 core 를 그대로
    재사용하면 된다. (예: PyQt/Tkinter 의 버튼 이벤트 → core 함수 호출)
  - 따라서 이 파일에는 어떤 화면 출력/사용자 입력 코드도 두지 않는다.

ftrace 개요:
  Android(리눅스) 커널의 trace 기능은 tracefs 라는 가상 파일시스템으로 제어한다.
  경로는 보통 다음 둘 중 하나이다.
      /sys/kernel/tracing
      /sys/kernel/debug/tracing
  주요 파일:
      available_events     : 사용 가능한 모든 trace 이벤트 목록
      available_tracers    : 사용 가능한 tracer(function, function_graph ...)
      current_tracer       : 현재 tracer 설정
      events/<group>/enable: 이벤트 그룹 전체 on/off
      set_event            : 활성화된 이벤트 목록
      buffer_size_kb       : CPU 당 ring buffer 크기(KB)
      trace                : 현재까지 누적된 trace 스냅샷
      trace_pipe          : 실시간 스트리밍(읽으면 소비됨)
      tracing_on           : 1=수집 시작, 0=수집 정지
"""

# ── 표준 라이브러리 ────────────────────────────────────────────────
import os                           # 로컬 파일 경로 처리
import subprocess                   # adb 프로세스 실행
import threading                    # 실시간 캡처용 백그라운드 스레드
from datetime import datetime       # 타임스탬프 생성


# ╔══════════════════════════════════════════════════════════════════╗
# ║ 예외 정의                                                          ║
# ╚══════════════════════════════════════════════════════════════════╝
class AdbError(Exception):
    """adb 명령 실행 실패 시 발생하는 예외."""
    pass


# ╔══════════════════════════════════════════════════════════════════╗
# ║ 자료구조                                                           ║
# ╚══════════════════════════════════════════════════════════════════╝
class Device:
    """adb 로 연결된 단말 1대를 나타내는 단순 자료구조."""

    def __init__(self, serial, state, model="", product="", transport_id=""):
        self.serial = serial          # 디바이스 시리얼(또는 emulator-5554)
        self.state = state            # device / unauthorized / offline ...
        self.model = model            # 모델명 (예: Pixel_5)
        self.product = product        # 제품 코드명
        self.transport_id = transport_id

    @property
    def ready(self):
        """실제 명령을 보낼 수 있는 정상 상태인지 여부."""
        return self.state == "device"

    def __repr__(self):
        label = self.model or self.product or ""
        return f"Device({self.serial}, {self.state}, {label})"


# ╔══════════════════════════════════════════════════════════════════╗
# ║ adb 래퍼                                                           ║
# ╚══════════════════════════════════════════════════════════════════╝
class Adb:
    """
    adb 명령을 감싸는 얇은 래퍼.

    Windows / Linux / macOS 모두에서 동작하도록 shell=True 를 쓰지 않고
    인자 리스트로 subprocess 를 실행한다. adb 실행 파일은 PATH 에 있어야 한다.
    """

    def __init__(self, adb_path="adb", serial=None, use_su=False):
        self.adb_path = adb_path      # adb 실행 파일 경로(기본: PATH 의 adb)
        self.serial = serial          # 대상 디바이스 시리얼(None 이면 -s 미지정)
        self.use_su = use_su          # adb root 가 안 될 때 'su -c' 로 우회할지

    # ── 내부 실행 헬퍼 ────────────────────────────────────────────
    def _base(self):
        """`adb [-s serial]` 형태의 기본 명령 리스트를 만든다."""
        cmd = [self.adb_path]
        if self.serial:
            cmd += ["-s", self.serial]
        return cmd

    def _run(self, args, timeout=30, check=True):
        """
        adb 하위 명령을 실행하고 CompletedProcess 를 반환한다.

        args   : adb 뒤에 붙는 인자 리스트 (예: ["devices", "-l"])
        check  : True 이면 종료코드 != 0 일 때 AdbError 발생
        """
        full = self._base() + list(args)
        try:
            proc = subprocess.run(
                full,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=timeout,
                text=True,                 # 문자열로 디코딩
                errors="replace",
            )
        except FileNotFoundError:
            raise AdbError(
                f"adb 실행 파일을 찾을 수 없습니다: '{self.adb_path}'. "
                "Android Platform Tools 설치 후 PATH 를 확인하세요."
            )
        except subprocess.TimeoutExpired:
            raise AdbError(f"adb 명령 시간 초과: {' '.join(full)}")
        except PermissionError:
            raise AdbError(
                f"adb 실행 권한이 없습니다: '{self.adb_path}'. "
                "실행 권한(chmod +x)을 확인하세요."
            )
        except OSError as e:
            # 그 외 시스템 수준 오류(메모리 부족, 파일 핸들 고갈 등)
            raise AdbError(f"adb 실행 중 시스템 오류: {e}")

        if check and proc.returncode != 0:
            raise AdbError(
                f"adb 명령 실패(code {proc.returncode}): {' '.join(full)}\n"
                f"{proc.stderr.strip()}"
            )
        return proc

    # ── 디바이스 목록 ─────────────────────────────────────────────
    def list_devices(self):
        """
        연결된 디바이스 목록을 Device 리스트로 반환한다.
        `adb devices -l` 출력을 파싱한다.
        """
        proc = self._run(["devices", "-l"], check=True)
        devices = []
        for line in proc.stdout.splitlines():
            line = line.strip()
            # 헤더/빈 줄/안내 문구는 건너뛴다.
            if not line or line.startswith("List of devices"):
                continue
            if line.startswith("*"):       # adb 데몬 시작 메시지 등
                continue
            parts = line.split()
            if len(parts) < 2:
                continue
            serial, state = parts[0], parts[1]
            # 나머지 토큰은 key:value 형태(model:Pixel_5 등)
            kv = {}
            for tok in parts[2:]:
                if ":" in tok:
                    k, v = tok.split(":", 1)
                    kv[k] = v
            devices.append(Device(
                serial=serial,
                state=state,
                model=kv.get("model", ""),
                product=kv.get("product", ""),
                transport_id=kv.get("transport_id", ""),
            ))
        return devices

    # ── shell 실행 ────────────────────────────────────────────────
    def shell(self, command, timeout=30, check=True):
        """
        `adb shell <command>` 을 실행하고 stdout 문자열을 반환한다.
        use_su=True 이면 root 권한이 필요한 명령을 'su -c' 로 감싼다.
        """
        if self.use_su:
            # 명령에 작은따옴표가 있으면 su -c '...' 래핑이 깨지므로 이스케이프한다.
            safe = command.replace("'", "'\\''")
            command = f"su -c '{safe}'"
        proc = self._run(["shell", command], timeout=timeout, check=check)
        return proc.stdout

    # ── root 권한 ─────────────────────────────────────────────────
    def root(self):
        """
        `adb root` 로 adbd 를 root 로 재시작한다.
        성공/실패 메시지 문자열을 반환한다(userdebug/eng 빌드에서만 동작).
        """
        proc = self._run(["root"], timeout=30, check=False)
        return (proc.stdout + proc.stderr).strip()

    def is_root(self):
        """현재 adb shell 이 root(uid 0)로 동작 중인지 확인."""
        out = self.shell("id -u", check=False).strip()
        return out == "0"

    # ── 파일 가져오기 ─────────────────────────────────────────────
    def pull(self, remote, local, timeout=300):
        """디바이스의 remote 파일을 로컬 local 경로로 내려받는다."""
        self._run(["pull", remote, local], timeout=timeout, check=True)
        return local

    # ── 파일 보내기 ───────────────────────────────────────────────
    def push(self, local, remote, timeout=300):
        """로컬 local 파일을 디바이스 remote 경로로 올려보낸다."""
        self._run(["push", local, remote], timeout=timeout, check=True)
        return remote


# ╔══════════════════════════════════════════════════════════════════╗
# ║ ftrace 제어                                                        ║
# ╚══════════════════════════════════════════════════════════════════╝
# tracefs 가 위치할 수 있는 후보 경로(우선순위 순).
TRACEFS_CANDIDATES = [
    "/sys/kernel/tracing",
    "/sys/kernel/debug/tracing",
]

# enable/header 처럼 그룹이 아닌 항목은 이벤트 목록에서 제외한다.
_NON_GROUP_ENTRIES = {"enable", "header_page", "header_event"}


# ── 관심 분야(스토리지) 이벤트 그룹 카탈로그 ────────────────────────
# 앱 → 파일시스템 → (라이트백) → 블록 → SCSI → UFS(UIC) 데이터 플로우 순서로
# 나열한 스토리지 관련 ftrace 이벤트 그룹과 한 줄 설명.
# 설정 단계에서는 이 카탈로그 중 "디바이스가 실제 지원하는" 그룹만 노출한다.
#
# 참고: f2fs 의 GC(가비지 컬렉션)·checkpoint·discard 는 별도 그룹이 아니라
#       'f2fs' 그룹 안의 개별 이벤트(f2fs_gc_begin/end, f2fs_get_victim ...)이다.
#       즉 'f2fs' 를 켜면 GC 동작도 함께 추적된다.
# (UI 가 아닌 도메인 지식이므로 core 에 두어 GUI 에서도 재사용 가능)
STORAGE_EVENT_GROUPS = {
    "android_fs": "앱→파일 I/O 매핑(read/write 시작·종료, 경로·inode·오프셋) — 플로우 최상단",
    "f2fs":       "F2FS 동작 전반: read/write/fsync, GC(가비지컬렉션), checkpoint, discard, truncate(삭제)",
    "ext4":       "EXT4 파일시스템 동작(/data 가 ext4 인 단말): write/할당(mballoc)/truncate 등",
    "erofs":      "EROFS 읽기전용 파일시스템(system/vendor 파티션) 읽기 동작",
    "jbd2":       "EXT4 저널링(jbd2) 커밋/체크포인트 — ext4 메타데이터 일관성",
    "writeback":  "더티 페이지 라이트백(페이지캐시→스토리지 flush 시점, balance_dirty_pages)",
    "block":      "블록 I/O 계층 요청 추적(bio 큐잉, 요청 발행/완료, 병합, discard)",
    "scsi":       "SCSI 명령 디스패치/완료 추적 — UFS 상위 계층",
    "ufs":        "UFS 드라이버: 디바이스 명령(ufshcd_command) + UIC 계층(ufshcd_uic_command) 추적",
}

# 앱의 파일 동작(read/write/erase)이 UFS/UIC 까지 내려가는 전형적인 데이터
# 플로우를 한 번에 켜기 위한 프리셋(플로우 순서).
# writeback 을 포함해 "페이지캐시 → 스토리지 flush" 시점까지 끊김 없이 추적한다.
# (ext4/erofs/jbd2 는 단말 파일시스템에 따라 선택적이므로 프리셋에서는 제외 —
#  필요하면 메뉴에서 개별 선택)
FLOW_PRESET_ORDER = ["android_fs", "f2fs", "writeback", "block", "scsi", "ufs"]


# ── 개별 이벤트 묶음 프리셋 ─────────────────────────────────────────
# 관심 있는 이벤트만 핀포인트로 켜기 위한 묶음. 각 묶음은 (group, event) 쌍의 리스트.
# 묶음에 적힌 이벤트 중 디바이스에 실제 존재하는 것만 켜진다(없는 건 자동 제외).
# (UI 가 아닌 도메인 지식이므로 core 에 두어 GUI 에서도 재사용 가능)
#
# fsync/sync 추적은 계층마다 이벤트가 다르다:
#   - 시스템콜 계층: syscalls/sys_enter_fsync 등 — CONFIG_FTRACE_SYSCALLS 필요(미지원多)
#   - 파일시스템 계층: f2fs_sync_file_enter/exit, ext4_sync_file_enter/exit
# syscalls 그룹이 없는 커널(GKI 등)이 많으므로, **파일시스템 레이어 fsync** 를
# 기본으로 삼는다. 이 이벤트들은 실제 fsync 가 어느 파일(ino)에서 일어났는지까지
# 보여줘 흐름 추적에도 더 유용하다.
EVENT_BUNDLES = {
    "sync_events": {
        "desc": "fsync/sync 추적 — f2fs/ext4 파일시스템 레이어(f2fs_sync_file 등)",
        "events": [
            # F2FS: 파일별 fsync 진입/종료 + 체크포인트(저널 flush)
            ("f2fs", "f2fs_sync_file_enter"),
            ("f2fs", "f2fs_sync_file_exit"),
            ("f2fs", "f2fs_write_checkpoint"),
            # EXT4(/data 가 ext4 인 단말 대비): 파일별 fsync 진입/종료
            ("ext4", "ext4_sync_file_enter"),
            ("ext4", "ext4_sync_file_exit"),
        ],
    },
}


# ── (A) function_graph 로 I/O 인과(호출 중첩)를 보기 위한 진입 함수 ──
# function_graph tracer 는 함수 호출 트리를 들여쓰기로 보여준다. 아래 진입
# 함수들로 범위를 한정하면 "vfs_read → f2fs_…read → submit_bio → scsi → ufshcd"
# 같은 동기 제출 경로의 인과(중첩)를 한 덩어리로 볼 수 있다.
# (디바이스에 실제 존재하는 함수만 set_graph_function 에 적용된다)
IO_GRAPH_FUNCTIONS = [
    "vfs_read", "vfs_write", "vfs_fsync", "vfs_fsync_range",
    "f2fs_file_read_iter", "f2fs_file_write_iter",
    "ext4_file_read_iter", "ext4_file_write_iter",
    "f2fs_write_data_pages", "do_writepages",
    "blk_mq_submit_bio", "submit_bio",
    "scsi_queue_rq", "ufshcd_queuecommand",
]

# ── (A-대체) function_graph 미지원 커널용: 이벤트 스택트레이스 ──────────
# 양산 커널은 CONFIG_FUNCTION_GRAPH_TRACER 가 꺼져 있어 function_graph 가 없는
# 경우가 많다. 그럴 때는 '스택트레이스 트리거'로 대체한다: 아래 이벤트가 찍힐 때마다
# 그 이벤트를 호출한 상위 함수 체인(예: vfs_read→f2fs→submit_bio→…)을 커널 스택으로
# 함께 남긴다. function_graph 의 들여쓰기 트리는 아니지만, 각 I/O 가 '누구로부터
# 내려왔는지'를 복원할 수 있다. 함수 트레이서가 없어도(이벤트만 있으면) 동작한다.
# 하위 계층 이벤트에 붙여야 호출 체인이 의미 있다(상위→하위로 내려온 경로가 보임).
STACK_TRACE_EVENTS = [
    ("block", "block_rq_issue"),
    ("scsi", "scsi_dispatch_cmd_start"),
    ("ufs", "ufshcd_command"),
    ("f2fs", "f2fs_sync_file_enter"),
]

# ── (B) hist/synthetic 흐름 추적 트리거 프리셋 ───────────────────────────
# 두 이벤트를 공유 키(dev,sector)로 커널에서 조인해 지연(latency)을 산출하고,
# 그 결과를 합성(synthetic) 이벤트로 만들어 같은 로그에 남긴다.
# 커널에 CONFIG_HIST_TRIGGERS / CONFIG_SYNTH_EVENTS 가 필요하다.
#
# 문제: onmatch 액션·합성 필드 문법이 커널 버전마다 다르다. 그래서 한 프리셋에
# 여러 "변형(variant)"을 두고, 앞에서부터 설치를 시도해 '실제로 먹히는' 변형을
# 자동 선택한다(설치 후 결과 이벤트 존재까지 확인). 변형 차이:
#   V1: 액션을 합성이벤트명으로 호출  .io_latency($lat,dev,sector)   (4.17+ 표준)
#   V2: trace() 액션 형태            .trace(io_latency,$lat,dev,sector) (일부 버전)
#   V3: 최소 합성(lat만)            필드 타입 불일치를 피해 호환성 최대화
CORRELATION_TRIGGERS = {
    "block_io_latency": {
        "desc": "block_rq_issue↔complete 를 (dev,sector)로 조인해 io_latency 합성 이벤트 생성",
        "variants": [
            {   # V1 — 표준: onmatch(...).<합성이벤트명>(인자...)
                "synthetic": "io_latency u64 lat; u64 dev; u64 sector",
                "triggers": [
                    ("block", "block_rq_issue",
                     "hist:keys=dev,sector:ts0=common_timestamp.usecs"),
                    ("block", "block_rq_complete",
                     "hist:keys=dev,sector:lat=common_timestamp.usecs-$ts0:"
                     "onmatch(block.block_rq_issue).io_latency($lat,dev,sector)"),
                ],
                "result_event": ("synthetic", "io_latency"),
            },
            {   # V2 — trace() 액션 형태
                "synthetic": "io_latency u64 lat; u64 dev; u64 sector",
                "triggers": [
                    ("block", "block_rq_issue",
                     "hist:keys=dev,sector:ts0=common_timestamp.usecs"),
                    ("block", "block_rq_complete",
                     "hist:keys=dev,sector:lat=common_timestamp.usecs-$ts0:"
                     "onmatch(block.block_rq_issue).trace(io_latency,$lat,dev,sector)"),
                ],
                "result_event": ("synthetic", "io_latency"),
            },
            {   # V3 — 최소 합성(lat만): 필드 타입 불일치 회피로 호환성 최대
                "synthetic": "io_latency u64 lat",
                "triggers": [
                    ("block", "block_rq_issue",
                     "hist:keys=dev,sector:ts0=common_timestamp.usecs"),
                    ("block", "block_rq_complete",
                     "hist:keys=dev,sector:lat=common_timestamp.usecs-$ts0:"
                     "onmatch(block.block_rq_issue).io_latency($lat)"),
                ],
                "result_event": ("synthetic", "io_latency"),
            },
        ],
    },
}

# 이벤트 그룹 디렉터리 안에서 개별 이벤트가 아닌 제어 파일들.
_NON_EVENT_ENTRIES = {"enable", "filter"}


class Ftrace:
    """
    Android 커널 ftrace 를 제어하는 핵심 클래스.

    사용 흐름:
        ft = Ftrace(adb)
        ft.detect_tracefs()              # tracefs 경로 탐지
        groups = ft.list_event_groups()  # 설정 가능한 옵션 목록
        ft.enable_event_group("sched")   # 옵션 enable
        ft.maximize_buffer()             # 버퍼 최대화
        session = ft.start_capture("out.log")   # 캡처 시작
        ...
        session.stop()                   # 캡처 종료
    """

    def __init__(self, adb, tracefs=None):
        self.adb = adb
        self.tracefs = tracefs        # detect_tracefs() 로 채워짐
        self._installed_triggers = []  # (group, event, trigger) — 정리용 추적
        self._installed_synth = []     # 생성한 synthetic 이벤트 이름 — 정리용
        self._installed_stack_triggers = []  # stacktrace 붙인 (group, event) — 정리용
        self._active_correlation_variant = None  # 마지막으로 먹힌 흐름추적 변형 번호

    # ── tracefs 경로 탐지 ─────────────────────────────────────────
    def detect_tracefs(self):
        """
        디바이스에서 tracefs 마운트 경로를 찾아 self.tracefs 에 저장하고 반환한다.
        찾지 못하면 AdbError 를 던진다.
        """
        for path in TRACEFS_CANDIDATES:
            # tracing_on 파일이 있으면 유효한 tracefs 로 간주한다.
            out = self.adb.shell(f"test -e {path}/tracing_on && echo OK",
                                 check=False).strip()
            if out == "OK":
                self.tracefs = path
                return path
        raise AdbError(
            "tracefs 경로를 찾을 수 없습니다. root 권한이 필요하거나 "
            "커널이 ftrace 를 지원하지 않을 수 있습니다."
        )

    def _path(self, *parts):
        """tracefs 하위 경로를 안전하게 조합한다."""
        if not self.tracefs:
            raise AdbError("tracefs 가 아직 탐지되지 않았습니다. detect_tracefs() 호출 필요.")
        return "/".join([self.tracefs] + list(parts))

    # ── 저수준 read/write ─────────────────────────────────────────
    def _read(self, rel):
        """tracefs 하위 파일을 cat 으로 읽어 문자열 반환."""
        return self.adb.shell(f"cat {self._path(rel)}", check=False)

    def _write(self, rel, value):
        """
        tracefs 하위 파일에 값을 기록한다(echo VALUE > path).
        root 권한이 없으면 실패할 수 있다.
        """
        self.adb.shell(f"echo {value} > {self._path(rel)}", check=True)

    # ── 조회 ──────────────────────────────────────────────────────
    def list_event_groups(self):
        """
        설정 가능한 ftrace 이벤트 그룹 목록을 정렬해 반환한다.
        (events/ 디렉터리의 하위 디렉터리 이름들)
        """
        out = self.adb.shell(f"ls {self._path('events')}", check=False)
        groups = []
        for name in out.split():
            name = name.strip()
            if name and name not in _NON_GROUP_ENTRIES:
                groups.append(name)
        return sorted(groups)

    def list_available_tracers(self):
        """available_tracers 내용을 리스트로 반환(function, function_graph, nop ...)."""
        out = self._read("available_tracers").strip()
        return out.split() if out else []

    def list_enabled(self):
        """현재 활성화된 이벤트 목록(set_event 내용)을 반환."""
        out = self._read("set_event").strip()
        return [l.strip() for l in out.splitlines() if l.strip()]

    # ── 이벤트 그룹 enable/disable ────────────────────────────────
    def enable_event_group(self, group, enable=True):
        """이벤트 그룹 전체를 on/off (events/<group>/enable 에 1/0 기록)."""
        self._write(f"events/{group}/enable", "1" if enable else "0")

    def list_events_in_group(self, group):
        """
        그룹에 속한 개별 이벤트 이름 목록을 정렬해 반환한다.
        (events/<group>/ 의 하위 디렉터리들 — enable/filter 제어파일은 제외)
        예) ufs → [ufshcd_command, ufshcd_uic_command, ufshcd_clk_gating, ...]
        """
        out = self.adb.shell(f"ls {self._path('events', group)}", check=False)
        events = []
        for name in out.split():
            name = name.strip()
            if name and name not in _NON_EVENT_ENTRIES:
                events.append(name)
        return sorted(events)

    def enable_event(self, group, event, enable=True):
        """그룹 내 개별 이벤트 하나만 on/off (events/<group>/<event>/enable)."""
        self._write(f"events/{group}/{event}/enable", "1" if enable else "0")

    # ── (A) function_graph: I/O 인과(호출 중첩) 보기 ──────────────
    def set_graph_functions(self, funcs):
        """
        set_graph_function 을 주어진 함수 목록으로 설정한다.
        디바이스에 존재하지 않는 함수는 커널이 거부하므로, 적용에 성공한 함수만
        리스트로 반환한다(범위 한정으로 로그 폭발 방지).
        """
        gf = self._path("set_graph_function")
        self.adb.shell(f"echo > {gf}", check=False)      # 먼저 비운다
        applied = []
        for fn in funcs:
            out = self.adb.shell(f"echo {fn} >> {gf} && echo OK", check=False)
            if out.strip().endswith("OK"):
                applied.append(fn)
        return applied

    def clear_graph_functions(self):
        """set_graph_function 을 비워 function_graph 범위 제한을 해제한다."""
        self.adb.shell(f"echo > {self._path('set_graph_function')}", check=False)

    # ── (B) hist/synthetic 흐름 추적 트리거 ────────────────────────────
    def create_synthetic_event(self, definition):
        """synthetic_events 에 합성 이벤트를 정의한다(예: 'io_latency u64 lat; ...')."""
        self.adb.shell(f"echo '{definition}' >> {self._path('synthetic_events')}",
                       check=True)

    def remove_synthetic_event(self, name):
        """이름으로 합성 이벤트를 제거한다."""
        self.adb.shell(f"echo '!{name}' >> {self._path('synthetic_events')}",
                       check=False)

    def set_event_trigger(self, group, event, trigger):
        """이벤트에 hist 등 트리거를 설치한다(events/<group>/<event>/trigger)."""
        self.adb.shell(
            f"echo '{trigger}' > {self._path('events', group, event, 'trigger')}",
            check=True)

    def clear_event_trigger(self, group, event, trigger):
        """설치한 트리거를 제거한다('!' 접두로 동일 문자열 기록)."""
        self.adb.shell(
            f"echo '!{trigger}' > {self._path('events', group, event, 'trigger')}",
            check=False)

    def apply_correlation_preset(self, name):
        """
        CORRELATION_TRIGGERS 프리셋을 설치한다(synthetic 이벤트 + hist 트리거).

        프리셋에 여러 변형(variants)이 있으면 앞에서부터 시도해 '실제로 먹히는'
        변형을 자동 선택한다. 각 변형은 (1)합성 이벤트 생성 (2)트리거 설치
        (3)결과 이벤트 실제 생성 확인 까지 통과해야 성공으로 본다. 실패하면 그
        변형의 설치분을 롤백하고 다음 변형을 시도한다. 모두 실패하면 마지막
        오류를 올린다.

        설치 항목은 추적해 두었다가 remove_correlation_presets() 로 정리한다.
        반환: 결과(합성) 이벤트 (group, event) 또는 None.
        """
        preset = CORRELATION_TRIGGERS[name]
        # 단일/다중 변형을 같은 코드로 다루기 위해 리스트로 정규화.
        variants = preset.get("variants") or [preset]

        last_err = None
        for idx, variant in enumerate(variants):
            try:
                # 1) 합성 이벤트 먼저 정의해야 트리거의 onmatch(...).<synth>() 가 유효.
                if variant.get("synthetic"):
                    self.create_synthetic_event(variant["synthetic"])
                    self._installed_synth.append(variant["synthetic"].split()[0])
                # 2) 트리거들을 차례로 설치(성공분만 추적 리스트에 누적).
                for g, e, trig in variant["triggers"]:
                    self.set_event_trigger(g, e, trig)
                    self._installed_triggers.append((g, e, trig))
                # 3) 결과 이벤트가 '실제로' 만들어졌는지 확인(echo 가 통과해도 커널이
                #    조용히 무시하는 경우가 있어 존재 검증이 필요하다).
                res = variant.get("result_event")
                if res:
                    chk = self.adb.shell(
                        f"test -e {self._path('events', res[0], res[1], 'enable')} "
                        f"&& echo OK", check=False)
                    if "OK" not in chk:
                        raise AdbError(
                            f"결과 이벤트 {res[0]}/{res[1]} 가 생성되지 않음(변형 불일치)")
                    # 결과 이벤트를 enable 해야 캡처 로그에 그 줄이 찍힌다.
                    try:
                        self.enable_event(res[0], res[1], True)
                    except AdbError:
                        pass                  # enable 실패는 치명적이지 않음
                self._active_correlation_variant = idx   # 어떤 변형이 먹었는지 기록
                return res
            except AdbError as e:
                # 이 변형 실패 → 부분 설치분만 롤백하고 다음 변형 시도.
                last_err = e
                self.remove_correlation_presets()
        # 모든 변형 실패.
        raise last_err if last_err else AdbError("흐름 추적 트리거 설치 실패")

    def remove_correlation_presets(self):
        """설치한 모든 흐름 추적 트리거와 합성 이벤트를 제거한다."""
        # 설치 역순으로 트리거를 떼야 의존(예: complete→issue 참조)이 안 깨진다.
        for g, e, trig in reversed(self._installed_triggers):
            self.clear_event_trigger(g, e, trig)
        self._installed_triggers = []
        # 트리거를 모두 뗀 뒤에야 합성 이벤트를 안전하게 삭제할 수 있다.
        for name in self._installed_synth:
            self.remove_synthetic_event(name)
        self._installed_synth = []

    # ── (A-대체) 이벤트 스택트레이스 ──────────────────────────────
    def apply_event_stacktrace(self, events):
        """
        주어진 (group, event) 들에 'stacktrace' 트리거를 설치한다.
        반환: (applied, failed) — applied=[(g,e)...], failed=[(g,e,사유)...].

        주의 1) 트리거는 도구를 종료해도 커널에 '잔류'한다. 이미 같은 stacktrace
        트리거가 남아 있으면 재설치가 "이미 있음(File exists)"으로 실패하므로,
        설치 전에 먼저 같은 트리거를 제거(idempotent)해 항상 깨끗하게 새로 건다.
        주의 2) 스택은 '그 이벤트가 켜져 있고 실제로 발생할 때' 찍힌다(해당 그룹을
        활성화해 둬야 함). 함수 트레이서가 없어도 동작한다.
        """
        applied, failed = [], []
        for g, e in events:
            # (1) 잔류분 제거 후 새로 설치 → 중복으로 인한 실패 방지(멱등).
            self.clear_event_trigger(g, e, "stacktrace")
            try:
                self.set_event_trigger(g, e, "stacktrace")
            except AdbError as err:
                # 이벤트가 없거나(미지원) 다른 트리거가 막는 경우 → 사유를 보존.
                failed.append((g, e, str(err)))
                continue
            self._installed_stack_triggers.append((g, e))
            applied.append((g, e))
        return applied, failed

    def remove_event_stacktrace(self):
        """설치한 모든 stacktrace 트리거를 제거한다."""
        for g, e in reversed(self._installed_stack_triggers):
            self.clear_event_trigger(g, e, "stacktrace")
        self._installed_stack_triggers = []

    def diagnose_hist_support(self):
        """
        hist 트리거 / synthetic 이벤트 지원 여부를 '실측'으로 진단한다.
        흐름 추적 트리거(h) 설치가 실패했을 때, 원인이
          (1) 쓰기 권한(root) 인지
          (2) hist 트리거 미지원(CONFIG_HIST_TRIGGERS) 인지
          (3) synthetic 이벤트 미지원(CONFIG_SYNTH_EVENTS) 인지
        를 구분하기 위함. 부작용 없이 시험용 트리거를 걸었다가 바로 제거한다.
        반환: dict(writable, hist, synth, detail).
        """
        result = {"writable": False, "hist": False, "synth": False, "detail": ""}
        trig = self._path("events", "block", "block_rq_issue", "trigger")

        # (2) bare hist 트리거가 먹는지 — 키만 있는 최소 hist 로 시험.
        #     쓰기 권한이 없으면 여기서 'Permission denied' 가 난다(권한 문제 구분).
        try:
            self.adb.shell(f"echo 'hist:keys=dev' > {trig}", check=True)
            result["writable"] = True
            result["hist"] = True
            # 시험용 트리거 즉시 제거(원상복구)
            self.adb.shell(f"echo '!hist:keys=dev' > {trig}", check=False)
        except AdbError as e:
            msg = str(e)
            result["detail"] = msg
            # 권한 문제와 '기능 미지원(Invalid argument)' 을 메시지로 구분
            if "ermission" in msg or "denied" in msg.lower():
                result["writable"] = False
            else:
                result["writable"] = True   # 쓰기는 됐으나 hist 자체가 거부됨

        # (3) synthetic_events 파일 존재 여부(CONFIG_SYNTH_EVENTS).
        out = self.adb.shell(
            f"test -e {self._path('synthetic_events')} && echo OK", check=False)
        result["synth"] = "OK" in out
        return result

    def set_tracer(self, tracer):
        """current_tracer 를 설정(function_graph 등). 'nop' 으로 해제."""
        self._write("current_tracer", tracer)

    def get_tracer(self):
        """현재 설정된 tracer 이름 반환."""
        return self._read("current_tracer").strip()

    # ── 버퍼 크기 제어 ────────────────────────────────────────────
    def get_buffer_size_kb(self):
        """현재 CPU 당 ring buffer 크기(KB)를 정수로 반환."""
        out = self._read("buffer_size_kb").strip()
        try:
            return int(out)
        except ValueError:
            return -1

    def set_buffer_size_kb(self, kb):
        """CPU 당 ring buffer 크기(KB)를 설정한다."""
        try:
            kb = int(kb)
        except (TypeError, ValueError):
            raise AdbError(f"버퍼 크기는 정수여야 합니다: {kb!r}")
        if kb <= 0:
            raise AdbError(f"버퍼 크기는 1 이상이어야 합니다: {kb}")
        self._write("buffer_size_kb", str(kb))

    def maximize_buffer(self, target_kb=65536):
        """
        ftrace ring buffer 를 최대한 크게 설정한다.

        커널은 메모리 한계에 따라 요청값을 자동으로 줄여(clamp) 적용하므로,
        넉넉히 큰 값(target_kb, 기본 64MB/CPU)을 요청한 뒤 실제 적용된 값을
        읽어서 반환한다.
        """
        if target_kb <= 0:
            raise AdbError(f"target_kb 는 1 이상이어야 합니다: {target_kb}")
        try:
            self.set_buffer_size_kb(target_kb)
        except AdbError:
            # 요청값이 너무 커서 거부되면 절반씩 줄여가며 재시도한다.
            size = target_kb
            while size >= 1024:
                size //= 2
                try:
                    self.set_buffer_size_kb(size)
                    break
                except AdbError:
                    continue
        return self.get_buffer_size_kb()

    # ── 수집 on/off 및 버퍼 비우기 ────────────────────────────────
    def set_tracing_on(self, on=True):
        """tracing_on 을 1/0 으로 설정해 수집을 시작/정지."""
        self._write("tracing_on", "1" if on else "0")

    def clear_trace(self):
        """trace 버퍼를 비운다(빈 내용을 기록)."""
        self.adb.shell(f"echo > {self._path('trace')}", check=False)

    def set_trace_clock(self, clock="mono"):
        """trace clock 설정(기본 mono: 부팅 후 단조 증가, 분석에 유리)."""
        self._write("trace_clock", clock)

    # ── 스냅샷 읽기 ───────────────────────────────────────────────
    def read_trace(self):
        """현재 trace 버퍼 전체 스냅샷을 문자열로 반환."""
        return self._read("trace")

    # ── 실시간 캡처 시작 ──────────────────────────────────────────
    def start_capture(self, local_path, header_lines=None):
        """
        trace_pipe 를 실시간으로 읽어 local_path 파일에 저장하는 캡처 세션을 시작한다.

        반환: CaptureSession 객체. session.stop() 으로 종료한다.

        header_lines: 파일 상단에 기록할 메타데이터 줄 리스트(선택).
        """
        # 수집 시작 전 버퍼를 비우고 tracing_on 을 켠다.
        self.clear_trace()
        self.set_tracing_on(True)
        pipe_path = self._path("trace_pipe")
        session = CaptureSession(self.adb, pipe_path, local_path,
                                 ftrace=self, header_lines=header_lines)
        session.start()
        return session

    # ── 정리(원복) ────────────────────────────────────────────────
    def disable_all_events(self):
        """모든 이벤트/트리거/그래프설정을 끄고 tracer 를 nop 으로 되돌린다(정리용)."""
        # 흐름 추적 트리거·합성 이벤트·스택트레이스 먼저 제거(이벤트보다 먼저 떼야 안전)
        self.remove_correlation_presets()
        self.remove_event_stacktrace()
        self.adb.shell(f"echo 0 > {self._path('events/enable')}", check=False)
        self.adb.shell(f"echo nop > {self._path('current_tracer')}", check=False)
        self.clear_graph_functions()
        self.adb.shell(f"echo 0 > {self._path('tracing_on')}", check=False)


# ╔══════════════════════════════════════════════════════════════════╗
# ║ 실시간 캡처 세션                                                   ║
# ╚══════════════════════════════════════════════════════════════════╝
class CaptureSession:
    """
    `adb shell cat trace_pipe` 출력을 백그라운드 스레드에서 읽어
    로컬 파일로 저장하는 캡처 세션.

    GUI 에서도 동일하게 start()/stop() 으로 제어할 수 있다.
    on_line 콜백을 등록하면 실시간으로 줄 단위 갱신을 받을 수 있어
    향후 GUI 의 실시간 로그 뷰에 그대로 연결할 수 있다.
    """

    def __init__(self, adb, pipe_path, local_path, ftrace=None,
                 header_lines=None, on_line=None):
        self.adb = adb
        self.pipe_path = pipe_path        # 디바이스의 trace_pipe 경로
        self.local_path = local_path      # 저장할 로컬 파일 경로
        self.ftrace = ftrace              # 종료 시 tracing_on=0 처리용
        self.header_lines = header_lines or []
        self.on_line = on_line            # (선택) 줄 단위 콜백

        self._proc = None                 # adb 캡처 프로세스
        self._thread = None               # 파일 기록 스레드
        self._running = False
        self._stopped = False             # stop() 중복 호출 방지
        self._file = None                 # 열린 로그 파일 핸들
        self.line_count = 0               # 저장된 줄 수(진행 표시용)
        self.error = None                 # 캡처 중 발생한 예외(있으면 저장)

    def start(self):
        """
        캡처 프로세스와 기록 스레드를 시작한다.

        파일 열기/폴더 생성/프로세스 실행 실패는 여기서 즉시 예외로 던져
        호출측(UI)이 인지할 수 있게 한다. (스레드 안에서 조용히 죽지 않도록)
        """
        # 1) 저장 폴더 생성 — 권한/경로 오류를 호출측에 알린다.
        folder = os.path.dirname(os.path.abspath(self.local_path))
        try:
            if folder and not os.path.isdir(folder):
                os.makedirs(folder, exist_ok=True)
        except OSError as e:
            raise AdbError(f"저장 폴더를 만들 수 없습니다: {folder} ({e})")

        # 2) 로그 파일을 먼저 열어 쓰기 가능 여부를 즉시 확인한다.
        try:
            self._file = open(self.local_path, "w",
                              encoding="utf-8", errors="replace")
        except OSError as e:
            raise AdbError(f"로그 파일을 열 수 없습니다: {self.local_path} ({e})")

        # 3) 메타데이터 헤더 기록
        try:
            for h in self.header_lines:
                self._file.write(f"# {h}\n")
            self._file.flush()
        except OSError as e:
            self._file.close()
            raise AdbError(f"로그 파일 기록 실패: {self.local_path} ({e})")

        # 4) adb 캡처 프로세스 실행
        cmd = self.adb._base() + ["shell", f"cat {self.pipe_path}"]
        try:
            self._proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                text=True,
                errors="replace",
                bufsize=1,                # 라인 버퍼링
            )
        except OSError as e:
            self._file.close()
            raise AdbError(f"adb 캡처 프로세스 실행 실패: {e}")

        self._running = True
        self._thread = threading.Thread(target=self._pump, daemon=True)
        self._thread.start()

    def _pump(self):
        """
        trace_pipe 스트림을 읽어 파일에 기록하는 내부 루프.
        스레드 안에서 발생한 예외는 self.error 에 저장해 stop() 시 확인 가능하게 한다.
        """
        f = self._file
        try:
            for line in self._proc.stdout:
                if not self._running:
                    break
                f.write(line)
                self.line_count += 1
                # 너무 잦은 flush 는 성능 저하 → 일정 주기로만 flush
                if self.line_count % 200 == 0:
                    f.flush()
                if self.on_line:
                    # 콜백 예외가 캡처를 중단시키지 않도록 격리한다(GUI 안전).
                    try:
                        self.on_line(line)
                    except Exception:
                        pass
        except (OSError, ValueError) as e:
            # ValueError: 파일이 외부에서 닫힌 경우 등
            self.error = e
        finally:
            try:
                f.flush()
            except Exception:
                pass

    def is_alive(self):
        """캡처 스레드가 살아있는지 여부(조기 종료 감지용)."""
        return self._thread is not None and self._thread.is_alive()

    def stop(self):
        """캡처를 종료하고 디바이스의 tracing_on 을 끈다. (중복 호출 안전)"""
        if self._stopped:
            return self.line_count
        self._stopped = True
        self._running = False
        # 디바이스 수집 정지 → trace_pipe 가 더 이상 데이터를 내보내지 않음
        if self.ftrace is not None:
            try:
                self.ftrace.set_tracing_on(False)
            except AdbError:
                pass
        # adb 캡처 프로세스 종료
        if self._proc is not None:
            try:
                self._proc.terminate()
                self._proc.wait(timeout=5)
            except Exception:
                try:
                    self._proc.kill()
                except Exception:
                    pass
        if self._thread is not None:
            self._thread.join(timeout=5)
        # 파일 핸들 정리
        if self._file is not None:
            try:
                self._file.close()
            except Exception:
                pass
        return self.line_count


# ╔══════════════════════════════════════════════════════════════════╗
# ║ 유틸리티                                                           ║
# ╚══════════════════════════════════════════════════════════════════╝
def default_log_filename(prefix="ftrace"):
    """타임스탬프가 포함된 기본 로그 파일명을 생성한다."""
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    return f"{prefix}_{ts}.log"
