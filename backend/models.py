import json
import math
from datetime import datetime
from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()


def _json_safe_float(v):
    """API JSON 不含 NaN/Inf，避免前端 JSON.parse 失败。"""
    if v is None:
        return None
    if isinstance(v, float) and (math.isnan(v) or math.isinf(v)):
        return None
    return v


def utc_now_second():
    """本地时间（系统时区），精确到秒（入库 DateTime 统一去掉微秒）。"""
    return datetime.now().replace(microsecond=0)


class CollectEndpoint(db.Model):
    """远程采集配置条目（可多条，每条独立 URL / 方法 / 头等）"""
    __tablename__ = "collect_endpoint"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(128), nullable=False)
    method = db.Column(db.String(16), default="GET")
    url = db.Column(db.String(2048), nullable=False)
    headers_json = db.Column(db.Text)
    body = db.Column(db.Text)
    source_label = db.Column(db.String(64))
    category_label = db.Column(db.String(64))
    list_path = db.Column(db.String(512))
    field_map_json = db.Column(db.Text)
    # 标签字段规则：{tag_name: json_path}，供"按字段规则一键暂存"使用，独立于 field_map_json
    tag_rules_json = db.Column(db.Text)
    sort_order = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime, default=utc_now_second)
    updated_at = db.Column(db.DateTime, default=utc_now_second, onupdate=utc_now_second)

    def to_dict(self):
        h_parsed = None
        if self.headers_json and self.headers_json.strip():
            try:
                h_parsed = json.loads(self.headers_json)
            except json.JSONDecodeError:
                h_parsed = None
        fm_parsed = None
        if self.field_map_json and self.field_map_json.strip():
            try:
                fm_parsed = json.loads(self.field_map_json)
            except json.JSONDecodeError:
                fm_parsed = None
        tr_parsed = None
        if self.tag_rules_json and self.tag_rules_json.strip():
            try:
                tr_parsed = json.loads(self.tag_rules_json)
            except json.JSONDecodeError:
                tr_parsed = None
        return {
            "id": self.id,
            "name": self.name,
            "method": self.method or "GET",
            "url": self.url,
            "headers_json": self.headers_json,
            "headers": h_parsed,
            "body": self.body,
            "source": self.source_label,
            "category": self.category_label,
            "list_path": self.list_path or "",
            "field_map": fm_parsed,
            "field_map_json": self.field_map_json,
            "tag_rules": tr_parsed,
            "tag_rules_json": self.tag_rules_json,
            "sort_order": self.sort_order or 0,
            "created_at": self.created_at.strftime("%Y-%m-%d %H:%M:%S") if self.created_at else None,
            "updated_at": self.updated_at.strftime("%Y-%m-%d %H:%M:%S") if self.updated_at else None,
        }


class CleanData(db.Model):
    """清洗、转换并入库后的数据"""
    __tablename__ = "clean_data"
    id = db.Column(db.Integer, primary_key=True)
    source = db.Column(db.String(64))
    category = db.Column(db.String(64))
    title = db.Column(db.String(255))
    content = db.Column(db.Text)
    metric_value = db.Column(db.Float)
    occur_time = db.Column(db.DateTime)
    tags = db.Column(db.String(255))
    # 手填优先；为空时由路由按 source 反查 endpoint.source_label / category_label。
    endpoint_source = db.Column(db.String(64))
    endpoint_category = db.Column(db.String(64))
    created_at = db.Column(db.DateTime, default=utc_now_second)

    def to_dict(self):
        return {
            "id": self.id, "source": self.source, "category": self.category,
            "title": self.title, "content": self.content,
            "metric_value": _json_safe_float(self.metric_value),
            "occur_time": self.occur_time.strftime("%Y-%m-%d %H:%M:%S") if self.occur_time else None,
            "tags": self.tags,
            "endpoint_source": self.endpoint_source or "",
            "endpoint_category": self.endpoint_category or "",
            "created_at": self.created_at.strftime("%Y-%m-%d %H:%M:%S") if self.created_at else None,
        }


class CollectTaggedValue(db.Model):
    """采集预览中手工截取的标签值（暂存区，后续可入库 CleanData）"""
    __tablename__ = "collect_tagged_value"
    id = db.Column(db.Integer, primary_key=True)
    endpoint_id = db.Column(db.Integer)  # CollectEndpoint.id，可空（URL 直连时）
    endpoint_name = db.Column(db.String(128))
    tag = db.Column(db.String(64), nullable=False)
    value = db.Column(db.Text, nullable=False)
    value_path = db.Column(db.String(512))  # 从 item_raw_json 中推导出的字段路径（如 data.count）
    source_excerpt = db.Column(db.Text)  # 选中片段来源（可选，截断后的 item_raw_json）
    status = db.Column(db.String(16), default="pending")  # pending/stored
    created_at = db.Column(db.DateTime, default=utc_now_second)
    stored_at = db.Column(db.DateTime)

    def to_dict(self):
        return {
            "id": self.id,
            "endpoint_id": self.endpoint_id,
            "endpoint_name": self.endpoint_name,
            "tag": self.tag,
            "value": self.value,
            "value_path": self.value_path,
            "status": self.status or "pending",
            "created_at": self.created_at.strftime("%Y-%m-%d %H:%M:%S") if self.created_at else None,
            "stored_at": self.stored_at.strftime("%Y-%m-%d %H:%M:%S") if self.stored_at else None,
        }


class ReportTemplate(db.Model):
    """值勤报告模板"""
    __tablename__ = "report_template"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(128))
    file_path = db.Column(db.String(255))            # 兼容旧数据
    file_blob = db.Column(db.LargeBinary)            # 原始文件字节
    file_size = db.Column(db.Integer)                # 字节数
    mime_type = db.Column(db.String(128))            # 下载时的 Content-Type
    original_filename = db.Column(db.String(255))    # 上传原始文件名
    content = db.Column(db.Text)                     # 模板纯文本（含占位符 {{xxx}}）
    keywords = db.Column(db.String(512))             # 自动提取的关键词，逗号分隔
    created_at = db.Column(db.DateTime, default=utc_now_second)

    def to_brief(self):
        """列表视图：不返回 content / file_blob，避免列表接口体积膨胀。"""
        from services.nlp_service import extract_placeholders
        return {
            "id": self.id,
            "name": self.name,
            "file_path": self.file_path,
            "file_size": self.file_size,
            "mime_type": self.mime_type,
            "original_filename": self.original_filename,
            "has_blob": bool(self.file_blob),
            "keywords": self.keywords,
            "placeholders": extract_placeholders(self.content or ""),
            "size": len(self.content or ""),
            "created_at": self.created_at.strftime("%Y-%m-%d %H:%M:%S") if self.created_at else None,
        }

    def to_dict(self):
        d = self.to_brief()
        d["content"] = self.content
        return d


class ReportComposeDraft(db.Model):
    """模板占位替换后的合成文稿草稿（非正式 duty_report；待纠错润色后再归档）"""

    __tablename__ = "report_compose_draft"

    id = db.Column(db.Integer, primary_key=True)
    template_id = db.Column(db.Integer)
    template_name = db.Column(db.String(128))
    title = db.Column(db.String(255), nullable=False)
    content = db.Column(db.Text)
    status = db.Column(db.String(32), default="pending_polish")
    bindings_json = db.Column(db.Text)
    file_blob = db.Column(db.LargeBinary)
    file_mime = db.Column(db.String(128))
    file_name = db.Column(db.String(255))
    created_at = db.Column(db.DateTime, default=utc_now_second)
    updated_at = db.Column(db.DateTime, default=utc_now_second, onupdate=utc_now_second)

    def office_kind(self):
        """Word / PPT / 无附件，供列表筛选与展示。"""
        if not self.file_blob:
            return ""
        fn = (self.file_name or "").lower()
        fm = (self.file_mime or "").lower()
        if ".pptx" in fn or "presentationml" in fm:
            return "ppt"
        if ".docx" in fn or "wordprocessingml" in fm:
            return "word"
        return ""

    def to_list_item(self):
        body = self.content or ""
        excerpt = body[:160] + ("…" if len(body) > 160 else "")
        ok = self.office_kind()
        kind_zh = {"word": "Word", "ppt": "PPT"}.get(ok, "—" if not ok else "其他")
        return {
            "id": self.id,
            "template_id": self.template_id,
            "template_name": self.template_name or "",
            "title": self.title,
            "status": self.status or "pending_polish",
            "excerpt": excerpt,
            "has_file": bool(self.file_blob),
            "file_name": self.file_name or "",
            "office_kind": ok,
            "office_kind_zh": kind_zh,
            "created_at": self.created_at.strftime("%Y-%m-%d %H:%M:%S") if self.created_at else None,
            "updated_at": self.updated_at.strftime("%Y-%m-%d %H:%M:%S") if self.updated_at else None,
        }


class DutyReport(db.Model):
    """值勤报告"""
    __tablename__ = "duty_report"
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(255))
    report_type = db.Column(db.String(32))       # word / ppt（Office 文稿类型）
    content = db.Column(db.Text)
    template_id = db.Column(db.Integer)
    report_date = db.Column(db.Date)
    file_blob = db.Column(db.LargeBinary)
    file_mime = db.Column(db.String(128))
    file_name = db.Column(db.String(255))
    created_at = db.Column(db.DateTime, default=utc_now_second)
    updated_at = db.Column(db.DateTime, default=utc_now_second, onupdate=utc_now_second)

    def to_dict(self):
        return {
            "id": self.id, "title": self.title, "report_type": self.report_type,
            "content": self.content,
            "template_id": self.template_id,
            "report_date": self.report_date.strftime("%Y-%m-%d") if self.report_date else None,
            "has_file": bool(self.file_blob),
            "file_name": self.file_name or "",
            "created_at": self.created_at.strftime("%Y-%m-%d %H:%M:%S") if self.created_at else None,
            "updated_at": self.updated_at.strftime("%Y-%m-%d %H:%M:%S") if self.updated_at else None,
        }


class AnalysisSnapshot(db.Model):
    """值勤数据分析 KPI 快照：把样本总量/日均采集/峰值/覆盖来源存档，便于回看。"""
    __tablename__ = "analysis_snapshot"
    id = db.Column(db.Integer, primary_key=True)
    total = db.Column(db.Integer, default=0)          # 样本总量
    daily_avg = db.Column(db.Integer, default=0)      # 日均采集（条/日）
    peak = db.Column(db.Integer, default=0)           # 峰值/日（条）
    source_count = db.Column(db.Integer, default=0)   # 覆盖来源（个）
    created_at = db.Column(db.DateTime, default=utc_now_second)

    def to_dict(self):
        return {
            "id": self.id,
            "total": self.total or 0,
            "daily_avg": self.daily_avg or 0,
            "peak": self.peak or 0,
            "source_count": self.source_count or 0,
            "created_at": self.created_at.strftime("%Y-%m-%d %H:%M:%S") if self.created_at else None,
        }


class OperationLog(db.Model):
    """操作日志（后置条件：日志记载操作细节）"""
    __tablename__ = "operation_log"
    id = db.Column(db.Integer, primary_key=True)
    module = db.Column(db.String(64))
    action = db.Column(db.String(64))
    detail = db.Column(db.Text)
    success = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=utc_now_second)

    def to_dict(self):
        return {
            "id": self.id, "module": self.module, "action": self.action,
            "detail": self.detail, "success": self.success,
            "created_at": self.created_at.strftime("%Y-%m-%d %H:%M:%S") if self.created_at else None,
        }


class SysRole(db.Model):
    """系统角色（RBAC：角色拥有一组权限点，用户挂到角色上继承其权限）。

    perms 存「权限点编码」的 JSON 数组，例如 ["collect:view","manage:edit"]；
    超级管理员存 ["*"]（通配，拥有全部权限，不可编辑、不可删除）。
    """
    __tablename__ = "sys_role"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(64), unique=True, nullable=False)   # 显示名，如「值班员」
    code = db.Column(db.String(64), unique=True, nullable=False)   # 角色标识，如「operator」
    description = db.Column(db.String(255))
    perms = db.Column(db.Text)                                     # JSON 数组：权限点编码
    is_builtin = db.Column(db.Boolean, default=False)             # 内置角色不可删除
    created_at = db.Column(db.DateTime, default=utc_now_second)
    updated_at = db.Column(db.DateTime, default=utc_now_second, onupdate=utc_now_second)

    def perm_list(self):
        """perms 解析为 list[str]；非法 JSON 视为空。"""
        if not self.perms or not self.perms.strip():
            return []
        try:
            v = json.loads(self.perms)
            return [str(x) for x in v] if isinstance(v, list) else []
        except (json.JSONDecodeError, TypeError):
            return []

    def is_super(self):
        return "*" in self.perm_list()

    def to_dict(self, user_count=None):
        d = {
            "id": self.id,
            "name": self.name,
            "code": self.code,
            "description": self.description or "",
            "perms": self.perm_list(),
            "is_super": self.is_super(),
            "is_builtin": bool(self.is_builtin),
            "created_at": self.created_at.strftime("%Y-%m-%d %H:%M:%S") if self.created_at else None,
            "updated_at": self.updated_at.strftime("%Y-%m-%d %H:%M:%S") if self.updated_at else None,
        }
        if user_count is not None:
            d["user_count"] = user_count
        return d


class SysUser(db.Model):
    """系统登录用户（用户管理：增删改查；密码以哈希存储）"""
    __tablename__ = "sys_user"
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(64), unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)
    role_id = db.Column(db.Integer)  # 挂载的角色（sys_role.id），单角色；可空=无角色
    created_at = db.Column(db.DateTime, default=utc_now_second)
    updated_at = db.Column(db.DateTime, default=utc_now_second, onupdate=utc_now_second)

    def to_dict(self, role=None):
        return {
            "id": self.id,
            "username": self.username,
            "role_id": self.role_id,
            "role_name": role.name if role else None,
            "role_code": role.code if role else None,
            "created_at": self.created_at.strftime("%Y-%m-%d %H:%M:%S") if self.created_at else None,
            "updated_at": self.updated_at.strftime("%Y-%m-%d %H:%M:%S") if self.updated_at else None,
        }
