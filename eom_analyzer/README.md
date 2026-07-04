# PAM4 EOM Agent

PAM4 EOM Test log → LLM 파싱(JSON) → Heatmap Plot → Eye Margin 계산 → DB 저장 → 비교 분석

## 환경
- Langflow **1.9.1**
- Python **3.12.13**
- DB: SQLite (Langflow SQL Database 컴포넌트, SQLAlchemy 연결 문자열 사용)
- LLM: Claude / OpenAI / Ollama (선택 가능)

## 전체 구조

```
[Web Frontend: FastAPI + HTML]  ← 사용자는 web URL로 접속
 ├─ 메뉴1: EOM Log 파일 업로드
 └─ 메뉴2: DB 결과 조회 / 비교 차트
        │  REST API (Langflow /api/v1/run/{flow_id})
        ▼
[Langflow 1.9.1 Flow: eom_analysis_flow]
 ① File Input (EOM log)
 ② LLM Parser        - 모델 선택(Claude/OpenAI/Ollama)
                       voltage step / timing step / error count
                       (또는 유사 키워드) 추출
 ③ EOM JSON Builder  - V step=세로축(row), T step=가로축(col)
                       matrix[row][col] = error count 인 JSON 생성
 ④ Heatmap Plotter   - error==0 → 파란색 / error!=0 → 빨간색
 ⑤ Margin Calculator - eye height margin / width margin 계산
 ⑥ DB Writer         - SQL Database 컴포넌트로 결과 INSERT
        ▼
[SQLite DB: eom_results.db]
        ▼
[분석 화면] DB 누적 결과 → 그래프/차트 비교
```

## 디렉터리

```
eom_analyzer/
├── frontend/
│   ├── main.py              # FastAPI 앱 (업로드/조회 메뉴)
│   └── templates/           # index / upload / results HTML
├── langflow_components/     # Langflow 커스텀 컴포넌트 (4종)
│   ├── eom_json_builder.py
│   ├── eom_heatmap_plotter.py
│   ├── eom_margin_calculator.py
│   └── eom_db_writer.py
├── flows/
│   └── eom_analysis_flow.md # Flow 구성 가이드 (Langflow에서 조립)
├── db/
│   └── schema.sql           # 결과 테이블 스키마
├── storage/                 # uploads / json / images 저장
└── docs/                    # 세션 작업 기록
```

## 실행 (스켈레톤 기준)

```bash
pip install fastapi uvicorn jinja2 python-multipart httpx matplotlib numpy chardet langflow==1.9.1
# 1) Langflow 실행 (커스텀 컴포넌트 경로 지정)
LANGFLOW_COMPONENTS_PATH=./langflow_components langflow run
# 2) Langflow UI에서 flow 조립 후 flow ID 확인 (flows/eom_analysis_flow.md 참조)
# 3) Frontend 실행 (프로젝트 루트에서)
export LANGFLOW_URL=http://localhost:7860
export EOM_FLOW_ID=<flow ID>
uvicorn frontend.main:app --reload --port 8000
```

Langflow 없이 결과 화면(/results)만 먼저 보려면 데모 데이터 시드:
```bash
python3 tests/seed_and_test_frontend.py --seed db/eom_results.db
```

## 구현 상태 (전 단계 완료)
- [x] 전체 구조 / 스켈레톤
- [x] ②a Log Sampler + ② LLM 패턴 프롬프트 (하이브리드 파싱)
- [x] ③ JSON Builder (lane별 matrix, fallback 포함)
- [x] ④ Heatmap Plotter (3-eye 마스크/마진 박스/컬러바)
- [x] ⑤ Margin Calculator (Pass/Fail 판정)
- [x] ⑥ DB Writer (lane × 3-eye 스키마, run_id 그룹)
- [x] Frontend ↔ Langflow API 연동 (업로드 → flow → 결과 표시)
- [x] 비교 차트 (A: W/H 산점도 + Fail zone, B: run별 추이)
