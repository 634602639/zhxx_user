"""用户管理 路由：sys_user 增 / 删 / 改 / 查（不能删除当前登录用户）。

每个用户可挂载一个角色（role_id -> sys_role.id），从而继承该角色的权限。
"""
from flask import Blueprint, jsonify, request, session
from werkzeug.security import generate_password_hash

from models import db, SysUser, SysRole
from validators import (
    validate_username, validate_password, validate_search_keyword, ValidationError,
)
from services.log_service import log_op

bp = Blueprint("user_manage", __name__, url_prefix="/api")


def _is_current(u):
    """是否当前登录用户（兼容旧 session 缺 uid 的情况，按用户名兜底）。"""
    return u.id == session.get("uid") or u.username == session.get("user")


def _role_map():
    """role_id -> SysRole，供列表/详情回填角色名。"""
    return {r.id: r for r in SysRole.query.all()}


def _resolve_role_id(value):
    """校验并返回合法的 role_id；空 / 0 视为「不挂角色」返回 None。

    抛 ValidationError 表示传入了一个不存在的角色。
    """
    if value in (None, "", 0, "0"):
        return None
    try:
        rid = int(value)
    except (TypeError, ValueError):
        raise ValidationError("角色无效")
    if not SysRole.query.get(rid):
        raise ValidationError("角色不存在")
    return rid


@bp.route("/users", methods=["GET"])
def list_users():
    try:
        keyword = validate_search_keyword(request.args.get("keyword"))
    except ValidationError as e:
        return jsonify({"code": 1, "msg": str(e)}), 400
    q = SysUser.query
    if keyword:
        q = q.filter(SysUser.username.ilike(f"%{keyword}%"))
    items = q.order_by(SysUser.id.asc()).all()
    roles = _role_map()
    data = []
    for u in items:
        d = u.to_dict(role=roles.get(u.role_id))
        d["is_current"] = _is_current(u)
        data.append(d)
    return jsonify({"code": 0, "data": {"items": data, "total": len(data)}})


@bp.route("/users", methods=["POST"])
def create_user():
    data = request.get_json(silent=True) or {}
    try:
        username = validate_username(data.get("username"))
        password = validate_password(data.get("password"), required=True)
        role_id = _resolve_role_id(data.get("role_id"))
    except ValidationError as e:
        return jsonify({"code": 1, "msg": str(e)}), 400
    if SysUser.query.filter_by(username=username).first():
        return jsonify({"code": 1, "msg": "用户名已存在"}), 400
    u = SysUser(
        username=username,
        password_hash=generate_password_hash(password),
        role_id=role_id,
    )
    db.session.add(u)
    db.session.commit()
    log_op("用户管理", "新增用户", f"username={username}, role_id={role_id}")
    return jsonify({"code": 0, "msg": "已新增", "data": u.to_dict(role=SysRole.query.get(role_id) if role_id else None)})


@bp.route("/users/<int:uid>", methods=["PUT"])
def update_user(uid):
    u = SysUser.query.get_or_404(uid)
    data = request.get_json(silent=True) or {}
    try:
        if "username" in data:
            new_name = validate_username(data.get("username"))
            if new_name != u.username and SysUser.query.filter_by(username=new_name).first():
                return jsonify({"code": 1, "msg": "用户名已存在"}), 400
            u.username = new_name
        pwd = data.get("password")
        if pwd:  # 仅当填了新密码才修改
            u.password_hash = generate_password_hash(validate_password(pwd, required=True))
        if "role_id" in data:
            u.role_id = _resolve_role_id(data.get("role_id"))
    except ValidationError as e:
        return jsonify({"code": 1, "msg": str(e)}), 400
    db.session.commit()
    if _is_current(u):  # 改了当前用户名，同步 session
        session["user"] = u.username
    log_op("用户管理", "修改用户", f"id={uid}, username={u.username}, role_id={u.role_id}")
    return jsonify({"code": 0, "msg": "已保存", "data": u.to_dict(role=SysRole.query.get(u.role_id) if u.role_id else None)})


@bp.route("/users/<int:uid>", methods=["DELETE"])
def delete_user(uid):
    u = SysUser.query.get_or_404(uid)
    if _is_current(u):
        return jsonify({"code": 1, "msg": "不能删除当前登录用户"}), 400
    name = u.username
    db.session.delete(u)
    db.session.commit()
    log_op("用户管理", "删除用户", f"id={uid}, username={name}")
    return jsonify({"code": 0, "msg": "已删除"})
