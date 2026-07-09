-- 将历史 duty_report.report_type（日报/周报等）迁移为 word / ppt
-- 优先按关联模板 MIME / 文件名推断；其余归为 word

UPDATE duty_report dr
SET report_type = 'ppt'
FROM report_template rt
WHERE dr.template_id = rt.id
  AND dr.report_type IS NOT NULL
  AND dr.report_type NOT IN ('word', 'ppt')
  AND (
      rt.mime_type ILIKE '%presentationml%'
      OR rt.original_filename ILIKE '%.pptx'
  );

UPDATE duty_report dr
SET report_type = 'word'
FROM report_template rt
WHERE dr.template_id = rt.id
  AND dr.report_type IS NOT NULL
  AND dr.report_type NOT IN ('word', 'ppt')
  AND (
      rt.mime_type ILIKE '%wordprocessingml%'
      OR rt.original_filename ILIKE '%.docx'
  );

UPDATE duty_report
SET report_type = 'word'
WHERE report_type IS NULL OR report_type NOT IN ('word', 'ppt');
