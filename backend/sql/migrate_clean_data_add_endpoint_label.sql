-- 给 clean_data 增加可手填的 来源 / 类别 列。
-- 原有 source = 所属配置（endpoint name），category = 入库类别（标签入库流程恒为"标签入库"）。
-- 新列允许在「新增 / 修改」弹窗里直接录入；为空时由后端按 source 反查 endpoint.source_label / category_label 回填。
ALTER TABLE clean_data
    ADD COLUMN IF NOT EXISTS endpoint_source   VARCHAR(64),
    ADD COLUMN IF NOT EXISTS endpoint_category VARCHAR(64);

COMMENT ON COLUMN clean_data.endpoint_source   IS '来源标签（手工填写优先；为空时按 source 反查 endpoint.source_label）';
COMMENT ON COLUMN clean_data.endpoint_category IS '类别标签（手工填写优先；为空时按 source 反查 endpoint.category_label）';
