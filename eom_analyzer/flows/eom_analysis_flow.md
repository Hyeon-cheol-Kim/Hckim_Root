# eom_analysis_flow — Langflow 1.9.1 조립 가이드

> **재구성됨**: 컴포넌트 단위 재분해 + import용 flow JSON은
> [`eom_flow_architecture.md`](eom_flow_architecture.md) 및
> [`eom_analysis_flow.json`](eom_analysis_flow.json) 참조.
> 아래는 초기 개념 가이드(기록용).


Langflow UI에서 아래 순서로 노드를 배치하고 연결합니다.
(flow JSON export는 flow 확정 후 이 폴더에 저장 예정)

## 노드 구성

| # | 노드 | 종류 | 역할 |
|---|------|------|------|
| ① | File | 기본 컴포넌트 | EOM log 파일 입력 |
| ② | Language Model | 기본 (Anthropic / OpenAI / Ollama) | 키워드·유사어 파싱. Prompt 컴포넌트와 연결 |
| ③ | EOM JSON Builder | 커스텀 | V(row) x T(col) matrix JSON 생성·저장 |
| ④ | EOM Heatmap Plotter | 커스텀 | blue(0)/red(!=0) 이미지 생성 |
| ⑤ | EOM Margin Calculator | 커스텀 | height/width margin 계산 |
| ⑥ | EOM DB Writer 또는 SQL Database | 커스텀/기본 | SQLite INSERT |

## 연결 (하이브리드 파싱 구조 — 확정)

LLM은 로그 **샘플**에서 키워드/정규식 패턴만 식별하고,
전체 로그의 숫자 추출은 ③ JSON Builder(Python)가 수행한다.

```
file_path (tweaks)
   ├─▶ ②a EOM Log Sampler ──▶ Prompt(eom_pattern_prompt.txt) ──▶ Language Model(②)
   │                                                                   │ 패턴 JSON
   └───────────────────────────────────────────────▶ ③ EOM JSON Builder ◀┘
                                                          │ matrix JSON (lane별)
                                          ┌───────────────┴─▶ ④ Heatmap Plotter ──┐
                                          └─▶ ⑤ Margin Calc ──────────▶ ⑥ DB Writer
```

- Prompt 컴포넌트 template에 `flows/prompts/eom_pattern_prompt.txt` 내용 사용
  (변수: `{log_sample}` ← ②a 출력 연결)
- ③은 LLM 패턴이 잘못되면 QC 기본 포맷 정규식으로 자동 fallback
- ④/⑤는 공용 코어(eom_eye_core.py) 사용: 참고 코드(PAM4_eye_diagram_converter.py)의
  좌표 변환·3-eye 중심 탐지·마진 계산·시각화 로직 승계
- ⑥ EOM DB Writer 입력 2개: ⑤ margins(필수) + ④ plot_result(선택, 이미지 경로 기록용)
  → eom_results 테이블에 run_id 그룹으로 lane × 3-eye 행 INSERT
  (SQLAlchemy URL, sqlite 기본 / SQLAlchemy 미설치 시 sqlite3 fallback)
- 중복 (t,v) 병합 규칙 / fill=63 / 축 방향은 참고 코드(eom_final_package_parser.py) 승계

## LLM 모델 선택 방식 (디테일 단계 확정 예정)
- 1안: 3개 모델 노드 + 조건 분기, Frontend에서 tweaks로 선택 전달
- 2안: Langflow의 Language Model 통합 컴포넌트에서 provider tweak

## Frontend 연동 (구현 완료)
- POST `{LANGFLOW_URL}/api/v1/run/{flow_id}`
  tweaks 키는 컴포넌트 ID와 일치 필요:
  `EOMLogSampler.file_path`, `EOMJsonBuilder.file_path/llm_model`
  (+ LLM provider 전환은 flow 조립 후 Language Model 컴포넌트 ID로 추가)
- flow 완료 후 Frontend는 응답 파싱 대신 **DB에서 최신 run_id 재조회** →
  이미지/마진 표시 (응답 스키마 변화에 견고)
- /results: 필터(파일/lane/eye) + 테이블 + 차트 A(W/H 산점도, Fail zone)
  + 차트 B(run별 W/H 추이, Chart.js 4.4.1 cdnjs)
