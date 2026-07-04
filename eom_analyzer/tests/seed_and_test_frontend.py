"""frontend db_queries 검증 + 데모 DB 시드 (Langflow 없이 /results 화면 확인용)

사용법: python3 tests/seed_and_test_frontend.py [--seed db/eom_results.db]
"""
import random
import sqlite3
import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from frontend.db_queries import build_chart_data, latest_run_id, query_results  # noqa: E402

SCHEMA = (Path(__file__).parent.parent / "db" / "schema.sql").read_text()


def seed(db_path: Path, n_runs: int = 8):
    db_path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(db_path)
    con.executescript(SCHEMA)
    rng = random.Random(7)
    t0 = datetime.now() - timedelta(days=n_runs)
    for i in range(n_runs):
        ts = (t0 + timedelta(days=i)).strftime("%Y%m%d_%H%M%S_%f")
        run_id = f"s{i:02d}_eom_{ts}"
        rows = []
        for lane in ["Lane0", "Lane1"]:
            for eye in ["Upper", "Middle", "Lower"]:
                w = (0.34 if eye == "Middle" else 0.31) + rng.gauss(0, 0.018)
                h = (125 if eye == "Middle" else 105) + rng.gauss(0, 7)
                if i < 2 and lane == "Lane1" and eye == "Upper":
                    w, h = 0.205 + 0.02 * i, 42 + 5 * i  # fail 샘플
                ok = int(w > 0.24 and h > 50)
                rows.append((run_id, f"s{i:02d}_eom.log", "claude",
                             f"storage/json/s{i:02d}_eom.json",
                             f"storage/images/s{i:02d}_eom_{lane}.png",
                             lane, eye, 0.0, 0.0, round(w, 4), round(h, 1),
                             ok, 0, 1))
        con.executemany(
            """INSERT INTO eom_results
               (run_id, filename, model, json_path, image_path, lane, eye,
                center_x_ui, center_y_mv, width_ui, height_mv,
                pass, overall_pass, params_complete)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""", rows)
    con.commit(); con.close()
    print(f"seeded {n_runs} runs -> {db_path}")


def run_tests():
    db = Path(__file__).parent / "out_test" / "frontend_test.db"
    db.unlink(missing_ok=True)
    seed(db, n_runs=5)

    rows = query_results(db)
    assert len(rows) == 5 * 6
    rows_l1 = query_results(db, lane="Lane1")
    assert len(rows_l1) == 15 and all(r["lane"] == "Lane1" for r in rows_l1)
    rows_f = query_results(db, filename="s03")
    assert len(rows_f) == 6 and all("s03" in r["filename"] for r in rows_f)
    assert latest_run_id(db).startswith("s04_eom_")

    chart = build_chart_data(query_results(db))
    assert len(chart["scatter"]) == 30
    fails = [p for p in chart["scatter"] if not p["pass"]]
    assert len(fails) == 2 and all(p["eye"] == "Upper" for p in fails)
    assert len(chart["trend"]["labels"]) == 5
    assert len(chart["trend"]["series"]) == 6  # 2 lane x 3 eye
    mid0 = next(s for s in chart["trend"]["series"]
                if s["eye"] == "Middle" and s["lane"] == "Lane0")
    assert len(mid0["width"]) == 5 and all(v is not None for v in mid0["width"])
    print("frontend db_queries PASS")


if __name__ == "__main__":
    if "--seed" in sys.argv:
        target = Path(sys.argv[sys.argv.index("--seed") + 1])
        seed(target)
    else:
        run_tests()
