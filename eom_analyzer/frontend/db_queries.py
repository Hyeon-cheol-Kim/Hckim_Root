"""
frontend/db_queries.py — eom_results 조회 및 차트 데이터 생성 (순수 로직)
"""
import sqlite3
from pathlib import Path

COLUMNS = [
    "id", "run_id", "filename", "model", "json_path", "image_path",
    "lane", "eye", "center_x_ui", "center_y_mv", "width_ui", "height_mv",
    "pass", "overall_pass", "params_complete", "created_at",
]


def _connect(db_path: str | Path) -> sqlite3.Connection:
    con = sqlite3.connect(db_path)
    con.row_factory = sqlite3.Row
    return con


def query_results(db_path, filename: str = "", lane: str = "", eye: str = "",
                  limit: int = 300) -> list[dict]:
    """필터 조건으로 결과 조회 (최신순)."""
    if not Path(db_path).exists():
        return []
    sql = "SELECT * FROM eom_results WHERE 1=1"
    args: list = []
    if filename:
        sql += " AND filename LIKE ?"
        args.append(f"%{filename}%")
    if lane:
        sql += " AND lane = ?"
        args.append(lane)
    if eye:
        sql += " AND eye = ?"
        args.append(eye)
    sql += " ORDER BY id DESC LIMIT ?"
    args.append(limit)
    con = _connect(db_path)
    try:
        rows = [dict(r) for r in con.execute(sql, args).fetchall()]
    finally:
        con.close()
    return rows


def fetch_run(db_path, run_id: str) -> list[dict]:
    con = _connect(db_path)
    try:
        rows = [dict(r) for r in con.execute(
            "SELECT * FROM eom_results WHERE run_id = ? ORDER BY lane, eye",
            (run_id,)).fetchall()]
    finally:
        con.close()
    return rows


def latest_run_id(db_path) -> str | None:
    if not Path(db_path).exists():
        return None
    con = _connect(db_path)
    try:
        r = con.execute(
            "SELECT run_id FROM eom_results ORDER BY id DESC LIMIT 1"
        ).fetchone()
    finally:
        con.close()
    return r["run_id"] if r else None


def build_chart_data(rows: list[dict]) -> dict:
    """조회 결과 → Chart.js용 데이터.

    scatter: [{x: width_ui, y: height_mv, lane, eye, run_id, pass}]
    trend:   runs(오래된순) 라벨 + (lane,eye)별 width/height 시리즈
    """
    scatter = [{
        "x": r["width_ui"], "y": r["height_mv"],
        "lane": r["lane"], "eye": r["eye"],
        "run_id": r["run_id"], "pass": bool(r["pass"]),
    } for r in rows]

    # run 순서: created_at(=id) 오름차순
    runs_ordered: list[str] = []
    for r in sorted(rows, key=lambda x: x["id"]):
        if r["run_id"] not in runs_ordered:
            runs_ordered.append(r["run_id"])
    run_idx = {rid: i for i, rid in enumerate(runs_ordered)}

    series: dict[str, dict] = {}
    for r in sorted(rows, key=lambda x: x["id"]):
        key = f'{r["eye"]} {r["lane"]}'
        s = series.setdefault(key, {
            "label": key, "lane": r["lane"], "eye": r["eye"],
            "width": [None] * len(runs_ordered),
            "height": [None] * len(runs_ordered),
        })
        i = run_idx[r["run_id"]]
        s["width"][i] = r["width_ui"]
        s["height"][i] = r["height_mv"]

    labels = [rid.rsplit("_", 3)[-3] + "_" + rid.rsplit("_", 3)[-2]
              if rid.count("_") >= 3 else rid for rid in runs_ordered]
    return {
        "scatter": scatter,
        "trend": {"labels": labels, "run_ids": runs_ordered,
                  "series": list(series.values())},
    }
