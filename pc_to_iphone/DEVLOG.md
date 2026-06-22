# PC → iPhone 파일 전송기 개발 로그

> 대화 기반 개발 기록. 설계 결정, Q&A, 기술 메모를 시간순으로 정리합니다.

---

## 2026-06-13

### 요구사항 정의

**목적**
- iPhone을 PC에 USB로 연결했을 때 PC → iPhone 방향으로 파일을 전송하는 프로그램 개발
- 기존에는 iPhone → PC 방향(사진 꺼내기)만 가능한 상황

**전송 지원 파일 형식**
`.txt` · `.pdf` · `.html` · `.py` · `.c` · `.cpp` · `.java` · `.bat` · `.sh`

**저장 경로**
iPhone 내부 저장소에 `내다운로드/` 폴더를 생성하여 저장
→ iPhone 파일 앱 → 나의 iPhone → 내다운로드 에서 확인 가능

---

### 구현 결정사항

**통신 라이브러리: `pymobiledevice3`**
- Apple의 AFC(Apple File Conduit) 프로토콜을 Python으로 구현한 오픈소스 라이브러리
- USB를 통해 iPhone 내부 저장소(`/var/mobile/Media/`)에 직접 파일 쓰기 가능
- `pip install pymobiledevice3` 한 줄로 설치

**GUI: `tkinter` (Python 내장)**
- 외부 UI 라이브러리 없이 동작
- 다크 테마 적용

**생성된 파일 구조**
```
pc_to_iphone/
├── main.py          # tkinter GUI 메인 앱
├── transfer.py      # iPhone AFC 통신 로직
├── requirements.txt # 의존성 (pymobiledevice3)
├── README.md        # 설치·사용 가이드
└── DEVLOG.md        # 이 파일
```

---

### Q&A

**Q. iTunes가 없는 경우에도 전송이 가능한가?**

가능하다. `pymobiledevice3`는 iTunes 자체가 필요한 것이 아니라 **USB 드라이버(usbmuxd)**만 있으면 동작한다.

| OS | iTunes 대체 방법 |
|----|----------------|
| Windows 10/11 | Microsoft Store에서 **"Apple Devices"** 앱 무료 설치 (드라이버만 포함, ~50MB) |
| macOS | Finder가 자동 처리 — 별도 설치 불필요 |
| Linux (Ubuntu) | `sudo apt install usbmuxd` |

처음에는 Wi-Fi 전송 모드를 추가하려 했으나, PC와 iPhone이 같은 네트워크에 있어야 하고 방화벽 문제도 있어 실용적이지 않다는 판단으로 **USB 전송 단일 모드**로 유지.

앱 내에 **"iTunes 없이 설치하는 방법"** 안내 버튼 추가.

---

**Q. 아이패드에도 동일하게 사용 가능한가?**

동일하게 사용 가능하다. 코드 변경 없음.

- iPhone과 iPad 모두 동일한 **AFC 프로토콜** 사용
- `pymobiledevice3`가 iOS/iPadOS 구분 없이 처리
- 저장 위치: 파일 앱 → 나의 iPad → 내다운로드/

---

**Q. 파일 전송 시 파일 변환이 발생하는가?**

발생하지 않는다.

```python
# transfer.py
with open(filepath, 'rb') as f:   # 바이너리 모드로 읽기
    data = f.read()
afc.set_file_contents(target_path, data)  # 그대로 전송
```

파일을 바이너리 모드(`'rb'`)로 읽어 AFC로 그대로 전송한다.
인코딩 변환, 포맷 변환, 압축 — 아무것도 없다. 원본과 **바이트 단위로 완전히 동일**하게 저장된다.

주의: 프로그램과 무관하게, Windows에서 생성된 `.txt`·`.sh` 파일은 원래부터 줄바꿈이 CRLF(`\r\n`)로 저장되어 있다.

---

**Q. Ubuntu OS를 사용하는 PC와도 전송이 가능한가?**

가능하다. Ubuntu 설치 절차:

```bash
# 1. 시스템 패키지
sudo apt install usbmuxd libimobiledevice-utils python3-tk python3-pip
sudo systemctl enable usbmuxd
sudo systemctl start usbmuxd

# 2. USB 권한 (1회, 재로그인 필요)
sudo usermod -aG plugdev $USER

# 3. Python 의존성
pip install -r requirements.txt

# 4. 실행
python3 main.py
```

---

**Q. usbmuxd란 무엇인가?**

**USB Multiplexer Daemon** — PC와 Apple 기기 사이의 USB 통신을 중계하는 백그라운드 서비스.

iPhone/iPad는 USB로 연결해도 일반 USB 저장장치처럼 동작하지 않고 Apple 전용 프로토콜을 사용한다. usbmuxd가 그 중간 다리 역할을 한다.

```
[PC 앱]
  ↕  TCP 소켓 (localhost)
[usbmuxd]           ← USB 케이블 1개로 여러 채널 동시 운영
  ↕  USB 케이블
[iPhone/iPad]
```

Multiplexing: USB 케이블 하나로 파일 전송(AFC), iTunes 동기화, Xcode 디버깅, 화면 미러링을 동시에 처리한다.

| OS | 구현체 |
|----|--------|
| Windows | Apple Mobile Device Service (iTunes/Apple Devices 앱 설치 시 자동) |
| macOS | Apple 내장 usbmuxd |
| Linux | 오픈소스 usbmuxd (역공학 구현) |

이 프로그램에서의 흐름:
```
main.py → pymobiledevice3 → usbmuxd 소켓 → USB → iPhone → AFC → 내다운로드/
```

---

## OS별 설치 요약

| OS | 드라이버 | tkinter | 실행 명령 |
|----|---------|---------|----------|
| Windows 10/11 | Microsoft Store "Apple Devices" 앱 | 기본 내장 | `python main.py` |
| macOS | 기본 내장 | 기본 내장 | `python3 main.py` |
| Ubuntu / Linux | `sudo apt install usbmuxd` | `sudo apt install python3-tk` | `python3 main.py` |
