"""
③ EOM JSON Builder - Langflow 1.9.1 Custom Component (하이브리드 방식)

② LLM이 식별한 정규식 패턴(JSON)을 받아 Python이 전체 로그에서 숫자를 추출,
V(row) x T(col) matrix JSON을 생성한다.

참고: eom_final_package_parser.py (CSV 변환 기본 코드)의 로직을 승계
  - config 헤더: TimingMaxSteps / TimingMaxOffset / VoltageMaxSteps / VoltageMaxOffset
  - 데이터 라인: lane / timing / voltage / error_cnt
  - 중복 (t,v) 병합: 63(fill)이 아닌 유효값 우선, 유효값끼리는 작은 값 우선
  - 누락 셀 기본값: 63
  - 축: timing -t_max~+t_max (가로), voltage +v_max→-v_max 내림차순 (세로)

LLM 패턴 파싱 실패 시 위 기본(QC 포맷) 패턴으로 fallback.
"""
import json
import re
from datetime import datetime
from pathlib import Path

# ---------------------------------------------------------------
# 순수 함수부 (Langflow 없이 단독 테스트 가능)
# ---------------------------------------------------------------

# 참고 코드(QC 포맷) 기반 fallback 패턴
DEFAULT_CONFIG_PATTERN = (
    r"TimingMaxSteps\s+(?P<timing_max_steps>\d+)\s+"
    r"TimingMaxOffset\s+(?P<timing_max_offset>\d+)\s+"
    r"VoltageMaxSteps\s+(?P<voltage_max_steps>\d+)\s+"
    r"VoltageMaxOffset\s+(?P<voltage_max_offset>\d+)"
)
DEFAULT_DATA_PATTERN = (
    r"lane:\s*(?P<lane>\d+)\s+timing:\s*(?P<timing>-?\d+)\s+"
    r"voltage:\s*(?P<voltage>-?\d+)\s+error_cnt:\s*(?P<error>\d+)"
)
DEFAULT_FILL = 63


def parse_llm_patterns(llm_text: str) -> tuple[dict, str]:
    """LLM 응답(JSON 문자열)에서 패턴 추출. 실패 시 fallback.

    Returns: (patterns dict, source: 'llm' | 'fallback')
    """
    fallback = {
        "config_pattern": DEFAULT_CONFIG_PATTERN,
        "data_pattern": DEFAULT_DATA_PATTERN,
        "default_fill": DEFAULT_FILL,
    }
    if not llm_text:
        return fallback, "fallback"
    # 마크다운 코드펜스 제거 후 첫 { ~ 마지막 } 구간 파싱
    cleaned = re.sub(r"```(json)?", "", llm_text).strip()
    start, end = cleaned.find("{"), cleaned.rfind("}")
    if start == -1 or end == -1:
        return fallback, "fallback"
    try:
        p = json.loads(cleaned[start : end + 1])
    except json.JSONDecodeError:
        return fallback, "fallback"

    data_pattern = p.get("data_pattern")
    if not data_pattern:
        return fallback, "fallback"
    # 필수 named group 검증 + 정규식 컴파일 검증
    try:
        compiled = re.compile(data_pattern)
    except re.error:
        return fallback, "fallback"
    required = {"timing", "voltage", "error"}
    if not required.issubset(compiled.groupindex.keys()):
        return fallback, "fallback"

    cfg_pattern = p.get("config_pattern")
    if cfg_pattern:
        try:
            re.compile(cfg_pattern)
        except re.error:
            cfg_pattern = None

    return {
        "config_pattern": cfg_pattern,
        "data_pattern": data_pattern,
        "default_fill": int(p.get("default_fill", DEFAULT_FILL)),
    }, "llm"


def extract_lane_data(text: str, patterns: dict) -> tuple[dict, dict]:
    """전체 로그에서 lane별 {(t, v): error} 맵과 config 추출."""
    fill = patterns["default_fill"]
    config = {}
    if patterns.get("config_pattern"):
        m = re.search(patterns["config_pattern"], text)
        if m:
            config = {k: int(v) for k, v in m.groupdict().items() if v is not None}

    re_data = re.compile(patterns["data_pattern"])
    lane_data: dict[int, dict] = {}
    for line in text.splitlines():
        m = re_data.search(line)
        if not m:
            continue
        g = m.groupdict()
        lane = int(g.get("lane") or 0)
        t, v, val = int(g["timing"]), int(g["voltage"]), int(g["error"])
        cur = lane_data.setdefault(lane, {})
        key = (t, v)
        # 참고 코드의 병합 규칙: fill(63) 아닌 유효값 우선, 더 작은 값 우선
        if (
            key not in cur
            or (cur[key] == fill and val != fill)
            or (val != fill and val < cur[key])
        ):
            cur[key] = val
    return lane_data, config


def build_axes(lane_data: dict, config: dict) -> tuple[list[int], list[int]]:
    """timing(가로, 오름차순) / voltage(세로, 내림차순) 축 생성.

    config 헤더가 있으면 MaxSteps 기준(-max~+max), 없으면 관측값 min/max 기준.
    """
    if "timing_max_steps" in config and "voltage_max_steps" in config:
        t_max, v_max = config["timing_max_steps"], config["voltage_max_steps"]
        t_axis = list(range(-t_max, t_max + 1))
        v_axis = list(range(v_max, -v_max - 1, -1))
        return t_axis, v_axis
    all_keys = [k for d in lane_data.values() for k in d.keys()]
    ts = sorted({t for t, _ in all_keys})
    vs = sorted({v for _, v in all_keys}, reverse=True)
    return ts, vs


def build_eom_json(
    text: str, patterns: dict, pattern_source: str, source_file: str, llm_model: str = ""
) -> dict:
    lane_data, config = extract_lane_data(text, patterns)
    if not lane_data:
        raise ValueError(
            "데이터 라인을 하나도 추출하지 못했습니다. "
            f"data_pattern을 확인하세요: {patterns['data_pattern']}"
        )
    t_axis, v_axis = build_axes(lane_data, config)
    fill = patterns["default_fill"]

    lanes = {}
    for lane_id in sorted(lane_data.keys()):
        cur = lane_data[lane_id]
        matrix = [[cur.get((t, v), fill) for t in t_axis] for v in v_axis]
        lanes[str(lane_id)] = {"matrix": matrix}

    return {
        "meta": {
            "source_file": source_file,
            "parsed_at": datetime.now().isoformat(timespec="seconds"),
            "pattern_source": pattern_source,  # 'llm' | 'fallback'
            "llm_model": llm_model,
            "lane_mode": "DualLane" if {0, 1}.issubset(lane_data.keys())
            else f"SingleLane {sorted(lane_data.keys())}",
        },
        "config": config,
        "timing_steps": t_axis,     # 가로축 (col)
        "voltage_steps": v_axis,    # 세로축 (row, 내림차순)
        "default_fill": fill,
        "lanes": lanes,
    }


def read_text_any_encoding(path: str) -> str:
    raw = Path(path).read_bytes()
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        try:
            import chardet

            enc = chardet.detect(raw)["encoding"] or "cp949"
        except ImportError:
            enc = "cp949"
        return raw.decode(enc, errors="replace")


# ---------------------------------------------------------------
# Langflow 컴포넌트부
# ---------------------------------------------------------------
from langflow.custom import Component
from langflow.io import MessageTextInput, Output
from langflow.schema import Data


class EOMJsonBuilder(Component):
    display_name = "EOM JSON Builder"
    description = "LLM 식별 패턴 + Python 추출로 V(row) x T(col) matrix JSON 생성"
    icon = "braces"
    name = "EOMJsonBuilder"

    inputs = [
        MessageTextInput(
            name="llm_patterns",
            display_name="LLM Pattern Output",
            info="② Language Model이 반환한 패턴 JSON",
        ),
        MessageTextInput(
            name="log_text",
            display_name="Log Text",
            info="① EOM Log Loader의 log_text 출력 연결 (전체 로그 원문)",
        ),
        MessageTextInput(
            name="source_file",
            display_name="Source File Name",
            value="",
            info="원본 로그 파일명 (meta/JSON 파일명용, Frontend가 tweaks로 전달)",
        ),
        MessageTextInput(
            name="output_dir",
            display_name="JSON Output Dir",
            value="storage/json",
        ),
        MessageTextInput(
            name="llm_model",
            display_name="LLM Model Name",
            value="",
            info="meta 기록용 (claude/openai/ollama)",
        ),
    ]

    outputs = [
        Output(display_name="EOM JSON", name="eom_json", method="build"),
    ]

    def build(self) -> Data:
        patterns, source = parse_llm_patterns(self.llm_patterns)
        text = self.log_text or ""
        source_file = self.source_file or "eom_log.txt"
        result = build_eom_json(
            text, patterns, source, Path(source_file).name, self.llm_model or ""
        )

        out_dir = Path(self.output_dir or "storage/json")
        out_dir.mkdir(parents=True, exist_ok=True)
        stem = Path(source_file).stem
        json_path = out_dir / f"{stem}.json"
        json_path.write_text(
            json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
        )

        result["meta"]["json_path"] = str(json_path)
        self.status = (
            f"pattern={source}, lanes={list(result['lanes'].keys())}, "
            f"grid={len(result['voltage_steps'])}x{len(result['timing_steps'])}"
        )
        return Data(data=result)
