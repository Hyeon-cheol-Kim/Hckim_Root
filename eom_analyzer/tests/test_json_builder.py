"""EOM JSON Builder 단독 검증 (langflow 미설치 환경용 mock 포함)"""
import json
import sys
import types
from pathlib import Path

# --- langflow 모듈 mock (순수 함수 테스트 목적) ---
for mod in ["langflow", "langflow.custom", "langflow.io", "langflow.schema"]:
    sys.modules.setdefault(mod, types.ModuleType(mod))
sys.modules["langflow.custom"].Component = object
for n in ["MessageTextInput", "IntInput", "Output"]:
    setattr(sys.modules["langflow.io"], n, lambda *a, **k: None)
sys.modules["langflow.schema"].Data = dict

sys.path.insert(0, str(Path(__file__).parent.parent / "langflow_components"))
from eom_json_builder import build_eom_json, parse_llm_patterns  # noqa: E402

# ---------- Test 1: QC 포맷 + fallback 패턴 (LLM 응답 없음) ----------
qc_log = """EOM Final Package Test
TimingMaxSteps 3 TimingMaxOffset 100 VoltageMaxSteps 2 VoltageMaxOffset 200
lane: 0 timing: -3 voltage: 2 error_cnt: 63
lane: 0 timing: 0 voltage: 0 error_cnt: 0
lane: 0 timing: 0 voltage: 0 error_cnt: 5
lane: 0 timing: 1 voltage: 1 error_cnt: 63
lane: 0 timing: 1 voltage: 1 error_cnt: 7
lane: 1 timing: 0 voltage: 0 error_cnt: 0
"""
patterns, src = parse_llm_patterns("")
assert src == "fallback"
r = build_eom_json(qc_log, patterns, src, "test_qc.log")
assert r["timing_steps"] == [-3, -2, -1, 0, 1, 2, 3]
assert r["voltage_steps"] == [2, 1, 0, -1, -2]
assert r["meta"]["lane_mode"] == "DualLane"
m0 = r["lanes"]["0"]["matrix"]
# (t=0,v=0): 0과 5 중복 → 작은 값 0 유지 / (t=1,v=1): 63→7 병합
assert m0[r["voltage_steps"].index(0)][r["timing_steps"].index(0)] == 0
assert m0[r["voltage_steps"].index(1)][r["timing_steps"].index(1)] == 7
# 미측정 셀 = 63
assert m0[0][0] == 63
print("Test 1 (QC fallback) PASS")
print("  lane0 matrix:")
for row in m0:
    print("   ", row)

# ---------- Test 2: 유사 키워드 포맷 + LLM 패턴 응답 시뮬레이션 ----------
alt_log = """PAM4 Eye Scan Result
ln=0 phase= -1 amp= 1 errs= 0
ln=0 phase= 0 amp= 0 errs= 0
ln=0 phase= 1 amp= -1 errs= 12
"""
llm_resp = """```json
{"config_pattern": null,
 "data_pattern": "ln=(?P<lane>\\\\d+)\\\\s+phase=\\\\s*(?P<timing>-?\\\\d+)\\\\s+amp=\\\\s*(?P<voltage>-?\\\\d+)\\\\s+errs=\\\\s*(?P<error>\\\\d+)",
 "default_fill": 63}
```"""
patterns2, src2 = parse_llm_patterns(llm_resp)
assert src2 == "llm", f"expected llm, got {src2}"
r2 = build_eom_json(alt_log, patterns2, src2, "test_alt.log", "claude")
assert r2["timing_steps"] == [-1, 0, 1]      # config 없음 → 관측값 기준
assert r2["voltage_steps"] == [1, 0, -1]
assert r2["lanes"]["0"]["matrix"][2][2] == 12
print("Test 2 (LLM pattern, 유사 키워드) PASS")
print("  lane0 matrix:")
for row in r2["lanes"]["0"]["matrix"]:
    print("   ", row)

# ---------- Test 3: 잘못된 LLM 응답 → fallback ----------
p3, s3 = parse_llm_patterns("정규식은 다음과 같습니다: timing.*")
assert s3 == "fallback"
p4, s4 = parse_llm_patterns('{"data_pattern": "(?P<timing>\\\\d+)"}')  # 필수 group 누락
assert s4 == "fallback"
print("Test 3 (invalid LLM → fallback) PASS")

print("\n전체 테스트 통과")
