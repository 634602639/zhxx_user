"""值勤数据分析与展示 路由"""
from flask import Blueprint, jsonify, request

from services.log_service import log_op
from services.unit_metric_service import theater_situation
from validators import ValidationError

bp = Blueprint("data_analysis", __name__, url_prefix="/api/analysis")


@bp.route("/theater", methods=["GET"])
def theater():
    """六单位运行态势：按数据对应时间筛选战区指标。"""
    try:
        result = theater_situation(
            request.args.get("date_from"),
            request.args.get("date_to"),
        )
        log_op(
            "数据分析",
            "运行态势",
            f"{result['date_from']}～{result['date_to']}"
            + ("（预置）" if result.get("from_demo") else ""),
        )
        return jsonify({"code": 0, "data": result})
    except ValidationError as e:
        return jsonify({"code": 1, "msg": str(e)}), 400
    except Exception as e:
        log_op("数据分析", "运行态势", str(e), success=False)
        return jsonify({"code": 1, "msg": f"分析失败: {e}"}), 500
