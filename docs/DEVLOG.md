# 개발 로그 (DEVLOG)

이 문서는 이 저장소에서 진행한 **대화·결정·구현 내역**을 누적 기록한다. 새 작업을
할 때마다 계속 갱신한다(규칙: `CLAUDE.md`). 코드 자체의 사용법은 각 도구의
`README.md`/`MANUAL.md` 를, 여기서는 **왜 그렇게 했는지(결정·맥락)** 를 남긴다.

- 대상 도구: `android_ftrace_tool/`(주력), `eye_diagram_converter/`,
  `tools/bpftrace-android/`
- 작업 브랜치: `claude/android-ftrace-log-tool-ivhpy9`

---

## 1. 핵심 개념 — "흐름 추적(연결)"

Android ftrace 로그는 "시간순으로 나열된 독립 이벤트"라, 계층을 관통하는 단일 ID가
없다. 따라서 **앱 read() ↔ UFS command** 같은 1:1 인과를 로그만으로 보장할 수 없다
(read 캐시 히트, readahead/병합, write 의 비동기 writeback 때문). 대신 **조인 키**로
계층을 잇는다. 이 "이벤트 연결"을 한글 용어로 **흐름 추적**이라 부른다("상관"은
쓰지 않음; 영문 식별자 `correlation` 등은 유지).

| 구간 | 조인 키 |
|------|---------|
| block ↔ scsi ↔ ufs | sector / LBA (device sector = LBA × 논리블록/512, 보통 ×8) |
| 파일 ↔ 블록 | `f2fs_map_blocks` 의 m_pblk + 파티션 오프셋 |
| 앱 ↔ 파일 | inode(ino) + 파일 오프셋 |

분석 스택(목적별):
1. 눈으로 인과 추적 → `g`(function_graph, 미지원 시 이벤트 스택트레이스)
2. 로그 기반 사후 흐름 추적/지연 → `h` + `analyzer.py`(best-effort)
3. 커널-내 정밀 1:1 → `bpftrace.py`(eBPF)

---

## 2. 기능별 결정·구현 기록

### (A) function_graph I/O 인과 보기 — `g`
- 동기 제출 경로(`vfs_read→f2fs→submit_bio→scsi→ufshcd`)를 호출 중첩으로 본다.
- 범위는 `core.py` 의 `IO_GRAPH_FUNCTIONS` 로 한정(로그 폭발 방지).
- **function_graph 미지원 커널 대체**: `CONFIG_FUNCTION_GRAPH_TRACER` 가 꺼진 양산
  커널이 많아, 주요 하위 이벤트(`block_rq_issue`, `scsi_dispatch_cmd_start`,
  `ufshcd_command`, `f2fs_sync_file_enter`)에 `stacktrace` 트리거를 붙여 호출 체인을
  로그에 남기는 방식으로 자동 대체(`STACK_TRACE_EVENTS`).
- **버그 수정(잔류 트리거)**: 트리거는 도구 종료 후에도 커널에 잔류 → 재설치가
  "File exists" 로 조용히 실패했음. `apply_event_stacktrace` 를 설치 전 제거(멱등)로
  바꾸고, 실패를 `[제외] group/event: 사유` 로 노출하도록 수정.

### (B) hist/synthetic 흐름 추적 트리거 — `h` (io_latency)
- `block_rq_issue↔block_rq_complete` 를 `(dev,sector)` 로 커널에서 조인해
  지연을 `io_latency` 합성 이벤트로 로그에 남긴다.
- 계산식: `io_latency(µs) = T_complete − T_issue`(같은 dev,sector). issue 트리거가
  `ts0=common_timestamp.usecs` 저장 → complete 트리거가 `lat=...-$ts0` 후
  `onmatch(...).io_latency(...)` 로 발행. 블록 계층 왕복(큐잉+디바이스).
- 요구: `CONFIG_HIST_TRIGGERS` / `CONFIG_SYNTH_EVENTS`.
- **실패 진단 추가**: 설치 실패 시 `diagnose_hist_support()` 로 권한 / hist 미지원 /
  synthetic 미지원 / 문법차이를 구분해 안내. (trigger 파일 존재 ≠ hist 지원)
- **버전 호환 변형 자동 선택**: onmatch 액션·필드 타입 문법이 커널마다 달라
  `CORRELATION_TRIGGERS` 를 변형(variants) 구조로 변경. V1 `.io_latency($lat,dev,sector)`
  → V2 `.trace(io_latency,...)` → V3 `lat`만(타입 불일치 회피) 순으로 시도하고,
  결과 이벤트가 실제 생성됐는지 확인 후 성공 변형을 채택(실패분 롤백).

### (C) 사후 흐름 추적 분석기 — `analyzer.py`
- 저장된 `.log` 를 파싱해 UFS↔block↔파일 스티칭 + opcode별 지연 요약.
- ratio(sector=LBA×r), 파티션 오프셋을 데이터에서 추정. UFS 지연은 tag로 send↔complete,
  block 지연은 (dev,sector)로 issue↔complete(또는 io_latency 우선).
- **android_fs 대체**: android_fs 미지원 커널을 위해 `f2fs_dataread_start`/
  `f2fs_datawrite_start` 도 파싱(ino/pos/len/cmdline/pid; 단 경로는 미제공 → `?`).

### (D) bpftrace — `bpftrace.py` (커널-내 1:1)
- 스크립트 생성/저장/실행(run)/준비도 점검(check) 서브커맨드.
- 스크립트: `block_latency`(dev,sector 조인), `ufs_latency`(tag 조인),
  `vfs_rw_latency`(tid), `read_to_device`(동기 read 인과),
  `io_callstack`(block 제출 kstack 집계 — function_graph 정밀 대체).
- `check`: BTF/CONFIG_BPF_*/tracefs/root/바이너리까지 ✅/⚠️/❌ 진단.
- 폰 바이너리는 정적(static aarch64) 필요 → `tools/bpftrace-android/`(Docker)로 빌드.
  기본 경로 `/data/local/tmp/bpftrace`.

### sync/fsync 추적 — `y`
- `syscalls` 그룹(`CONFIG_FTRACE_SYSCALLS`)이 없는 커널이 많아, **파일시스템 레이어
  fsync**(`f2fs_sync_file_enter/exit`, `f2fs_write_checkpoint`, ext4 동등)로 전환.
- 묶음 토글이 없는 그룹은 통째로 제외하고 있는 것만 켜도록 수정(f2fs-only 단말 대응).

---

## 3. 작업 규칙 / 구조 결정

- **주석 필수**: 모든 코드에 "왜"를 설명하는 상세 주석(한국어). `CLAUDE.md`.
- **폴더 규칙**: 새 파일은 루트에 흩뿌리지 않고 기능/도구 단위 전용 폴더에.
  루트 예외는 전역 문서(`CLAUDE.md`, `REQUEST_GUIDE.md`)와 `docs/`.
- **UI/로직 분리**: `core.py` 순수 로직(print/input 금지), UI 는 `cli.py`.
- **파일 정리 이력**: PAM4 관련 파일을 `eye_diagram_converter/` 로 `git mv`.

---

## 4. 커밋 타임라인 (이 세션)

| 커밋 | 내용 |
|------|------|
| `6d99149` | 흐름 추적 도입: function_graph(`g`), hist 트리거(`h`), analyzer |
| `e162369` | bpftrace 스크립트 생성기 |
| `ae36487` | eBPF 준비도 점검, aarch64 빌드 도구, 전체 MANUAL |
| `2fd12c2` | 용어 "상관"→"흐름 추적", 주석 보강 |
| `4423b7d` | CLAUDE.md(주석·규칙) 추가 |
| `18f5c82` | 기능 단위 폴더 정리(eye_diagram_converter) |
| `f38d47e` | analyzer: f2fs_dataread/datawrite 지원(android_fs 대체) |
| `d4edd5e` | sync(`y`): f2fs/ext4 fsync 레이어로 전환 |
| `5bc9f10` | `g`: function_graph 미지원 시 이벤트 스택트레이스 대체 |
| `91975bd` | `h`: 설치 실패 원인 진단(권한/hist/synthetic) |
| `87dc183` | `h`: hist/synthetic 문법 변형 자동 선택 |
| `0bb336c` | `g`: 스택트레이스 멱등 설치 + 실패 노출 |

---

## 5. 디바이스 확인 메모 (사용자 환경)

- `android_fs` 미지원 → `f2fs`(특히 `f2fs_map_blocks`, `f2fs_dataread_start`)로 대체.
- `syscalls` 미지원 → `y` 가 `f2fs_sync_file_enter`(확인됨) 등 FS 레이어 사용.
- `function_graph` 미지원 → `g` 가 이벤트 스택트레이스로 대체.
- `h` 설치 실패 진단: hist/synthetic 자체는 가능, onmatch/필드 문법 차이 → 변형
  자동 시도로 대응(V3까지).

---

## 6. 미해결 / 다음에 볼 것

- `h` 변형이 실 디바이스에서 어디까지 먹는지(V1/V2/V3) 확인 필요.
- 스택트레이스 부착 후 실제 로그에 호출 체인이 찍히는지 디바이스 확인.
- (선택) bpftrace 바이너리 빌드(`tools/bpftrace-android`) 실제 수행/검증.

---

> 갱신 규칙: 새 요청/결정/구현이 있을 때마다 이 문서의 해당 절(기능 기록·커밋
> 타임라인·미해결)을 업데이트한다. 한 작업 = 한 커밋 + 로그 갱신을 기본으로 한다.
