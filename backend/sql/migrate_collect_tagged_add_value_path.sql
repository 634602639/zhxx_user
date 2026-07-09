-- 给 collect_tagged_value 增加 value_path，用于“按历史标签一键暂存”
-- psql -h 127.0.0.1 -p 5432 -U postgres -d YOUR_DB -f migrate_collect_tagged_add_value_path.sql

BEGIN;

ALTER TABLE collect_tagged_value ADD COLUMN IF NOT EXISTS value_path VARCHAR(512);
COMMENT ON COLUMN collect_tagged_value.value_path IS '从 item_raw_json 识别的字段路径；后续可按此路径一键自动暂存';

COMMIT;

