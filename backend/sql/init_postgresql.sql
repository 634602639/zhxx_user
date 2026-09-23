-- ============================================================================
-- 综合信息服务中心 · PostgreSQL 初始化脚本
-- 连接参数（与应用 config 默认一致）：host=127.0.0.1 port=5432 db=zonghexinxi_suojian user=postgres
-- Qt 侧 databaseType=QPSQL；Python/SQLAlchemy 侧驱动为 psycopg2。
--
-- 【请先创建数据库，仅需一次】在 postgres 库下执行：
--   CREATE DATABASE zonghexinxi_suojian ENCODING 'UTF8';
--
-- 【再执行本脚本】：
--   psql -h 127.0.0.1 -p 5432 -U postgres -d zonghexinxi_suojian -f init_postgresql.sql
-- Windows 可先: set PGPASSWORD=2020
-- ============================================================================

BEGIN;

-- ---------- clean_data ----------
CREATE TABLE IF NOT EXISTS clean_data (
    id            SERIAL PRIMARY KEY,
    source        VARCHAR(64),
    category      VARCHAR(64),
    title         VARCHAR(255),
    content       TEXT,
    metric_value  DOUBLE PRECISION,
    occur_time    TIMESTAMP WITHOUT TIME ZONE,
    tags          VARCHAR(255),
    endpoint_source   VARCHAR(64),
    endpoint_category VARCHAR(64),
    created_at    TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

COMMENT ON TABLE clean_data IS '清洗与转换后入库的标准化业务数据';
COMMENT ON COLUMN clean_data.endpoint_source   IS '来源标签（手工填写优先；为空时按 source 反查 endpoint.source_label）';
COMMENT ON COLUMN clean_data.endpoint_category IS '类别标签（手工填写优先；为空时按 source 反查 endpoint.category_label）';
COMMENT ON COLUMN clean_data.id IS '主键';
COMMENT ON COLUMN clean_data.source IS '数据来源系统标识';
COMMENT ON COLUMN clean_data.category IS '业务类别';
COMMENT ON COLUMN clean_data.title IS '标题';
COMMENT ON COLUMN clean_data.content IS '正文内容';
COMMENT ON COLUMN clean_data.metric_value IS '标准化后的数值度量';
COMMENT ON COLUMN clean_data.occur_time IS '数据对应时间（业务真实产生时间，填入报告用此时间）';
COMMENT ON COLUMN clean_data.tags IS '标签（可多值语义，应用中常以分隔符存储）';
COMMENT ON COLUMN clean_data.created_at IS '采集时间（写入本系统的时间）';

-- ---------- report_template ----------
CREATE TABLE IF NOT EXISTS report_template (
    id                 SERIAL PRIMARY KEY,
    name               VARCHAR(128),
    file_path          VARCHAR(255),
    file_blob          BYTEA,
    file_size          INTEGER,
    mime_type          VARCHAR(128),
    original_filename  VARCHAR(255),
    content            TEXT,
    keywords           VARCHAR(512),
    created_at         TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

COMMENT ON TABLE report_template IS '值勤报告模板（支持占位符替换的正文模板）';
COMMENT ON COLUMN report_template.id IS '主键';
COMMENT ON COLUMN report_template.name IS '模板名称';
COMMENT ON COLUMN report_template.file_path IS '兼容旧数据：若来源于本地文件，保存路径';
COMMENT ON COLUMN report_template.file_blob IS '原始文件字节内容（直接存库，下载时回写）';
COMMENT ON COLUMN report_template.file_size IS '文件字节数';
COMMENT ON COLUMN report_template.mime_type IS 'MIME 类型，下载时用作 Content-Type';
COMMENT ON COLUMN report_template.original_filename IS '上传时的原始文件名';
COMMENT ON COLUMN report_template.content IS '模板正文纯文本，可含占位符如 {{变量名}}';
COMMENT ON COLUMN report_template.keywords IS '自动提取的关键词列表，逗号分隔存储';
COMMENT ON COLUMN report_template.created_at IS '模板创建时间';

-- ---------- duty_report ----------
CREATE TABLE IF NOT EXISTS duty_report (
    id               SERIAL PRIMARY KEY,
    title            VARCHAR(255),
    report_type      VARCHAR(32),
    content          TEXT,
    template_id      INTEGER,
    report_date      DATE,
    file_blob        BYTEA,
    file_mime        VARCHAR(128),
    file_name        VARCHAR(255),
    created_at       TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at       TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

COMMENT ON TABLE duty_report IS '值勤报告实例（基于模板生成或直接编辑）';
COMMENT ON COLUMN duty_report.id IS '主键';
COMMENT ON COLUMN duty_report.title IS '报告标题';
COMMENT ON COLUMN duty_report.report_type IS 'Office 类型：word（Word）或 ppt（PowerPoint）';
COMMENT ON COLUMN duty_report.content IS '报告正文全文';
COMMENT ON COLUMN duty_report.template_id IS '若由模板生成，对应 report_template.id；可空';
COMMENT ON COLUMN duty_report.report_date IS '报告归属的业务日期';
COMMENT ON COLUMN duty_report.file_blob IS '纠错归档转正时带入的 Office 完整文件（与合成草稿 file_blob 一致）';
COMMENT ON COLUMN duty_report.file_mime IS 'Office 文件 MIME';
COMMENT ON COLUMN duty_report.file_name IS '建议下载文件名';
COMMENT ON COLUMN duty_report.created_at IS '创建时间';
COMMENT ON COLUMN duty_report.updated_at IS '最后更新时间';

-- ---------- operation_log ----------
CREATE TABLE IF NOT EXISTS operation_log (
    id          SERIAL PRIMARY KEY,
    module      VARCHAR(64),
    action      VARCHAR(64),
    detail      TEXT,
    success     BOOLEAN DEFAULT TRUE,
    created_at  TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

COMMENT ON TABLE operation_log IS '用户或系统的关键操作审计日志';
COMMENT ON COLUMN operation_log.id IS '主键';
COMMENT ON COLUMN operation_log.module IS '功能模块名';
COMMENT ON COLUMN operation_log.action IS '操作类型简述';
COMMENT ON COLUMN operation_log.detail IS '操作详情（参数、结果说明等）';
COMMENT ON COLUMN operation_log.success IS '是否执行成功';
COMMENT ON COLUMN operation_log.created_at IS '日志记录时间';

-- ---------- analysis_snapshot ----------
CREATE TABLE IF NOT EXISTS analysis_snapshot (
    id            SERIAL PRIMARY KEY,
    total         INTEGER DEFAULT 0,
    daily_avg     INTEGER DEFAULT 0,
    peak          INTEGER DEFAULT 0,
    source_count  INTEGER DEFAULT 0,
    created_at    TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

COMMENT ON TABLE analysis_snapshot IS '值勤数据分析 KPI 快照：「数据存储」按钮把当前 4 个 KPI 存档';
COMMENT ON COLUMN analysis_snapshot.id IS '主键';
COMMENT ON COLUMN analysis_snapshot.total IS '样本总量';
COMMENT ON COLUMN analysis_snapshot.daily_avg IS '日均采集（条/日）';
COMMENT ON COLUMN analysis_snapshot.peak IS '峰值/日（条）';
COMMENT ON COLUMN analysis_snapshot.source_count IS '覆盖来源（个）';
COMMENT ON COLUMN analysis_snapshot.created_at IS '存储时间';

-- ---------- collect_endpoint ----------
CREATE TABLE IF NOT EXISTS collect_endpoint (
    id              SERIAL PRIMARY KEY,
    name            VARCHAR(128) NOT NULL,
    method          VARCHAR(16) DEFAULT 'GET',
    url             VARCHAR(2048) NOT NULL,
    headers_json    TEXT,
    body            TEXT,
    source_label    VARCHAR(64),
    category_label  VARCHAR(64),
    list_path       VARCHAR(512),
    field_map_json  TEXT,
    tag_rules_json  TEXT,
    sort_order      INTEGER DEFAULT 0,
    created_at      TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at      TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

COMMENT ON TABLE collect_endpoint IS '远程采集配置条目：每条可独立配置 URL、HTTP 方法、请求头与默认来源/类别';
COMMENT ON COLUMN collect_endpoint.id IS '主键（自增）';
COMMENT ON COLUMN collect_endpoint.name IS '配置显示名称';
COMMENT ON COLUMN collect_endpoint.method IS 'HTTP 方法：GET/POST/PUT/PATCH/DELETE 等';
COMMENT ON COLUMN collect_endpoint.url IS '请求完整 URL（含查询参数）';
COMMENT ON COLUMN collect_endpoint.headers_json IS '请求头 JSON 字符串';
COMMENT ON COLUMN collect_endpoint.body IS 'POST/PUT/PATCH 请求体（多为 JSON 文本）';
COMMENT ON COLUMN collect_endpoint.source_label IS '解析预览时 source 字段的默认值';
COMMENT ON COLUMN collect_endpoint.category_label IS '解析预览时 category 字段的默认值';
COMMENT ON COLUMN collect_endpoint.list_path IS '响应 JSON 中记录数组的点号路径，如 data.items；为空则自动识别 data/items 等';
COMMENT ON COLUMN collect_endpoint.field_map_json IS '字段映射 JSON：键为 title/content/raw_value/occur_time/source/category，值为相对每条记录的 JSON 路径';
COMMENT ON COLUMN collect_endpoint.tag_rules_json IS '标签字段规则 JSON：{tag_name: json_path}，供"按字段规则一键暂存"使用';
COMMENT ON COLUMN collect_endpoint.sort_order IS '列表与批量采集时的顺序号；新建时自动递增排在末尾';
COMMENT ON COLUMN collect_endpoint.created_at IS '创建时间';
COMMENT ON COLUMN collect_endpoint.updated_at IS '最后修改时间';

-- ---------- collect_tagged_value ----------
CREATE TABLE IF NOT EXISTS collect_tagged_value (
    id             SERIAL PRIMARY KEY,
    endpoint_id    INTEGER,
    endpoint_name  VARCHAR(128),
    tag            VARCHAR(64) NOT NULL,
    value          TEXT NOT NULL,
    value_path     VARCHAR(512),
    source_excerpt TEXT,
    status         VARCHAR(16) DEFAULT 'pending',
    created_at     TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    stored_at      TIMESTAMP WITHOUT TIME ZONE,
    occur_time     TIMESTAMP WITHOUT TIME ZONE
);

COMMENT ON TABLE collect_tagged_value IS '采集预览中手工截取的标签值（暂存区，后续可入库 CleanData）';
COMMENT ON COLUMN collect_tagged_value.id IS '主键';
COMMENT ON COLUMN collect_tagged_value.endpoint_id IS '采集配置 ID（CollectEndpoint.id，可空）';
COMMENT ON COLUMN collect_tagged_value.endpoint_name IS '采集配置名称（便于展示）';
COMMENT ON COLUMN collect_tagged_value.tag IS '标签（用户手工填写）';
COMMENT ON COLUMN collect_tagged_value.value IS '选中的中间部分值（待后续入库）';
COMMENT ON COLUMN collect_tagged_value.value_path IS '从 item_raw_json 识别的字段路径；后续可按此路径一键自动暂存';
COMMENT ON COLUMN collect_tagged_value.source_excerpt IS '选中内容来源（该条 item_raw_json 的节选，便于追溯）';
COMMENT ON COLUMN collect_tagged_value.status IS '状态：pending/stored';
COMMENT ON COLUMN collect_tagged_value.created_at IS '暂存时间';
COMMENT ON COLUMN collect_tagged_value.stored_at IS '入库时间';
COMMENT ON COLUMN collect_tagged_value.occur_time IS '数据对应时间（业务产生时间，写入报告；不是采集时间）';

-- ---------- report_compose_draft ----------
CREATE TABLE IF NOT EXISTS report_compose_draft (
    id             SERIAL PRIMARY KEY,
    template_id    INTEGER,
    template_name  VARCHAR(128),
    title          VARCHAR(255) NOT NULL,
    content        TEXT,
    status         VARCHAR(32) DEFAULT 'pending_polish',
    status_detail  VARCHAR(512),
    bindings_json  TEXT,
    file_blob      BYTEA,
    file_mime      VARCHAR(128),
    file_name      VARCHAR(255),
    created_at     TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at     TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

COMMENT ON TABLE report_compose_draft IS '模板 X 占位替换后的合成草稿（供纠错润色；非正式 duty_report）';
COMMENT ON COLUMN report_compose_draft.template_id IS '来源模板 report_template.id';
COMMENT ON COLUMN report_compose_draft.template_name IS '保存时模板名称快照';
COMMENT ON COLUMN report_compose_draft.status IS 'pending_polish=待润色；polishing=正在润色；polished=润色完成；polish_error=润色失败';
COMMENT ON COLUMN report_compose_draft.status_detail IS '润色进度或失败原因（列表展示）';
COMMENT ON COLUMN report_compose_draft.bindings_json IS '占位映射快照 JSON';
COMMENT ON COLUMN report_compose_draft.file_blob IS '替换后的 Office 文件字节（与下载预览一致）';
COMMENT ON COLUMN report_compose_draft.file_mime IS 'file_blob 的 MIME 类型';
COMMENT ON COLUMN report_compose_draft.file_name IS '建议下载文件名';

-- ---------- org_unit / metric_source ----------
CREATE TABLE IF NOT EXISTS org_unit (
    id            SERIAL PRIMARY KEY,
    code          VARCHAR(32)  NOT NULL UNIQUE,
    name          VARCHAR(64)  NOT NULL,
    base_url      VARCHAR(2048),
    aliases_json  TEXT,
    remark        VARCHAR(64),
    sort_order    INTEGER DEFAULT 0,
    created_at    TIMESTAMP WITHOUT TIME ZONE,
    updated_at    TIMESTAMP WITHOUT TIME ZONE
);
COMMENT ON TABLE org_unit IS '空军本级及五大战区空军：各自配置基地 URL';

CREATE TABLE IF NOT EXISTS metric_source (
    id                  SERIAL PRIMARY KEY,
    code                VARCHAR(64)  NOT NULL UNIQUE,
    name                VARCHAR(128) NOT NULL,
    method              VARCHAR(16)  DEFAULT 'GET',
    path                VARCHAR(512) NOT NULL,
    extract_rules_json  TEXT,
    sort_order          INTEGER DEFAULT 0,
    created_at          TIMESTAMP WITHOUT TIME ZONE,
    updated_at          TIMESTAMP WITHOUT TIME ZONE
);
COMMENT ON TABLE metric_source IS '共享指标接口路径与 JSON 抽取规则';

COMMIT;
