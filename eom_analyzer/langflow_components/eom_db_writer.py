"""
⑥ EOM DB Writer - Langflow 1.9.1 Custom Component

⑤ Margin Calculator 결과(+ ④ 이미지 경로)를 SQLite에 INSERT.
- 연결: SQLAlchemy URL (기본 sqlite:///db/eom_results.db)
  → PostgreSQL 등으로 확장 시 URL만 교체
- 테이블: db/schema.sql 의 eom_results (lane × 3-eye, run_id 그룹핑)
- 테이블이 없으면 자동 생성 (idempotent)
"""
import json
from datetime import datetime
from pathlib import Path

# ---------------------------------------------------------------
# 순수 함수부 (단독 테스트 가능)
# ---------------------------------------------------------------
SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS eom_results (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id          TEXT NOT NULL,
    filename        TEXT NOT NULL,
    model           TEXT,
    json_path       TEXT,
    image_path      TEXT,
    lane            TEXT NOT NULL,
    eye             TEXT NOT NULL,
    center_x_ui     REAL,
    center_y_mv     REAL,
    width_ui        REAL,
    height_mv       REAL,
    pass            INTEGER,
    overall_pass    INTEGER,
    params_complete INTEGER,
    created_at      TEXT DEFAULT (datetime('now', 'localtime'))
);
"""
INDEX_SQL = [
    "CREATE INDEX IF NOT EXISTS idx_eom_results_run  ON eom_results(run_id);",
    "CREATE INDEX IF NOT EXISTS idx_eom_results_file ON eom_results(filename);",
]
INSERT_SQL = """
INSERT INTO eom_results
    (run_id, filename, model, json_path, image_path, lane, eye,
     center_x_ui, center_y_mv, width_ui, height_mv,
     pass, overall_pass, params_complete)
VALUES
    (:run_id, :filename, :model, :json_path, :image_path, :lane, :eye,
     :cx, :cy, :width_ui, :height_mv,
     :pass, :overall_pass, :params_complete)
"""


def build_rows(margins: dict, images: dict | None) -> list[dict]:
    """⑤ margins Data(+④ images)를 INSERT 파라미터 행 목록으로 변환."""
    images = images or {}
    filename = margins["source_file"]
    run_id = f"{Path(filename).stem}_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}"
    rows = []
    for lane_name, eyes in margins["lanes"].items():
        for m in eyes:
            rows.append({
                "run_id": run_id,
                "filename": filename,
                "model": margins.get("llm_model", ""),
                "json_path": margins.get("json_path", ""),
                "image_path": images.get(lane_name, ""),
                "lane": lane_name,
                "eye": m["eye"],
                "cx": m["cx"],
                "cy": m["cy"],
                "width_ui": m["width_ui"],
                "height_mv": m["height_mv"],
                "pass": int(m.get("pass", False)),
                "overall_pass": int(margins.get("overall_pass", False)),
                "params_complete": int(margins.get("params_complete", True)),
            })
    return rows


def insert_margins(db_url: str, margins: dict, images: dict | None = None) -> dict:
    """스키마 보장 후 lane × 3-eye 행 INSERT. Returns 요약 dict.

    SQLAlchemy 사용(Langflow 기본 포함). 미설치 + sqlite URL이면
    표준 라이브러리 sqlite3로 자동 fallback.
    """
    # sqlite 파일 디렉터리 보장
    if db_url.startswith("sqlite:///"):
        Path(db_url.removeprefix("sqlite:///")).parent.mkdir(
            parents=True, exist_ok=True
        )

    rows = build_rows(margins, images)
    try:
        from sqlalchemy import create_engine, text

        engine = create_engine(db_url)
        with engine.begin() as conn:
            conn.execute(text(SCHEMA_SQL))
            for stmt in INDEX_SQL:
                conn.execute(text(stmt))
            conn.execute(text(INSERT_SQL), rows)
        engine.dispose()
    except ImportError:
        if not db_url.startswith("sqlite:///"):
            raise
        import sqlite3

        con = sqlite3.connect(db_url.removeprefix("sqlite:///"))
        try:
            con.executescript(SCHEMA_SQL + "\n".join(INDEX_SQL))
            con.executemany(INSERT_SQL, rows)  # :name 스타일 그대로 지원
            con.commit()
        finally:
            con.close()
    return {
        "run_id": rows[0]["run_id"],
        "inserted_rows": len(rows),
        "db_url": db_url,
        "overall_pass": bool(rows[0]["overall_pass"]),
    }


# ---------------------------------------------------------------
# Langflow 컴포넌트부
# ---------------------------------------------------------------
from langflow.custom import Component
from langflow.io import DataInput, MessageTextInput, Output
from langflow.schema import Data


class EOMDbWriter(Component):
    display_name = "EOM DB Writer"
    description = "lane × 3-eye margin 결과를 eom_results 테이블에 INSERT"
    icon = "database"
    name = "EOMDbWriter"

    inputs = [
        DataInput(name="margins", display_name="Margins (⑤ 출력)"),
        DataInput(
            name="plot_result",
            display_name="Plot Result (④ 출력, 이미지 경로용)",
            required=False,
        ),
        MessageTextInput(
            name="db_url",
            display_name="Database URL",
            value="sqlite:///db/eom_results.db",
            info="SQLAlchemy URL. PostgreSQL 확장 시 URL만 교체",
        ),
    ]

    outputs = [
        Output(display_name="Insert Result", name="result", method="write"),
    ]

    def write(self) -> Data:
        margins = (
            self.margins.data if hasattr(self.margins, "data") else self.margins
        )
        images = None
        if self.plot_result is not None:
            pr = (
                self.plot_result.data
                if hasattr(self.plot_result, "data")
                else self.plot_result
            )
            images = pr.get("images")

        summary = insert_margins(
            self.db_url or "sqlite:///db/eom_results.db", margins, images
        )
        self.status = json.dumps(summary, ensure_ascii=False)
        return Data(data=summary)
