-- 合成草稿：润色状态说明（正在润色 / 完成摘要 / 失败原因）
BEGIN;

ALTER TABLE report_compose_draft ADD COLUMN IF NOT EXISTS status_detail VARCHAR(512);

COMMENT ON COLUMN report_compose_draft.status IS 'pending_polish=待润色；polishing=正在润色；polished=润色完成；polish_error=润色失败';
COMMENT ON COLUMN report_compose_draft.status_detail IS '润色进度或失败原因（列表展示）';

COMMIT;
