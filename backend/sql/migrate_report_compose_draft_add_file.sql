-- 已有库：为 report_compose_draft 增加 Office 文件字段（与下载预览一致的二进制）
BEGIN;

ALTER TABLE report_compose_draft ADD COLUMN IF NOT EXISTS file_blob BYTEA;
ALTER TABLE report_compose_draft ADD COLUMN IF NOT EXISTS file_mime VARCHAR(128);
ALTER TABLE report_compose_draft ADD COLUMN IF NOT EXISTS file_name VARCHAR(255);

COMMENT ON COLUMN report_compose_draft.file_blob IS '替换后的 Office 文件字节（与下载预览一致）';
COMMENT ON COLUMN report_compose_draft.file_mime IS 'file_blob 的 MIME 类型';
COMMENT ON COLUMN report_compose_draft.file_name IS '建议下载文件名';

COMMIT;
