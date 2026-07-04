"""
build_flow_json.py — 재구성된 컴포넌트 그래프를 Langflow 1.9.1 flow JSON으로 생성.

Langflow flow는 JSON 포맷이다:
  {"data": {"nodes": [...], "edges": [...]}, "name", "description", "id"}
  - node : 컴포넌트 1개 (template=입력필드/코드, outputs=출력)
  - edge : 출력→입력 연결. sourceHandle/targetHandle 문자열은
           Langflow가 큰따옴표(")를 'œ' 문자로 치환해 인코딩한다.

각 커스텀 컴포넌트의 파이썬 소스를 node.template.code.value 에 임베드한다.
(실배포에서는 LANGFLOW_COMPONENTS_PATH 로 .py 를 로드하는 것이 권장 —
 eom_eye_core.py 같은 사이드 모듈 import 때문. 아래 임베드는 구조 표현/참고용.)

사용:
  python3 flows/build_flow_json.py        # flows/eom_analysis_flow.json 생성
"""
import json
import uuid
from pathlib import Path

HERE = Path(__file__).resolve().parent
COMP = HERE.parent / "langflow_components"
PROMPT_TXT = HERE / "prompts" / "eom_pattern_prompt.txt"
OUT = HERE / "eom_analysis_flow.json"


def code_of(fname: str) -> str:
    p = COMP / fname
    return p.read_text(encoding="utf-8") if p.exists() else ""


def enc_handle(d: dict) -> str:
    """핸들 dict → Langflow 문자열 형식 (키/값 " 를 œ 로 치환, 공백 없음)."""
    return json.dumps(d, separators=(",", ":"), ensure_ascii=False).replace('"', "œ")


# ── 입력 필드 템플릿 헬퍼 ────────────────────────────────────────────
def f_str(name, value="", input_types=("Message",), display=None, info=""):
    return {
        name: {
            "type": "str", "value": value, "name": name,
            "display_name": display or name, "info": info,
            "input_types": list(input_types),
            "show": True, "required": False, "advanced": False,
            "list": False, "_input_type": "MessageTextInput",
        }
    }


def f_int(name, value, display=None, info=""):
    return {name: {"type": "int", "value": value, "name": name,
                   "display_name": display or name, "info": info, "show": True,
                   "required": False, "advanced": False, "_input_type": "IntInput"}}


def f_float(name, value, display=None, info=""):
    return {name: {"type": "float", "value": value, "name": name,
                   "display_name": display or name, "info": info, "show": True,
                   "required": False, "advanced": False, "_input_type": "FloatInput"}}


def f_data(name, display=None, info=""):
    return {name: {"type": "other", "value": "", "name": name,
                   "display_name": display or name, "info": info,
                   "input_types": ["Data"], "show": True, "required": True,
                   "advanced": False, "_input_type": "DataInput"}}


def f_code(src):
    return {"code": {"type": "code", "value": src, "name": "code",
                     "show": True, "advanced": True, "fileTypes": [],
                     "password": False, "dynamic": True, "_input_type": "CodeInput"}}


def out(name, display, method, types):
    return {"types": list(types), "selected": types[0], "name": name,
            "display_name": display, "method": method, "value": "__UNDEFINED__",
            "cache": True, "hidden": False}


def node(nid, ctype, display, desc, template, outputs, icon, x, y, base_classes):
    tmpl = {"_type": "Component"}
    tmpl.update(template)
    return {
        "id": nid, "type": "genericNode",
        "position": {"x": x, "y": y},
        "data": {
            "type": ctype, "id": nid,
            "node": {
                "template": tmpl, "description": desc, "display_name": display,
                "icon": icon, "base_classes": list(base_classes),
                "outputs": outputs, "documentation": "", "beta": False,
                "edited": False, "official": False,
            },
        },
        "width": 320, "height": 400, "selected": False, "dragging": False,
        "positionAbsolute": {"x": x, "y": y},
    }


# ── 노드 정의 ────────────────────────────────────────────────────────
nodes = []

nodes.append(node(
    "EOMLogLoader", "EOMLogLoader", "EOM Log Loader",
    "EOM log 파일을 읽어 인코딩 자동 감지 후 전체 원문 텍스트를 출력",
    {**f_code(code_of("eom_log_loader.py")),
     **f_str("file_path", info="storage/uploads/... (tweaks)")},
    [out("log_text", "Log Text", "load", ["Message"])],
    "file-text", 60, 300, ["Message"]))

nodes.append(node(
    "EOMLogSampler", "EOMLogSampler", "EOM Log Sampler",
    "① Loader의 로그 원문에서 LLM 패턴 식별용 샘플 추출",
    {**f_code(code_of("eom_log_sampler.py")),
     **f_str("log_text", info="① Loader의 log_text 연결"),
     **f_int("head_lines", 60, info="앞부분 줄 수")},
    [out("log_sample", "Log Sample", "get_sample", ["Message"])],
    "scissors", 440, 120, ["Message"]))

# Prompt (Langflow 내장) — template 에 패턴 프롬프트, 변수 {log_sample}
prompt_text = PROMPT_TXT.read_text(encoding="utf-8") if PROMPT_TXT.exists() else "{log_sample}"
nodes.append(node(
    "Prompt", "Prompt", "Prompt (Pattern)",
    "eom_pattern_prompt.txt 템플릿. 변수 {log_sample} ← Sampler 출력",
    {"template": {"type": "prompt", "value": prompt_text, "name": "template",
                  "display_name": "Template", "show": True, "_input_type": "PromptInput"},
     **f_str("log_sample", info="②a Sampler의 log_sample 연결")},
    [out("prompt", "Prompt Message", "build_prompt", ["Message"])],
    "prompt", 820, 120, ["Message"]))

# Language Model (Langflow 내장, provider 선택형: Anthropic/OpenAI/Ollama)
nodes.append(node(
    "LanguageModelComponent", "LanguageModelComponent", "Language Model",
    "패턴 식별 LLM. provider tweak 으로 Claude/OpenAI/Ollama 전환",
    {"provider": {"type": "str", "value": "Anthropic", "name": "provider",
                  "display_name": "Model Provider",
                  "options": ["Anthropic", "OpenAI", "Ollama"],
                  "show": True, "_input_type": "DropdownInput"},
     "model_name": {"type": "str", "value": "claude-3-5-sonnet-latest",
                    "name": "model_name", "display_name": "Model Name",
                    "show": True, "_input_type": "DropdownInput"},
     "api_key": {"type": "str", "value": "", "name": "api_key",
                 "display_name": "API Key", "password": True, "show": True,
                 "_input_type": "SecretStrInput"},
     "temperature": {"type": "float", "value": 0.0, "name": "temperature",
                     "display_name": "Temperature", "show": True,
                     "_input_type": "SliderInput"},
     **f_str("input_value", info="Prompt 연결")},
    [out("text_output", "Text", "text_response", ["Message"])],
    "brain-circuit", 1200, 120, ["Message"]))

nodes.append(node(
    "EOMJsonBuilder", "EOMJsonBuilder", "EOM JSON Builder",
    "LLM 패턴 + Python 추출로 V(row)×T(col) matrix JSON 생성 (fallback 포함)",
    {**f_code(code_of("eom_json_builder.py")),
     **f_str("llm_patterns", info="② LLM text 연결"),
     **f_str("log_text", info="① Loader의 log_text 연결"),
     **f_str("source_file", info="원본 파일명 (tweaks)"),
     **f_str("output_dir", value="storage/json"),
     **f_str("llm_model", info="meta 기록용 (tweaks)")},
    [out("eom_json", "EOM JSON", "build", ["Data"])],
    "braces", 1580, 300, ["Data"]))

nodes.append(node(
    "EOMHeatmapPlotter", "EOMHeatmapPlotter", "EOM Heatmap Plotter",
    "matrix JSON → lane별 Eye Diagram PNG (3-eye 마스크/마진 박스)",
    {**f_code(code_of("eom_heatmap_plotter.py")),
     **f_data("eom_json", info="③ JSON Builder 연결"),
     **f_str("output_dir", value="storage/images"),
     **f_int("dpi", 150)},
    [out("plot_result", "Plot Result", "plot", ["Data"])],
    "image", 1960, 120, ["Data"]))

nodes.append(node(
    "EOMMarginCalculator", "EOMMarginCalculator", "EOM Margin Calculator",
    "lane별 3-eye Width/Height margin + Pass/Fail 계산",
    {**f_code(code_of("eom_margin_calculator.py")),
     **f_data("eom_json", info="③ JSON Builder 연결"),
     **f_float("fail_width_ui", 0.24), **f_float("fail_height_mv", 50.0)},
    [out("margins", "Margins", "calculate", ["Data"])],
    "ruler", 1960, 480, ["Data"]))

nodes.append(node(
    "EOMDbWriter", "EOMDbWriter", "EOM DB Writer",
    "lane × 3-eye margin 결과를 eom_results 테이블에 INSERT",
    {**f_code(code_of("eom_db_writer.py")),
     **f_data("margins", info="⑤ Margin Calculator 연결"),
     **f_data("plot_result", info="④ Heatmap Plotter 연결(이미지 경로)"),
     **f_str("db_url", value="sqlite:///db/eom_results.db")},
    [out("result", "Insert Result", "write", ["Data"])],
    "database", 2340, 300, ["Data"]))


# ── edge 정의 (source_out → target_in) ───────────────────────────────
def edge(src, src_out, src_types, tgt, tgt_in, tgt_types, tgt_field_type="str"):
    sh = {"dataType": src, "id": src, "name": src_out, "output_types": src_types}
    th = {"fieldName": tgt_in, "id": tgt, "inputTypes": tgt_types, "type": tgt_field_type}
    shs, ths = enc_handle(sh), enc_handle(th)
    return {
        "source": src, "target": tgt,
        "sourceHandle": shs, "targetHandle": ths,
        "data": {"sourceHandle": sh, "targetHandle": th},
        "id": f"xy-edge__{src}{shs}-{tgt}{ths}",
        "animated": False, "className": "", "selected": False,
    }


edges = [
    edge("EOMLogLoader", "log_text", ["Message"], "EOMLogSampler", "log_text", ["Message"]),
    edge("EOMLogLoader", "log_text", ["Message"], "EOMJsonBuilder", "log_text", ["Message"]),
    edge("EOMLogSampler", "log_sample", ["Message"], "Prompt", "log_sample", ["Message"]),
    edge("Prompt", "prompt", ["Message"], "LanguageModelComponent", "input_value", ["Message"]),
    edge("LanguageModelComponent", "text_output", ["Message"], "EOMJsonBuilder", "llm_patterns", ["Message"]),
    edge("EOMJsonBuilder", "eom_json", ["Data"], "EOMHeatmapPlotter", "eom_json", ["Data"], "other"),
    edge("EOMJsonBuilder", "eom_json", ["Data"], "EOMMarginCalculator", "eom_json", ["Data"], "other"),
    edge("EOMHeatmapPlotter", "plot_result", ["Data"], "EOMDbWriter", "plot_result", ["Data"], "other"),
    edge("EOMMarginCalculator", "margins", ["Data"], "EOMDbWriter", "margins", ["Data"], "other"),
]

flow = {
    "id": str(uuid.uuid4()),
    "name": "eom_analysis_flow",
    "description": "PAM4 EOM Agent — Loader→Sampler→Prompt→LLM→JSON Builder→(Plotter,Margin)→DB Writer",
    "data": {"nodes": nodes, "edges": edges, "viewport": {"x": 0, "y": 0, "zoom": 0.6}},
    "is_component": False,
    "endpoint_name": None,
}

OUT.write_text(json.dumps(flow, ensure_ascii=False, indent=2), encoding="utf-8")
print(f"wrote {OUT}  ({len(nodes)} nodes, {len(edges)} edges)")
