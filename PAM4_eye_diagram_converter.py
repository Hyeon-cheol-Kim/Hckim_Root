"""
Eye Diagram CSV → Image Converter
==================================
입력 파일 규칙:
  - *_QC_Offsets.txt : 파라미터 파일 (TimingMaxSteps, TimingMaxOffset, VoltageMaxSteps, VoltageMaxOffset)
  - *_lane0.csv      : Lane0 eye diagram 데이터 (127x127 or N x M, 헤더 포함)
  - *_lane1.csv      : Lane1 eye diagram 데이터

축 계산:
  X (UI)  = index / TimingMaxSteps  * TimingMaxOffset / 100
  Y (mV)  = index / VoltageMaxSteps * VoltageMaxOffset * 10

마스크:
  - 마름모 형태, 크기 ±0.12 UI × ±25 mV
  - Upper  : voltage >  130 mV 영역에서 0값 가장 많은 행의 중앙
  - Middle : -130 ~ 130 mV 영역에서 0값 가장 많은 행의 중앙
  - Lower  : voltage < -130 mV 영역에서 0값 가장 많은 행의 중앙

사용법 (CLI):
  python eye_diagram_converter.py <QC_Offsets.txt> [lane0.csv] [lane1.csv] ...

사용법 (인터랙티브):
  python eye_diagram_converter.py
"""

# ── 표준 라이브러리 ────────────────────────────────────────────────
import csv                          # CSV 파일 읽기/쓰기
import re                           # 정규식 파싱
import os                           # 파일/폴더 경로 처리
import sys                          # 명령줄 인수(argv) 처리
import numpy as np                  # 행렬 연산
from datetime import datetime       # 타임스탬프 생성

# ── 시각화 라이브러리 ──────────────────────────────────────────────
import matplotlib.pyplot as plt
import matplotlib.colors as mcolors
from matplotlib.collections import LineCollection   # 격자선 일괄 그리기
from matplotlib.patches import Polygon              # 마름모 마스크

# ── xlsx 저장 라이브러리 (선택적) ─────────────────────────────────
# openpyxl 이 설치되어 있으면 xlsx, 없으면 csv 로 폴백
try:
    import openpyxl
    from openpyxl.styles import Font, PatternFill, Alignment
    _XLSX_AVAILABLE = True
except ImportError:
    _XLSX_AVAILABLE = False

# 스크립트가 시작된 시각 → xlsx 시트 이름으로 사용
# 한 번 실행에서 여러 세트를 변환해도 같은 시트에 행이 누적됨
_RUN_TIMESTAMP = datetime.now().strftime('%Y%m%d_%H%M%S')


# ─────────────────────────────────────────────────────────────────
# 1. 파일 파싱
# ─────────────────────────────────────────────────────────────────

def parse_offsets_txt(txt_path: str) -> dict:
    """
    QC_Offsets.txt 에서 측정 파라미터 4개를 파싱하여 dict 로 반환.

    파일 형식 예시:
        TimingMaxSteps   : 63
        TimingMaxOffset  : 40
        VoltageMaxSteps  : 63
        VoltageMaxOffset : 30

    반환 예시:
        {'TimingMaxSteps': 63, 'TimingMaxOffset': 40,
         'VoltageMaxSteps': 63, 'VoltageMaxOffset': 30}
    """
    with open(txt_path, 'r') as f:
        content = f.read()

    params = {}
    for key in ['TimingMaxSteps', 'TimingMaxOffset',
                'VoltageMaxSteps', 'VoltageMaxOffset']:
        # 정규식: "키 : 숫자" 패턴에서 숫자만 추출 (\s* 로 공백 허용)
        m = re.search(rf'{key}\s*:\s*(\d+)', content)
        if m:
            params[key] = int(m.group(1))
    return params


def parse_eye_csv(csv_path: str):
    """
    Eye diagram CSV 파일을 파싱하여 데이터 행렬 반환.

    CSV 파일 구조:
        첫 행  : LaneName, x_idx_0, x_idx_1, ..., x_idx_N   (헤더)
        이후 행: y_idx,    val_0,   val_1,   ..., val_N      (데이터)
        - val 범위: 0(오류 없음) ~ 63(최대 오류)

    반환값:
        lane_name  : 레인 이름 문자열 (예: "Lane0")
        x_indices  : X 인덱스 정수 리스트
        y_indices  : Y 인덱스 정수 리스트 (내림차순, 양수→음수)
        data       : shape=(n_y, n_x) float64 배열, 각 셀의 error count
    """
    with open(csv_path, newline='', encoding='utf-8') as f:
        rows = list(csv.reader(f))

    # 헤더 행 분리: 첫 셀=레인명, 나머지=X 인덱스
    header    = rows[0]
    lane_name = header[0]
    x_indices = [int(v) for v in header[1:]]

    # 데이터 행 파싱: 첫 셀=Y 인덱스, 나머지=error count
    y_indices, data_rows = [], []
    for row in rows[1:]:
        if not row:          # 빈 행 건너뜀
            continue
        y_indices.append(int(row[0]))
        data_rows.append([int(v) for v in row[1:]])

    # 리스트 → 2D numpy 배열 (float 으로 변환해야 imshow에서 정규화 가능)
    return lane_name, x_indices, y_indices, np.array(data_rows, dtype=float)


# ─────────────────────────────────────────────────────────────────
# 2. 좌표 변환
# ─────────────────────────────────────────────────────────────────

def calc_x_coords(x_indices: list, params: dict) -> np.ndarray:
    """
    X 인덱스 배열을 실제 Timing Offset (UI 단위) 좌표로 변환.

    공식: x_ui = index / TimingMaxSteps * TimingMaxOffset / 100
    예시: index=63, Steps=63, Offset=40 → 1.0 × 0.40 = 0.40 UI
    범위: -TimingMaxOffset/100 ~ +TimingMaxOffset/100
    """
    return np.array([
        i / params['TimingMaxSteps'] * params['TimingMaxOffset'] / 100
        for i in x_indices
    ])


def calc_y_coords(y_indices: list, params: dict) -> np.ndarray:
    """
    Y 인덱스 배열을 실제 Voltage Level (mV 단위) 좌표로 변환.

    공식: y_mv = index / VoltageMaxSteps * VoltageMaxOffset * 10
    VoltageMaxOffset × 10 = 실제 최대 mV 값
    예시: index=63, Steps=63, Offset=30 → 1.0 × 300 = 300 mV
    범위: -VoltageMaxOffset×10 ~ +VoltageMaxOffset×10
    """
    v_mv = params['VoltageMaxOffset'] * 10   # 실제 전압 범위 최대값 (mV)
    return np.array([
        i / params['VoltageMaxSteps'] * v_mv
        for i in y_indices
    ])


# ─────────────────────────────────────────────────────────────────
# 3. 마스크 중심점 및 마진 계산
# ─────────────────────────────────────────────────────────────────

def _max_contiguous_zeros(row_data: np.ndarray):
    """
    1D 배열(한 행)에서 연속된 0의 최장 구간을 찾아 반환.

    알고리즘:
        1. 0 위치를 0/1 배열로 변환
        2. 앞뒤에 0 패딩 후 np.diff() 로 run 시작/종료 지점 감지
           - diff == +1: 연속 구간 시작
           - diff == -1: 연속 구간 종료
        3. 가장 긴 구간의 (길이, 시작인덱스, 끝인덱스) 반환

    반환값:
        (max_length, start_idx, end_idx)
        - 0이 없으면 (0, -1, -1) 반환
        - 인덱스는 원본 row_data 기준 (0-based)
    """
    # 0인 위치를 1, 나머지를 0으로 변환
    is_zero = (row_data == 0).astype(int)

    # 앞뒤에 0 추가 → 배열 시작/끝에서의 run도 감지 가능하게 함
    padded = np.concatenate([[0], is_zero, [0]])

    # 인접 값의 차이: +1이면 0-run 시작, -1이면 0-run 종료
    diff   = np.diff(padded)
    starts = np.where(diff == 1)[0]    # 각 연속 구간의 시작 인덱스
    ends   = np.where(diff == -1)[0]   # 각 연속 구간의 종료 인덱스(exclusive)

    if len(starts) == 0:
        return 0, -1, -1   # 0이 한 개도 없는 경우

    lengths  = ends - starts                   # 각 구간의 길이
    best_idx = int(np.argmax(lengths))         # 가장 긴 구간의 인덱스
    return (
        int(lengths[best_idx]),
        int(starts[best_idx]),                 # 시작 인덱스 (원본 배열 기준)
        int(ends[best_idx] - 1)                # 끝 인덱스 (inclusive, 원본 배열 기준)
    )


def find_mask_center(data: np.ndarray,
                     x_coords: np.ndarray,
                     y_coords: np.ndarray,
                     y_min_mv: float,
                     y_max_mv: float):
    """
    지정된 voltage 범위(y_min_mv ~ y_max_mv) 안에서 Eye 중심점을 탐색.

    알고리즘:
        1. 해당 voltage 범위에 속하는 행들만 추출
        2. 각 행에서 _max_contiguous_zeros() 로 최장 연속 0 길이 계산
        3. 최장 길이가 가장 큰 행 선택 (동점 시 중간 행 사용)
        4. cy = 선택된 행의 voltage (mV)
        5. cx = 선택된 행의 최장 연속 0 구간 중앙 x (UI)

    반환값:
        (cx, cy) : Eye 중심 좌표 (UI, mV)
        해당 범위에 0이 없으면 (None, None) 반환
    """
    # 지정 전압 범위의 행 인덱스 추출
    row_mask = (y_coords >= y_min_mv) & (y_coords <= y_max_mv)
    if not np.any(row_mask):
        return None, None   # 해당 범위에 행이 없는 경우

    sub_idx = np.where(row_mask)[0]

    # 각 행의 최장 연속 0 길이 계산
    runs    = [_max_contiguous_zeros(data[r, :])[0] for r in sub_idx]
    max_run = max(runs)
    if max_run == 0:
        return None, None   # 모든 행에 0이 없는 경우

    # 최장 연속 0을 가진 행(들) 중 중간 행 선택
    best_rows = sub_idx[np.array(runs) == max_run]
    mid_row   = best_rows[len(best_rows) // 2]
    cy        = float(y_coords[mid_row])   # 해당 행의 전압값

    # 선택된 행의 최장 연속 0 구간 시작/끝 인덱스 → 중앙 x 좌표 계산
    _, s, e = _max_contiguous_zeros(data[mid_row, :])
    cx = float((x_coords[s] + x_coords[e]) / 2.0)
    return cx, cy


def _contiguous_cluster(values: np.ndarray, target: float, step: float):
    """
    1D 좌표 배열에서 target 값을 포함하는 연속 클러스터를 찾아 반환.

    클러스터 분리 기준:
        인접한 두 값의 간격이 step × 1.5 초과이면 별도 클러스터로 판단.
        (1.5 × step → 데이터 포인트 1개가 non-zero여도 클러스터 분리됨)
        ※ 2.0 × step 으로 설정하면 1개 non-zero 간격(= 2×step)이
          경계로 인식되지 않아 인접 Eye 영역까지 포함되는 오류 발생

    반환값:
        target 을 포함하는 클러스터 배열
        포함 클러스터가 없으면 target 에 가장 가까운 클러스터 반환
        values 가 비어 있으면 None 반환
    """
    if len(values) == 0:
        return None

    sorted_v = np.sort(values)   # 오름차순 정렬

    # 값이 1개인 경우: target과 1 step 이내면 해당 값 반환
    if len(sorted_v) == 1:
        return sorted_v if abs(sorted_v[0] - target) <= step else None

    # 인접 값 간격 계산 후 클러스터 분리
    gaps      = np.diff(sorted_v)
    split_pts = np.where(gaps > step * 1.5)[0] + 1   # 분리 지점 인덱스
    clusters  = np.split(sorted_v, split_pts)

    # target 이 포함된 클러스터 탐색 (min <= target <= max)
    for c in clusters:
        if c.min() <= target <= c.max():
            return c

    # target 이 어느 클러스터에도 포함되지 않으면 가장 가까운 클러스터 반환
    closest = min(clusters, key=lambda c: min(abs(c - target)))
    return closest


def calc_mask_margin(data: np.ndarray,
                     x_coords: np.ndarray,
                     y_coords: np.ndarray,
                     cx: float, cy: float,
                     y_min_mv: float, y_max_mv: float):
    """
    Eye 영역의 Width / Height 마진을 계산.

    계산 순서:
        [Width]
        1. y_min_mv ~ y_max_mv 범위에서 최장 연속 0 행(ref_row) 탐색
           (find_mask_center 와 동일 기준, 독립적으로 재계산)
        2. ref_row 의 최장 연속 0 구간 (s, e) 추출
        3. width_ui = x_coords[e] - x_coords[s]
        4. cx_ref   = (x_coords[s] + x_coords[e]) / 2

        [Height]
        5. cx_ref 에 가장 가까운 열(col_idx) 선택
        6. 해당 열에서 y_min_mv ~ y_max_mv 범위 내의 0값 y 좌표 추출
        7. _contiguous_cluster() 로 cy 포함 연속 클러스터 탐색
        8. height_mv = cluster.max() - cluster.min()

    ※ Width 의 기준 행 중앙(cx_ref)을 Height 측정 기준 열로 사용하는 이유:
       Width 가 가장 넓은 지점의 수직 방향 마진이 실제 Eye 개구부 높이에 해당함

    반환값:
        (width_ui, height_mv) : 단위 각각 UI, mV
    """
    x_arr  = np.array(x_coords)
    y_arr  = np.array(y_coords)
    # 인접 데이터 포인트 간격 (클러스터 분리 임계값 계산에 사용)
    step_x = float(abs(x_arr[1] - x_arr[0])) if len(x_arr) > 1 else 1.0
    step_y = float(abs(y_arr[1] - y_arr[0])) if len(y_arr) > 1 else 1.0

    # ── Width 기준 행 탐색 ───────────────────────────────────────
    # 해당 Eye 영역에서 연속 0의 최대 길이가 가장 긴 행을 기준으로 삼음
    row_mask = (y_arr >= y_min_mv) & (y_arr <= y_max_mv)
    sub_idx  = np.where(row_mask)[0]
    if len(sub_idx) == 0:
        return 0.0, 0.0   # 해당 전압 범위에 데이터 없음

    runs    = [_max_contiguous_zeros(data[r, :])[0] for r in sub_idx]
    max_run = max(runs)
    if max_run == 0:
        return 0.0, 0.0   # 해당 범위에 0이 없음 (Eye 개구부 없음)

    # 동점 행이 여러 개면 중간 행 선택
    best_rows = sub_idx[np.array(runs) == max_run]
    ref_row   = best_rows[len(best_rows) // 2]

    # ── Width 계산 ───────────────────────────────────────────────
    # 기준 행의 최장 연속 0 구간 → 시작(s)·끝(e) 인덱스
    _, s, e  = _max_contiguous_zeros(data[ref_row, :])
    width_ui = float(x_arr[e] - x_arr[s])          # UI 단위 가로 마진
    cx_ref   = float((x_arr[s] + x_arr[e]) / 2)    # 해당 구간의 중앙 x 좌표

    # ── Height 계산 ──────────────────────────────────────────────
    # cx_ref 에 가장 가까운 열에서 세로 방향 연속 0값 범위를 구함
    col_idx     = int(np.argmin(np.abs(x_arr - cx_ref)))
    region_mask = (y_arr >= y_min_mv) & (y_arr <= y_max_mv)

    # 해당 열·영역 내에서 0인 y 좌표만 추출
    col_zeros_y = y_arr[(data[:, col_idx] == 0) & region_mask]

    # cy 를 포함하는 연속 클러스터로 한정 (인접 Eye 영역의 0값 제외)
    cluster_y = _contiguous_cluster(col_zeros_y, cy, step_y)
    if cluster_y is not None and len(cluster_y) >= 2:
        height_mv = float(cluster_y.max() - cluster_y.min())
    elif cluster_y is not None:
        height_mv = step_y   # 클러스터에 값이 1개뿐인 경우 → 1 step 크기로 처리
    else:
        height_mv = 0.0

    return width_ui, height_mv


# ─────────────────────────────────────────────────────────────────
# 4. 그리기 유틸
# ─────────────────────────────────────────────────────────────────

def build_colormap():
    """
    Error Count 값에 따른 컬러맵 생성.

        0      → 파란색 (#0000FF) : error 없음, Eye 개구부
        1      → 흰색   (#FFFFFF) : error 시작 (0→1 급전환)
        2~63   → 흰색~빨간색 그라데이션
        63     → 빨간색 (#FF0000) : 최대 error

    0과 1 사이를 1/63 위치에서 급전환시켜 Eye 개구부(파란색)와
    error 영역(흰~빨간색)의 시각적 구분을 명확히 함.
    """
    return mcolors.LinearSegmentedColormap.from_list('eye', [
        (0.0,   '#0000FF'),   # error count = 0  : 파란색
        (1/63,  '#FFFFFF'),   # error count = 1  : 흰색 (급전환)
        (1.0,   '#FF0000'),   # error count = 63 : 빨간색
    ])


def draw_grid_lines(ax, x_coords: np.ndarray, y_coords: np.ndarray):
    """
    각 데이터 셀의 경계에 반투명 흰색 격자선을 그린다.

    경계선 위치:
        - 첫 셀 왼쪽/위쪽 + 마지막 셀 오른쪽/아래쪽 (half step 확장)
        - 인접 셀 중간 지점

    LineCollection 으로 한 번에 그려 성능 최적화.
    """
    # 각 축의 셀 절반 크기 (셀 경계 = 셀 중심 ± half step)
    dx = (x_coords[-1] - x_coords[0]) / (len(x_coords) - 1) / 2
    dy = (y_coords[0]  - y_coords[-1]) / (len(y_coords) - 1) / 2

    # X 경계: 왼쪽 확장 + 셀 사이 중간점 + 오른쪽 확장
    x_edges = (
        [x_coords[0] - dx]
        + [(x_coords[i] + x_coords[i + 1]) / 2 for i in range(len(x_coords) - 1)]
        + [x_coords[-1] + dx]
    )
    # Y 경계: 위쪽 확장 + 셀 사이 중간점 + 아래쪽 확장
    y_edges = (
        [y_coords[0] + dy]
        + [(y_coords[i] + y_coords[i + 1]) / 2 for i in range(len(y_coords) - 1)]
        + [y_coords[-1] - dy]
    )

    y_min, y_max = y_edges[-1], y_edges[0]
    x_min, x_max = x_edges[0],  x_edges[-1]

    # 수직선(X 경계) + 수평선(Y 경계) 세그먼트 목록 생성
    segments = (
        [[(x, y_min), (x, y_max)] for x in x_edges]     # 수직 경계선
        + [[(x_min, y), (x_max, y)] for y in y_edges]   # 수평 경계선
    )
    ax.add_collection(LineCollection(
        segments, colors='#ffffff', linewidths=0.5, alpha=0.5, zorder=2
    ))


def draw_diamond_mask(ax, cx: float, cy: float,
                      half_w: float, half_h: float,
                      color='yellow', alpha=0.4, zorder=5):
    """
    Eye 중심(cx, cy)에 마름모 형태의 마스크를 그린다.

    꼭짓점 4개 (시계 방향):
        상단 : (cx,          cy + half_h)
        우측 : (cx + half_w, cy)
        하단 : (cx,          cy - half_h)
        좌측 : (cx - half_w, cy)

    스타일:
        - 내부 채움: 노란색, 투명도 40%
        - 테두리: 없음 (edgecolor='none')
        - 중심 마커: '+' 기호
    """
    verts = np.array([
        [cx,           cy + half_h],   # 상단 꼭짓점
        [cx + half_w,  cy         ],   # 우측 꼭짓점
        [cx,           cy - half_h],   # 하단 꼭짓점
        [cx - half_w,  cy         ],   # 좌측 꼭짓점
    ])
    ax.add_patch(Polygon(verts, closed=True,
                         facecolor=color, alpha=alpha,
                         edgecolor='none', zorder=zorder))

    # 마스크 중심에 '+' 마커 표시
    ax.plot(cx, cy, '+', color=color, markersize=7,
            markeredgewidth=1.2, alpha=0.95, zorder=zorder + 1)


# ─────────────────────────────────────────────────────────────────
# 5. 메인 플롯
# ─────────────────────────────────────────────────────────────────

# ── 마스크 고정 크기 설정 ─────────────────────────────────────────
MASK_HALF_W = 0.12    # 마름모 가로 절반 크기 (단위: UI)
MASK_HALF_H = 25.0    # 마름모 세로 절반 크기 (단위: mV)

# ── Eye 영역 정의 ─────────────────────────────────────────────────
# 형식: (레이블, y_min(mV), y_max(mV), fallback_cx, fallback_cy)
# fallback_cx/cy: 해당 영역에 Eye가 없을 때 사용하는 기본 마스크 위치
MASK_REGIONS = [
    ('Upper',   130.0,   9999.0,  0.0,  200.0),   # 상단 Eye (130 mV 이상)
    ('Middle', -130.0,    130.0,  0.0,    0.0),   # 중간 Eye (-130 ~ 130 mV)
    ('Lower',  -9999.0, -130.0,  0.0, -200.0),   # 하단 Eye (-130 mV 이하)
]


def plot_eye_diagram(ax, data: np.ndarray,
                     x_coords: np.ndarray, y_coords: np.ndarray,
                     lane_name: str, params: dict):
    """
    단일 Lane 의 Eye Diagram 을 ax 에 완전히 그린다.

    그리는 순서:
        1. 히트맵 (error count → 색상)
        2. 셀 경계 격자선
        3. 3개 Eye 마스크 (Upper/Middle/Lower) + 마진 계산
        4. 컬러바
        5. 축 스타일 (배경색, 레이블, 눈금 간격)
        6. 마진 정보 박스 (우상단)
        7. 파라미터 정보 박스 (좌하단)

    반환값:
        mask_info_list : [(label, width_ui, height_mv), ...] × 3개 Eye
    """

    # ── 히트맵 ──────────────────────────────────────────────────
    cmap = build_colormap()
    norm = mcolors.Normalize(vmin=0, vmax=63)   # error count 0~63 정규화

    # 각 셀의 중심이 아닌 셀 경계를 extent 로 설정
    # → imshow 가 셀 중심을 좌표값으로 사용하므로 half step 확장 필요
    dx = (x_coords[-1] - x_coords[0]) / (len(x_coords) - 1) / 2
    dy = (y_coords[0]  - y_coords[-1]) / (len(y_coords) - 1) / 2
    extent = [x_coords[0] - dx, x_coords[-1] + dx,
              y_coords[-1] - dy, y_coords[0]  + dy]

    im = ax.imshow(
        data,
        cmap=cmap, norm=norm,
        aspect='auto',              # 축 비율 자동 (X·Y 스케일이 다르므로)
        extent=extent,
        origin='upper',             # 배열 첫 행이 위쪽 (y 내림차순과 일치)
        interpolation='nearest',    # 보간 없음 (원본 셀 크기 그대로 표시)
        zorder=1
    )

    # ── 셀 경계 격자선 ──────────────────────────────────────────
    draw_grid_lines(ax, x_coords, y_coords)

    # ── 3개 Eye 마스크 계산 및 그리기 ───────────────────────────
    mask_info_list = []   # 각 Eye 의 (label, width_ui, height_mv) 저장

    for label, y_lo, y_hi, fb_x, fb_y in MASK_REGIONS:
        # Eye 중심점 탐색
        cx, cy = find_mask_center(data, x_coords, y_coords, y_lo, y_hi)

        if cx is None:
            # 해당 영역에 Eye 가 없으면 fallback 위치에 마스크 배치
            cx, cy   = fb_x, fb_y
            w_ui, h_mv = 0.0, 0.0
        else:
            # Eye 중심 기준으로 Width/Height 마진 계산
            w_ui, h_mv = calc_mask_margin(
                data, x_coords, y_coords, cx, cy, y_lo, y_hi
            )

        # 고정 크기(±MASK_HALF_W × ±MASK_HALF_H)로 마름모 마스크 그리기
        draw_diamond_mask(ax, cx, cy, MASK_HALF_W, MASK_HALF_H)
        mask_info_list.append((label, w_ui, h_mv))

    # ── 컬러바 ──────────────────────────────────────────────────
    cbar = plt.colorbar(im, ax=ax, fraction=0.046, pad=0.04)
    cbar.set_label('Error Count (Max 63)', color='white',
                   fontsize=9, rotation=270, labelpad=14)
    cbar.set_ticks([0, 10, 20, 30, 40, 50, 60])
    cbar.ax.set_yticklabels(
        ['0', '10', '20', '30', '40', '50', '60'], color='white', fontsize=8
    )
    cbar.ax.yaxis.set_tick_params(color='white')
    cbar.outline.set_edgecolor('#555555')

    # ── 축 스타일 ────────────────────────────────────────────────
    ax.set_facecolor('#0d0d0d')   # 다크 배경
    ax.set_xlabel('Timing Offset (UI)', color='white', fontsize=10)
    ax.set_ylabel('Voltage Level (mV)', color='white', fontsize=10)
    ax.set_title(f'{lane_name}  –  Eye Diagram', color='white', fontsize=12, pad=8)
    ax.tick_params(colors='white', labelsize=7.5)
    for sp in ax.spines.values():
        sp.set_edgecolor('#444444')

    # X축 눈금: 0.04 UI 간격
    x_min_val = x_coords[0]
    x_max_val = x_coords[-1]
    x_ticks = np.arange(
        np.ceil(x_min_val / 0.04) * 0.04,   # 0.04 배수로 올림 시작
        x_max_val + 0.04 * 0.5,             # 마지막 눈금 포함되도록 여유 추가
        0.04
    )
    ax.set_xticks(x_ticks)
    ax.xaxis.set_major_formatter(plt.FuncFormatter(lambda v, _: f'{v:.2f}'))

    # Y축 눈금: 20 mV 간격
    y_min_val = y_coords[-1]
    y_max_val = y_coords[0]
    y_ticks = np.arange(
        np.ceil(y_min_val / 20) * 20,   # 20 배수로 올림 시작
        y_max_val + 20 * 0.5,           # 마지막 눈금 포함되도록 여유 추가
        20
    )
    ax.set_yticks(y_ticks)
    ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda v, _: f'{int(v)}'))

    ax.tick_params(axis='x', labelrotation=90)   # X축 레이블 90도 회전
    # 원점 기준선 (0 UI, 0 mV)
    ax.axhline(0, color='white', lw=0.8, ls='--', alpha=0.5, zorder=3)
    ax.axvline(0, color='white', lw=0.8, ls='--', alpha=0.5, zorder=3)

    # ── 마진 정보 박스 (우상단) ──────────────────────────────────
    # 레이블 약어: Upper→H(High), Middle→M(Mid), Lower→L(Low)
    label_map = {'Upper': 'H', 'Middle': 'M', 'Lower': 'L'}
    lines = []
    for label, w_ui, h_mv in mask_info_list:
        tag    = label_map.get(label, label)
        w_line = f"[{tag}]W:{w_ui:.3f}UI"     # Width 행
        h_line = f"   H:{h_mv:>5.1f}mV"       # Height 행 (들여쓰기 정렬)
        lines.append(w_line)
        lines.append(h_line)
    margin_text = '\n'.join(lines)

    ax.text(0.99, 0.99, margin_text,
            transform=ax.transAxes,
            fontsize=20, color='yellow', va='top', ha='right',
            fontfamily='monospace',
            bbox=dict(boxstyle='square,pad=0.2', fc='#1a1a1a',
                      alpha=0.88, ec='yellow', lw=1.0))

    # ── 파라미터 정보 박스 (좌하단) ─────────────────────────────
    # UI/step, mV/step 으로 측정 해상도를 표시
    v_mv    = params['VoltageMaxOffset'] * 10
    ui_step = params['TimingMaxOffset'] / 100 / params['TimingMaxSteps']
    mv_step = v_mv / params['VoltageMaxSteps']
    param_info = (
        f"TimingOffset={params['TimingMaxOffset']}  "
        f"Step={params['TimingMaxSteps']}  →  {ui_step:.5f} UI/step\n"
        f"VoltageOffset={params['VoltageMaxOffset']} (×10={v_mv} mV)  "
        f"Step={params['VoltageMaxSteps']}  →  {mv_step:.4f} mV/step"
    )
    ax.text(0.01, 0.01, param_info,
            transform=ax.transAxes,
            fontsize=7, color='#aaaaaa', va='bottom',
            bbox=dict(boxstyle='round,pad=0.3', fc='#1a1a1a',
                      alpha=0.75, ec='#444444'))

    return mask_info_list   # DB 저장을 위해 호출자에게 반환


# ─────────────────────────────────────────────────────────────────
# 6. 변환 실행
# ─────────────────────────────────────────────────────────────────

def append_to_db(base_name: str, all_lane_margins: list, out_dir: str = ''):
    """
    변환 결과(마진 값)를 EOM_DB.xlsx 에 기록.

    저장 구조:
        - 파일: EOM_DB.xlsx (스크립트 실행 경로의 현재 디렉토리)
        - 시트: 변환 폴더명에서 앞의 "EOM_" 또는 "EOM" 을 제거한 이름으로 생성
          → 같은 폴더에서 여러 세트를 변환해도 같은 시트에 행이 추가됨
          → 다른 폴더 변환 시 새 시트가 생성되어 탭으로 구분됨
        - 헤더: datetime, input_file, {lane}_{eye}_{w/h} ...
        - 데이터: 1행 = 1개 변환 세트 (lane0 + lane1 + ... 순서)

    openpyxl 미설치 시 EOM_DB.csv 로 폴백 저장.

    인수:
        base_name        : 입력 파일 기본 이름 (BaseName_QC_Offsets.txt 에서 추출)
        all_lane_margins : [(lane_name, mask_info_list), ...]
            mask_info_list : [('Upper', w_ui, h_mv),
                              ('Middle', w_ui, h_mv),
                              ('Lower', w_ui, h_mv)]
        out_dir          : 변환 폴더 경로 (탭 이름 생성에 사용)
    """
    # 폴더명에서 "EOM_" 또는 "EOM" 접두어 제거 → 탭 이름
    folder_name = os.path.basename(os.path.abspath(out_dir)) if out_dir else ''
    sheet_name  = re.sub(r'^EOM_?', '', folder_name) or _RUN_TIMESTAMP
    sheet_name  = sheet_name[:31]   # Excel 시트명 최대 31자 제한
    # ── 헤더 및 데이터 행 구성 ───────────────────────────────────
    # 각 Lane 의 컬럼: up_w, up_h, mid_w, mid_h, low_w, low_h
    header_lane = ['up_w(UI)', 'up_h(mV)', 'mid_w(UI)',
                   'mid_h(mV)', 'low_w(UI)', 'low_h(mV)']
    header = ['datetime', 'input_file']
    for lane_name, _ in all_lane_margins:
        header += [f'{lane_name}_{col}' for col in header_lane]

    # 데이터 행: 타임스탬프 + 파일명("Result_" 제거) + 각 Lane 의 6개 마진 값
    input_file_name = re.sub(r'^Result_', '', base_name)
    data_row = [datetime.now().strftime('%Y/%m/%d/%H/%M/%S'), input_file_name]
    for _, mask_info_list in all_lane_margins:
        for _, w_ui, h_mv in mask_info_list:
            data_row += [round(w_ui, 4), round(h_mv, 2)]   # 숫자 타입 유지 (Excel 계산 가능)

    # ── xlsx 저장 ────────────────────────────────────────────────
    if _XLSX_AVAILABLE:
        db_path = os.path.join(os.getcwd(), 'EOM_DB.xlsx')

        # 기존 파일이 있으면 열고, 없으면 새로 생성
        if os.path.exists(db_path):
            wb = openpyxl.load_workbook(db_path)
        else:
            wb = openpyxl.Workbook()
            # 기본 생성되는 빈 'Sheet' 제거
            if 'Sheet' in wb.sheetnames:
                del wb['Sheet']

        # 해당 폴더명 시트가 없으면 새로 생성 + 헤더 기록
        if sheet_name not in wb.sheetnames:
            ws = wb.create_sheet(title=sheet_name)
            ws.append(header)

            # 헤더 행 스타일: 굵은 흰색 글씨 + 남색 배경
            hdr_fill = PatternFill('solid', fgColor='1F4E79')
            for cell in ws[1]:
                cell.font      = Font(bold=True, color='FFFFFF')
                cell.fill      = hdr_fill
                cell.alignment = Alignment(horizontal='center')

            # 열 너비: 헤더 텍스트 길이 + 2 (최소 12)
            for i, col_title in enumerate(header, 1):
                ws.column_dimensions[
                    openpyxl.utils.get_column_letter(i)
                ].width = max(len(col_title) + 2, 12)
        else:
            # 이미 시트가 있으면 기존 시트에 행만 추가
            ws = wb[sheet_name]

        ws.append(data_row)
        wb.save(db_path)
        print(f"  → DB 저장: {db_path}  [시트: {sheet_name}]")

    # ── 폴백: csv 저장 (openpyxl 미설치 시) ─────────────────────
    else:
        print("  [경고] openpyxl 미설치 → EOM_DB.csv 로 저장합니다.")
        db_path   = os.path.join(os.getcwd(), 'EOM_DB.csv')
        write_hdr = not os.path.exists(db_path)   # 새 파일이면 헤더 포함
        with open(db_path, 'a', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            if write_hdr:
                writer.writerow(header)
            writer.writerow(data_row)
        print(f"  → DB 저장: {db_path}")


def convert(txt_path: str, csv_paths: list, out_dir: str = None, dpi: int = 150):
    """
    단일 변환 세트(QC_Offsets.txt + lane CSVs)를 처리하는 메인 함수.

    처리 순서:
        1. QC_Offsets.txt 파싱 → 파라미터 dict
        2. 각 lane CSV 파싱 → 좌표 변환 → Eye Diagram 플롯
        3. PNG 이미지로 저장
        4. 전체 lane 마진 값을 DB 에 기록

    인수:
        txt_path  : QC_Offsets.txt 파일 경로
        csv_paths : lane CSV 파일 경로 리스트 (lane0, lane1, ...)
        out_dir   : PNG 저장 폴더 (None 이면 현재 작업 디렉토리)
        dpi       : 저장 이미지 해상도 (기본 150 dpi)
    """
    if out_dir is None:
        out_dir = os.getcwd()

    # ── 파라미터 파싱 ────────────────────────────────────────────
    params = parse_offsets_txt(txt_path)
    print(f"[파라미터] {params}")
    print(f"           VoltageMaxOffset × 10 = {params['VoltageMaxOffset'] * 10} mV\n")

    # txt 파일명에서 "_QC_Offsets" 접미사 제거 → 출력 파일 기본 이름
    base_name = re.sub(r'_QC_Offsets$',
                       '',
                       os.path.splitext(os.path.basename(txt_path))[0])

    all_lane_margins = []   # 전체 lane 마진 정보 누적 (DB 저장용)

    # ── Lane 별 처리 ─────────────────────────────────────────────
    for csv_path in csv_paths:
        # CSV 파싱 → 인덱스 배열 + error count 행렬
        lane_name, x_idx, y_idx, data = parse_eye_csv(csv_path)

        # 인덱스 → 실제 좌표 변환
        x_coords = calc_x_coords(x_idx, params)
        y_coords = calc_y_coords(y_idx, params)

        print(f"[{lane_name}] X: {x_coords[0]:.4f} ~ {x_coords[-1]:.4f} UI  |  "
              f"Y: {y_coords[0]:.1f} ~ {y_coords[-1]:.1f} mV")

        # 플롯 생성 (다크 배경)
        fig, ax = plt.subplots(figsize=(10, 9), facecolor='#0d0d0d')
        mask_info_list = plot_eye_diagram(
            ax, data, x_coords, y_coords, lane_name, params
        )
        plt.tight_layout()

        # PNG 저장: {BaseName}_{LaneName}.png
        out_path = os.path.join(out_dir, f'{base_name}_{lane_name}.png')
        plt.savefig(out_path, dpi=dpi, bbox_inches='tight',
                    facecolor=fig.get_facecolor())
        plt.close(fig)   # 메모리 해제
        print(f"  → 저장: {out_path}")

        # 이 lane 의 마진 정보 누적
        all_lane_margins.append((lane_name, mask_info_list))

    # 전체 lane 마진을 DB 에 한 줄로 기록
    append_to_db(base_name, all_lane_margins, out_dir)
    print("\n완료!")


# ─────────────────────────────────────────────────────────────────
# 7. CLI / 인터랙티브 실행
# ─────────────────────────────────────────────────────────────────

def find_eom_folder(base_dir: str) -> str:
    """
    base_dir 안에서 이름이 'EOM_' 으로 시작하는 폴더를 탐색.

    반환값:
        폴더가 1개면 자동으로 해당 경로 반환.
        여러 개면 번호 선택 프롬프트 후 반환.
        없으면 None 반환.
    """
    candidates = sorted([
        os.path.join(base_dir, d)
        for d in os.listdir(base_dir)
        if d.startswith('EOM_') and os.path.isdir(os.path.join(base_dir, d))
    ])

    if len(candidates) == 1:
        return candidates[0]   # 1개면 자동 선택

    if len(candidates) > 1:
        print(f"  EOM_ 폴더가 여러 개 발견되었습니다:")
        for i, c in enumerate(candidates):
            print(f"    [{i}] {os.path.basename(c)}")
        while True:
            sel = input("  사용할 폴더 번호를 입력하세요: ").strip()
            if sel.isdigit() and int(sel) < len(candidates):
                return candidates[int(sel)]

    return None   # EOM_ 폴더 없음


def find_txt_in_folder(folder: str) -> list:
    """
    폴더 안의 모든 *_QC_Offsets.txt 파일 경로를 정렬하여 반환.
    """
    return sorted([
        os.path.join(folder, f)
        for f in os.listdir(folder)
        if f.endswith('_QC_Offsets.txt')
    ])


def find_lane_csvs(txt_path: str) -> list:
    """
    QC_Offsets.txt 와 같은 폴더에서 대응하는 lane CSV 파일들을 탐색.

    명명 규칙: {BaseName}_lane{숫자}.csv
    예시: EOM_ABC_QC_Offsets.txt → EOM_ABC_lane0.csv, EOM_ABC_lane1.csv

    반환값: 파일 경로 리스트 (정렬됨)
    """
    folder = os.path.dirname(os.path.abspath(txt_path))
    base   = re.sub(r'_QC_Offsets$',
                    '',
                    os.path.splitext(os.path.basename(txt_path))[0])
    return sorted([
        os.path.join(folder, f)
        for f in os.listdir(folder)
        if re.match(rf'{re.escape(base)}_lane\d+\.csv$', f)
    ])


def resolve_folder(raw: str) -> str:
    """
    사용자 입력 문자열을 유효한 폴더 경로로 변환.

    처리 순서:
        1. 빈 문자열 → 현재 디렉토리(cwd)에서 EOM_ 폴더 자동 탐색
        2. 폴더 경로 → 그대로 반환
        3. 파일 경로 → 해당 파일이 있는 폴더 반환
        4. 찾을 수 없으면 None 반환
    """
    # 앞뒤 공백 및 인용 부호 제거
    raw = raw.strip().strip('"').strip("'")

    if not raw:
        # 빈 입력 → 현재 경로의 EOM_ 폴더 자동 탐색
        cwd    = os.getcwd()
        folder = find_eom_folder(cwd)
        if folder:
            print(f"  → EOM_ 폴더 자동 탐색: {os.path.basename(folder)}")
            return folder
        print("  [오류] 현재 경로에서 EOM_ 폴더를 찾을 수 없습니다.")
        return None

    if os.path.isdir(raw):
        return raw   # 폴더 경로 직접 입력

    if os.path.isfile(raw):
        # 파일 경로 입력 → 해당 파일의 폴더 반환
        return os.path.dirname(os.path.abspath(raw))

    print(f"  [오류] 파일 또는 폴더를 찾을 수 없습니다: {raw}")
    return None


def select_txt(txt_list: list) -> str:
    """
    QC_Offsets.txt 파일 목록에서 1개를 선택.
    1개면 자동 선택, 여러 개면 번호 선택 프롬프트.
    'all' 입력 시 전체 선택을 의미하는 문자열 반환.
    """
    if len(txt_list) == 1:
        print(f"  → QC_Offsets.txt 자동 탐색: {os.path.basename(txt_list[0])}")
        return txt_list[0]

    print(f"\n  QC_Offsets.txt 파일이 {len(txt_list)}개 발견되었습니다:")
    for i, t in enumerate(txt_list):
        print(f"    [{i}] {os.path.basename(t)}")
    while True:
        sel = input("  변환할 파일 번호를 입력하세요 (all=전체): ").strip().lower()
        if sel == 'all':
            return 'all'
        if sel.isdigit() and int(sel) < len(txt_list):
            return txt_list[int(sel)]


def run_interactive():
    """
    인터랙티브 모드 실행 루프.

    흐름:
        1. 폴더 경로 입력 (Enter → EOM_ 자동 탐색)
        2. 폴더 내 변환 가능 세트 목록 표시
        3. 번호 선택 / 'a' 전체 변환 / 'q' 종료
        4. 변환 완료 후 다른 폴더 계속 여부 확인
        5. y 입력 시 새 폴더 입력 → 2번으로 반복
    """
    print("=" * 55)
    print("  Eye Diagram CSV → Image Converter")
    print("=" * 55)
    print("  ※ 경로를 입력하거나 Enter 키를 누르세요.")
    print("  ※ Enter: 현재 폴더의 EOM_ 하위 폴더 자동 탐색")
    print("  ※ 폴더 경로 입력: 해당 폴더에서 파일 자동 탐색\n")

    # 유효한 폴더가 확정될 때까지 반복 입력
    folder = None
    while not folder:
        raw    = input("폴더 / QC_Offsets.txt 경로 (Enter=자동): ")
        folder = resolve_folder(raw)

    while True:
        # 폴더 내 변환 가능한 세트(txt 파일) 탐색
        txt_list = find_txt_in_folder(folder)
        if not txt_list:
            print("  [오류] 폴더 안에서 *_QC_Offsets.txt 를 찾을 수 없습니다.")
            break

        # 세트가 여러 개면 선택 메뉴 표시
        if len(txt_list) > 1:
            print(f"\n  ─── 변환 가능한 세트 ({len(txt_list)}개) ───")
            for i, t in enumerate(txt_list):
                base = re.sub(r'_QC_Offsets\.txt$', '', os.path.basename(t))
                csvs = find_lane_csvs(t)
                print(f"    [{i}] {base}  ({len(csvs)}개 CSV)")
            print(f"    [a] 전체 변환")
            print(f"    [q] 종료")
            sel = input("\n  선택: ").strip().lower()

            if sel == 'q':
                break
            elif sel == 'a':
                targets = txt_list            # 전체 선택
            elif sel.isdigit() and int(sel) < len(txt_list):
                targets = [txt_list[int(sel)]]  # 번호 선택
            else:
                print("  잘못된 입력입니다.")
                continue
        else:
            targets = txt_list   # 1개면 자동 선택

        # 선택된 세트 순서대로 변환
        for txt_path in targets:
            csv_paths = find_lane_csvs(txt_path)
            if not csv_paths:
                print(f"  [건너뜀] {os.path.basename(txt_path)} - CSV 없음")
                continue
            base = re.sub(r'_QC_Offsets\.txt$', '', os.path.basename(txt_path))
            print(f"\n  ▶ {base} ({len(csv_paths)}개 CSV)")
            out_dir = os.path.dirname(os.path.abspath(txt_path))
            convert(txt_path, csv_paths, out_dir=out_dir)

        # 추가 변환 여부 확인
        print()
        ans = input("  다른 폴더를 계속 변환할까요? [y/N]: ").strip().lower()
        if ans != 'y':
            break

        # 새 폴더 입력 (빈 값 → 마지막 txt 파일의 폴더 유지)
        folder = None
        while not folder:
            raw = input("\n폴더 경로 (Enter=현재 폴더 유지): ").strip()
            if not raw:
                folder = os.path.dirname(os.path.abspath(txt_path if targets else folder))
                print(f"  → 현재 폴더 유지: {folder}")
            else:
                folder = resolve_folder(raw)

    print("\n모든 변환이 완료되었습니다.")


# ─────────────────────────────────────────────────────────────────
# 8. 진입점
# ─────────────────────────────────────────────────────────────────

if __name__ == '__main__':
    # 도움말 출력 후 종료
    if len(sys.argv) >= 2 and sys.argv[1] in ('-h', '--help'):
        print(__doc__)
        sys.exit(0)

    # ── CLI 모드: 인수가 있으면 자동 처리 ───────────────────────
    if len(sys.argv) >= 2:
        raw    = sys.argv[1].strip().strip('"').strip("'")
        folder = resolve_folder(raw)
        if not folder:
            sys.exit(1)

        txt_list = find_txt_in_folder(folder)
        if not txt_list:
            print("[오류] *_QC_Offsets.txt 파일을 찾을 수 없습니다.")
            sys.exit(1)

        if len(sys.argv) > 2:
            # CSV 파일 경로를 추가 인수로 직접 전달한 경우
            convert(txt_list[0], sys.argv[2:],
                    out_dir=os.path.dirname(os.path.abspath(txt_list[0])))
        else:
            # 폴더 내 모든 세트 자동 변환
            for txt_path in txt_list:
                csv_paths = find_lane_csvs(txt_path)
                if csv_paths:
                    convert(txt_path, csv_paths,
                            out_dir=os.path.dirname(os.path.abspath(txt_path)))

    # ── 인터랙티브 모드: 인수 없이 실행 ────────────────────────
    else:
        run_interactive()
