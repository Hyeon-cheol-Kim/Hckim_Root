# PC → iPhone USB 파일 전송기

USB로 연결된 iPhone에 PC의 파일을 전송하는 데스크톱 GUI 프로그램입니다.  
전송된 파일은 iPhone 내부 저장소의 **`내다운로드/`** 폴더에 저장됩니다.

---

## 지원 파일 형식

`.txt` · `.pdf` · `.html` · `.py` · `.c` · `.cpp` · `.java` · `.bat` · `.sh`

---

## 설치 및 실행

### 1. 드라이버 설치 (iTunes 불필요)

`pymobiledevice3`는 iTunes 전체 설치 없이 **USB 드라이버**만 있으면 동작합니다.

| OS | 드라이버 설치 방법 |
|----|------------------|
| **Windows 10/11** | Microsoft Store에서 **"Apple Devices"** 검색 후 무료 설치 (iTunes 불필요) |
| **macOS** | Finder가 자동으로 처리 — 별도 설치 불필요 |
| **Linux** | `sudo apt install libimobiledevice-utils usbmuxd` |

> **Apple Devices 앱** (Windows) = 드라이버만 포함된 경량 패키지입니다.  
> iTunes를 이미 설치한 경우에도 동작합니다.

### 2. Python 의존성 설치

```bash
pip install -r requirements.txt
```

### 3. 실행

```bash
python main.py
```

---

## 사용 방법

1. iPhone을 USB 케이블로 PC에 연결합니다.
2. iPhone 화면에서 **"신뢰"** 버튼을 누릅니다. (최초 1회)
3. 프로그램 상단에 `연결됨: [기기명]` 표시 확인.
4. **`+ 파일 추가`** 버튼으로 전송할 파일을 선택합니다.
5. **`iPhone으로 전송`** 버튼을 클릭합니다.
6. 전송 완료 후 iPhone의 **파일 앱 → 나의 iPhone → 내다운로드** 에서 확인합니다.

---

## iPhone에서 파일 확인하기

```
파일 앱 → 나의 iPhone → 내다운로드/
```

> iOS 13 이상에서 기본 제공되는 **파일(Files)** 앱에서 확인 가능합니다.

---

## 문제 해결

| 증상 | 해결 방법 |
|------|----------|
| 연결 안 됨 | USB 케이블 교체, Apple Devices 앱 재설치 |
| `신뢰` 창이 안 뜸 | iPhone 잠금 해제 후 재연결 |
| 권한 오류 | 관리자 권한으로 실행 |
| `libimobiledevice` 오류 | `pip install --upgrade pymobiledevice3` |
