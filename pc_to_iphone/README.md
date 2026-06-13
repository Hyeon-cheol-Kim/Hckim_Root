# PC → iPhone USB 파일 전송기

USB로 연결된 iPhone에 PC의 파일을 전송하는 데스크톱 GUI 프로그램입니다.  
전송된 파일은 iPhone 내부 저장소의 **`내다운로드/`** 폴더에 저장됩니다.

---

## 지원 파일 형식

`.txt` · `.pdf` · `.html` · `.py` · `.c` · `.cpp` · `.java` · `.bat` · `.sh`

---

## 설치 및 실행

### 1. 환경 요구사항

| 항목 | 내용 |
|------|------|
| OS | Windows 10/11 (macOS·Linux도 지원) |
| Python | 3.9 이상 |
| iTunes / Apple 드라이버 | Windows에서 필수 (Microsoft Store 버전 사용 시 별도 드라이버 필요) |

> **Windows iTunes 설치 방법**  
> Microsoft Store 버전이 아닌 [Apple 공식 사이트](https://www.apple.com/itunes/)에서 직접 설치를 권장합니다.

### 2. 의존성 설치

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
| 연결 안 됨 | iTunes 재설치, USB 케이블 교체 |
| `신뢰` 창이 안 뜸 | iPhone 잠금 해제 후 재연결 |
| 권한 오류 | 관리자 권한으로 실행 (`python main.py` → 터미널을 관리자로 열기) |
| `libimobiledevice` 오류 | `pip install --upgrade pymobiledevice3` |
