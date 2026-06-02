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

import csv
import re
import os
import sys
import numpy as np
from datetime import datetime
import matplotlib.pyplot as plt
import matplotlib.colors as mcolors
from matplotlib.collections import LineCollection
from matplotlib.patches import Polygon


# ─────────────────────────────────────────────────────────────────
# 1. 파일 파싱
# ─────────────────────────────────────────────────────────────────

def parse_offsets_txt(txt_path: str) -> dict:
    """QC_Offsets.txt 에서 파라미터 파싱."""
    with open(txt_path, 'r') as f:
        content = f.read()
    params = {}
    for key in ['TimingMaxSteps', 'TimingMaxOffset',
                'VoltageMaxSteps', 'VoltageMaxOffset']:
        m = re.search(rf'{key}\s*:\s*(\d+)', content)
        if m:
            params[key] = int(m.group(1))
    return params


def parse_eye_csv(csv_path: str):
    """
    CSV 파싱.
    첫 행  : LaneName, x_idx1, x_idx2, ...
    이후 행: y_idx, val, val, ...
    반환   : (lane_name, x_indices, y_indices, data[n_y, n_x])
    """
    with open(csv_path, newline='', encoding='utf-8') as f:
        rows = list(csv.reader(f))

    header    = rows[0]
    lane_name = header[0]
    x_indices = [int(v) for v in header[1:]]

    y_indices, data_rows = [], []
    for row in rows[1:]:
        if not row:
            continue
        y_indices.append(int(row[0]))
        data_rows.append([int(v) for v in row[1:]])

    return lane_name, x_indices, y_indices, np.array(data_rows, dtype=float)


# ─────────────────────────────────────────────────────────────────
# 2. 좌표 변환
# ─────────────────────────────────────────────────────────────────

def calc_x_coords(x_indices: list, params: dict) -> np.ndarray:
    """X 인덱스 → UI 좌표."""
    return np.array([
        i / params['TimingMaxSteps'] * params['TimingMaxOffset'] / 100
        for i in x_indices
    ])


def calc_y_coords(y_indices: list, params: dict) -> np.ndarray:
    """Y 인덱스 → mV 좌표  (VoltageMaxOffset × 10 = 실제 mV)."""
    v_mv = params['VoltageMaxOffset'] * 10
    return np.array([
        i / params['VoltageMaxSteps'] * v_mv
        for i in y_indices
    ])



# ─────────────────────────────────────────────────────────────────
# 3. 마스크 중심점 및 마진 계산
# ─────────────────────────────────────────────────────────────────

def find_mask_center(data: np.ndarray,
                     x_coords: np.ndarray,
                     y_coords: np.ndarray,
                     y_min_mv: float,
                     y_max_mv: float):
    """
    지정 voltage 범위에서 value==0 셀이 가장 많은 행(들)을 찾아
    중심점 (cx, cy) 반환.
    - 동점 행이 여러 개이면 그 행들의 중간(median) voltage를 cy로 사용
    - cx = 해당 행(들)에서 0인 셀의 (min_x + max_x) / 2
    없으면 (None, None) 반환.
    """
    row_mask = (y_coords >= y_min_mv) & (y_coords <= y_max_mv)
    if not np.any(row_mask):
        return None, None

    sub_idx   = np.where(row_mask)[0]
    zero_cnts = np.array([np.sum(data[r, :] == 0) for r in sub_idx])
    max_count = zero_cnts.max()
    if max_count == 0:
        return None, None

    best_rows = sub_idx[zero_cnts == max_count]

    # 동점 행들의 중간(median) 인덱스 → voltage
    mid_row = best_rows[len(best_rows) // 2]
    cy = float(y_coords[mid_row])

    # 해당 행들 전체에서 0인 셀의 x 범위
    all_zero_x = []
    for r in best_rows:
        zmask = (data[r, :] == 0)
        all_zero_x.extend(x_coords[zmask].tolist())

    cx = (min(all_zero_x) + max(all_zero_x)) / 2.0
    return cx, cy


def calc_mask_margin(data: np.ndarray,
                     x_coords: np.ndarray,
                     y_coords: np.ndarray,
                     cx: float, cy: float,
                     y_min_mv: float, y_max_mv: float):
    """
    마스크 중심점(cx, cy) 기준으로 해당 Eye 영역 안에서만 계산.
    - Width  : cy 행에서 0인 셀들의 (max_x - min_x) → UI
    - Height : cx 열에서 해당 Eye 영역(y_min_mv~y_max_mv) 안의
               0인 행들의 (max_y - min_y) → mV
    반환: (width_ui, height_mv)
    """
    x_arr = np.array(x_coords)
    y_arr = np.array(y_coords)

    # Width: cy에 가장 가까운 행에서 0인 셀의 x 범위
    row_idx  = int(np.argmin(np.abs(y_arr - cy)))
    zero_x   = x_arr[data[row_idx, :] == 0]
    if len(zero_x) >= 2:
        width_ui = float(zero_x.max() - zero_x.min())
    elif len(zero_x) == 1:
        width_ui = float((x_arr[-1] - x_arr[0]) / (len(x_arr) - 1))
    else:
        width_ui = 0.0

    # Height: cx에 가장 가까운 열에서 해당 Eye 영역 안의 0인 행 y 범위
    col_idx     = int(np.argmin(np.abs(x_arr - cx)))
    region_mask = (y_arr >= y_min_mv) & (y_arr <= y_max_mv)
    col_zeros_y = y_arr[(data[:, col_idx] == 0) & region_mask]
    if len(col_zeros_y) >= 2:
        height_mv = float(col_zeros_y.max() - col_zeros_y.min())
    elif len(col_zeros_y) == 1:
        height_mv = float(abs(y_arr[1] - y_arr[0]))
    else:
        height_mv = 0.0

    return width_ui, height_mv


# ─────────────────────────────────────────────────────────────────
# 4. 그리기 유틸
# ─────────────────────────────────────────────────────────────────

def build_colormap():
    """Error count 0 (파란색) → 63 (빨간색) 컬러맵."""
    return mcolors.LinearSegmentedColormap.from_list('eye', [
        (0.00, '#0000FF'),
        (0.25, '#00BFFF'),
        (0.50, '#00FF80'),
        (0.75, '#FFFF00'),
        (1.00, '#FF0000'),
    ])


def draw_grid_lines(ax, x_coords: np.ndarray, y_coords: np.ndarray):
    """셀 경계에 연한 흰색 구분선 추가."""
    dx = (x_coords[-1] - x_coords[0]) / (len(x_coords) - 1) / 2
    dy = (y_coords[0]  - y_coords[-1]) / (len(y_coords) - 1) / 2

    x_edges = (
        [x_coords[0] - dx]
        + [(x_coords[i] + x_coords[i + 1]) / 2 for i in range(len(x_coords) - 1)]
        + [x_coords[-1] + dx]
    )
    y_edges = (
        [y_coords[0] + dy]
        + [(y_coords[i] + y_coords[i + 1]) / 2 for i in range(len(y_coords) - 1)]
        + [y_coords[-1] - dy]
    )

    y_min, y_max = y_edges[-1], y_edges[0]
    x_min, x_max = x_edges[0],  x_edges[-1]

    segments = (
        [[(x, y_min), (x, y_max)] for x in x_edges]
        + [[(x_min, y), (x_max, y)] for y in y_edges]
    )
    ax.add_collection(LineCollection(
        segments, colors='#ffffff', linewidths=0.5, alpha=0.5, zorder=2
    ))


def draw_diamond_mask(ax, cx: float, cy: float,
                      half_w: float, half_h: float,
                      color='yellow', alpha=0.4, zorder=5):
    """
    마름모 마스크.
    경계선 없음 (edgecolor='none'), 내부 투명도 60% (alpha=0.4).
    중심에 + 마커 표시.
    """
    verts = np.array([
        [cx,           cy + half_h],
        [cx + half_w,  cy         ],
        [cx,           cy - half_h],
        [cx - half_w,  cy         ],
    ])
    ax.add_patch(Polygon(verts, closed=True,
                         facecolor=color, alpha=alpha,
                         edgecolor='none', zorder=zorder))
    ax.plot(cx, cy, '+', color=color, markersize=7,
            markeredgewidth=1.2, alpha=0.95, zorder=zorder + 1)


# ─────────────────────────────────────────────────────────────────
# 5. 메인 플롯
# ─────────────────────────────────────────────────────────────────

# 마스크 설정 (필요 시 변경)
MASK_HALF_W  = 0.12    # UI  (마름모 가로 절반)
MASK_HALF_H  = 25.0    # mV  (마름모 세로 절반)
MASK_REGIONS = [
    ('Upper',   130.0,   9999.0,  0.0,  200.0),
    ('Middle', -130.0,    130.0,  0.0,    0.0),
    ('Lower',  -9999.0, -130.0,  0.0, -200.0),
]


def plot_eye_diagram(ax, data: np.ndarray,
                     x_coords: np.ndarray, y_coords: np.ndarray,
                     lane_name: str, params: dict):
    """Eye diagram 1개를 ax에 그린다."""

    # ── 히트맵 ──────────────────────────────────────────────────
    cmap = build_colormap()
    norm = mcolors.Normalize(vmin=0, vmax=63)

    dx = (x_coords[-1] - x_coords[0]) / (len(x_coords) - 1) / 2
    dy = (y_coords[0]  - y_coords[-1]) / (len(y_coords) - 1) / 2
    extent = [x_coords[0] - dx, x_coords[-1] + dx,
              y_coords[-1] - dy, y_coords[0]  + dy]

    im = ax.imshow(data, cmap=cmap, norm=norm,
                   aspect='auto', extent=extent,
                   origin='upper', interpolation='nearest', zorder=1)

    # ── 셀 구분선 ───────────────────────────────────────────────
    draw_grid_lines(ax, x_coords, y_coords)

    # ── 마스크 중심점 + 마진 계산 후 그리기 ─────────────────────
    mask_info_list = []   # (label, width_ui, height_mv) 순서대로 저장

    for label, y_lo, y_hi, fb_x, fb_y in MASK_REGIONS:
        cx, cy = find_mask_center(data, x_coords, y_coords, y_lo, y_hi)
        if cx is None:
            cx, cy = fb_x, fb_y
            w_ui, h_mv = 0.0, 0.0
        else:
            w_ui, h_mv = calc_mask_margin(data, x_coords, y_coords, cx, cy, y_lo, y_hi)

        # 마스크 크기는 고정 (±MASK_HALF_W UI × ±MASK_HALF_H mV)
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
    ax.set_facecolor('#0d0d0d')
    ax.set_xlabel('Timing Offset (UI)', color='white', fontsize=10)
    ax.set_ylabel('Voltage Level (mV)', color='white', fontsize=10)
    ax.set_title(f'{lane_name}  –  Eye Diagram', color='white', fontsize=12, pad=8)
    ax.tick_params(colors='white', labelsize=7.5)
    for sp in ax.spines.values():
        sp.set_edgecolor('#444444')

    # X축: 0.04 UI 간격
    x_min_val = x_coords[0]
    x_max_val = x_coords[-1]
    x_ticks = np.arange(
        np.ceil(x_min_val / 0.04) * 0.04,
        x_max_val + 0.04 * 0.5,
        0.04
    )
    ax.set_xticks(x_ticks)
    ax.xaxis.set_major_formatter(plt.FuncFormatter(lambda v, _: f'{v:.2f}'))

    # Y축: 20 mV 간격
    y_min_val = y_coords[-1]
    y_max_val = y_coords[0]
    y_ticks = np.arange(
        np.ceil(y_min_val / 20) * 20,
        y_max_val + 20 * 0.5,
        20
    )
    ax.set_yticks(y_ticks)
    ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda v, _: f'{int(v)}'))

    ax.tick_params(axis='x', labelrotation=90)
    ax.axhline(0, color='white', lw=0.8, ls='--', alpha=0.5, zorder=3)
    ax.axvline(0, color='white', lw=0.8, ls='--', alpha=0.5, zorder=3)

    # ── 마스크 마진 정보 박스 (우상단) ──────────────────────────
    label_map = {'Upper': 'High', 'Middle': 'Mid ', 'Lower': 'Low '}
    lines = []
    for label, w_ui, h_mv in mask_info_list:
        tag = label_map.get(label, label)
        w_line = f"[{tag}] W:{w_ui:.3f}UI"
        h_line = f"       H:{h_mv:>5.1f}mV"
        lines.append(w_line)
        lines.append(h_line)
    margin_text = '\n'.join(lines)

    ax.text(0.99, 0.99, margin_text, transform=ax.transAxes,
            fontsize=20, color='yellow', va='top', ha='right',
            fontfamily='monospace',
            bbox=dict(boxstyle='square,pad=0.2', fc='#1a1a1a',
                      alpha=0.88, ec='yellow', lw=1.0))

    # ── 파라미터 정보 박스 (좌하단) ─────────────────────────────
    v_mv    = params['VoltageMaxOffset'] * 10
    ui_step = params['TimingMaxOffset'] / 100 / params['TimingMaxSteps']
    mv_step = v_mv / params['VoltageMaxSteps']
    param_info = (
        f"TimingOffset={params['TimingMaxOffset']}  "
        f"Step={params['TimingMaxSteps']}  →  {ui_step:.5f} UI/step\n"
        f"VoltageOffset={params['VoltageMaxOffset']} (×10={v_mv} mV)  "
        f"Step={params['VoltageMaxSteps']}  →  {mv_step:.4f} mV/step"
    )
    ax.text(0.01, 0.01, param_info, transform=ax.transAxes,
            fontsize=7, color='#aaaaaa', va='bottom',
            bbox=dict(boxstyle='round,pad=0.3', fc='#1a1a1a',
                      alpha=0.75, ec='#444444'))

    return mask_info_list

# ─────────────────────────────────────────────────────────────────
# 6. 변환 실행
# ─────────────────────────────────────────────────────────────────

def append_to_db(base_name: str, all_lane_margins: list):
    """
    EOM_DB.csv 에 한 줄 추가.
    all_lane_margins : [(lane_name, mask_info_list), ...]
      mask_info_list : [('Upper', w, h), ('Middle', w, h), ('Lower', w, h)]
    한 줄 형식:
      datetime, input_file, l0_up_w, l0_up_h, l0_mid_w, l0_mid_h, l0_low_w, l0_low_h,
                            l1_up_w, l1_up_h, l1_mid_w, l1_mid_h, l1_low_w, l1_low_h
    """
    db_path   = os.path.join(os.getcwd(), 'EOM_DB.csv')
    write_hdr = not os.path.exists(db_path)

    header_lane = ['up_w(UI)', 'up_h(mV)', 'mid_w(UI)', 'mid_h(mV)', 'low_w(UI)', 'low_h(mV)']
    header = ['datetime', 'input_file']
    for lane_name, _ in all_lane_margins:
        header += [f'{lane_name}_{col}' for col in header_lane]

    row = [datetime.now().strftime('%Y%m%d%H%M%S'), base_name]
    for _, mask_info_list in all_lane_margins:
        for _, w_ui, h_mv in mask_info_list:
            row += [f'{w_ui:.4f}', f'{h_mv:.2f}']

    with open(db_path, 'a', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        if write_hdr:
            writer.writerow(header)
        writer.writerow(row)

    print(f"  → DB 저장: {db_path}")


def convert(txt_path: str, csv_paths: list, out_dir: str = None, dpi: int = 150):
    """
    txt_path  : QC_Offsets.txt 경로
    csv_paths : lane CSV 파일 경로 리스트
    out_dir   : 출력 폴더 (None → 현재 작업 디렉토리)
    """
    if out_dir is None:
        out_dir = os.getcwd()

    params = parse_offsets_txt(txt_path)
    print(f"[파라미터] {params}")
    print(f"           VoltageMaxOffset × 10 = {params['VoltageMaxOffset'] * 10} mV\n")

    base_name = re.sub(r'_QC_Offsets$', '',
                       os.path.splitext(os.path.basename(txt_path))[0])

    all_lane_margins = []

    for csv_path in csv_paths:
        lane_name, x_idx, y_idx, data = parse_eye_csv(csv_path)
        x_coords = calc_x_coords(x_idx, params)
        y_coords = calc_y_coords(y_idx, params)

        print(f"[{lane_name}] X: {x_coords[0]:.4f} ~ {x_coords[-1]:.4f} UI  |  "
              f"Y: {y_coords[0]:.1f} ~ {y_coords[-1]:.1f} mV")

        fig, ax = plt.subplots(figsize=(10, 9), facecolor='#0d0d0d')
        mask_info_list = plot_eye_diagram(ax, data, x_coords, y_coords, lane_name, params)
        plt.tight_layout()

        out_path = os.path.join(out_dir, f'{base_name}_{lane_name}.png')
        plt.savefig(out_path, dpi=dpi, bbox_inches='tight',
                    facecolor=fig.get_facecolor())
        plt.close(fig)
        print(f"  → 저장: {out_path}")

        all_lane_margins.append((lane_name, mask_info_list))

    append_to_db(base_name, all_lane_margins)
    print("\n완료!")




# ─────────────────────────────────────────────────────────────────
# 7. CLI / 인터랙티브 실행
# ─────────────────────────────────────────────────────────────────

def find_eom_folder(base_dir: str) -> str:
    """현재 경로에서 EOM_ 으로 시작하는 폴더 탐색. 없으면 None."""
    candidates = sorted([
        os.path.join(base_dir, d)
        for d in os.listdir(base_dir)
        if d.startswith('EOM_') and os.path.isdir(os.path.join(base_dir, d))
    ])
    if len(candidates) == 1:
        return candidates[0]
    if len(candidates) > 1:
        print(f"  EOM_ 폴더가 여러 개 발견되었습니다:")
        for i, c in enumerate(candidates):
            print(f"    [{i}] {os.path.basename(c)}")
        while True:
            sel = input("  사용할 폴더 번호를 입력하세요: ").strip()
            if sel.isdigit() and int(sel) < len(candidates):
                return candidates[int(sel)]
    return None


def find_txt_in_folder(folder: str) -> list:
    """폴더 내 *_QC_Offsets.txt 전체 목록 반환."""
    return sorted([
        os.path.join(folder, f)
        for f in os.listdir(folder)
        if f.endswith('_QC_Offsets.txt')
    ])


def find_lane_csvs(txt_path: str) -> list:
    """txt 파일과 같은 폴더에서 _lane*.csv 자동 탐색."""
    folder = os.path.dirname(os.path.abspath(txt_path))
    base   = re.sub(r'_QC_Offsets$', '',
                    os.path.splitext(os.path.basename(txt_path))[0])
    return sorted([
        os.path.join(folder, f)
        for f in os.listdir(folder)
        if re.match(rf'{re.escape(base)}_lane\d+\.csv$', f)
    ])


def resolve_folder(raw: str) -> str:
    """
    입력값이 폴더  → 그대로 반환.
    빈 값          → 현재 경로의 EOM_ 폴더 자동 탐색.
    찾지 못하면 None 반환.
    """
    raw = raw.strip().strip('"').strip("'")

    if not raw:
        cwd    = os.getcwd()
        folder = find_eom_folder(cwd)
        if folder:
            print(f"  → EOM_ 폴더 자동 탐색: {os.path.basename(folder)}")
            return folder
        print("  [오류] 현재 경로에서 EOM_ 폴더를 찾을 수 없습니다.")
        return None

    if os.path.isdir(raw):
        return raw

    # 파일이 직접 입력된 경우 → 해당 파일의 폴더
    if os.path.isfile(raw):
        return os.path.dirname(os.path.abspath(raw))

    print(f"  [오류] 파일 또는 폴더를 찾을 수 없습니다: {raw}")
    return None


def select_txt(txt_list: list) -> str:
    """
    txt 파일 목록에서 하나 선택.
    1개이면 자동 선택, 여러 개이면 번호 선택.
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
    """인터랙티브 모드: 폴더 내 여러 세트를 이어서 변환."""
    print("=" * 55)
    print("  Eye Diagram CSV → Image Converter")
    print("=" * 55)
    print("  ※ 경로를 입력하거나 Enter 키를 누르세요.")
    print("  ※ Enter: 현재 폴더의 EOM_ 하위 폴더 자동 탐색")
    print("  ※ 폴더 경로 입력: 해당 폴더에서 파일 자동 탐색\n")

    # 폴더 확정
    folder = None
    while not folder:
        raw    = input("폴더 / QC_Offsets.txt 경로 (Enter=자동): ")
        folder = resolve_folder(raw)

    while True:
        # 폴더 내 변환 가능 세트 탐색
        txt_list = find_txt_in_folder(folder)
        if not txt_list:
            print("  [오류] 폴더 안에서 *_QC_Offsets.txt 를 찾을 수 없습니다.")
            break

        # 전체 변환 or 선택
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
                targets = txt_list
            elif sel.isdigit() and int(sel) < len(txt_list):
                targets = [txt_list[int(sel)]]
            else:
                print("  잘못된 입력입니다.")
                continue
        else:
            targets = txt_list

        # 선택된 세트 변환
        for txt_path in targets:
            csv_paths = find_lane_csvs(txt_path)
            if not csv_paths:
                print(f"  [건너뜀] {os.path.basename(txt_path)} - CSV 없음")
                continue
            base = re.sub(r'_QC_Offsets\.txt$', '', os.path.basename(txt_path))
            print(f"\n  ▶ {base} ({len(csv_paths)}개 CSV)")
            out_dir = os.path.dirname(os.path.abspath(txt_path))
            convert(txt_path, csv_paths, out_dir=out_dir)

        # 계속 여부
        print()
        ans = input("  다른 폴더를 계속 변환할까요? [y/N]: ").strip().lower()
        if ans != 'y':
            break

        # 새 폴더 입력
        folder = None
        while not folder:
            raw    = input("\n폴더 경로 (Enter=현재 폴더 유지): ").strip()
            if not raw:
                # 현재 폴더 유지
                folder = os.path.dirname(os.path.abspath(txt_path if targets else folder))
                print(f"  → 현재 폴더 유지: {folder}")
            else:
                folder = resolve_folder(raw)

    print("\n모든 변환이 완료되었습니다.")


if __name__ == '__main__':
    if len(sys.argv) >= 2 and sys.argv[1] in ('-h', '--help'):
        print(__doc__)
        sys.exit(0)

    # ── CLI 모드 (인수 직접 전달) ────────────────────────────────
    if len(sys.argv) >= 2:
        raw      = sys.argv[1].strip().strip('"').strip("'")
        folder   = resolve_folder(raw)
        if not folder:
            sys.exit(1)

        txt_list = find_txt_in_folder(folder)
        if not txt_list:
            print("[오류] *_QC_Offsets.txt 파일을 찾을 수 없습니다.")
            sys.exit(1)

        # CSV가 추가 인수로 주어진 경우
        if len(sys.argv) > 2:
            convert(txt_list[0], sys.argv[2:],
                    out_dir=os.path.dirname(os.path.abspath(txt_list[0])))
        else:
            for txt_path in txt_list:
                csv_paths = find_lane_csvs(txt_path)
                if csv_paths:
                    convert(txt_path, csv_paths,
                            out_dir=os.path.dirname(os.path.abspath(txt_path)))

    # ── 인터랙티브 모드 ──────────────────────────────────────────
    else:
        run_interactive()
