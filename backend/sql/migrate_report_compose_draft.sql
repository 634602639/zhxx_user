-- 已有库增量：合成草稿表（模板替换结果，非正式报告）
BEGIN;

CREATE TABLE IF NOT EXISTS report_compose_draft (
    id             SERIAL PRIMARY KEY,
    template_id    INTEGER,
    template_name  VARCHAR(128),
    title          VARCHAR(255) NOT NULL,
    content        TEXT,
    status         VARCHAR(32) DEFAULT 'pending_polish',
    bindings_json  TEXT,
    created_at     TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at     TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

COMMENT ON TABLE report_compose_draft IS '模板 X 占位替换后的合成草稿（供纠错润色；非正式 duty_report）';

COMMIT;
