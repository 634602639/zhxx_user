-- 移除 duty_report.keywords / duty_report.location（与 ORM 同步）
-- psql -h 127.0.0.1 -p 5432 -U postgres -d YOUR_DB -f migrate_duty_report_drop_keywords_location.sql

ALTER TABLE duty_report DROP COLUMN IF EXISTS keywords;
ALTER TABLE duty_report DROP COLUMN IF EXISTS location;
