-- 为已有 PostgreSQL 库增加「列表路径」「字段映射」列（与 models.CollectEndpoint 一致）
-- psql -h 127.0.0.1 -p 5432 -U postgres -d YOUR_DB -f migrate_collect_endpoint_list_path_field_map.sql

BEGIN;

ALTER TABLE collect_endpoint ADD COLUMN IF NOT EXISTS list_path VARCHAR(512);
ALTER TABLE collect_endpoint ADD COLUMN IF NOT EXISTS field_map_json TEXT;

COMMENT ON COLUMN collect_endpoint.list_path IS '响应 JSON 中记录数组的点号路径，如 data.items；为空则自动识别 data/items 等';
COMMENT ON COLUMN collect_endpoint.field_map_json IS '字段映射 JSON：键为 title/content/raw_value/occur_time/source/category，值为相对每条记录的 JSON 路径';

COMMIT;
