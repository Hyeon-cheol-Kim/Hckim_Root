# 작업 세션 기록 — 2026-07-04

## 세션: PAM4 EOM Analysis System 전체 구조 설계

### 요구사항 정리
- PAM4 EOM Test log → JSON 변환 → heatmap plotting → eye H/W margin DB 저장 → 비교 분석
- Web URL 접속, 첫 화면: ①log 입력 메뉴 ②DB 조회 메뉴
- LLM(선택형)으로 voltage step / timing step / error count 및 유사 키워드 파싱
- JSON: V step=세로축, T step=가로축 matrix, 셀=error count
- Plot: error==0 파란색 / !=0 빨간색

### 결정 사항
| 항목 | 결정 |
|------|------|
| Frontend | FastAPI + HTML (다크 네이비/틸) |
| DB | Langflow SQL Database 컴포넌트 + SQLite (`sqlite:///db/eom_results.db`) |
| LLM | Claude + OpenAI + Ollama 선택형 |
| 버전 | Langflow 1.9.1 / Python 3.12.13 |

### 산출물 (스켈레톤)
- README.md, requirements 안내
- frontend/main.py + templates 3종 (index/upload/results)
- langflow_components 4종 (json_builder / heatmap_plotter / margin_calculator / db_writer)
- db/schema.sql, flows/eom_analysis_flow.md

### 다음 단계 (미구현 TODO)
1. LLM Parser 프롬프트 + 모델 선택 방식 확정
2. JSON Builder 상세 로직
3. Heatmap Plotter 상세 (matplotlib)
4. Margin 계산 알고리즘 (eye center 정의 포함)
5. DB Writer / Frontend-Langflow API 연동
6. 비교 차트 화면
