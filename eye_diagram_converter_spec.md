# Eye Diagram CSV → Image Converter 설계 명세서

> 이 문서만으로 `eye_diagram_converter.py` 를 처음부터 재구현할 수 있도록 작성되었습니다.

---

## 1. 개요

EOM(Eye Opening Monitor) 측정 장비가 출력하는 CSV 파일을 읽어  
Lane별 Eye Diagram 이미지(PNG)를 생성하고, 마진 값을 DB CSV에 누적 저장하는 도구.

### 핵심 기능
- `*_QC_Offsets.txt` 파라미터 파일 + `*_lane*.csv` 데이터 파일 → PNG 이미지
- Upper / Middle / Lower 3개 Eye의 Width · Height 마진 자동 계산
- 마름모(Diamond) 마스크 오버레이 표시
- 변환 결과를 `EOM_DB.csv` 에 한 줄로 누적 저장
- CLI 모드 / 인터랙티브 모드 지원

---

## 2. 의존성

```
python >= 3.8
numpy
matplotlib
```

표준 라이브러리: `csv`, `re`, `os`, `sys`, `datetime`

---

## 3. 입력 파일 형식

### 3-1. 파라미터 파일 (`*_QC_Offsets.txt`)

정규식 `{Key}\s*:\s*(\d+)` 로 파싱. 키 4개 필수:

```
TimingMaxSteps   : 63
TimingMaxOffset  : 40
VoltageMaxSteps  : 63
VoltageMaxOffset : 30
```

| 파라미터 | 의미 |
|---|---|
| `TimingMaxSteps` | X축 인덱스 최대값 (예: 63 → 인덱스 0~63) |
| `TimingMaxOffset` | X축 물리 범위의 절반 × 100 (예: 40 → ±0.40 UI) |
| `VoltageMaxSteps` | Y축 인덱스 최대값 |
| `VoltageMaxOffset` | Y축 물리 범위의 절반 ÷ 10 (예: 30 → ±300 mV) |

### 3-2. Eye 데이터 파일 (`*_lane0.csv`, `*_lane1.csv`, ...)

```
Lane0,-63,-62,-61,...,0,...,62,63     ← 헤더 행: 첫 셀=LaneName, 나머지=X 인덱스
-63,63,63,63,...,0,...,63,63          ← 데이터 행: 첫 셀=Y 인덱스, 나머지=Error Count
-62,63,63,...,0,0,...,63,63
...
63,63,63,...,63,63,...,63,63
```

- Error Count 범위: **0 ~ 63** (0 = error 없음, 63 = 최대 오류)
- 행 수 = Y 인덱스 개수, 열 수 = X 인덱스 개수 (일반적으로 127×127)
- Y 인덱스는 **내림차순** (양수 → 음수 방향)으로 저장됨

### 3-3. 파일 명명 규칙

```
{BaseName}_QC_Offsets.txt
{BaseName}_lane0.csv
{BaseName}_lane1.csv
```

`BaseName` 이 일치해야 자동 탐색됨.

---

## 4. 좌표 변환 공식

### X축 (Timing Offset, 단위: UI)
```
x_ui = index / TimingMaxSteps * TimingMaxOffset / 100
```
- 예: index=63, Steps=63, Offset=40 → x = 1.0 × 0.40 = **0.40 UI**
- 범위: `-TimingMaxOffset/100` ~ `+TimingMaxOffset/100`

### Y축 (Voltage Level, 단위: mV)
```
y_mv = index / VoltageMaxSteps * VoltageMaxOffset * 10
```
- `VoltageMaxOffset × 10` = 실제 최대 mV
- 예: index=63, Steps=63, Offset=30 → y = 1.0 × 300 = **300 mV**
- 범위: `-VoltageMaxOffset×10` ~ `+VoltageMaxOffset×10`

---

## 5. 마스크 영역 정의

Eye Diagram 은 전압 범위에 따라 3개 Eye로 나뉨:

```python
MASK_REGIONS = [
    ('Upper',   130.0,   9999.0,  fallback_cx=0.0,  fallback_cy= 200.0),
    ('Middle', -130.0,    130.0,  fallback_cx=0.0,  fallback_cy=   0.0),
    ('Lower',  -9999.0, -130.0,  fallback_cx=0.0,  fallback_cy=-200.0),
]
```

마스크 고정 크기:
```python
MASK_HALF_W = 0.12   # ± 0.12 UI (가로 절반)
MASK_HALF_H = 25.0   # ± 25 mV  (세로 절반)
```

---

## 6. 마스크 중심점 계산 알고리즘

### 6-1. `_max_contiguous_zeros(row_data)` → `(length, start_idx, end_idx)`

한 행(1D 배열)에서 **연속된 0의 최장 구간** 탐색:

```
1. is_zero = (row_data == 0) 를 0/1 배열로 변환
2. 앞뒤에 0을 padding: [0, is_zero..., 0]
3. np.diff() 로 변화 지점 감지
   - diff == +1 → run 시작
   - diff == -1 → run 종료
4. 가장 긴 run의 (길이, 시작인덱스, 끝인덱스) 반환
   - 인덱스는 원본 row_data 기준
```

### 6-2. `find_mask_center(data, x_coords, y_coords, y_min_mv, y_max_mv)` → `(cx, cy)`

```
1. y_min_mv ~ y_max_mv 범위의 행(row)들 추출
2. 각 행에서 _max_contiguous_zeros() 로 최장 연속 0 길이 계산
3. 최장 길이가 가장 큰 행(들) 선택
   - 동점 행이 여러 개면 중간(median) 행 사용
4. cy = 선택된 행의 y 좌표 (mV)
5. cx = 선택된 행의 최장 연속 0 구간의 (x_start + x_end) / 2 (UI)
6. 해당 범위에 0이 없으면 (None, None) 반환
```

---

## 7. 마진 계산 알고리즘

### 7-1. `_contiguous_cluster(values, target, step)` → `ndarray | None`

1D 좌표 배열에서 `target` 을 포함하는 연속 클러스터 반환:

```
1. values 를 오름차순 정렬
2. 인접 값 간격(gap) 계산: np.diff(sorted_values)
3. gap > step × 1.5 인 지점을 클러스터 경계로 분리
   - 인접한 두 값이 1.5 step 이상 떨어져 있으면 별도 클러스터
4. target 이 포함된 클러스터(c.min <= target <= c.max) 반환
5. 포함 클러스터 없으면 target 에 가장 가까운 클러스터 반환
```

> **임계값 1.5 × step 의 의미**: 인접 데이터 포인트 1개가 non-zero 여도 클러스터가 분리됨.  
> `2 × step` 이상으로 설정하면 1개 non-zero 행이 끼어 있어도 하나의 클러스터로 병합되어 마진이 과대 계산됨.

### 7-2. `calc_mask_margin(data, x_coords, y_coords, cx, cy, y_min_mv, y_max_mv)` → `(width_ui, height_mv)`

```
[Width 계산]
1. y_min_mv ~ y_max_mv 범위 내에서 최장 연속 0 행(ref_row) 탐색
   (find_mask_center 와 동일한 기준 — 독립적으로 재계산)
2. ref_row 에서 _max_contiguous_zeros() 로 최장 연속 0 구간 (s, e) 획득
3. width_ui  = x_coords[e] - x_coords[s]
4. cx_ref    = (x_coords[s] + x_coords[e]) / 2

[Height 계산]
5. cx_ref 에 가장 가까운 열(col_idx) 선택
6. 해당 열에서 y_min_mv ~ y_max_mv 범위 내의 0인 y 좌표 목록 추출
7. _contiguous_cluster(col_zeros_y, cy, step_y) 로
   cy 를 포함하는 연속 클러스터 선택
8. height_mv = cluster.max() - cluster.min()
```

> **핵심 원칙**: Width 의 기준 행(ref_row) 중앙(cx_ref)을 Height 측정 기준 열로 사용.  
> cx_ref 는 `find_mask_center` 의 cx 와 다를 수 있으며, `calc_mask_margin` 내부에서 재계산됨.

---

## 8. 시각화 명세

### 8-1. 컬러맵

| Error Count | 색상 |
|---|---|
| 0 | `#0000FF` (파란색) |
| 1 | `#FFFFFF` (흰색) — 0→1 사이 급전환 |
| 63 | `#FF0000` (빨간색) |

```python
LinearSegmentedColormap.from_list('eye', [
    (0.0,   '#0000FF'),
    (1/63,  '#FFFFFF'),
    (1.0,   '#FF0000'),
])
Normalize(vmin=0, vmax=63)
```

### 8-2. 히트맵

- `ax.imshow()` 사용
- `origin='upper'`: 양수 Y(mV)가 위, 음수가 아래
- `interpolation='nearest'`: 보간 없음 (원본 셀 그대로 표시)
- `aspect='auto'`: 축 비율 자동
- `extent`: 각 셀의 중심이 아닌 **셀 경계** 기준으로 설정
  ```python
  dx = step_x / 2
  dy = step_y / 2
  extent = [x_min - dx, x_max + dx, y_min - dy, y_max + dy]
  ```

### 8-3. 셀 구분선

- 각 셀 경계에 흰색 격자선 추가
- `LineCollection` 사용: `color='#ffffff'`, `linewidth=0.5`, `alpha=0.5`
- X 경계선: 인접 셀 중간 + 양끝 확장
- Y 경계선: 인접 셀 중간 + 양끝 확장

### 8-4. 마름모 마스크

```
꼭짓점 4개 (cx, cy 기준):
  상단: (cx,          cy + MASK_HALF_H)
  우측: (cx + MASK_HALF_W, cy)
  하단: (cx,          cy - MASK_HALF_H)
  좌측: (cx - MASK_HALF_W, cy)
```
- `facecolor='yellow'`, `alpha=0.4`, `edgecolor='none'`
- 중심에 `+` 마커: `markersize=7`, `markeredgewidth=1.2`

### 8-5. 축 설정

| 항목 | 설정 |
|---|---|
| X축 간격 | 0.04 UI |
| X축 레이블 | 소수점 2자리 (`{v:.2f}`) |
| X축 레이블 회전 | 90° |
| Y축 간격 | 20 mV |
| Y축 레이블 | 정수 |
| 배경색 | `#0d0d0d` |
| 수평/수직 기준선 | 흰색 점선 (`lw=0.8`, `ls='--'`, `alpha=0.5`) |

### 8-6. 마진 정보 박스 (우상단)

```
위치: ax.transAxes 기준 (0.99, 0.99), va='top', ha='right'
폰트: monospace, size=20, color='yellow'
bbox: square, pad=0.2, fc='#1a1a1a', alpha=0.88, ec='yellow'

표시 형식 (Upper=H, Middle=M, Lower=L):
[H]W:0.320UI
   H:120.0mV
[M]W:0.410UI
   H: 95.0mV
[L]W:0.300UI
   H:110.0mV
```

### 8-7. 파라미터 정보 박스 (좌하단)

```
위치: ax.transAxes 기준 (0.01, 0.01), va='bottom'
폰트: size=7, color='#aaaaaa'
bbox: round, pad=0.3, fc='#1a1a1a', alpha=0.75, ec='#444444'

표시 내용:
TimingOffset={val}  Step={val}  →  {x:.5f} UI/step
VoltageOffset={val} (×10={val} mV)  Step={val}  →  {y:.4f} mV/step
```

### 8-8. 컬러바

- 우측에 세로 배치: `fraction=0.046`, `pad=0.04`
- 레이블: `'Error Count (Max 63)'`, 세로 방향, 흰색
- 틱: `[0, 10, 20, 30, 40, 50, 60]`, 흰색 레이블
- 테두리: `#555555`

### 8-9. 이미지 저장

```python
fig.set_facecolor('#0d0d0d')
figsize = (10, 9)
dpi = 150
bbox_inches = 'tight'
출력파일명: {BaseName}_{LaneName}.png
```

---

## 9. DB 저장 (`EOM_DB.csv`)

변환 완료 시 `os.getcwd()/EOM_DB.csv` 에 **1줄** 추가 (파일 없으면 생성 + 헤더 자동 추가).

### 컬럼 순서

```
datetime, input_file,
{lane0}_up_w(UI), {lane0}_up_h(mV), {lane0}_mid_w(UI), {lane0}_mid_h(mV), {lane0}_low_w(UI), {lane0}_low_h(mV),
{lane1}_up_w(UI), {lane1}_up_h(mV), {lane1}_mid_w(UI), {lane1}_mid_h(mV), {lane1}_low_w(UI), {lane1}_low_h(mV)
```

### 예시

```
datetime,input_file,Lane0_up_w(UI),Lane0_up_h(mV),Lane0_mid_w(UI),...
20260601153045,EOM_ABC,0.3200,120.00,0.4100,95.00,0.3000,110.00,...
```

- `datetime` 형식: `YYYYMMDDHHmmss`
- Width: 소수점 4자리 (`{:.4f}`)
- Height: 소수점 2자리 (`{:.2f}`)
- Lane 컬럼명: CSV 헤더 첫 셀(`LaneName`)에서 동적으로 생성

---

## 10. 함수 목록 및 역할

| 함수 | 역할 |
|---|---|
| `parse_offsets_txt(txt_path)` | `*_QC_Offsets.txt` → `dict` 파라미터 파싱 |
| `parse_eye_csv(csv_path)` | `*_lane*.csv` → `(lane_name, x_idx[], y_idx[], data[N,M])` |
| `calc_x_coords(x_indices, params)` | X 인덱스 → UI 좌표 배열 |
| `calc_y_coords(y_indices, params)` | Y 인덱스 → mV 좌표 배열 |
| `_max_contiguous_zeros(row_data)` | 한 행에서 최장 연속 0 구간 `(length, start, end)` 반환 |
| `find_mask_center(data, x, y, y_min, y_max)` | Eye 영역에서 마스크 중심 `(cx, cy)` 탐색 |
| `_contiguous_cluster(values, target, step)` | 1D 배열에서 target 포함 연속 클러스터 반환 |
| `calc_mask_margin(data, x, y, cx, cy, y_min, y_max)` | `(width_ui, height_mv)` 계산 |
| `build_colormap()` | Blue→White→Red 컬러맵 생성 |
| `draw_grid_lines(ax, x, y)` | 셀 경계 격자선 그리기 |
| `draw_diamond_mask(ax, cx, cy, hw, hh)` | 마름모 마스크 + 중심 마커 그리기 |
| `plot_eye_diagram(ax, data, x, y, lane, params)` | Eye diagram 1개 완전히 그리기 → `mask_info_list` 반환 |
| `append_to_db(base_name, all_lane_margins)` | `EOM_DB.csv` 에 결과 1줄 추가 |
| `convert(txt_path, csv_paths, out_dir, dpi)` | 파싱 → 플롯 → 저장 → DB 기록 전체 흐름 |
| `find_eom_folder(base_dir)` | `EOM_*` 폴더 자동 탐색 |
| `find_txt_in_folder(folder)` | 폴더 내 `*_QC_Offsets.txt` 목록 반환 |
| `find_lane_csvs(txt_path)` | txt 와 같은 폴더의 `*_lane*.csv` 목록 반환 |
| `resolve_folder(raw)` | 사용자 입력 문자열 → 유효한 폴더 경로 반환 |
| `select_txt(txt_list)` | txt 파일 목록에서 1개 선택 (1개면 자동) |
| `run_interactive()` | 인터랙티브 루프 실행 |

---

## 11. 실행 방법

### CLI 모드

```bash
# 폴더 지정 (내부의 모든 세트 자동 변환)
python eye_diagram_converter.py /path/to/EOM_folder

# CSV 직접 지정
python eye_diagram_converter.py file_QC_Offsets.txt lane0.csv lane1.csv

# 도움말
python eye_diagram_converter.py --help
```

### 인터랙티브 모드

```bash
python eye_diagram_converter.py
```

실행 후 프롬프트:
```
폴더 / QC_Offsets.txt 경로 (Enter=자동):
```
- **Enter**: 현재 폴더의 `EOM_*` 하위 폴더 자동 탐색
- **폴더 경로 입력**: 해당 폴더에서 `*_QC_Offsets.txt` 자동 탐색
- 여러 세트 발견 시 번호 선택 / `a` 입력 시 전체 변환
- 변환 완료 후 다른 폴더 계속 변환 여부 질문

### 폴더 자동 탐색 우선순위

```
1. 인수로 전달된 경로
2. 인수 없음 → 현재 디렉토리(cwd)에서 EOM_* 폴더 탐색
3. EOM_* 폴더가 1개면 자동 선택, 여러 개면 번호 선택
```

---

## 12. 출력 파일 구조

```
{입력폴더}/
├── {BaseName}_Lane0.png       ← Lane0 Eye Diagram 이미지
├── {BaseName}_Lane1.png       ← Lane1 Eye Diagram 이미지
└── (기타 입력 파일들)

{현재 실행 경로(cwd)}/
└── EOM_DB.csv                 ← 마진 DB (누적 추가)
```

---

## 13. 상수 / 조정 가능한 설정값

```python
# 마스크 고정 크기
MASK_HALF_W = 0.12    # UI  (마름모 가로 절반)
MASK_HALF_H = 25.0    # mV  (마름모 세로 절반)

# Eye 영역 경계 전압 (mV)
Upper  영역: voltage > 130 mV
Middle 영역: -130 mV ~ 130 mV
Lower  영역: voltage < -130 mV

# 이미지 저장 DPI
dpi = 150

# 컬러맵 Error Count 최대값
vmax = 63

# 클러스터 분리 임계값
gap_threshold = step × 1.5   (_contiguous_cluster 내부)
```
