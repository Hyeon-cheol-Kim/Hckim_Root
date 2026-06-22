# PAM4 Eye Diagram Converter — 작업 세션 로그

> 브랜치: `claude/eye-plot-code-0AmpR`
> 파일: `PAM4_eye_diagram_converter.py`

---

## 작업 이력

---

### [1] 초기 코드 저장 및 기능 추가
- 기존에 작성된 eye plot 코드를 git에 저장
- EOM_DB.csv → **EOM_DB.xlsx** (openpyxl) 형식으로 변경
  - 실행 시마다 새 탭(시트) 추가
  - 탭 이름: 실행 시각 타임스탬프 (`_RUN_TIMESTAMP`)

---

### [2] 이미지 내 Margin 출력 박스 개선
- Width / Height 를 각각 별도 줄로 출력
- 공백 최소화, 폰트 크기 확대 (fontsize=20)
- 박스 가로 폭 축소
- 레이블 변경: `High/Mid/Low` → `H / M / L`

---

### [3] 컬러맵 변경
- 기존: 다색 컬러맵
- 변경: **Blue → White → Red**
  - `error = 0` → Blue (`#0000FF`)
  - `error = 1` → White (`#FFFFFF`) ← 급격한 경계
  - `error = 63` → Red (`#FF0000`)
- 구현: `build_colormap()` 3-포인트 LinearSegmentedColormap

---

### [4] Margin 계산 로직 수정

#### 문제
- Middle eye height margin이 257.1 mV로 과대 계산
- 원인: 해당 region 내 전체 zero 개수를 사용 → 인접 Eye 경계 혼입

#### 수정 내용
1. **`_max_contiguous_zeros(row_data)`** 함수 신규 추가
   - 행에서 가장 긴 연속 0 런(length, start_idx, end_idx) 반환
2. **`find_mask_center()`** 수정
   - 전체 zero 합산 → **최장 연속 zero 런** 보유 행 기준으로 변경
3. **`_contiguous_cluster(values, target, step)`** 함수 신규 추가
   - `gap > 1.5 × step` 기준으로 클러스터 분리
   - target 포함 클러스터만 반환 (인접 Eye 경계 혼입 방지)
4. **`calc_mask_margin()`** 수정
   - Width: 기준행의 최장 연속 0 런 길이 사용
   - `cx_ref`: 기준 런의 중심 → Height 측정 열 기준
   - Height: `cx_ref` 열에서 `_contiguous_cluster()` 적용

#### 핵심 상수
| 상수 | 값 | 설명 |
|---|---|---|
| `MASK_HALF_W` | ±0.12 UI | 마름모 마스크 가로 반폭 |
| `MASK_HALF_H` | ±25 mV | 마름모 마스크 세로 반높이 |
| `gap threshold` | 1.5 × step | 클러스터 분리 임계값 |

---

### [5] 파일명 변경
- `eye_diagram_converter.py` → **`PAM4_eye_diagram_converter.py`**

---

### [6] DB 탭 이름 변경
- 기존: 실행 시각 타임스탬프 (`20250608_143000`)
- 변경: **변환 폴더명에서 `EOM_` / `EOM` 제거한 문자열**
  - 예: `EOM_20250601_TestA` → 탭 이름 `20250601_TestA`
  - Excel 시트명 최대 31자 자동 truncate

---

### [7] DB input_file 이름 수정
- 저장값에서 앞의 `Result_` 제거
  - 예: `Result_EOM_ABC_QC_Offsets` → `EOM_ABC_QC_Offsets`

---

### [8] DB datetime 형식 변경
- 기존: `20250608143000`
- 변경: `2025/06/08/14/30/00` (년/월/일/시/분/초)

---

### [9] EOM_DB.xlsx 탭 내 분포 차트 삽입
- 함수: **`_embed_sheet_chart(ws)`**
- 동작:
  - 변환 실행 후 해당 탭의 데이터 마지막 행 아래에 차트 자동 삽입
  - 새 데이터 추가 시 탭 전체 데이터로 차트 재생성 (누적)
- 차트 구성:
  - **2행 × 3열** = 6개 서브플롯 (Lane0/Lane1 × Upper/Middle/Lower)
  - X축: Width margin (UI), Y축: Height margin (mV), 둘 다 0부터 시작
  - **Fail 영역**: L자형 빨간색 30% 투명도
    - Width ≤ 0.24 UI **OR** Height ≤ 50 mV
  - Fail 경계선: 빨간 점선
  - 데이터 점 크기: `s=10` (지름 기준)
- 기술: `BytesIO` → `openpyxl.drawing.image.Image` → `ws.add_image()`

---

### [10] 코드 전체 한국어 주석 추가
- 모든 함수에 docstring 추가 (목적, 알고리즘, 인수, 반환값)
- 비직관적인 로직에 인라인 주석 추가
- 섹션 헤더 정리 (총 8개 섹션)

---

### [11] Block Diagram PDF 생성 (`block_diagram.pdf`)
- matplotlib으로 코드 구조 블록 다이어그램 생성
- 여러 차례 반복 개선:
  - 한글 폰트 적용 (NanumGothic)
  - 글씨 크기 2배 → 3배 확대
  - 박스 크기 텍스트에 자동 맞춤 (2-pass renderer 방식)
  - 가로형(landscape) 레이아웃으로 전환 (iPad 가독성 개선)
  - **최종**: A2 landscape (24×17인치), 폰트 18~36pt

#### 다이어그램 구성 (5개 Zone)
| Zone | 내용 |
|---|---|
| ① 진입점 | `__main__` → `run_interactive` / CLI 분기 |
| ② 파일 탐색 | `find_eom_folder`, `resolve_folder`, `find_txt_in_folder`, `find_lane_csvs`, `select_txt` |
| ③ 파이프라인 | `convert()` 전체 흐름 (parse → loop → plot → DB → chart) |
| ④ 알고리즘 | `_max_contiguous_zeros`, `find_mask_center`, `_contiguous_cluster`, `calc_mask_margin` |
| ⑤ 좌표·컬러 | `calc_x_coords`, `calc_y_coords`, `build_colormap` |

---

## 주요 함수 목록

| 함수 | 역할 |
|---|---|
| `parse_offsets_txt()` | QC_Offsets.txt 파싱 → 파라미터 dict |
| `parse_eye_csv()` | lane CSV 파싱 → (lane_name, x_idx, y_idx, data) |
| `calc_x_coords()` | 인덱스 → UI 좌표 |
| `calc_y_coords()` | 인덱스 → mV 좌표 |
| `_max_contiguous_zeros()` | 행의 최장 연속 0 런 탐색 |
| `find_mask_center()` | Eye 중심점 (cx, cy) 계산 |
| `_contiguous_cluster()` | gap 기준 클러스터 분리 |
| `calc_mask_margin()` | Width / Height margin 계산 |
| `build_colormap()` | Blue→White→Red 컬러맵 생성 |
| `draw_grid_lines()` | 격자선 그리기 |
| `draw_diamond_mask()` | 마름모 마스크 그리기 |
| `plot_eye_diagram()` | Eye Diagram 전체 플롯 |
| `_embed_sheet_chart()` | xlsx 탭에 분포 차트 삽입 |
| `append_to_db()` | EOM_DB.xlsx에 마진 데이터 기록 |
| `convert()` | 메인 변환 파이프라인 |
| `find_eom_folder()` | EOM_ 폴더 자동 탐색 |
| `find_txt_in_folder()` | QC_Offsets.txt 검색 |
| `find_lane_csvs()` | lane CSV 목록 수집 |
| `resolve_folder()` | 입력 경로 해석 |
| `select_txt()` | 복수 TXT 사용자 선택 |
| `run_interactive()` | 인터랙티브 CLI 실행 |

---

## 입출력 파일 구조

### 입력
```
*_QC_Offsets.txt   — TimingMaxSteps, TimingMaxOffset,
                     VoltageMaxSteps, VoltageMaxOffset
*_lane0.csv        — error count 행렬 (N×M)
*_lane1.csv        — error count 행렬 (N×M)
```

### 출력
```
PAM4_{BaseName}_{lane}.png   — Eye Diagram 이미지
EOM_DB.xlsx
  └── 탭: 폴더명(EOM_ 제거)
       ├── 헤더: datetime, input_file,
       │         lane0_up_w/h, lane0_mid_w/h, lane0_low_w/h,
       │         lane1_up_w/h, lane1_mid_w/h, lane1_low_w/h
       ├── 데이터 행: 변환 1회 = 1행
       └── 차트: 데이터 아래에 2×3 scatter 분포도
```

---

## Spec 기준

| 항목 | 기준값 |
|---|---|
| Width margin Fail | ≤ 0.24 UI |
| Height margin Fail | ≤ 50 mV |
| Upper Eye 범위 | voltage > 130 mV |
| Middle Eye 범위 | −130 ~ 130 mV |
| Lower Eye 범위 | voltage < −130 mV |
| 마름모 마스크 크기 | ±0.12 UI × ±25 mV |
