"""④ Heatmap / ⑤ Margin 검증 — 합성 PAM4 3-eye 데이터 (127x127)"""
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parent.parent / "langflow_components"))
from eom_eye_core import (  # noqa: E402
    calc_lane_margins, calc_x_coords, calc_y_coords, plot_lane_png, resolve_params,
)

# ── 합성 데이터: TimingMaxSteps=63, Offset=40 → ±0.4UI / VoltageMaxSteps=63, Offset=30 → ±300mV
config = {"timing_max_steps": 63, "timing_max_offset": 40,
          "voltage_max_steps": 63, "voltage_max_offset": 30}
t_steps = list(range(-63, 64))
v_steps = list(range(63, -64, -1))
params, complete = resolve_params(config, t_steps, v_steps)
assert complete
x = calc_x_coords(t_steps, params)   # UI
y = calc_y_coords(v_steps, params)   # mV

# 3개 eye: 중심 (0, +200), (0, 0), (0, -200), 마름모 개구부 (반폭 0.18UI, 반높이 60mV)
matrix = np.full((127, 127), 63, dtype=float)
for cy_mv, half_w_ui, half_h_mv in [(200, 0.18, 60), (0, 0.20, 70), (-200, 0.18, 60)]:
    for r in range(127):
        for c in range(127):
            if abs(x[c]) / half_w_ui + abs(y[r] - cy_mv) / half_h_mv <= 1.0:
                matrix[r, c] = 0
# 노이즈: middle eye 내부 1셀에 error 3 (병합/클러스터 로직 확인용)
matrix[63, 60] = 3

# ── ⑤ 마진 계산 검증 ──
margins = calc_lane_margins(matrix, x, y)
for m in margins:
    print(f"{m['eye']:6s} center=({m['cx']:+.3f}UI, {m['cy']:+.1f}mV) "
          f"W={m['width_ui']:.4f}UI H={m['height_mv']:.1f}mV")

up, mid, low = margins
# 이산화 해석값 (x step=0.4/63, y step=300/63):
#  - Middle: 노이즈 셀이 중앙 행(v=0)의 연속-0을 끊음 → 한 행 아래(v=-4.76) 기준
#            W = 2×29셀×0.006349 = 0.3683UI / H = 2×14셀×4.7619 = 133.3mV
#  - Upper/Lower: W = 2×28셀 = 0.3556UI / H = 2×12셀 = 114.3mV
assert abs(mid["width_ui"] - 0.3683) < 1e-3 and abs(mid["cy"] + 4.76) < 0.1, mid
assert abs(mid["height_mv"] - 133.33) < 0.1, mid
assert abs(up["cy"] - 200) < 1 and abs(low["cy"] + 200) < 1
assert abs(up["width_ui"] - 0.3556) < 1e-3 and abs(up["height_mv"] - 114.29) < 0.1, up
assert all(abs(m["cx"]) < 0.01 for m in margins)
print("⑤ margin 계산 PASS (노이즈 셀 회피 동작 포함)")

# ── ④ PNG 생성 검증 ──
out = Path(__file__).parent / "out_test"
out.mkdir(exist_ok=True)
m2 = plot_lane_png(matrix.tolist(), t_steps, v_steps, config, "Lane0",
                   str(out / "synthetic_Lane0.png"))
assert (out / "synthetic_Lane0.png").exists()
assert m2 == margins  # 이미지 표기 마진 == ⑤ 계산 마진 (동일 코어)
print("④ PNG 생성 PASS:", out / "synthetic_Lane0.png")
