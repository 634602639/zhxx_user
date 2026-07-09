-- 为 collect_endpoint 增加标签字段规则列：{tag_name: json_path}
-- 与原有 field_map_json（系统固定键 title/content/raw_value/...）解耦，
-- 专供"按字段规则一键暂存"读取规则、回写规则。
ALTER TABLE collect_endpoint
    ADD COLUMN IF NOT EXISTS tag_rules_json TEXT;

COMMENT ON COLUMN collect_endpoint.tag_rules_json IS
    '标签字段规则 JSON：{tag_name: json_path}，供"按字段规则一键暂存"使用';

-- 可选：清理历史 stored 暂存记录（新流程入库后即删除，无需保留 stored 状态）
-- 取消下面注释以执行：
-- DELETE FROM collect_tagged_value WHERE status = 'stored';
