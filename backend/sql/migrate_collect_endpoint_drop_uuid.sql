-- 已有库曾包含 uuid 列时执行一次，移除采集配置的 UUID（保留 id）
-- psql -h 127.0.0.1 -p 5432 -U postgres -d zonghexinxi -f migrate_collect_endpoint_drop_uuid.sql

BEGIN;

DROP INDEX IF EXISTS ix_collect_endpoint_uuid;

ALTER TABLE collect_endpoint DROP COLUMN IF EXISTS uuid;

COMMIT;
