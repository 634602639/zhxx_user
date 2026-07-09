-- 增加「采集标签暂存」表：collect_tagged_value
-- psql -h 127.0.0.1 -p 5432 -U postgres -d YOUR_DB -f migrate_add_collect_tagged_value.sql

BEGIN;

CREATE TABLE IF NOT EXISTS collect_tagged_value (
    id             SERIAL PRIMARY KEY,
    endpoint_id    INTEGER,
    endpoint_name  VARCHAR(128),
    tag            VARCHAR(64) NOT NULL,
    value          TEXT NOT NULL,
    source_excerpt TEXT,
    status         VARCHAR(16) DEFAULT 'pending',
    created_at     TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    stored_at      TIMESTAMP WITHOUT TIME ZONE
);

COMMENT ON TABLE collect_tagged_value IS '采集预览中手工截取的标签值（暂存区，后续可入库 CleanData）';
COMMENT ON COLUMN collect_tagged_value.id IS '主键';
COMMENT ON COLUMN collect_tagged_value.endpoint_id IS '采集配置 ID（CollectEndpoint.id，可空）';
COMMENT ON COLUMN collect_tagged_value.endpoint_name IS '采集配置名称（便于展示）';
COMMENT ON COLUMN collect_tagged_value.tag IS '标签（用户手工填写）';
COMMENT ON COLUMN collect_tagged_value.value IS '选中的中间部分值（待后续入库）';
COMMENT ON COLUMN collect_tagged_value.source_excerpt IS '选中内容来源（该条 item_raw_json 的节选，便于追溯）';
COMMENT ON COLUMN collect_tagged_value.status IS '状态：pending/stored';
COMMENT ON COLUMN collect_tagged_value.created_at IS '暂存时间';
COMMENT ON COLUMN collect_tagged_value.stored_at IS '入库时间';

COMMIT;

