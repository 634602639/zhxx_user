-- 把模板文件直接存进 report_template 表，去掉对本地磁盘的依赖。
-- 旧行 file_path 仍然保留可读；新上传的会写到 file_blob，磁盘文件可选保留作为缓存。
ALTER TABLE report_template
    ADD COLUMN IF NOT EXISTS file_blob         BYTEA,
    ADD COLUMN IF NOT EXISTS file_size         INTEGER,
    ADD COLUMN IF NOT EXISTS mime_type         VARCHAR(128),
    ADD COLUMN IF NOT EXISTS original_filename VARCHAR(255);

COMMENT ON COLUMN report_template.file_blob         IS '原始文件字节内容（直接存库，下载时回写）';
COMMENT ON COLUMN report_template.file_size         IS '文件字节数';
COMMENT ON COLUMN report_template.mime_type         IS 'MIME 类型，下载时用作 Content-Type';
COMMENT ON COLUMN report_template.original_filename IS '上传时的原始文件名';
