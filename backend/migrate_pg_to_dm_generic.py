"""通用数据迁移：PostgreSQL -> 达梦(DM)，自动按源库真实表结构建表并拷数据。

与 migrate_pg_to_dm.py（suojian 专用、写死列名）不同，本脚本从 PG 的
information_schema 反射每张表的列名/类型/主键，自动映射为达梦类型后建表迁移，
适配任意（含差异）schema。

默认任务：PG 库 zonghexinxi_moxing -> DM 用户 zhxx_mo_xing(schema ZHXX_MO_XING)。
改下方 PG / DM / DM_SCHEMA 常量即可用于其它迁移。
"""
import sys
import psycopg2
import dmPython

# ---- 源 PostgreSQL ----
PG = dict(host="127.0.0.1", port="5432", dbname="zonghexinxi_moxing",
          user="postgres", password="123456")
# ---- 目标达梦 ----
DM = dict(user="zhxx_mo_xing", password="zhxx_mo_xing", server="LOCALHOST", port=5236)
DM_SCHEMA = "ZHXX_MO_XING"

DM_VARCHAR_MAX = 8000  # 超过则改用 CLOB（达梦 VARCHAR 上限约 8188 字节）


def map_type(col):
    """PG 列信息 -> (达梦类型串, 值类别)。值类别：blob/bit/plain。"""
    dt = col["data_type"]
    n = col["character_maximum_length"]
    if dt in ("integer",):
        return "INT", "plain"
    if dt in ("bigint",):
        return "BIGINT", "plain"
    if dt in ("smallint",):
        return "SMALLINT", "plain"
    if dt == "boolean":
        return "BIT", "bit"
    if dt in ("double precision", "real", "numeric", "money"):
        return "DOUBLE", "plain"
    if dt == "bytea":
        return "BLOB", "blob"
    if dt == "text" or dt in ("json", "jsonb"):
        return "CLOB", "plain"
    if dt == "date":
        return "DATE", "plain"
    if dt.startswith("timestamp"):
        return "TIMESTAMP", "plain"
    if dt == "time without time zone" or dt.startswith("time"):
        return "TIMESTAMP", "plain"
    if dt in ("character varying", "character"):
        if not n:
            return "CLOB", "plain"
        bytelen = n * 3  # 中文 UTF-8 留足
        if bytelen > DM_VARCHAR_MAX:
            return "CLOB", "plain"
        return f"VARCHAR({bytelen})", "plain"
    # 兜底
    return "CLOB", "plain"


def get_columns(cur, table):
    cur.execute("""
        SELECT column_name, data_type, character_maximum_length, ordinal_position
        FROM information_schema.columns
        WHERE table_schema='public' AND table_name=%s
        ORDER BY ordinal_position
    """, (table,))
    return [dict(column_name=r[0], data_type=r[1], character_maximum_length=r[2],
                 ordinal_position=r[3]) for r in cur.fetchall()]


def get_pk(cur, table):
    cur.execute("""
        SELECT a.attname
        FROM pg_index i
        JOIN pg_attribute a ON a.attrelid = i.indrelid AND a.attnum = ANY(i.indkey)
        WHERE i.indrelid = ('public.' || %s)::regclass AND i.indisprimary
        ORDER BY a.attnum
    """, (table,))
    return [r[0] for r in cur.fetchall()]


def main():
    print(f"源 PG: {PG['user']}@{PG['host']}:{PG['port']}/{PG['dbname']}")
    print(f"目标 DM: {DM['user']}@{DM['server']}:{DM['port']} schema={DM_SCHEMA}\n")
    pg = psycopg2.connect(**PG)
    dm = dmPython.connect(**DM)
    pgc = pg.cursor()
    dmc = dm.cursor()

    pgc.execute("""SELECT table_name FROM information_schema.tables
                   WHERE table_schema='public' AND table_type='BASE TABLE'
                   ORDER BY table_name""")
    tables = [r[0] for r in pgc.fetchall()]

    total_rows = 0
    for tbl in tables:
        cols = get_columns(pgc, tbl)
        pk = get_pk(pgc, tbl)
        col_names = [c["column_name"] for c in cols]
        type_cat = {}        # col -> 值类别
        # 单列整型主键 -> IDENTITY；否则普通
        ident_col = None
        if len(pk) == 1:
            pc = next((c for c in cols if c["column_name"] == pk[0]), None)
            if pc and pc["data_type"] in ("integer", "bigint", "smallint"):
                ident_col = pk[0]

        # 建表 DDL
        defs = []
        for c in cols:
            name = c["column_name"]
            dm_type, cat = map_type(c)
            type_cat[name] = cat
            if name == ident_col:
                base = "BIGINT" if c["data_type"] == "bigint" else "INT"
                defs.append(f"{name} {base} IDENTITY(1,1) PRIMARY KEY")
            else:
                defs.append(f"{name} {dm_type}")
        if pk and ident_col is None:
            defs.append("PRIMARY KEY (" + ", ".join(pk) + ")")
        ddl = f"CREATE TABLE {DM_SCHEMA}.{tbl.upper()} (\n  " + ",\n  ".join(defs) + "\n)"

        # 目标表存在则删
        try:
            dmc.execute(f"DROP TABLE {DM_SCHEMA}.{tbl.upper()}"); dm.commit()
        except Exception:
            dm.rollback()
        dmc.execute(ddl); dm.commit()

        # 读源数据
        order = (" ORDER BY " + ", ".join(pk)) if pk else ""
        col_list = ", ".join(col_names)
        pgc.execute(f"SELECT {col_list} FROM \"{tbl}\"{order}")
        rows = pgc.fetchall()

        if rows:
            placeholders = ", ".join(["?"] * len(col_names))
            ins = f"INSERT INTO {DM_SCHEMA}.{tbl.upper()} ({col_list}) VALUES ({placeholders})"
            if ident_col is not None:
                dmc.execute(f"SET IDENTITY_INSERT {DM_SCHEMA}.{tbl.upper()} ON")
            for row in rows:
                vals = []
                for i, name in enumerate(col_names):
                    v = row[i]
                    cat = type_cat[name]
                    if v is None:
                        vals.append(None)
                    elif cat == "blob":
                        vals.append(bytes(v))
                    elif cat == "bit":
                        vals.append(1 if v else 0)
                    else:
                        vals.append(v)
                dmc.execute(ins, tuple(vals))
            dm.commit()
            if ident_col is not None:
                dmc.execute(f"SET IDENTITY_INSERT {DM_SCHEMA}.{tbl.upper()} OFF"); dm.commit()

        dmc.execute(f"SELECT COUNT(*) FROM {DM_SCHEMA}.{tbl.upper()}")
        dm_n = dmc.fetchone()[0]
        flag = "OK" if dm_n == len(rows) else "!! 不一致"
        ident = f"(IDENTITY:{ident_col})" if ident_col else "(无自增PK)"
        print(f"  {tbl:<26} PG={len(rows):<5} DM={dm_n:<5} {flag} {ident}")
        total_rows += dm_n

    pgc.close(); pg.close(); dmc.close(); dm.close()
    print(f"\n完成，{DM_SCHEMA} 共 {total_rows} 行。")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print("迁移失败:", repr(e))
        sys.exit(1)
