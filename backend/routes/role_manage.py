"""角色管理 路由：sys_role 增 / 删 / 改 / 查，以及权限点目录查询。

RBAC：角色拥有一组权限点（perms），用户挂到角色上继承其权限。
超级管理员角色（is_super，perms 含 "*"）不可改权限、不可删除。
被用户挂载的角色不可删除（需先把用户改挂别的角色）。
"""
import json

from flask import Blueprint, jsonify, request

from models import db, SysRole, SysUser
from permissions import PERMISSION_CATALOG, normalize_perms, WILDCARD
from validators import (
    validate_role_name, validate_role_code, validate_role_desc,
    validate_role_perms, validate_search_keyword, ValidationError,
)
from services.log_service import log_op

bp = Blueprint("role_manage", __name__, url_prefix="/api")


def _user_count_map():
    """role_id -> 挂载用户数，用于列表展示与「被占用不可删」判断。"""
    rows = (
        db.session.query(SysUser.role_id, db.func.count(SysUser.id))
        .group_by(SysUser.role_id)
        .all()
    )
    return {rid: cnt for rid, cnt in rows if rid is not None}


@bp.route("/permissions", methods=["GET"])
def list_permissions():
    """权限点目录：供前端渲染「勾选权限」的复选树。"""
    return jsonify({"code": 0, "data": {"catalog": PERMISSION_CATALOG}})


@bp.route("/roles", methods=["GET"])
def list_roles():
    try:
        keyword = validate_search_keyword(request.args.get("keyword"))
    except ValidationError as e:
        return jsonify({"code": 1, "msg": str(e)}), 400
    q = SysRole.query
    if keyword:
        like = f"%{keyword}%"
        q = q.filter(db.or_(SysRole.name.ilike(like), SysRole.code.ilike(like)))
    items = q.order_by(SysRole.id.asc()).all()
    counts = _user_count_map()
    data = [r.to_dict(user_count=counts.get(r.id, 0)) for r in items]
    return jsonify({"code": 0, "data": {"items": data, "total": len(data)}})


@bp.route("/roles", methods=["POST"])
def create_role():
    data = request.get_json(silent=True) or {}
    try:
        name = validate_role_name(data.get("name"))
        code = validate_role_code(data.get("code"))
        desc = validate_role_desc(data.get("description"))
        perms = normalize_perms(validate_role_perms(data.get("perms")))
    except ValidationError as e:
        return jsonify({"code": 1, "msg": str(e)}), 400
    if SysRole.query.filter_by(name=name).first():
        return jsonify({"code": 1, "msg": "角色名称已存在"}), 400
    if SysRole.query.filter_by(code=code).first():
        return jsonify({"code": 1, "msg": "角色标识已存在"}), 400
    r = SysRole(
        name=name, code=code, description=desc,
        perms=json.dumps(perms, ensure_ascii=False), is_builtin=False,
    )
    db.session.add(r)
    db.session.commit()
    log_op("角色管理", "新增角色", f"name={name}, code={code}, perms={len(perms)}")
    return jsonify({"code": 0, "msg": "已新增", "data": r.to_dict(user_count=0)})


@bp.route("/roles/<int:rid>", methods=["PUT"])
def update_role(rid):
    r = SysRole.query.get_or_404(rid)
    data = request.get_json(silent=True) or {}
    try:
        if "name" in data:
            new_name = validate_role_name(data.get("name"))
            if new_name != r.name and SysRole.query.filter_by(name=new_name).first():
                return jsonify({"code": 1, "msg": "角色名称已存在"}), 400
            r.name = new_name
        if "description" in data:
            r.description = validate_role_desc(data.get("description"))
        # 角色标识 code 一经创建不允许改（用户/会话可能按 code 引用），忽略传入的 code。
        if "perms" in data:
            if r.is_super():
                return jsonify({"code": 1, "msg": "超级管理员角色拥有全部权限，不可修改"}), 400
            perms = normalize_perms(validate_role_perms(data.get("perms")))
            r.perms = json.dumps(perms, ensure_ascii=False)
    except ValidationError as e:
        return jsonify({"code": 1, "msg": str(e)}), 400
    db.session.commit()
    counts = _user_count_map()
    log_op("角色管理", "修改角色", f"id={rid}, name={r.name}")
    return jsonify({"code": 0, "msg": "已保存", "data": r.to_dict(user_count=counts.get(r.id, 0))})


@bp.route("/roles/<int:rid>", methods=["DELETE"])
def delete_role(rid):
    r = SysRole.query.get_or_404(rid)
    if r.is_builtin:
        return jsonify({"code": 1, "msg": "内置角色不可删除"}), 400
    used = SysUser.query.filter_by(role_id=rid).count()
    if used:
        return jsonify({"code": 1, "msg": f"该角色已分配给 {used} 个用户，请先改挂其它角色"}), 400
    name = r.name
    db.session.delete(r)
    db.session.commit()
    log_op("角色管理", "删除角色", f"id={rid}, name={name}")
    return jsonify({"code": 0, "msg": "已删除"})
