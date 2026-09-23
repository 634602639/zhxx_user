"""
综合信息服务中心应用 - 后端入口
B/S 架构：Flask + SQLAlchemy(PostgreSQL) + 静态前端
表结构请在 PostgreSQL 中执行 backend/sql/init_postgresql.sql 创建（含表/列注释）。
"""
import os
import sys

# 确保 backend 目录在 sys.path 上（嵌入式 Python 带 ._pth 时不会自动加入脚本目录）
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from flask import Flask, send_from_directory, jsonify
from flask_cors import CORS
from config import Config
from models import db

# 确保达梦方言注册（PyInstaller 冻结后 entry_points 元数据可能丢失，手动注册一次）
try:
    from sqlalchemy.dialects import registry as _sa_registry
    _sa_registry.register("dm", "sqlalchemy_dm.dmPython", "DMDialect_dmPython")
    _sa_registry.register("dm.dmPython", "sqlalchemy_dm.dmPython", "DMDialect_dmPython")
except Exception:
    pass


def _patch_duty_report_report_type_word_ppt(app):
    """历史库 duty_report.report_type 曾为日报/周报等，迁移为 word / ppt。"""
    from sqlalchemy import inspect, text

    try:
        insp = inspect(db.engine)
        if not insp.has_table("duty_report"):
            return
    except Exception as ex:
        app.logger.warning("inspect duty_report (report_type 迁移): %s", ex)
        return

    stmts = (
        """
        UPDATE duty_report dr SET report_type = 'ppt'
        FROM report_template rt
        WHERE dr.template_id = rt.id
          AND dr.report_type IS NOT NULL
          AND dr.report_type NOT IN ('word', 'ppt')
          AND (rt.mime_type ILIKE '%presentationml%' OR rt.original_filename ILIKE '%.pptx')
        """,
        """
        UPDATE duty_report dr SET report_type = 'word'
        FROM report_template rt
        WHERE dr.template_id = rt.id
          AND dr.report_type IS NOT NULL
          AND dr.report_type NOT IN ('word', 'ppt')
          AND (rt.mime_type ILIKE '%wordprocessingml%' OR rt.original_filename ILIKE '%.docx')
        """,
        """
        UPDATE duty_report SET report_type = 'word'
        WHERE report_type IS NULL OR report_type NOT IN ('word', 'ppt')
        """,
    )
    try:
        with db.engine.begin() as conn:
            for s in stmts:
                conn.execute(text(s))
    except Exception as ex:
        app.logger.warning("duty_report.report_type 迁移未应用: %s", ex)


def _patch_duty_report_drop_keywords_location(app):
    """ORM 已移除 keywords/location；已有库启动时 DROP COLUMN IF EXISTS。"""
    from sqlalchemy import inspect, text

    try:
        insp = inspect(db.engine)
        if not insp.has_table("duty_report"):
            return
    except Exception as ex:
        app.logger.warning("inspect duty_report: %s", ex)
        return

    stmts = (
        "ALTER TABLE duty_report DROP COLUMN IF EXISTS keywords",
        "ALTER TABLE duty_report DROP COLUMN IF EXISTS location",
    )
    try:
        with db.engine.begin() as conn:
            for s in stmts:
                conn.execute(text(s))
    except Exception as ex:
        app.logger.warning("duty_report 列删除补丁未应用: %s", ex)


def _patch_duty_report_office_file_columns(app):
    """duty_report 增加 Office 附件列（与纠错归档转正 file_blob 对齐）。"""
    from sqlalchemy import inspect, text

    try:
        insp = inspect(db.engine)
        if not insp.has_table("duty_report"):
            return
    except Exception as ex:
        app.logger.warning("inspect duty_report (office 附件列): %s", ex)
        return

    stmts = (
        "ALTER TABLE duty_report ADD COLUMN IF NOT EXISTS file_blob BYTEA",
        "ALTER TABLE duty_report ADD COLUMN IF NOT EXISTS file_mime VARCHAR(128)",
        "ALTER TABLE duty_report ADD COLUMN IF NOT EXISTS file_name VARCHAR(255)",
    )
    try:
        with db.engine.begin() as conn:
            for s in stmts:
                conn.execute(text(s))
    except Exception as ex:
        app.logger.warning("duty_report Office 附件列补丁未应用: %s", ex)


def _patch_duty_report_drop_summary_related(app):
    """ORM 已移除 summary / related_systems；已有库启动时 DROP COLUMN IF EXISTS。"""
    from sqlalchemy import inspect, text

    try:
        insp = inspect(db.engine)
        if not insp.has_table("duty_report"):
            return
    except Exception as ex:
        app.logger.warning("inspect duty_report (drop summary): %s", ex)
        return

    stmts = (
        "ALTER TABLE duty_report DROP COLUMN IF EXISTS summary",
        "ALTER TABLE duty_report DROP COLUMN IF EXISTS related_systems",
    )
    try:
        with db.engine.begin() as conn:
            for s in stmts:
                conn.execute(text(s))
    except Exception as ex:
        app.logger.warning("duty_report 删除 summary/related_systems 未应用: %s", ex)


def _patch_report_compose_draft_file_columns(app):
    """已有库若早于「Office 文件字段」版本，create_all 不会补列；启动时 ALTER IF NOT EXISTS。"""
    from sqlalchemy import inspect, text

    try:
        insp = inspect(db.engine)
        if not insp.has_table("report_compose_draft"):
            return
    except Exception as ex:
        app.logger.warning("inspect report_compose_draft: %s", ex)
        return

    stmts = (
        "ALTER TABLE report_compose_draft ADD COLUMN IF NOT EXISTS file_blob BYTEA",
        "ALTER TABLE report_compose_draft ADD COLUMN IF NOT EXISTS file_mime VARCHAR(128)",
        "ALTER TABLE report_compose_draft ADD COLUMN IF NOT EXISTS file_name VARCHAR(255)",
    )
    try:
        with db.engine.begin() as conn:
            for s in stmts:
                conn.execute(text(s))
    except Exception as ex:
        app.logger.warning("report_compose_draft 列补丁未应用: %s", ex)


def _ensure_compose_draft_status_detail(app):
    """合成草稿增加 status_detail，用于列表展示正在润色 / 失败原因。"""
    from sqlalchemy import text

    is_dm = db.engine.dialect.name == "dm"
    try:
        with db.engine.connect() as conn:
            conn.execute(text("SELECT status_detail FROM report_compose_draft WHERE 1=0"))
        return
    except Exception:
        pass
    try:
        with db.engine.begin() as conn:
            ddl = (
                "ALTER TABLE report_compose_draft ADD status_detail VARCHAR(512)"
                if is_dm
                else "ALTER TABLE report_compose_draft ADD COLUMN IF NOT EXISTS status_detail VARCHAR(512)"
            )
            conn.execute(text(ddl))
    except Exception as ex:
        app.logger.info("report_compose_draft.status_detail 列暂未补: %s", ex)


def _ensure_user_store(app):
    """确保 sys_user 表存在并有默认管理员 admin/123456。

    达梦下 create_all 不可用（无 sysobjects 权限），故按方言手动建表。
    """
    from sqlalchemy import text
    from werkzeug.security import generate_password_hash
    from models import SysUser

    # 1) 确保表存在：能查到则表已存在；异常则建表
    try:
        SysUser.query.first()
    except Exception:
        db.session.rollback()
        try:
            if db.engine.dialect.name == "dm":
                db.session.execute(text(
                    "CREATE TABLE SYS_USER ("
                    "id INT IDENTITY(1,1) PRIMARY KEY, "
                    "username VARCHAR(192) NOT NULL UNIQUE, "
                    "password_hash VARCHAR(768) NOT NULL, "
                    "role_id INT, "
                    "created_at TIMESTAMP, updated_at TIMESTAMP)"
                ))
                db.session.commit()
            else:
                db.create_all()
        except Exception as ex:
            db.session.rollback()
            app.logger.warning("创建 sys_user 表失败: %s", ex)
            return

    # 2) 种子默认管理员
    try:
        if not SysUser.query.filter_by(username="admin").first():
            db.session.add(SysUser(
                username="admin",
                password_hash=generate_password_hash("123456"),
            ))
            db.session.commit()
    except Exception as ex:
        db.session.rollback()
        app.logger.warning("初始化默认管理员失败: %s", ex)


def _ensure_user_role_column(app):
    """给已有 sys_user 补 role_id 列。

    必须在任何 SysUser 的 ORM 查询之前调用：ORM 模型已含 role_id，若库里还没有该列，
    任何 SELECT 都会失败并污染连接。这里用独立连接探测/加列，失败不影响 ORM 会话。
    （表尚不存在的全新库会在此 no-op，建表时自带 role_id 列。）
    """
    from sqlalchemy import text
    is_dm = db.engine.dialect.name == "dm"
    # 1) 探测列是否已存在（独立连接）
    try:
        with db.engine.connect() as conn:
            conn.execute(text("SELECT role_id FROM sys_user WHERE 1=0"))
        return  # 已存在，无需补
    except Exception:
        pass
    # 2) 加列（独立事务；表不存在则失败，属预期，建表时会带上该列）
    try:
        with db.engine.begin() as conn:
            ddl = ("ALTER TABLE sys_user ADD role_id INT" if is_dm
                   else "ALTER TABLE sys_user ADD COLUMN IF NOT EXISTS role_id INTEGER")
            conn.execute(text(ddl))
    except Exception as ex:
        app.logger.warning("sys_user.role_id 列暂未补（表可能尚未创建，建表时会带上）: %s", ex)


def _ensure_tagged_occur_time(app):
    """collect_tagged_value 增加 occur_time（数据对应时间），与暂存时间 created_at 分开。"""
    from sqlalchemy import text
    is_dm = db.engine.dialect.name == "dm"
    try:
        with db.engine.connect() as conn:
            conn.execute(text("SELECT occur_time FROM collect_tagged_value WHERE 1=0"))
        return
    except Exception:
        pass
    try:
        with db.engine.begin() as conn:
            ddl = (
                "ALTER TABLE collect_tagged_value ADD occur_time TIMESTAMP"
                if is_dm
                else "ALTER TABLE collect_tagged_value ADD COLUMN IF NOT EXISTS occur_time TIMESTAMP"
            )
            conn.execute(text(ddl))
    except Exception as ex:
        app.logger.info("collect_tagged_value.occur_time 列暂未补: %s", ex)


def _ensure_role_store(app):
    """确保 sys_role 表存在并种子超级管理员角色，再把 admin 挂上去。

    达梦下 create_all 不可用，手动建表；PostgreSQL 下 create_all 已建好 sys_role 表。
    建表用独立连接，避免失败污染 ORM 会话。调用前应已通过 _ensure_user_role_column 补好列。
    """
    import json as _json
    from sqlalchemy import text
    from models import SysRole, SysUser
    from permissions import WILDCARD, all_permission_codes

    is_dm = db.engine.dialect.name == "dm"

    # 1) 确保 sys_role 表存在（独立连接探测；不存在则建）
    exists = True
    try:
        with db.engine.connect() as conn:
            conn.execute(text("SELECT 1 FROM sys_role WHERE 1=0"))
    except Exception:
        exists = False
    if not exists:
        try:
            if is_dm:
                with db.engine.begin() as conn:
                    conn.execute(text(
                        "CREATE TABLE SYS_ROLE ("
                        "id INT IDENTITY(1,1) PRIMARY KEY, "
                        "name VARCHAR(192) NOT NULL UNIQUE, "
                        "code VARCHAR(192) NOT NULL UNIQUE, "
                        "description VARCHAR(765), "
                        "perms CLOB, "
                        "is_builtin BIT DEFAULT 0, "
                        "created_at TIMESTAMP, updated_at TIMESTAMP)"
                    ))
            else:
                db.create_all()
        except Exception as ex:
            app.logger.warning("创建 sys_role 表失败: %s", ex)
            return

    # 2) 内置「管理员」角色（code=super_admin）：拥有全部权限（通配 "*"），锁定不可改 / 不可删。
    #    历史库里它叫「超级管理员」，按要求统一改名为「管理员」（权限与锁定不变）。
    LOCKED_ADMIN_NAME = "管理员"
    super_role = None
    try:
        super_role = SysRole.query.filter_by(code="super_admin").first()
        if not super_role:
            super_role = SysRole(
                name=LOCKED_ADMIN_NAME, code="super_admin",
                description="系统内置，拥有全部权限，锁定不可修改 / 删除",
                perms=_json.dumps([WILDCARD]), is_builtin=True,
            )
            db.session.add(super_role)
            db.session.commit()
        elif super_role.name != LOCKED_ADMIN_NAME:
            super_role.name = LOCKED_ADMIN_NAME
            db.session.commit()
    except Exception as ex:
        db.session.rollback()
        app.logger.warning("初始化/重命名管理员(锁定)角色失败: %s", ex)

    # 2.1) 常规「管理员A」角色（code=admin）：拥有全部权限，但可编辑 / 可删 / 可分配。
    #      与锁定的「管理员」区分；预置一次，缺失时自动补。
    try:
        if not SysRole.query.filter_by(code="admin").first():
            db.session.add(SysRole(
                name="管理员A", code="admin",
                description="常规管理员：拥有全部权限，可编辑 / 可删 / 可分配",
                perms=_json.dumps(all_permission_codes(), ensure_ascii=False),
                is_builtin=False,
            ))
            db.session.commit()
    except Exception as ex:
        db.session.rollback()
        app.logger.warning("初始化常规管理员角色失败: %s", ex)

    # 3) 默认管理员 admin 挂到超级管理员角色（仅当其当前无角色，不覆盖人工调整）
    try:
        if super_role:
            admin = SysUser.query.filter_by(username="admin").first()
            if admin and not admin.role_id:
                admin.role_id = super_role.id
                db.session.commit()
    except Exception as ex:
        db.session.rollback()
        app.logger.warning("admin 绑定超级管理员角色失败: %s", ex)


def _ensure_org_metric_store(app):
    """确保 org_unit / metric_source 存在，并种子 6 单位与 15所指标路径。"""
    import json as _json
    from sqlalchemy import text
    from models import OrgUnit, MetricSource, utc_now_second, to_db_text
    from services.metric_catalog import DEFAULT_ORG_UNITS, DEFAULT_METRIC_SOURCES, DEFAULT_ORG_UNIT_REMARK
    from validators import L_ORG_REMARK

    is_dm = db.engine.dialect.name == "dm"
    now = utc_now_second()
    default_remark = to_db_text(DEFAULT_ORG_UNIT_REMARK)[:L_ORG_REMARK]

    try:
        with db.engine.connect() as conn:
            conn.execute(text("SELECT remark FROM org_unit WHERE 1=0"))
    except Exception:
        try:
            with db.engine.begin() as conn:
                ddl = (
                    "ALTER TABLE org_unit ADD remark VARCHAR(192)"
                    if is_dm
                    else "ALTER TABLE org_unit ADD COLUMN IF NOT EXISTS remark VARCHAR(64)"
                )
                conn.execute(text(ddl))
        except Exception as ex:
            app.logger.info("org_unit.remark 列暂未补: %s", ex)

    def _table_ok(model):
        try:
            model.query.first()
            return True
        except Exception:
            db.session.rollback()
            return False

    if not _table_ok(OrgUnit):
        try:
            if is_dm:
                with db.engine.begin() as conn:
                    conn.execute(text(
                        "CREATE TABLE ORG_UNIT ("
                        "id INT IDENTITY(1,1) PRIMARY KEY, "
                        "code VARCHAR(96) NOT NULL UNIQUE, "
                        "name VARCHAR(192) NOT NULL, "
                        "base_url VARCHAR(6144), "
                        "aliases_json CLOB, "
                        "remark VARCHAR(192), "
                        "sort_order INT DEFAULT 0, "
                        "created_at TIMESTAMP, updated_at TIMESTAMP)"
                    ))
            else:
                db.create_all()
        except Exception as ex:
            app.logger.warning("创建 org_unit 表失败: %s", ex)

    if not _table_ok(MetricSource):
        try:
            if is_dm:
                with db.engine.begin() as conn:
                    conn.execute(text(
                        "CREATE TABLE METRIC_SOURCE ("
                        "id INT IDENTITY(1,1) PRIMARY KEY, "
                        "code VARCHAR(192) NOT NULL UNIQUE, "
                        "name VARCHAR(384) NOT NULL, "
                        "method VARCHAR(48) DEFAULT 'GET', "
                        "path VARCHAR(1536) NOT NULL, "
                        "extract_rules_json CLOB, "
                        "sort_order INT DEFAULT 0, "
                        "created_at TIMESTAMP, updated_at TIMESTAMP)"
                    ))
            else:
                db.create_all()
        except Exception as ex:
            app.logger.warning("创建 metric_source 表失败: %s", ex)

    try:
        existing = OrgUnit.query.all()
        if not existing:
            for spec in DEFAULT_ORG_UNITS:
                db.session.add(OrgUnit(
                    code=spec["code"],
                    name=spec["name"],
                    base_url="",
                    remark=default_remark,
                    aliases_json=_json.dumps(spec.get("aliases") or [], ensure_ascii=False),
                    sort_order=spec.get("sort_order") or 0,
                    created_at=now,
                    updated_at=now,
                ))
        for u in OrgUnit.query.all():
            if not (u.remark or "").strip():
                u.remark = default_remark
                u.updated_at = now
        db.session.commit()
    except Exception as ex:
        db.session.rollback()
        app.logger.warning("种子 org_unit 失败: %s", ex)

    try:
        existing_s = {s.code: s for s in MetricSource.query.all()}
        for spec in DEFAULT_METRIC_SOURCES:
            rules = _json.dumps(spec.get("rules") or [], ensure_ascii=False)
            row = existing_s.get(spec["code"])
            if row:
                row.name = spec["name"]
                row.method = spec.get("method") or "GET"
                row.path = spec["path"]
                row.extract_rules_json = rules
                row.sort_order = spec.get("sort_order") or 0
                row.updated_at = now
            else:
                db.session.add(MetricSource(
                    code=spec["code"],
                    name=spec["name"],
                    method=spec.get("method") or "GET",
                    path=spec["path"],
                    extract_rules_json=rules,
                    sort_order=spec.get("sort_order") or 0,
                    created_at=now,
                    updated_at=now,
                ))
        db.session.commit()
    except Exception as ex:
        db.session.rollback()
        app.logger.warning("种子 metric_source 失败: %s", ex)


def create_app():
    if getattr(sys, "frozen", False):
        # PyInstaller 冻结：前端从打包资源目录(_MEIPASS)读，可写数据放 exe 同级目录
        frontend_dir = os.path.join(sys._MEIPASS, "frontend")
        base = os.path.dirname(sys.executable)
    else:
        base = os.path.abspath(os.path.dirname(__file__))
        frontend_dir = os.path.abspath(os.path.join(base, "..", "frontend"))

    app = Flask(__name__, static_folder=frontend_dir, static_url_path="")
    app.config.from_object(Config)
    CORS(app)

    os.makedirs(os.path.join(base, "data"), exist_ok=True)
    os.makedirs(app.config["UPLOAD_DIR"], exist_ok=True)
    os.makedirs(app.config["EXPORT_DIR"], exist_ok=True)

    db.init_app(app)

    # 确保 ORM 模型对应表存在（仅创建缺失表，不改动已有表）
    with app.app_context():
        import models  # noqa: F401
        # 达梦：修正自带方言自增主键回填缺陷（用 SCOPE_IDENTITY 取回主键）。
        if db.engine.dialect.name == "dm":
            from dm_compat import apply as _apply_dm_patch
            _apply_dm_patch(db.engine)
        # 达梦：表结构与历史数据由 backend/migrate_pg_to_dm.py 管理；
        # 且 SUO_JIAN 用户无 sysobjects 查询权限，create_all 的 has_table 反射会失败，
        # 下列补丁也都是 PostgreSQL 专用语法 —— 故仅在 PostgreSQL 后端执行。
        if db.engine.dialect.name == "postgresql":
            db.create_all()
            _patch_duty_report_drop_keywords_location(app)
            _patch_duty_report_report_type_word_ppt(app)
            _patch_duty_report_office_file_columns(app)
            _patch_duty_report_drop_summary_related(app)
            _patch_report_compose_draft_file_columns(app)

        # RBAC：先给已有 sys_user 补 role_id 列（必须早于任何 SysUser 的 ORM 查询）
        _ensure_user_role_column(app)
        _ensure_tagged_occur_time(app)
        _ensure_compose_draft_status_detail(app)
        # 用户表与默认管理员（两种后端都需要；达梦下手动建表）
        _ensure_user_store(app)
        # 角色表 + 内置超级管理员角色，并把 admin 挂上去
        _ensure_role_store(app)
        _ensure_org_metric_store(app)

    # 注册蓝图
    from routes.data_collection import bp as bp_dc
    from routes.data_analysis import bp as bp_da
    from routes.report_generate import bp as bp_rg, gen_bp as bp_rg_run
    from routes.report_manage import bp as bp_rm
    from routes.report_export import bp as bp_re
    from routes.operation_log import bp as bp_log
    from routes.auth import bp as bp_auth
    from routes.user_manage import bp as bp_user
    from routes.role_manage import bp as bp_role

    app.register_blueprint(bp_dc)
    app.register_blueprint(bp_da)
    app.register_blueprint(bp_rg)
    app.register_blueprint(bp_rg_run)
    app.register_blueprint(bp_rm)
    app.register_blueprint(bp_re)
    app.register_blueprint(bp_log)
    app.register_blueprint(bp_auth)
    app.register_blueprint(bp_user)
    app.register_blueprint(bp_role)

    # 登录守卫：未登录时拦截数据接口（/api/*）。静态外壳（HTML/JS/CSS）无敏感数据，放行；
    # 登录/登出/状态/健康检查 放行。
    from flask import session, request, jsonify
    _OPEN_API = {"/api/login", "/api/logout", "/api/auth/status", "/api/health"}

    @app.before_request
    def _require_login():
        if request.method == "OPTIONS":
            return None
        path = request.path
        if not path.startswith("/api/"):
            return None
        if path in _OPEN_API:
            return None
        if not session.get("logged_in"):
            return jsonify({"code": 401, "msg": "未登录或登录已失效"}), 401
        return None

    @app.route("/")
    def index():
        return send_from_directory(frontend_dir, "index.html")

    @app.route("/api/health")
    def health():
        return jsonify({"code": 0, "msg": "ok"})

    @app.errorhandler(404)
    def _404(e):
        # 前端单页/多页路由的兜底：回退到首页
        if (str(e).find("api") < 0):
            return send_from_directory(frontend_dir, "index.html")
        return jsonify({"code": 404, "msg": "Not Found"}), 404

    return app


if __name__ == "__main__":
    app = create_app()
    # 关闭 debug/热重载的情形：① 打包成 exe(frozen)；② 便携包启动（运行.bat 设了 ZHXX_PROD=1）。
    # 普通开发 `python app.py` 仍保留 debug 热重载。
    _debug = (not getattr(sys, "frozen", False)) and os.environ.get("ZHXX_PROD") != "1"
    app.run(host="0.0.0.0", port=5000, debug=_debug)
