# 대화 로그 — eom_final_package_parser

> 이 파일은 Claude와의 작업 대화를 요약한 기록입니다. 작업이 진행될 때마다 업데이트됩니다.

---

## 2026-06-22

### 1. `eom_final_package_parser.py` 최초 등록

**내용:** 사용자가 EOM(Eye Opening Monitor) 로그 파일을 파싱하는 Python 스크립트를 제공.

**스크립트 주요 기능:**
- `ensure_utf8_encoding()` — `chardet`로 파일 인코딩 감지, UTF-8이 아닌 경우 변환 후 원본을 `.bak`으로 백업
- `parse_eom_final_package()` — EOM 로그에서 lane별 timing/voltage sweep 데이터 추출
  - `TimingMaxSteps / Offset`, `VoltageMaxSteps / Offset` 헤더 파싱
  - `lane / timing / voltage / error_cnt` 데이터 수집, 중복 키는 "63이 아닌 최솟값 우선" 병합
  - `Result_<파일명>_QC_Offsets.txt` 생성 (lane 구성 + 파라미터)
  - `Result_<파일명>_lane{N}.csv` 생성 (T×V 그리드, voltage 내림차순, 미탐지 셀은 63)
- `__main__` — 단일 파일 인자 또는 `EOM*` 폴더 자동 탐색 모드

**커밋:** `9c31f92` — Add EOM final package parser script

---

### 2. 코드 리뷰 및 버그 수정

**발견된 문제 4건:**

| # | 위치 | 문제 | 수정 |
|---|------|------|------|
| 1 | `ensure_utf8_encoding` | `chardet`가 `None` 반환 시 `decode(None)` → `TypeError`. `except`에 잡혀 파일이 조용히 스킵됨 | `encoding is None` 명시적 체크 후 명확한 에러 메시지 출력 |
| 2 | `ensure_utf8_encoding` | BOM 있는 UTF-8(`utf-8-sig`)을 변환 대상으로 오분류 → 불필요한 `.bak` 생성 | 허용 목록에 `'utf-8-sig'` 추가 |
| 3 | `parse_eom_final_package` | 파일명만 전달 시 `os.path.dirname` → `''` → 출력 파일이 예상치 못한 경로에 생성될 수 있음 | `os.path.abspath` 적용 |
| 4 | `parse_eom_final_package` | `existing_lanes`를 `with` 블록 안에서 정의하고 블록 밖에서 사용 (스타일 문제) | `with` 블록 앞으로 이동 |

**커밋:** `2905521` — Fix encoding detection edge cases and base_dir resolution

---

### 3. 파일 탐색 패턴 수정

**요청:** 파일 탐색을 `EOM`으로 시작하는 폴더 내에서만 수행하도록 변경.

**변경 내용:**
- 폴더 탐색: `glob.glob('EOM_*')` → `glob.glob('EOM*')`
- 폴더 내 파일 탐색: `glob.glob(folder, 'EOM_*')` → `glob.glob(folder, 'EOM*')`
- 안내 메시지: `'EOM_'로 시작하는` → `'EOM'으로 시작하는`

**커밋:** `cae6e02` — Broaden EOM folder/file search pattern from EOM_ to EOM prefix

---
