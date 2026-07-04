# 작업 세션 기록 — 2026-07-04 (4차)

## 세션: ⑥ DB Writer + 스키마 확장

### 결정 사항
- 스키마를 lane × 3-eye 구조로 확장: 1회 변환(run_id) = lane 수 × eye 3개 행
  - 컬럼: run_id, filename, model, json/image path, lane, eye,
    center_x_ui/center_y_mv, width_ui/height_mv, pass, overall_pass,
    params_complete, created_at + 인덱스 2종
- 연결은 SQLAlchemy URL 방식 (sqlite 기본, PostgreSQL 확장 시 URL만 교체)
- SQLAlchemy 미설치 + sqlite URL이면 표준 sqlite3로 자동 fallback
- run_id에 마이크로초 포함 (동일 초 연속 변환 충돌 방지)

### 산출물
- `db/schema.sql` 확정판
- `langflow_components/eom_db_writer.py` 구현 완료
  (입력: ⑤ margins 필수 + ④ plot_result 선택)
- `tests/test_db_writer.py` — 통과 (dual lane 6행 INSERT × 2 run,
  run_id 그룹핑, Fail 행 판별 확인)

### 다음 단계
1. Frontend ↔ Langflow API 연동 (업로드 → flow 실행 → 결과 표시)
2. 결과 조회 화면 DB 연결 + 비교 분석 차트
