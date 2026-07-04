-- PAM4 EOM 결과 테이블 (lane × 3-eye 구조, 확정)
-- 1회 변환(run) = run_id 1개 = lane 수 × eye 3개 행
CREATE TABLE IF NOT EXISTS eom_results (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id          TEXT NOT NULL,          -- 변환 1회 그룹 ID (파일명+시각)
    filename        TEXT NOT NULL,          -- 원본 log 파일명
    model           TEXT,                   -- 파싱 LLM (claude/openai/ollama)
    json_path       TEXT,                   -- 변환 JSON 경로
    image_path      TEXT,                   -- 해당 lane heatmap 이미지 경로
    lane            TEXT NOT NULL,          -- Lane0 / Lane1
    eye             TEXT NOT NULL,          -- Upper / Middle / Lower
    center_x_ui     REAL,                   -- eye 중심 X (UI)
    center_y_mv     REAL,                   -- eye 중심 Y (mV)
    width_ui        REAL,                   -- Width margin (UI)
    height_mv       REAL,                   -- Height margin (mV)
    pass            INTEGER,                -- eye별 Pass=1/Fail=0 (W>0.24UI AND H>50mV)
    overall_pass    INTEGER,                -- run 전체 Pass 여부
    params_complete INTEGER,                -- config 완전 추출=1 / 기본 Offset 환산=0
    created_at      TEXT DEFAULT (datetime('now', 'localtime'))
);

CREATE INDEX IF NOT EXISTS idx_eom_results_run  ON eom_results(run_id);
CREATE INDEX IF NOT EXISTS idx_eom_results_file ON eom_results(filename);
