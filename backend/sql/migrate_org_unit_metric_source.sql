-- 战区单位 + 共享指标接口（PostgreSQL）
-- 应用启动时 app.py 的 _ensure_org_metric_store() 会自动建表并种子 6 单位 / 15所路径；
-- 本文件仅作结构留档。

CREATE TABLE IF NOT EXISTS org_unit (
    id            SERIAL PRIMARY KEY,
    code          VARCHAR(32)  NOT NULL UNIQUE,
    name          VARCHAR(64)  NOT NULL,
    base_url      VARCHAR(2048),
    aliases_json  TEXT,
    remark        VARCHAR(64),
    sort_order    INTEGER DEFAULT 0,
    created_at    TIMESTAMP,
    updated_at    TIMESTAMP
);

COMMENT ON TABLE org_unit IS '空军本级及五大战区空军：各自配置基地 URL';
COMMENT ON COLUMN org_unit.code IS '稳定标识：hq/east/west/south/north/center';
COMMENT ON COLUMN org_unit.base_url IS '基地地址，如 http://host:8080';
COMMENT ON COLUMN org_unit.aliases_json IS '模板列名别名 JSON 数组';
COMMENT ON COLUMN org_unit.remark IS '接口备注，默认运维、安防数据';

CREATE TABLE IF NOT EXISTS metric_source (
    id                  SERIAL PRIMARY KEY,
    code                VARCHAR(64)  NOT NULL UNIQUE,
    name                VARCHAR(128) NOT NULL,
    method              VARCHAR(16)  DEFAULT 'GET',
    path                VARCHAR(512) NOT NULL,
    extract_rules_json  TEXT,
    sort_order          INTEGER DEFAULT 0,
    created_at          TIMESTAMP,
    updated_at          TIMESTAMP
);

COMMENT ON TABLE metric_source IS '共享指标接口路径与 JSON 抽取规则（拼到各单位 base_url）';

-- 达梦 DM8 参考：
-- CREATE TABLE ZHXX_SUO_JIAN.ORG_UNIT (
--     id INT IDENTITY(1,1) PRIMARY KEY,
--     code VARCHAR(96) NOT NULL UNIQUE,
--     name VARCHAR(192) NOT NULL,
--     base_url VARCHAR(6144),
--     aliases_json CLOB,
--     remark VARCHAR(192),
--     sort_order INT DEFAULT 0,
--     created_at TIMESTAMP, updated_at TIMESTAMP);
-- CREATE TABLE ZHXX_SUO_JIAN.METRIC_SOURCE (
--     id INT IDENTITY(1,1) PRIMARY KEY,
--     code VARCHAR(192) NOT NULL UNIQUE,
--     name VARCHAR(384) NOT NULL,
--     method VARCHAR(48) DEFAULT 'GET',
--     path VARCHAR(1536) NOT NULL,
--     extract_rules_json CLOB,
--     sort_order INT DEFAULT 0,
--     created_at TIMESTAMP, updated_at TIMESTAMP);
