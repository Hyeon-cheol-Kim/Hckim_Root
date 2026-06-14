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
2. **ftrace 옵션 설정** — 디바이스에서 실제 지원하는 이벤트 그룹과 tracer 목록을
   읽어와 보여줍니다. 번호를 입력하면 해당 그룹이 즉시 on/off 토글되며,
   `s`(설정완료)를 누르기 전까지 자유롭게 선택할 수 있습니다.
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
