"""达梦(DM) SQLAlchemy 方言兼容补丁。

DM 自带方言（sqlalchemy_dm 1.4.39，按 SQLAlchemy 1.4.6 编写）在当前
SQLAlchemy 1.4.54 上，自增主键插入回填存在两类问题：

1. 版本契约变更：1.4.54 的 `_setup_ins_pk_from_lastrowid` 需 **返回** 主键行
   （赋给 inserted_primary_key_rows），而方言旧实现是去 *设置* self.inserted_primary_key
   并返回 None，导致 ORM 报 “did not produce a new primary key”。
2. 取值缺陷：方言 get_lastrowid 依赖 cursor.lastrowid（此驱动恒为 None），
   且 implicit_returning(RETURNING INTO) 路径在此驱动下不稳（ResourceClosedError）。

修法：
- 关闭 implicit_returning，统一走 lastrowid 路径；
- get_lastrowid 改用 DM 的 SCOPE_IDENTITY()（另开一个 cursor 取，避免污染主结果游标）；
- _setup_ins_pk_from_lastrowid 重写为 1.4.x 契约（返回主键行）。

仅在 DM 后端调用 apply(engine)。
"""


def apply(engine=None):
    from sqlalchemy_dm.base import DMExecutionContext

    # 关闭 implicit returning：DM 的 RETURNING INTO 在此驱动/版本下不稳，统一走 lastrowid 路径
    if engine is not None:
        try:
            engine.dialect.implicit_returning = False
        except Exception:
            pass

    if getattr(DMExecutionContext, "_dm_pk_patched", False):
        return

    def get_lastrowid(self):
        # 另开 cursor 取本次插入的自增值（同一连接=同一会话），避免改动主结果游标状态
        conn = self.cursor.connection
        c = conn.cursor()
        try:
            c.execute("SELECT SCOPE_IDENTITY()")
            row = c.fetchone()
            return int(row[0]) if row and row[0] is not None else None
        finally:
            c.close()

    def _setup_ins_pk_from_lastrowid(self):
        # 1.4.x 契约：返回主键行列表，由调用方赋给 inserted_primary_key_rows
        getter = self.compiled._inserted_primary_key_from_lastrowid_getter
        lastrowid = self.get_lastrowid()
        return [getter(lastrowid, self.compiled_parameters[0])]

    DMExecutionContext.get_lastrowid = get_lastrowid
    DMExecutionContext._setup_ins_pk_from_lastrowid = _setup_ins_pk_from_lastrowid
    DMExecutionContext._dm_pk_patched = True
