"""一次性数据迁移：PostgreSQL -> 达梦(DM)

- 源：当前 PostgreSQL（config.py 中的连接参数 / 环境变量）
- 目标：达梦 ZHXX_SUO_JIAN schema

要点：
- 达梦 VARCHAR 按字节计长，故所有 VARCHAR 字符长度 × 3，给中文留足空间。
- TEXT -> CLOB，LargeBinary -> BLOB，Float -> DOUBLE，Boolean -> BIT，DateTime -> TIMESTAMP，Date -> DATE。
- 主键用 IDENTITY，迁移时开启 IDENTITY_INSERT 以保留原 ID。
- 无外键约束，建表/拷贝顺序无关紧要。

用法：在 backend 目录下用 venv 的 python 执行：
    venv\\Scripts\\python.exe migrate_pg_to_dm.py
"""
import os
import sys

import psycopg2
import dmPython

# ---- 源 PostgreSQL 连接参数（与 config.py 默认值一致，可用环境变量覆盖）----
PG = dict(
    host=os.environ.get("PGHOST", "127.0.0.1"),
    port=os.environ.get("PGPORT", "5432"),
    dbname=os.environ.get("PGDATABASE", "zonghexinxi_suojian"),
    user=os.environ.get("PGUSER", "postgres"),
    password=os.environ.get("PGPASSWORD", "123456"),
)

# ---- 目标达梦连接参数 ----
DM = dict(
    user=os.environ.get("DMUSER", "zhxx_suo_jian"),
    password=os.environ.get("DMPASSWORD", "zhxx_suo_jian"),
    server=os.environ.get("DMHOST", "LOCALHOST"),
    port=int(os.environ.get("DMPORT", "5236")),
)
DM_SCHEMA = "ZHXX_SUO_JIAN"

V = lambda n: f"VARCHAR({n * 3})"  # 字符长度 -> 达梦字节长度（× 3 容纳中文）

# 每张表：达梦建表 DDL（列顺序即拷贝顺序）+ 列名列表 + 各列“达梦类型类别”用于值转换
# 类型类别：blob / bit / 其它(直接绑定)
TABLES = {
    "collect_endpoint": {
        "ddl": f"""CREATE TABLE {DM_SCHEMA}.COLLECT_ENDPOINT (
            id INT IDENTITY(1,1) PRIMARY KEY,
            name {V(128)}, method {V(16)}, url {V(2048)},
            headers_json CLOB, body CLOB,
            source_label {V(64)}, category_label {V(64)},
            list_path {V(512)}, field_map_json CLOB, tag_rules_json CLOB,
            sort_order INT, created_at TIMESTAMP, updated_at TIMESTAMP)""",
        "cols": ["id", "name", "method", "url", "headers_json", "body",
                 "source_label", "category_label", "list_path", "field_map_json",
                 "tag_rules_json", "sort_order", "created_at", "updated_at"],
        "blob": set(),
    },
    "clean_data": {
        "ddl": f"""CREATE TABLE {DM_SCHEMA}.CLEAN_DATA (
            id INT IDENTITY(1,1) PRIMARY KEY,
            source {V(64)}, category {V(64)}, title {V(255)}, content CLOB,
            metric_value DOUBLE, occur_time TIMESTAMP, tags {V(255)},
            endpoint_source {V(64)}, endpoint_category {V(64)}, created_at TIMESTAMP)""",
        "cols": ["id", "source", "category", "title", "content", "metric_value",
                 "occur_time", "tags", "endpoint_source", "endpoint_category", "created_at"],
        "blob": set(),
    },
    "collect_tagged_value": {
        "ddl": f"""CREATE TABLE {DM_SCHEMA}.COLLECT_TAGGED_VALUE (
            id INT IDENTITY(1,1) PRIMARY KEY,
            endpoint_id INT, endpoint_name {V(128)}, tag {V(64)}, value CLOB,
            value_path {V(512)}, source_excerpt CLOB, status {V(16)},
            created_at TIMESTAMP, stored_at TIMESTAMP)""",
        "cols": ["id", "endpoint_id", "endpoint_name", "tag", "value", "value_path",
                 "source_excerpt", "status", "created_at", "stored_at"],
        "blob": set(),
    },
    "report_template": {
        "ddl": f"""CREATE TABLE {DM_SCHEMA}.REPORT_TEMPLATE (
            id INT IDENTITY(1,1) PRIMARY KEY,
            name {V(128)}, file_path {V(255)}, file_blob BLOB, file_size INT,
            mime_type {V(128)}, original_filename {V(255)}, content CLOB,
            keywords {V(512)}, created_at TIMESTAMP)""",
        "cols": ["id", "name", "file_path", "file_blob", "file_size", "mime_type",
                 "original_filename", "content", "keywords", "created_at"],
        "blob": {"file_blob"},
    },
    "report_compose_draft": {
        "ddl": f"""CREATE TABLE {DM_SCHEMA}.REPORT_COMPOSE_DRAFT (
            id INT IDENTITY(1,1) PRIMARY KEY,
            template_id INT, template_name {V(128)}, title {V(255)}, content CLOB,
            status {V(32)}, bindings_json CLOB, file_blob BLOB,
            file_mime {V(128)}, file_name {V(255)}, created_at TIMESTAMP, updated_at TIMESTAMP)""",
        "cols": ["id", "template_id", "template_name", "title", "content", "status",
                 "bindings_json", "file_blob", "file_mime", "file_name", "created_at", "updated_at"],
        "blob": {"file_blob"},
    },
    "duty_report": {
        "ddl": f"""CREATE TABLE {DM_SCHEMA}.DUTY_REPORT (
            id INT IDENTITY(1,1) PRIMARY KEY,
            title {V(255)}, report_type {V(32)}, content CLOB, template_id INT,
            report_date DATE, file_blob BLOB, file_mime {V(128)}, file_name {V(255)},
            created_at TIMESTAMP, updated_at TIMESTAMP)""",
        "cols": ["id", "title", "report_type", "content", "template_id", "report_date",
                 "file_blob", "file_mime", "file_name", "created_at", "updated_at"],
        "blob": {"file_blob"},
    },
    "operation_log": {
        "ddl": f"""CREATE TABLE {DM_SCHEMA}.OPERATION_LOG (
            id INT IDENTITY(1,1) PRIMARY KEY,
            module {V(64)}, action {V(64)}, detail CLOB, success BIT, created_at TIMESTAMP)""",
        "cols": ["id", "module", "action", "detail", "success", "created_at"],
        "blob": set(),
        "bit": {"success"},
    },
    "analysis_snapshot": {
        "ddl": f"""CREATE TABLE {DM_SCHEMA}.ANALYSIS_SNAPSHOT (
            id INT IDENTITY(1,1) PRIMARY KEY,
            total INT, daily_avg INT, peak INT, source_count INT, created_at TIMESTAMP)""",
        "cols": ["id", "total", "daily_avg", "peak", "source_count", "created_at"],
        "blob": set(),
    },
}


def convert(col, val, spec):
    if val is None:
        return None
    if col in spec.get("blob", set()):
        # PG bytea -> memoryview/bytes -> bytes
        return bytes(val) if not isinstance(val, (bytes, bytearray)) else bytes(val)
    if col in spec.get("bit", set()):
        return 1 if val else 0
    return val


def main():
    print(f"源 PG: {PG['user']}@{PG['host']}:{PG['port']}/{PG['dbname']}")
    print(f"目标 DM: {DM['user']}@{DM['server']}:{DM['port']} schema={DM_SCHEMA}")
    pg = psycopg2.connect(**PG)
    dm = dmPython.connect(**DM)
    pgc = pg.cursor()
    dmc = dm.cursor()

    total_rows = 0
    for tbl, spec in TABLES.items():
        # 1) 目标表存在则先删
        try:
            dmc.execute(f"DROP TABLE {DM_SCHEMA}.{tbl.upper()}")
            dm.commit()
        except Exception:
            dm.rollback()
        # 2) 建表
        dmc.execute(spec["ddl"])
        dm.commit()

        # 3) 读源数据（按 DM 列顺序 SELECT）
        cols = spec["cols"]
        col_list = ", ".join(cols)
        pgc.execute(f"SELECT {col_list} FROM {tbl} ORDER BY id")
        rows = pgc.fetchall()

        if rows:
            placeholders = ", ".join(["?"] * len(cols))
            ins = f"INSERT INTO {DM_SCHEMA}.{tbl.upper()} ({col_list}) VALUES ({placeholders})"
            # 保留原始主键
            dmc.execute(f"SET IDENTITY_INSERT {DM_SCHEMA}.{tbl.upper()} ON")
            n = 0
            for row in rows:
                vals = [convert(cols[i], row[i], spec) for i in range(len(cols))]
                dmc.execute(ins, tuple(vals))
                n += 1
            dm.commit()
            dmc.execute(f"SET IDENTITY_INSERT {DM_SCHEMA}.{tbl.upper()} OFF")
            dm.commit()
        else:
            n = 0

        # 4) 校验目标行数
        dmc.execute(f"SELECT COUNT(*) FROM {DM_SCHEMA}.{tbl.upper()}")
        dm_n = dmc.fetchone()[0]
        flag = "OK" if dm_n == len(rows) else "!! 不一致"
        print(f"  {tbl:<22} PG={len(rows):<6} DM={dm_n:<6} {flag}")
        total_rows += dm_n

    pgc.close(); pg.close()
    dmc.close(); dm.close()
    print(f"完成，目标库共 {total_rows} 行。")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print("迁移失败:", repr(e))
        sys.exit(1)
