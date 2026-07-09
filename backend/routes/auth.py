"""登录鉴权路由：账号存于 sys_user 表（密码哈希），基于 Flask session。

登录态接口同时下发当前用户的「角色 + 权限点集合」，供前端按权限隐藏菜单/按钮。
（当前仅前端隐藏；如需后端强制拦截，可在 app.py 的 before_request 里用 _user_perms 校验。）
"""
from flask import Blueprint, jsonify, request, session

from werkzeug.security import check_password_hash

from models import SysUser, SysRole
from permissions import expand_perms, WILDCARD
from services.log_service import log_op

bp = Blueprint("auth", __name__, url_prefix="/api")


def _user_perms(user):
    """返回 (perms_list, is_super, role_dict)。无角色则空权限。"""
    role = SysRole.query.get(user.role_id) if user and user.role_id else None
    if not role:
        return [], False, None
    if role.is_super():
        return [WILDCARD], True, {"id": role.id, "name": role.name, "code": role.code}
    perms = sorted(expand_perms(role.perm_list()))
    return perms, False, {"id": role.id, "name": role.name, "code": role.code}


@bp.route("/login", methods=["POST"])
def login():
    data = request.get_json(silent=True) or {}
    user = (data.get("username") or "").strip()
    pwd = data.get("password") or ""
    u = SysUser.query.filter_by(username=user).first()
    if u and check_password_hash(u.password_hash, pwd):
        session["logged_in"] = True
        session["user"] = u.username
        session["uid"] = u.id
        perms, is_super, role = _user_perms(u)
        log_op("用户登录", "登录", f"用户「{u.username}」登录成功")
        return jsonify({"code": 0, "msg": "登录成功", "data": {
            "user": u.username, "perms": perms, "is_super": is_super, "role": role,
        }})
    log_op("用户登录", "登录", f"登录失败：用户名「{user}」或密码错误", success=False)
    return jsonify({"code": 1, "msg": "用户名或密码错误"}), 401


@bp.route("/logout", methods=["POST"])
def logout():
    user = session.get("user")
    session.clear()
    if user:
        log_op("用户登录", "退出", f"用户「{user}」退出登录")
    return jsonify({"code": 0, "msg": "已退出登录"})


@bp.route("/auth/status", methods=["GET"])
def status():
    logged_in = bool(session.get("logged_in"))
    perms, is_super, role = [], False, None
    if logged_in and session.get("uid"):
        u = SysUser.query.get(session.get("uid"))
        if u:
            perms, is_super, role = _user_perms(u)
    return jsonify({
        "code": 0,
        "data": {
            "logged_in": logged_in,
            "user": session.get("user"),
            "uid": session.get("uid"),
            "perms": perms,
            "is_super": is_super,
            "role": role,
        },
    })
