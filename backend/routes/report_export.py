"""值勤报告输出：Word / PPT / PDF（PDF 按正文文字生成）"""
import io

from flask import Blueprint, jsonify, request, send_file, current_app
from models import DutyReport
from utils.exporter import export_word, export_pdf
from services.log_service import log_op

bp = Blueprint("report_export", __name__, url_prefix="/api/report")


@bp.route("/<int:rid>/export", methods=["GET"])
def export(rid):
    fmt = request.args.get("format", "word").lower()
    rpt = DutyReport.query.get_or_404(rid)
    out_dir = current_app.config["EXPORT_DIR"]
    try:
        if fmt == "pdf":
            path = export_pdf(rpt, out_dir)
            safe_title = ((rpt.title or "report").replace("/", "_").replace("\\", "_"))[:200]
            log_op("报告输出", "导出PDF（正文生成）", f"报告id={rid}, 路径={path}")
            return send_file(path, as_attachment=True, download_name=f"{safe_title}.pdf")
        if fmt in ("word", "docx", "doc", "ppt", "pptx"):
            if rpt.file_blob:
                buf = io.BytesIO(rpt.file_blob)
                buf.seek(0)
                mime = (rpt.file_mime or "application/octet-stream").strip()[:128] or "application/octet-stream"
                dn = (rpt.file_name or "").strip()
                if not dn:
                    safe_title = ((rpt.title or "report").replace("/", "_").replace("\\", "_"))[:200]
                    dn = f"{safe_title}.docx" if (rpt.report_type or "") == "word" else f"{safe_title}.pptx"
                log_op("报告输出", "导出Office附件", f"报告id={rid}, download={dn}")
                return send_file(
                    buf,
                    mimetype=mime,
                    as_attachment=True,
                    download_name=dn[:255],
                )
            path = export_word(rpt, out_dir)
            log_op("报告输出", "导出Word（正文生成）", f"报告id={rid}, 路径={path}")
            return send_file(path, as_attachment=True,
                             download_name=f"{rpt.title}.docx")
        return jsonify({"code": 1, "msg": "不支持的格式，仅支持 word / ppt / pdf"}), 400
    except Exception as e:
        log_op("报告输出", f"导出{fmt}", str(e), success=False)
        return jsonify({"code": 1, "msg": f"导出失败: {e}"}), 500
