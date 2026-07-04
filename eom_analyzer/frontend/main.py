"""
PAM4 EOM Agent - Web Frontend (FastAPI)
Python 3.12.13 / Langflow 1.9.1 연동

  /            첫 화면 (메뉴 2개)
  /upload      EOM log 업로드 → Langflow flow 실행 → 최신 run 결과 표시
  /results     eom_results 조회 + 비교 차트 (A: W/H 산점도, B: run 추이)

실행:
  export LANGFLOW_URL=http://localhost:7860
  export EOM_FLOW_ID=<Langflow에서 조립한 flow의 ID>
  uvicorn frontend.main:app --reload --port 8000  (프로젝트 루트에서)
"""
import json
import os
from pathlib import Path

import httpx
from fastapi import FastAPI, File, Form, Request, UploadFile
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from .db_queries import build_chart_data, fetch_run, latest_run_id, query_results

BASE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = BASE_DIR.parent
STORAGE = PROJECT_ROOT / "storage"
DB_PATH = PROJECT_ROOT / "db" / "eom_results.db"

LANGFLOW_URL = os.environ.get("LANGFLOW_URL", "http://localhost:7860")
FLOW_ID = os.environ.get("EOM_FLOW_ID", "eom_analysis_flow")
FLOW_TIMEOUT_S = int(os.environ.get("EOM_FLOW_TIMEOUT", "300"))

app = FastAPI(title="PAM4 EOM Agent")
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")
app.mount("/storage", StaticFiles(directory=STORAGE), name="storage")
templates = Jinja2Templates(directory=BASE_DIR / "templates")


def build_tweaks(file_path: str, model: str) -> dict:
    """Langflow run API tweaks (재구성된 컴포넌트 단위 반영).

    키는 Langflow에서 조립한 flow의 노드 ID와 일치해야 한다.
    Langflow는 노드에 접미사를 붙여 ID를 만들 수 있으므로(예: EOMLogLoader-a1B2c),
    flow 조립 시 노드 ID를 아래 name 값으로 고정하거나, export한 flow JSON의
    노드 ID에 맞춰 이 키들을 교체해야 한다.

    - ① Loader     : 파일 경로 주입 (파일 읽기 단일 책임)
    - ③ JSON Builder: 파일명(meta/파일명용) + LLM 모델명 주입
      (log_text는 Loader 출력이 edge로 전달되므로 tweaks 불필요)
    """
    tweaks = {
        "EOMLogLoader": {"file_path": file_path},
        "EOMJsonBuilder": {
            "source_file": Path(file_path).name,
            "llm_model": model,
        },
    }
    # LLM provider 전환: flow에서 사용한 Language Model 컴포넌트 ID로 교체
    # 예) tweaks["LanguageModelComponent"] = {"provider": model_provider_map[model]}
    return tweaks


async def run_langflow_flow(file_path: str, model: str) -> dict:
    url = f"{LANGFLOW_URL}/api/v1/run/{FLOW_ID}"
    payload = {
        "input_value": "run",
        "output_type": "text",
        "input_type": "text",
        "tweaks": build_tweaks(file_path, model),
    }
    async with httpx.AsyncClient(timeout=FLOW_TIMEOUT_S) as client:
        resp = await client.post(url, json=payload)
        resp.raise_for_status()
        return resp.json()


# ---------- 첫 화면 ----------
@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})


# ---------- 메뉴 1: 업로드 → flow 실행 ----------
@app.get("/upload", response_class=HTMLResponse)
async def upload_page(request: Request):
    return templates.TemplateResponse("upload.html", {"request": request})


@app.post("/upload", response_class=HTMLResponse)
async def upload_log(request: Request,
                     file: UploadFile = File(...),
                     model: str = Form("claude")):
    (STORAGE / "uploads").mkdir(parents=True, exist_ok=True)
    dest = STORAGE / "uploads" / file.filename
    dest.write_bytes(await file.read())

    ctx: dict = {"request": request, "filename": file.filename, "model": model}
    try:
        await run_langflow_flow(str(dest), model)
        # flow가 DB/이미지를 생성하므로, 최신 run을 DB에서 재조회해 표시
        run_id = latest_run_id(DB_PATH)
        rows = fetch_run(DB_PATH, run_id) if run_id else []
        images = sorted({r["image_path"] for r in rows if r["image_path"]})
        ctx.update({"run_id": run_id, "rows": rows, "images": images,
                    "error": None if rows else
                    "flow는 완료됐지만 DB에서 결과를 찾지 못했습니다. "
                    "⑥ DB Writer 연결과 db_url 경로를 확인하세요."})
    except httpx.HTTPError as e:
        ctx["error"] = (f"Langflow 호출 실패: {e}. "
                        f"LANGFLOW_URL({LANGFLOW_URL})과 "
                        f"EOM_FLOW_ID({FLOW_ID})를 확인하세요.")
    return templates.TemplateResponse("upload.html", ctx)


# ---------- 메뉴 2: 결과 조회 + 비교 차트 ----------
@app.get("/results", response_class=HTMLResponse)
async def results_page(request: Request, filename: str = "",
                       lane: str = "", eye: str = "", limit: int = 300):
    rows = query_results(DB_PATH, filename=filename, lane=lane,
                         eye=eye, limit=limit)
    chart = build_chart_data(rows)
    return templates.TemplateResponse("results.html", {
        "request": request, "rows": rows,
        "chart_json": json.dumps(chart, ensure_ascii=False),
        "f_filename": filename, "f_lane": lane, "f_eye": eye,
    })
