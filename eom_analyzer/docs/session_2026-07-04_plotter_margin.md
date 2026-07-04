# 작업 세션 기록 — 2026-07-04 (3차)

## 세션: ④ Heatmap Plotter + ⑤ Margin Calculator 구현

### 참고 코드
- GitHub: Hckim_Root / PAM4_eye_diagram_converter.py (CSV+QC_Offsets → 이미지 기본 코드)
- 승계 로직:
  - 좌표 변환: X(UI)=idx/TimingMaxSteps×TimingMaxOffset/100,
    Y(mV)=idx/VoltageMaxSteps×VoltageMaxOffset×10
  - PAM4 3-eye 영역: Upper(>130mV)/Middle(±130mV)/Lower(<-130mV) + fallback 중심
  - 중심 탐지: 영역 내 최장 연속-0 행(동점 시 중간 행) → cy, 구간 중앙 → cx
  - Width(UI)=기준 행 연속-0 구간, Height(mV)=cx 열의 cy 포함 클러스터(gap>1.5step 분리)
  - 색상: 0=파랑/≥1=빨강(1/63 급전환), 격자선, 컬러바, 마름모 마스크(±0.12UI×±25mV),
    마진 박스(우상단)/파라미터 박스(좌하단), 다크 배경, lane별 PNG(dpi 150)

### 결정 사항
- 참고 코드 시각화 전체 승계 (단순화 버전 대신)
- ④/⑤ 공용 로직을 `eom_eye_core.py`로 분리 (계산 결과 일치 보장)
- config 누락 시 기본 Offset(T=40, V=30)으로 환산 + `params_complete=false` 플래그
- ⑤에 Pass/Fail 판정 추가: W ≤ 0.24 UI 또는 H ≤ 50 mV → Fail (참고 코드 기준)
- ⑥ DB 스키마는 3-eye × lane 구조로 확장 필요 (다음 단계에서 반영)

### 산출물
- `langflow_components/eom_eye_core.py` (신규 공용 코어)
- `langflow_components/eom_heatmap_plotter.py` (구현 완료)
- `langflow_components/eom_margin_calculator.py` (구현 완료)
- `tests/test_eye_core.py` — 합성 127×127 3-eye 데이터 검증 통과
  (노이즈 셀이 최장 연속-0 행을 끊는 경우의 회피 동작 포함, PNG 시각 확인 완료)

### 다음 단계
1. ⑥ DB Writer + schema 확장 (lane × 3-eye × W/H, pass/fail)
2. Frontend ↔ Langflow API 연동
3. 비교 분석 차트 화면
