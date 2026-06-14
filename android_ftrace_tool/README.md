# Android ftrace 로그 수집 도구

Android(리눅스) 커널이 지원하는 **ftrace** trace 로그를 골라서 켜고, 실시간으로
캡처해 `.log` 파일로 저장하는 도구입니다.

PC 와 Android 폰을 USB(adb)로 연결한 뒤 실행하면 됩니다.

---

## 요구 사항

- **PC**: Python 3.7+
- **adb** (Android Platform Tools) 설치 및 `PATH` 등록
  - 확인: 터미널에서 `adb version`
- **Android 폰**
  - 설정 → 개발자 옵션 → **USB 디버깅** 켜기
  - ftrace(tracefs) 제어에는 보통 **root 권한**이 필요합니다
    (`userdebug`/`eng` 빌드에서 `adb root` 가 동작, 양산 빌드는 `su` 필요).

---

## 실행 방법

```bash
# 저장소 루트에서
python -m android_ftrace_tool

# adb 경로를 직접 지정하려면
python -m android_ftrace_tool --adb /path/to/adb
```

---

## 동작 시퀀스

1. **디바이스 연결** — 연결된 adb 디바이스 목록을 출력하고 번호로 선택합니다.
2. **ftrace 옵션 설정** — 앱의 파일 I/O 가 **앱 → F2FS → block → SCSI → UFS/UIC**
   까지 내려가는 **스토리지 데이터 플로우** 순서로 이벤트 그룹을 보여줍니다
   (디바이스가 실제 지원하는 것만 선택 가능, 미지원은 `[X]`).

   | 계층 | 그룹 | 설명 |
   |------|------|------|
   | 앱 I/O   | `android_fs` | 앱→파일 I/O 매핑(read/write 시작·종료, 경로·inode·오프셋) |
   | 파일시스템 | `f2fs`    | F2FS 전반: read/write/fsync, **GC**, checkpoint, discard, truncate(삭제) |
   | 파일시스템 | `ext4`    | EXT4 동작(/data 가 ext4 인 단말): write/할당/truncate |
   | 파일시스템 | `erofs`   | EROFS 읽기전용(system/vendor) 읽기 |
   | 저널링   | `jbd2`      | EXT4 저널링 커밋/체크포인트 |
   | 라이트백 | `writeback` | 더티 페이지 flush 시점(`balance_dirty_pages`) — 앱 write→block 연결 |
   | 블록     | `block`     | 블록 I/O 요청(bio 큐잉, 발행/완료, 병합, discard) |
   | SCSI     | `scsi`      | SCSI 명령 디스패치/완료 (UFS 상위 계층) |
   | UFS/UIC  | `ufs`       | UFS 디바이스 명령(`ufshcd_command`) + UIC 계층(`ufshcd_uic_command`) |

   > **GC 등 백그라운드 동작**: f2fs 의 GC·checkpoint·discard 는 `f2fs` 그룹 안의
   > 개별 이벤트라, `f2fs` 를 켜면(또는 `f` 프리셋) 자동으로 추적됩니다.
   > 플로우 프리셋(`f`)은 `android_fs → f2fs → writeback → block → scsi → ufs` 를 켭니다
   > (ext4/erofs/jbd2 는 단말 파일시스템에 따라 메뉴에서 개별 선택).

   조작 명령:
   - **번호** — 그룹 전체 on/off 토글
   - **`f`** — read/write/erase **플로우 전체 켜기**(위 5개 그룹을 한 번에, 지원분만)
   - **`y`** — **sync 시스템콜 추적** on/off (아래 "sync 추적" 참고)
   - **`d`** — 켜진 그룹의 **개별 이벤트 세부 선택**(예: `ufs` 에서 클럭/전원 이벤트만
     빼고 `ufshcd_command`·`ufshcd_uic_command` 만 남기기) → 표시는 `[~]`(일부)
   - **`x`** — 전체 그룹 보기(고급), **`t`** — tracer, **`a`** — 전체 해제, **`s`** — 설정완료

   **sync 추적**: `fsync`/`sync` 동작은 계층마다 다른 이벤트로 나타납니다.
   파일시스템 레벨(`f2fs_sync_file_enter/exit`, `f2fs_write_checkpoint`)·라이트백·
   블록 FLUSH·UFS `SYNCHRONIZE_CACHE`(opcode 0x35)는 위 그룹들로 이미 잡힙니다.
   추가로 **시스템콜 진입점**(`sys_enter_fsync` 등)까지 보려면 `y` 를 누르세요.
   `syscalls` 그룹 전체(수백 개)가 아니라 sync 계열 이벤트만 핀포인트로 켜므로
   로그가 폭발하지 않습니다. (정의: `core.py` 의 `EVENT_BUNDLES`)

   상태 표시: `[O]` 그룹 전체 / `[~]` 일부 이벤트만 / `[ ]` 꺼짐

   > 관심 분야(그룹)를 바꾸려면 `core.py` 의 `STORAGE_EVENT_GROUPS` 딕셔너리만,
   > 플로우 프리셋 순서는 `FLOW_PRESET_ORDER` 만 수정하면 됩니다.

   **앱 read/write/erase 플로우 추적 팁**: `f`(프리셋)로 전체 계층을 켜면, 같은
   파일 동작이 각 계층에서 어떻게 변환되어 UFS 명령까지 내려가는지 한 로그에서
   볼 수 있습니다. 로그량을 줄이려면 `d` 로 `ufs` 그룹에서 `ufshcd_command`,
   `ufshcd_uic_command` 만 남기는 것을 권장합니다.
3. **캡처 준비** — `trace_clock`을 `mono`로 설정하고 ring buffer 를 최대화한 뒤,
   저장할 로그 파일명을 입력받습니다(미입력 시 타임스탬프 파일명 자동 생성).
4. **캡처 시작/저장** — `trace_pipe`를 실시간으로 읽어 파일에 저장합니다.
   **Enter** 키를 누르면 캡처를 종료하고, 원하면 디바이스 ftrace 설정을 원복합니다.

저장 파일 상단에는 사용한 tracefs 경로/tracer/이벤트/버퍼 크기가 주석(`#`)으로
기록됩니다.

---

## 아키텍처 (UI / 로직 분리)

향후 **Windows GUI 도구**로 확장할 것을 고려해, 화면 출력과 로직을 분리했습니다.

| 파일 | 역할 |
|------|------|
| `core.py` | adb 통신 + ftrace 제어 **순수 로직**. `print`/`input` 없음. GUI 에서 그대로 재사용. |
| `cli.py`  | 대화형 **콘솔 UI**. 모든 출력/입력이 여기 격리됨. |
| `__main__.py` | `python -m android_ftrace_tool` 진입점. |

### GUI 확장 시

`cli.py` 를 대체하는 `gui.py`(예: PyQt/Tkinter)를 새로 만들고, 동일한
`core.py` API 를 호출하면 됩니다. **로직 수정은 불필요**합니다.

```python
from android_ftrace_tool.core import Adb, Ftrace

adb = Adb(serial="...")
ft  = Ftrace(adb); ft.detect_tracefs()
groups = ft.list_event_groups()      # 체크박스 목록에 표시
ft.enable_event_group("sched")       # 체크박스 클릭 → 호출
ft.maximize_buffer()
session = ft.start_capture("out.log", on_line=update_log_view)  # 실시간 뷰 콜백
...
session.stop()                       # '중지' 버튼 → 호출
```

`CaptureSession` 은 `on_line` 콜백을 지원하므로, GUI 의 실시간 로그 뷰에
바로 연결할 수 있습니다.

---

## 예외/에러 처리

입력 조건과 시스템 예외를 다음과 같이 방어적으로 처리합니다.

**입력 조건**
- 잘못된 메뉴 번호/문자는 무시하고 다시 입력을 요청합니다.
- 디바이스 상태가 `device`(정상)가 아니면(예: `unauthorized`, `offline`) 선택을 차단합니다.
- 파일명 검증: 금지 문자(`<>:"|?*`), 빈 이름/디렉터리만 지정, `.`/`..` 차단,
  확장자 자동 보정(`.log`), 기존 파일 덮어쓰기 확인, 저장 폴더 쓰기 권한 확인.
- `Ctrl-C`/`Ctrl-D`(EOF)/파이프 입력 종료를 트레이스백 없이 안전하게 종료하며,
  입력 스트림이 끝난 상태에서 재프롬프트가 무한 반복되지 않도록 제한합니다.

**시스템 예외**
- `adb` 미설치/실행권한 없음/시간 초과/시스템 오류를 명확한 메시지로 안내합니다.
- tracefs 미탐지(미지원 커널/권한 부족) 시 원인을 안내합니다.
- ring buffer 최대화 요청이 거부되면 절반씩 줄여 재시도하고, 실제 적용값을 표시합니다.
- 실시간 캡처 스레드에서 발생한 오류(파일 쓰기 실패 등)는 조용히 묻히지 않고
  종료 시 보고됩니다. 캡처가 즉시 종료되면(권한/`trace_pipe` 접근 불가) 경고합니다.
- 어떤 경로로 종료하든 캡처 정지(`tracing_on=0`)와 파일 핸들 정리가 보장됩니다.

## 주의

- ftrace 제어는 root 권한이 필요합니다. 권한이 없으면 일부 명령이 실패할 수 있으며,
  도구는 자동으로 `su -c` 우회를 시도합니다.
- ring buffer 최대화는 커널 메모리 한계 내에서 자동으로 조정(clamp)됩니다.
