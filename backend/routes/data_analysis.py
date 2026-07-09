"""值勤数据分析与展示 路由"""
from flask import Blueprint, jsonify, request
from services import data_service
from services.log_service import log_op

bp = Blueprint("data_analysis", __name__, url_prefix="/api/analysis")


@bp.route("/multi-dim", methods=["GET"])
def multi_dim():
    """多维数据分析（来源/类别/日期/数值）+ 用于多维数据展示"""
    try:
        result = data_service.multi_dim_analysis()
        log_op("数据分析", "多维分析", f"分析完成，共{result['total']}条")
        return jsonify({"code": 0, "data": result})
    except Exception as e:
        log_op("数据分析", "多维分析", str(e), success=False)
        return jsonify({"code": 1, "msg": f"分析失败: {e}"}), 500


@bp.route("/snapshot", methods=["POST"])
def save_snapshot():
    """数据存储：把当前 4 个 KPI（样本总量/日均采集/峰值/覆盖来源）存为一条快照。"""
    data = request.get_json(silent=True) or {}
    try:
        snap = data_service.save_analysis_snapshot(data)
        log_op(
            "数据分析", "KPI存储",
            f"样本{snap['total']}/日均{snap['daily_avg']}/峰值{snap['peak']}/来源{snap['source_count']}",
        )
        return jsonify({"code": 0, "data": snap, "msg": "已存储"})
    except ValueError as e:
        return jsonify({"code": 1, "msg": str(e)}), 400
    except Exception as e:
        log_op("数据分析", "KPI存储", str(e), success=False)
        return jsonify({"code": 1, "msg": f"存储失败: {e}"}), 500
