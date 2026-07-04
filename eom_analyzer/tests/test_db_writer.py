"""⑥ DB Writer 검증 — ⑤ 출력 형식 그대로 INSERT 후 조회"""
import sys
import types
from pathlib import Path

# langflow mock
for mod in ["langflow", "langflow.custom", "langflow.io", "langflow.schema"]:
    sys.modules.setdefault(mod, types.ModuleType(mod))
sys.modules["langflow.custom"].Component = object
for n in ["MessageTextInput", "DataInput", "IntInput", "FloatInput", "Output"]:
    setattr(sys.modules["langflow.io"], n, lambda *a, **k: None)
sys.modules["langflow.schema"].Data = dict

sys.path.insert(0, str(Path(__file__).parent.parent / "langflow_components"))
from eom_db_writer import build_rows, insert_margins  # noqa: E402

# ⑤ Margin Calculator 출력 형식 샘플 (dual lane × 3 eye)
margins = {
    "source_file": "sample_eom.log",
    "llm_model": "claude",
    "json_path": "storage/json/sample_eom.json",
    "params_complete": True,
    "overall_pass": False,
    "lanes": {
        "Lane0": [
            {"eye": "Upper", "cx": 0.0, "cy": 200.0, "width_ui": 0.3556, "height_mv": 114.3, "pass": True},
            {"eye": "Middle", "cx": 0.0, "cy": -4.76, "width_ui": 0.3683, "height_mv": 133.3, "pass": True},
            {"eye": "Lower", "cx": 0.0, "cy": -200.0, "width_ui": 0.3556, "height_mv": 114.3, "pass": True},
        ],
        "Lane1": [
            {"eye": "Upper", "cx": 0.0, "cy": 200.0, "width_ui": 0.20, "height_mv": 40.0, "pass": False},
            {"eye": "Middle", "cx": 0.0, "cy": 0.0, "width_ui": 0.30, "height_mv": 90.0, "pass": True},
            {"eye": "Lower", "cx": 0.0, "cy": -200.0, "width_ui": 0.25, "height_mv": 60.0, "pass": True},
        ],
    },
}
images = {"Lane0": "storage/images/sample_eom_Lane0.png",
          "Lane1": "storage/images/sample_eom_Lane1.png"}

rows = build_rows(margins, images)
assert len(rows) == 6
assert {r["lane"] for r in rows} == {"Lane0", "Lane1"}
assert all(r["run_id"] == rows[0]["run_id"] for r in rows)
assert rows[0]["image_path"].endswith("Lane0.png")

db_file = Path(__file__).parent / "out_test" / "test_eom.db"
db_file.parent.mkdir(exist_ok=True)
db_file.unlink(missing_ok=True)
summary = insert_margins(f"sqlite:///{db_file}", margins, images)
print("insert:", summary)
assert summary["inserted_rows"] == 6 and summary["overall_pass"] is False

# 두 번째 run (다른 run_id 그룹 확인)
summary2 = insert_margins(f"sqlite:///{db_file}", margins, images)

import sqlite3  # noqa: E402
con = sqlite3.connect(db_file)
n_total = con.execute("SELECT COUNT(*) FROM eom_results").fetchone()[0]
n_runs = con.execute("SELECT COUNT(DISTINCT run_id) FROM eom_results").fetchone()[0]
fail_rows = con.execute(
    "SELECT lane, eye, width_ui, height_mv FROM eom_results WHERE pass=0"
).fetchall()
con.close()
assert n_total == 12 and n_runs == 2
assert all(r[0] == "Lane1" and r[1] == "Upper" for r in fail_rows)
print(f"rows={n_total}, runs={n_runs}, fail_rows={fail_rows}")
print("⑥ DB Writer PASS")
