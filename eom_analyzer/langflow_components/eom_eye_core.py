"""
eom_eye_core.py — PAM4 Eye 공용 로직 (Langflow 컴포넌트 ④/⑤ 공용)

PAM4_eye_diagram_converter.py (CSV→이미지 기본 코드)의 로직을
matrix JSON 입력 기반으로 승계한 모듈.

승계 로직:
- 좌표 변환: X(UI) = idx/TimingMaxSteps × TimingMaxOffset/100
             Y(mV) = idx/VoltageMaxSteps × VoltageMaxOffset×10
- Eye 영역 3개(PAM4): Upper(>130mV) / Middle(±130mV) / Lower(<-130mV)
- 중심 탐지: 영역 내 최장 연속-0 행(동점 시 중간 행) → cy,
             해당 구간 중앙 → cx
- Width  = 기준 행 최장 연속-0 구간 길이 (UI)
- Height = cx 기준 열에서 cy 포함 연속-0 클러스터 높이 (mV, gap>1.5step 분리)
- 색상: error=0 파란색 / ≥1 빨간색 (1/63 급전환)
- 마름모 마스크 ±0.12UI × ±25mV, 격자선, 컬러바, 마진/파라미터 박스
"""
import numpy as np
import matplotlib

matplotlib.use("Agg")  # 서버(headless) 환경
import matplotlib.pyplot as plt
import matplotlib.colors as mcolors
from matplotlib.collections import LineCollection
from matplotlib.patches import Polygon

# ── 마스크 고정 크기 / Eye 영역 정의 (참고 코드 동일) ──────────────
MASK_HALF_W = 0.12   # 마름모 가로 절반 (UI)
MASK_HALF_H = 25.0   # 마름모 세로 절반 (mV)
MASK_REGIONS = [
    ("Upper", 130.0, 9999.0, 0.0, 200.0),
    ("Middle", -130.0, 130.0, 0.0, 0.0),
    ("Lower", -9999.0, -130.0, 0.0, -200.0),
]
# config 누락 시 기본 Offset (참고 코드 예시 값)
DEFAULT_T_OFFSET = 40
DEFAULT_V_OFFSET = 30


# ─────────────────────────────────────────────────────────────────
# 좌표 변환
# ─────────────────────────────────────────────────────────────────
def resolve_params(config: dict, t_steps: list, v_steps: list) -> tuple[dict, bool]:
    """JSON config에서 변환 파라미터를 확보. 누락 시 기본값으로 보완.

    Returns: (params, is_complete)
    """
    t_max_step = max(abs(t_steps[0]), abs(t_steps[-1]))
    v_max_step = max(abs(v_steps[0]), abs(v_steps[-1]))
    params = {
        "TimingMaxSteps": config.get("timing_max_steps", t_max_step),
        "TimingMaxOffset": config.get("timing_max_offset", DEFAULT_T_OFFSET),
        "VoltageMaxSteps": config.get("voltage_max_steps", v_max_step),
        "VoltageMaxOffset": config.get("voltage_max_offset", DEFAULT_V_OFFSET),
    }
    complete = all(
        k in config
        for k in ["timing_max_steps", "timing_max_offset",
                  "voltage_max_steps", "voltage_max_offset"]
    )
    return params, complete


def calc_x_coords(t_steps: list, params: dict) -> np.ndarray:
    return np.array([
        i / params["TimingMaxSteps"] * params["TimingMaxOffset"] / 100
        for i in t_steps
    ])


def calc_y_coords(v_steps: list, params: dict) -> np.ndarray:
    v_mv = params["VoltageMaxOffset"] * 10
    return np.array([i / params["VoltageMaxSteps"] * v_mv for i in v_steps])


# ─────────────────────────────────────────────────────────────────
# 중심 탐지 / 마진 계산 (참고 코드 승계)
# ─────────────────────────────────────────────────────────────────
def _max_contiguous_zeros(row_data: np.ndarray):
    is_zero = (row_data == 0).astype(int)
    padded = np.concatenate([[0], is_zero, [0]])
    diff = np.diff(padded)
    starts = np.where(diff == 1)[0]
    ends = np.where(diff == -1)[0]
    if len(starts) == 0:
        return 0, -1, -1
    lengths = ends - starts
    best = int(np.argmax(lengths))
    return int(lengths[best]), int(starts[best]), int(ends[best] - 1)


def find_mask_center(data, x_coords, y_coords, y_min_mv, y_max_mv):
    row_mask = (y_coords >= y_min_mv) & (y_coords <= y_max_mv)
    if not np.any(row_mask):
        return None, None
    sub_idx = np.where(row_mask)[0]
    runs = [_max_contiguous_zeros(data[r, :])[0] for r in sub_idx]
    max_run = max(runs)
    if max_run == 0:
        return None, None
    best_rows = sub_idx[np.array(runs) == max_run]
    mid_row = best_rows[len(best_rows) // 2]
    cy = float(y_coords[mid_row])
    _, s, e = _max_contiguous_zeros(data[mid_row, :])
    cx = float((x_coords[s] + x_coords[e]) / 2.0)
    return cx, cy


def _contiguous_cluster(values: np.ndarray, target: float, step: float):
    if len(values) == 0:
        return None
    sorted_v = np.sort(values)
    if len(sorted_v) == 1:
        return sorted_v if abs(sorted_v[0] - target) <= step else None
    gaps = np.diff(sorted_v)
    split_pts = np.where(gaps > step * 1.5)[0] + 1
    clusters = np.split(sorted_v, split_pts)
    for c in clusters:
        if c.min() <= target <= c.max():
            return c
    return min(clusters, key=lambda c: min(abs(c - target)))


def calc_mask_margin(data, x_coords, y_coords, cx, cy, y_min_mv, y_max_mv):
    x_arr, y_arr = np.array(x_coords), np.array(y_coords)
    step_y = float(abs(y_arr[1] - y_arr[0])) if len(y_arr) > 1 else 1.0

    row_mask = (y_arr >= y_min_mv) & (y_arr <= y_max_mv)
    sub_idx = np.where(row_mask)[0]
    if len(sub_idx) == 0:
        return 0.0, 0.0
    runs = [_max_contiguous_zeros(data[r, :])[0] for r in sub_idx]
    max_run = max(runs)
    if max_run == 0:
        return 0.0, 0.0
    best_rows = sub_idx[np.array(runs) == max_run]
    ref_row = best_rows[len(best_rows) // 2]

    _, s, e = _max_contiguous_zeros(data[ref_row, :])
    width_ui = float(x_arr[e] - x_arr[s])
    cx_ref = float((x_arr[s] + x_arr[e]) / 2)

    col_idx = int(np.argmin(np.abs(x_arr - cx_ref)))
    region_mask = (y_arr >= y_min_mv) & (y_arr <= y_max_mv)
    col_zeros_y = y_arr[(data[:, col_idx] == 0) & region_mask]
    cluster_y = _contiguous_cluster(col_zeros_y, cy, step_y)
    if cluster_y is not None and len(cluster_y) >= 2:
        height_mv = float(cluster_y.max() - cluster_y.min())
    elif cluster_y is not None:
        height_mv = step_y
    else:
        height_mv = 0.0
    return width_ui, height_mv


def calc_lane_margins(data: np.ndarray, x_coords, y_coords) -> list[dict]:
    """lane 1개의 3-eye 마진 계산.

    Returns: [{"eye": "Upper", "cx": ..., "cy": ..., "width_ui": ..., "height_mv": ...}, x3]
    """
    results = []
    for label, y_lo, y_hi, fb_x, fb_y in MASK_REGIONS:
        cx, cy = find_mask_center(data, x_coords, y_coords, y_lo, y_hi)
        if cx is None:
            cx, cy, w_ui, h_mv = fb_x, fb_y, 0.0, 0.0
        else:
            w_ui, h_mv = calc_mask_margin(data, x_coords, y_coords, cx, cy, y_lo, y_hi)
        results.append({
            "eye": label, "cx": round(cx, 4), "cy": round(cy, 2),
            "width_ui": round(w_ui, 4), "height_mv": round(h_mv, 2),
        })
    return results


# ─────────────────────────────────────────────────────────────────
# 그리기 (참고 코드 승계)
# ─────────────────────────────────────────────────────────────────
def build_colormap():
    """error=0 파란색 / ≥1 빨간색 (1/63 지점 급전환)."""
    return mcolors.LinearSegmentedColormap.from_list("eye", [
        (0.0, "#0000FF"), (1 / 63, "#FF0000"), (1.0, "#FF0000"),
    ])


def draw_grid_lines(ax, x_coords, y_coords):
    dx = (x_coords[-1] - x_coords[0]) / (len(x_coords) - 1) / 2
    dy = (y_coords[0] - y_coords[-1]) / (len(y_coords) - 1) / 2
    x_edges = ([x_coords[0] - dx]
               + [(x_coords[i] + x_coords[i + 1]) / 2 for i in range(len(x_coords) - 1)]
               + [x_coords[-1] + dx])
    y_edges = ([y_coords[0] + dy]
               + [(y_coords[i] + y_coords[i + 1]) / 2 for i in range(len(y_coords) - 1)]
               + [y_coords[-1] - dy])
    y_min, y_max = y_edges[-1], y_edges[0]
    x_min, x_max = x_edges[0], x_edges[-1]
    segments = ([[(x, y_min), (x, y_max)] for x in x_edges]
                + [[(x_min, y), (x_max, y)] for y in y_edges])
    ax.add_collection(LineCollection(segments, colors="#ffffff",
                                     linewidths=0.5, alpha=0.5, zorder=2))


def draw_diamond_mask(ax, cx, cy, half_w, half_h, color="yellow", alpha=0.4, zorder=5):
    verts = np.array([
        [cx, cy + half_h], [cx + half_w, cy],
        [cx, cy - half_h], [cx - half_w, cy],
    ])
    ax.add_patch(Polygon(verts, closed=True, facecolor=color, alpha=alpha,
                         edgecolor="none", zorder=zorder))
    ax.plot(cx, cy, "+", color=color, markersize=7,
            markeredgewidth=1.2, alpha=0.95, zorder=zorder + 1)


def plot_eye_diagram(ax, data, x_coords, y_coords, lane_name, params,
                     margins: list[dict]):
    """단일 lane Eye Diagram 렌더링 (마진은 사전 계산값 사용)."""
    cmap = build_colormap()
    norm = mcolors.Normalize(vmin=0, vmax=63)
    dx = (x_coords[-1] - x_coords[0]) / (len(x_coords) - 1) / 2
    dy = (y_coords[0] - y_coords[-1]) / (len(y_coords) - 1) / 2
    extent = [x_coords[0] - dx, x_coords[-1] + dx,
              y_coords[-1] - dy, y_coords[0] + dy]
    im = ax.imshow(data, cmap=cmap, norm=norm, aspect="auto", extent=extent,
                   origin="upper", interpolation="nearest", zorder=1)

    draw_grid_lines(ax, x_coords, y_coords)
    for m in margins:
        draw_diamond_mask(ax, m["cx"], m["cy"], MASK_HALF_W, MASK_HALF_H)

    cbar = plt.colorbar(im, ax=ax, fraction=0.046, pad=0.04)
    cbar.set_label("Error Count (Max 63)", color="white",
                   fontsize=9, rotation=270, labelpad=14)
    cbar.set_ticks([0, 10, 20, 30, 40, 50, 60])
    cbar.ax.set_yticklabels(["0", "10", "20", "30", "40", "50", "60"],
                            color="white", fontsize=8)
    cbar.ax.yaxis.set_tick_params(color="white")
    cbar.outline.set_edgecolor("#555555")

    ax.set_facecolor("#0d0d0d")
    ax.set_xlabel("Timing Offset (UI)", color="white", fontsize=10)
    ax.set_ylabel("Voltage Level (mV)", color="white", fontsize=10)
    ax.set_title(f"{lane_name} \u2013 Eye Diagram", color="white", fontsize=12, pad=8)
    ax.tick_params(colors="white", labelsize=7.5)
    for sp in ax.spines.values():
        sp.set_edgecolor("#444444")

    x_ticks = np.arange(np.ceil(x_coords[0] / 0.04) * 0.04,
                        x_coords[-1] + 0.02, 0.04)
    ax.set_xticks(x_ticks)
    ax.xaxis.set_major_formatter(plt.FuncFormatter(lambda v, _: f"{v:.2f}"))
    y_ticks = np.arange(np.ceil(y_coords[-1] / 20) * 20, y_coords[0] + 10, 20)
    ax.set_yticks(y_ticks)
    ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda v, _: f"{int(v)}"))
    ax.tick_params(axis="x", labelrotation=90)
    ax.axhline(0, color="white", lw=0.8, ls="--", alpha=0.5, zorder=3)
    ax.axvline(0, color="white", lw=0.8, ls="--", alpha=0.5, zorder=3)

    # 마진 정보 박스 (우상단)
    label_map = {"Upper": "H", "Middle": "M", "Lower": "L"}
    lines = []
    for m in margins:
        tag = label_map.get(m["eye"], m["eye"])
        lines.append(f"[{tag}]W:{m['width_ui']:.3f}UI")
        lines.append(f"   H:{m['height_mv']:>5.1f}mV")
    ax.text(0.99, 0.99, "\n".join(lines), transform=ax.transAxes,
            fontsize=20, color="yellow", va="top", ha="right",
            fontfamily="monospace",
            bbox=dict(boxstyle="square,pad=0.2", fc="#1a1a1a",
                      alpha=0.88, ec="yellow", lw=1.0))

    # 파라미터 정보 박스 (좌하단)
    v_mv = params["VoltageMaxOffset"] * 10
    ui_step = params["TimingMaxOffset"] / 100 / params["TimingMaxSteps"]
    mv_step = v_mv / params["VoltageMaxSteps"]
    param_info = (
        f"TimingOffset={params['TimingMaxOffset']} "
        f"Step={params['TimingMaxSteps']} \u2192 {ui_step:.5f} UI/step\n"
        f"VoltageOffset={params['VoltageMaxOffset']} (\u00d710={v_mv} mV) "
        f"Step={params['VoltageMaxSteps']} \u2192 {mv_step:.4f} mV/step"
    )
    ax.text(0.01, 0.01, param_info, transform=ax.transAxes,
            fontsize=7, color="#aaaaaa", va="bottom",
            bbox=dict(boxstyle="round,pad=0.3", fc="#1a1a1a",
                      alpha=0.75, ec="#444444"))


def plot_lane_png(matrix, t_steps, v_steps, config, lane_name,
                  out_path: str, dpi: int = 150) -> list[dict]:
    """lane 1개를 PNG로 저장하고 3-eye 마진 리스트 반환."""
    params, _ = resolve_params(config, t_steps, v_steps)
    data = np.array(matrix, dtype=float)
    x_coords = calc_x_coords(t_steps, params)
    y_coords = calc_y_coords(v_steps, params)
    margins = calc_lane_margins(data, x_coords, y_coords)

    fig, ax = plt.subplots(figsize=(10, 9), facecolor="#0d0d0d")
    plot_eye_diagram(ax, data, x_coords, y_coords, lane_name, params, margins)
    plt.tight_layout()
    fig.savefig(out_path, dpi=dpi, bbox_inches="tight",
                facecolor=fig.get_facecolor())
    plt.close(fig)
    return margins
