"""
⑤ EOM Margin Calculator - Langflow 1.9.1 Custom Component

matrix JSON에서 lane별 PAM4 3-eye(Upper/Middle/Lower) margin 계산.
참고 코드 알고리즘 승계:
  - 중심: 영역 내 최장 연속-0 행 → cy, 구간 중앙 → cx
  - Width(UI): 기준 행 최장 연속-0 구간 길이
  - Height(mV): cx 기준 열에서 cy 포함 연속-0 클러스터 (gap>1.5step 분리)
Fail 기준(참고 코드 분포 차트): Width ≤ 0.24 UI 또는 Height ≤ 50 mV
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import numpy as np  # noqa: E402
from eom_eye_core import (  # noqa: E402
    calc_lane_margins, calc_x_coords, calc_y_coords, resolve_params,
)

from langflow.custom import Component
from langflow.io import DataInput, FloatInput, Output
from langflow.schema import Data


class EOMMarginCalculator(Component):
    display_name = "EOM Margin Calculator"
    description = "lane별 3-eye(Upper/Middle/Lower) Width/Height margin 계산"
    icon = "ruler"
    name = "EOMMarginCalculator"

    inputs = [
        DataInput(name="eom_json", display_name="EOM JSON"),
        FloatInput(name="fail_width_ui", display_name="Fail Width (UI)", value=0.24),
        FloatInput(name="fail_height_mv", display_name="Fail Height (mV)", value=50.0),
    ]

    outputs = [
        Output(display_name="Margins", name="margins", method="calculate"),
    ]

    def calculate(self) -> Data:
        j = self.eom_json.data if hasattr(self.eom_json, "data") else self.eom_json
        config = j.get("config", {})
        t_steps, v_steps = j["timing_steps"], j["voltage_steps"]
        params, complete = resolve_params(config, t_steps, v_steps)
        x_coords = calc_x_coords(t_steps, params)
        y_coords = calc_y_coords(v_steps, params)

        fw = self.fail_width_ui or 0.24
        fh = self.fail_height_mv or 50.0

        lanes_out, overall_pass = {}, True
        for lane_id, lane in j["lanes"].items():
            data = np.array(lane["matrix"], dtype=float)
            margins = calc_lane_margins(data, x_coords, y_coords)
            for m in margins:
                m["pass"] = bool(m["width_ui"] > fw and m["height_mv"] > fh)
                overall_pass &= m["pass"]
            lanes_out[f"Lane{lane_id}"] = margins

        result = {
            "source_file": j["meta"]["source_file"],
            "llm_model": j["meta"].get("llm_model", ""),
            "json_path": j["meta"].get("json_path", ""),
            "params": params,
            "params_complete": complete,  # False면 기본 Offset으로 환산됨
            "fail_criteria": {"width_ui": fw, "height_mv": fh},
            "overall_pass": overall_pass,
            "lanes": lanes_out,
            # 예: {"Lane0": [{"eye":"Upper","cx":..,"cy":..,
            #                 "width_ui":..,"height_mv":..,"pass":true}, x3]}
        }
        self.status = f"overall_pass={overall_pass}, lanes={list(lanes_out.keys())}"
        return Data(data=result)
