-- 移除原始数据表（采集改为仅内存预览，不落库）
-- psql -h 127.0.0.1 -p 5432 -U postgres -d YOUR_DB -f migrate_drop_raw_data.sql

BEGIN;

DROP TABLE IF EXISTS raw_data;

COMMIT;
