"""
④ EOM Heatmap Plotter - Langflow 1.9.1 Custom Component

③ JSON Builder의 matrix JSON을 받아 lane별 Eye Diagram PNG 생성.
참고 코드(PAM4_eye_diagram_converter.py) 시각화 로직 전체 승계:
  - error=0 파란색 / ≥1 빨간색, 셀 격자선, 컬러바(0~63)
  - PAM4 3-eye 마름모 마스크(±0.12UI × ±25mV) + 중심 '+' 마커
  - 우상단 마진 박스 / 좌하단 파라미터 박스, 다크 배경
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))  # 사이드 모듈 import 경로
from eom_eye_core import plot_lane_png  # noqa: E402

from langflow.custom import Component
from langflow.io import DataInput, IntInput, MessageTextInput, Output
from langflow.schema import Data


class EOMHeatmapPlotter(Component):
    display_name = "EOM Heatmap Plotter"
    description = "matrix JSON을 lane별 Eye Diagram PNG로 저장 (3-eye 마스크/마진 박스 포함)"
    icon = "image"
    name = "EOMHeatmapPlotter"

    inputs = [
        DataInput(name="eom_json", display_name="EOM JSON"),
        MessageTextInput(
            name="output_dir",
            display_name="Image Output Dir",
            value="storage/images",
        ),
        IntInput(name="dpi", display_name="DPI", value=150),
    ]

    outputs = [
        Output(display_name="Plot Result", name="plot_result", method="plot"),
    ]

    def plot(self) -> Data:
        j = self.eom_json.data if hasattr(self.eom_json, "data") else self.eom_json
        out_dir = Path(self.output_dir or "storage/images")
        out_dir.mkdir(parents=True, exist_ok=True)
        stem = Path(j["meta"]["source_file"]).stem

        images, margins_all = {}, {}
        for lane_id, lane in j["lanes"].items():
            lane_name = f"Lane{lane_id}"
            out_path = out_dir / f"{stem}_{lane_name}.png"
            margins = plot_lane_png(
                lane["matrix"], j["timing_steps"], j["voltage_steps"],
                j.get("config", {}), lane_name, str(out_path),
                dpi=self.dpi or 150,
            )
            images[lane_name] = str(out_path)
            margins_all[lane_name] = margins

        self.status = f"images: {list(images.values())}"
        return Data(data={
            "images": images,          # {"Lane0": "storage/images/....png", ...}
            "margins": margins_all,    # 이미지에 표기된 마진 (참고용)
            "source_file": j["meta"]["source_file"],
        })
