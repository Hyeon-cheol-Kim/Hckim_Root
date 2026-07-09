"""
PAM4 EOM Agent - Web Frontend (FastAPI)
Python 3.12.13 / Langflow 1.9.1 연동

사이드바 워크스페이스 구조 (EOM_Agent_Frontend 설계 반영):
  /            → /convert 로 리다이렉트
  /convert     SCREEN 01 · EOM 변환 (업로드 → flow 실행 → Eye·Margin 결과)
  /analysis    SCREEN 02 · DB 분석 (검색/필터 + 테이블 + 차트 4종 + KPI)
  /analysis/export  결과 CSV 내보내기
  /upload,/results  하위호환 리다이렉트

실행:
  export LANGFLOW_URL=http://localhost:7860
  export EOM_FLOW_ID=<Langflow에서 조립한 flow의 ID>
  uvicorn frontend.main:app --reload --port 8000  (프로젝트 루트에서)
"""
import csv
import io
import json
import os
from pathlib import Path
from urllib.parse import urlencode

import httpx
from fastapi import FastAPI, File, Form, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse, StreamingResponse
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


class FlowRunError(Exception):
    """Langflow flow 실행 실패. 사용자에게 보여줄 진단 메시지를 담는다."""


def _extract_flow_error(resp: httpx.Response) -> str:
    """Langflow 오류 응답에서 사용자용 진단 메시지를 최대한 추출.

    ③ JSON Builder의 EOMParseError('파싱 실패: ...') 같은 컴포넌트 오류를
    우선 골라내고, 없으면 detail/message/error 필드, 그래도 없으면 raw 일부.
    """
    raw = resp.text or ""
    # 1) 우리 컴포넌트가 낸 진단 메시지 우선 (JSON 이스케이프 정리 후 첫 문장)
    for marker in ("파싱 실패", "EOMParseError", "키워드 식별/파싱"):
        idx = raw.find(marker)
        if idx != -1:
            snippet = raw[idx:idx + 600].replace("\\n", "\n").replace('\\"', '"')
            return snippet.split("\n")[0].rstrip('"\\ ,}')[:400]
    # 2) 표준 오류 필드
    try:
        body = resp.json()
    except Exception:
        return (raw[:400] or f"HTTP {resp.status_code}")
    for key in ("detail", "message", "error"):
        v = body.get(key) if isinstance(body, dict) else None
        if isinstance(v, str) and v.strip():
            return v[:400]
        if isinstance(v, dict):
            for k2 in ("message", "error", "detail"):
                if isinstance(v.get(k2), str) and v[k2].strip():
                    return v[k2][:400]
    return (json.dumps(body, ensure_ascii=False)[:400] or f"HTTP {resp.status_code}")


async def run_langflow_flow(file_path: str, model: str) -> dict:
    url = f"{LANGFLOW_URL}/api/v1/run/{FLOW_ID}"
    payload = {
        "input_value": "run",
        "output_type": "text",
        "input_type": "text",
        "tweaks": build_tweaks(file_path, model),
    }
    async with httpx.AsyncClient(timeout=FLOW_TIMEOUT_S) as client:
        try:
            resp = await client.post(url, json=payload)
        except httpx.HTTPError as e:
            raise FlowRunError(
                f"Langflow 연결 실패: {e}. "
                f"LANGFLOW_URL({LANGFLOW_URL})과 EOM_FLOW_ID({FLOW_ID})를 확인하세요."
            ) from e
        if resp.is_error:
            raise FlowRunError(_extract_flow_error(resp))
        return resp.json()


# ---------- 진입: 워크스페이스 기본 화면 ----------
@app.get("/")
async def index():
    return RedirectResponse(url="/convert", status_code=307)


# ---------- SCREEN 01 · EOM 변환 ----------
@app.get("/convert", response_class=HTMLResponse)
async def convert_page(request: Request):
    return templates.TemplateResponse(
        "convert.html", {"request": request, "active": "convert"})


@app.post("/convert", response_class=HTMLResponse)
async def convert_run(request: Request,
                      file: UploadFile = File(...),
                      model: str = Form("claude"),
                      output: str = Form("json")):
    (STORAGE / "uploads").mkdir(parents=True, exist_ok=True)
    safe_name = Path(file.filename or "eom_log.txt").name  # 경로 탈출 방지
    dest = STORAGE / "uploads" / safe_name
    dest.write_bytes(await file.read())

    ctx: dict = {"request": request, "active": "convert",
                 "filename": safe_name, "model": model, "output": output}
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
    except FlowRunError as e:
        # ③ JSON Builder의 파싱 진단 등 Langflow 오류를 그대로 화면에 표시
        ctx["error"] = str(e)
    return templates.TemplateResponse("convert.html", ctx)


# ---------- SCREEN 02 · DB 분석 ----------
@app.get("/analysis", response_class=HTMLResponse)
async def analysis_page(request: Request, filename: str = "",
                        lane: str = "", eye: str = "", limit: int = 300):
    rows = query_results(DB_PATH, filename=filename, lane=lane, eye=eye, limit=limit)
    chart = build_chart_data(rows)
    qs = {k: v for k, v in
          {"filename": filename, "lane": lane, "eye": eye}.items() if v}
    return templates.TemplateResponse("analysis.html", {
        "request": request, "active": "analysis", "rows": rows,
        "chart_json": json.dumps(chart, ensure_ascii=False),
        "f_filename": filename, "f_lane": lane, "f_eye": eye,
        "query_string": ("?" + urlencode(qs)) if qs else "",
    })


@app.get("/analysis/export")
async def analysis_export(filename: str = "", lane: str = "", eye: str = "",
                          limit: int = 5000):
    rows = query_results(DB_PATH, filename=filename, lane=lane, eye=eye, limit=limit)
    cols = ["run_id", "filename", "model", "lane", "eye",
            "center_x_ui", "center_y_mv", "width_ui", "height_mv",
            "pass", "overall_pass", "params_complete", "created_at"]
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(cols)
    for r in rows:
        w.writerow([r.get(c, "") for c in cols])
    buf.seek(0)
    return StreamingResponse(
        iter([buf.getvalue()]), media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=eom_results.csv"})


# ---------- 하위호환 리다이렉트 ----------
@app.get("/upload")
async def _r_upload():
    return RedirectResponse(url="/convert", status_code=308)


@app.get("/results")
async def _r_results(request: Request):
    q = request.url.query
    return RedirectResponse(url="/analysis" + (("?" + q) if q else ""), status_code=308)
