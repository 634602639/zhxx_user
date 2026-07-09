"""操作日志 查询路由（只读；写入由 services.log_service.log_op 负责）"""
from flask import Blueprint, jsonify, request
from sqlalchemy import or_

from models import OperationLog
from validators import validate_search_keyword, ValidationError

bp = Blueprint("operation_log", __name__, url_prefix="/api")


@bp.route("/logs", methods=["GET"])
def list_logs():
    """按时间倒序返回操作日志，支持按模块/操作/详情关键词过滤。"""
    try:
        keyword = validate_search_keyword(request.args.get("keyword"))
    except ValidationError as e:
        return jsonify({"code": 1, "msg": str(e)}), 400

    try:
        size = int(request.args.get("size", 300))
    except (TypeError, ValueError):
        size = 300
    size = max(1, min(size, 2000))

    q = OperationLog.query
    if keyword:
        like = f"%{keyword}%"
        q = q.filter(or_(
            OperationLog.module.ilike(like),
            OperationLog.action.ilike(like),
            OperationLog.detail.ilike(like),
        ))
    total = q.count()
    items = q.order_by(OperationLog.id.desc()).limit(size).all()
    return jsonify({
        "code": 0,
        "data": {"items": [r.to_dict() for r in items], "total": total, "size": size},
    })
