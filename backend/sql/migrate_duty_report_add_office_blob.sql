-- duty_report：存储纠错归档转入的 Office 文件字节（与 report_compose_draft.file_blob 一致）

ALTER TABLE duty_report ADD COLUMN IF NOT EXISTS file_blob BYTEA;
ALTER TABLE duty_report ADD COLUMN IF NOT EXISTS file_mime VARCHAR(128);
ALTER TABLE duty_report ADD COLUMN IF NOT EXISTS file_name VARCHAR(255);
