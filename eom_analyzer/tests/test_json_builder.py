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
from eom_json_builder import (  # noqa: E402
    EOMParseError, build_eom_json, evaluate_candidate, parse_llm_patterns,
    select_and_build,
)

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

# ---------- Test 4: 재선택 — LLM 패턴이 0줄 매칭 → 기본 패턴으로 자동 재선택 ----------
# 구조는 유효하지만 이 로그와는 안 맞는 LLM 패턴
bad_llm = '{"config_pattern": null, "data_pattern": "XYZ(?P<timing>\\\\d+)(?P<voltage>\\\\d+)(?P<error>\\\\d+)", "default_fill": 63}'
r4 = select_and_build(qc_log, bad_llm, "test_qc.log")
assert r4["meta"]["validation"]["chosen"] == "fallback", r4["meta"]["validation"]
assert r4["lanes"]["0"]["matrix"][r4["voltage_steps"].index(0)][r4["timing_steps"].index(0)] == 0
cands4 = r4["meta"]["validation"]["candidates"]
print("Test 4 (재선택 llm→fallback) PASS  chosen=fallback, 후보수=%d" % len(cands4))

# ---------- Test 5: 검증 — error 값 범위 이탈이면 후보 탈락 ----------
oor_log = """p=-1 a=1 e=9999
p=0 a=0 e=8888
p=1 a=-1 e=7777
p=1 a=1 e=6666
"""
oor_pat = {"config_pattern": None,
           "data_pattern": r"p=(?P<timing>-?\d+)\s+a=(?P<voltage>-?\d+)\s+e=(?P<error>\d+)",
           "default_fill": 63}
rep5 = evaluate_candidate(oor_log, oor_pat)
assert rep5["matched_cells"] == 4 and not rep5["passed"], rep5
assert rep5["valid_error_ratio"] == 0.0 and any("범위 이탈" in r for r in rep5["reasons"]), rep5
print("Test 5 (error 범위 이탈 검증) PASS  reasons=%s" % rep5["reasons"])

# ---------- Test 6: 예외처리 — 어느 후보도 파싱 못하면 EOMParseError ----------
try:
    select_and_build("의미 없는 텍스트, 데이터 라인 없음\nfoo bar baz\n", "", "empty.log")
    raise AssertionError("EOMParseError가 발생해야 함")
except EOMParseError as e:
    assert e.report.get("candidates"), "진단 리포트 필요"
    print("Test 6 (전 후보 실패 → EOMParseError) PASS  msg=%s" % str(e)[:40])

# ---------- Test 7: 거대 config 축 방지 ----------
huge_log = """MaxT 100000 MaxV 100000
lane: 0 timing: 0 voltage: 0 error_cnt: 0
lane: 0 timing: 1 voltage: 1 error_cnt: 0
lane: 0 timing: 2 voltage: 2 error_cnt: 0
lane: 0 timing: 3 voltage: 3 error_cnt: 0
"""
huge_pat = {"config_pattern": r"MaxT\s+(?P<timing_max_steps>\d+)\s+MaxV\s+(?P<voltage_max_steps>\d+)",
            "data_pattern": r"lane:\s*(?P<lane>\d+)\s+timing:\s*(?P<timing>-?\d+)\s+voltage:\s*(?P<voltage>-?\d+)\s+error_cnt:\s*(?P<error>\d+)",
            "default_fill": 63}
rep7 = evaluate_candidate(huge_log, huge_pat)
assert not rep7["passed"] and any("축 범위 비정상" in r for r in rep7["reasons"]), rep7
print("Test 7 (거대 config 축 방지) PASS  reasons=%s" % rep7["reasons"])

print("\n전체 테스트 통과")
