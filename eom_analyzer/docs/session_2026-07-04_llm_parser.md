# 작업 세션 기록 — 2026-07-04 (2차)

## 세션: ② LLM Parser + ③ JSON Builder 구현 (하이브리드 방식)

### 참고 코드
- GitHub: Hckim_Root / eom_final_package_parser.py (log→CSV 변환 기본 코드)
- 승계한 로직: QC config 헤더(TimingMaxSteps 등) / lane별 분리 /
  중복 (t,v) 병합(63 아닌 유효값 우선, 작은 값 우선) / 미측정 fill=63 /
  timing 가로 -max~+max, voltage 세로 +max→-max 내림차순 / chardet 인코딩 처리

### 결정 사항
- **하이브리드 파싱** 채택: LLM은 로그 샘플에서 키워드·정규식 패턴만 식별(named group),
  전체 로그 숫자 추출은 Python 수행 → 정확·저비용
- LLM 응답 불량 시 QC 기본 패턴 자동 fallback
- JSON 스키마 변경: lane 구조 추가 (`lanes: {"0": {matrix}, "1": {matrix}}`)

### 산출물
- `langflow_components/eom_log_sampler.py` (신규, ②a)
- `langflow_components/eom_json_builder.py` (스켈레톤 → 구현 완료)
- `flows/prompts/eom_pattern_prompt.txt` (LLM 패턴 식별 프롬프트)
- `flows/eom_analysis_flow.md` 연결 구조 갱신
- `tests/test_json_builder.py` — 3종 테스트 통과
  (QC fallback / 유사 키워드 LLM 패턴 / 불량 응답 fallback)

### 다음 단계
1. ④ Heatmap Plotter 상세 (blue/red, lane별 이미지)
2. ⑤ Margin 계산 알고리즘
3. ⑥ DB Writer / Frontend 연동
- 산출물 추가: docs/EOM_Analysis_System_Overview.pptx (전체 시스템 설명 자료, 매 작업 완료 시 갱신 예정)
