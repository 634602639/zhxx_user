"""值勤报告在线管理 路由：增删改查 + 本地文件导入"""
import io
import mimetypes
import os
import zipfile
from datetime import datetime

from flask import Blueprint, jsonify, request

from models import ReportComposeDraft, db, DutyReport
from services.log_service import log_op
from validators import (
    ValidationError,
    L_REPORT_TITLE,
    require_str,
    validate_report_payload,
    validate_search_keyword,
)
from services.ooxml_preview_service import (
    docx_zip_document_body_plain,
    pptx_zip_plain_extract,
)

# 让 mimetypes 在 Windows 上稳定识别 Office 类型
mimetypes.add_type(
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document", ".docx"
)
mimetypes.add_type("application/msword", ".doc")
mimetypes.add_type(
    "application/vnd.openxmlformats-officedocument.presentationml.presentation", ".pptx"
)
mimetypes.add_type("application/vnd.ms-powerpoint", ".ppt")

bp = Blueprint("report_manage", __name__, url_prefix="/api/report")

# duty_report.report_type 存 word / ppt
_OFFICE_REPORT_TYPES = frozenset({"word", "ppt"})

# 「新增报告」本地导入：仅接受 Office 文档；25MB 防止异常大文件压垮 DB
_IMPORT_ALLOWED_EXT = frozenset({".docx", ".doc", ".pptx", ".ppt"})
_IMPORT_MAX_BYTES = 25 * 1024 * 1024
_IMPORT_MAX_TEXT = 200_000


def _sniff_office_zip_ext(blob: bytes):
    """OOXML zip 嗅探：根据内部目录前缀识别真实 Office 类型；非 zip 返回 None。"""
    if not blob or len(blob) < 4 or blob[:2] != b"PK":
        return None
    try:
        with zipfile.ZipFile(io.BytesIO(blob)) as zf:
            names = zf.namelist()
    except (zipfile.BadZipFile, OSError):
        return None
    if any(n.startswith("word/") for n in names):
        return ".docx"
    if any(n.startswith("ppt/") for n in names):
        return ".pptx"
    return None


def _import_extract_plain(eff_ext: str, blob: bytes) -> str:
    """仅 OOXML 才能可靠抽正文；旧版 .doc/.ppt 不抽，让 content 留空，文件本身仍然入库。"""
    try:
        if eff_ext == ".docx":
            return (docx_zip_document_body_plain(blob) or "").strip()[:_IMPORT_MAX_TEXT]
        if eff_ext == ".pptx":
            return (pptx_zip_plain_extract(blob) or "").strip()[:_IMPORT_MAX_TEXT]
    except Exception:
        return ""
    return ""


@bp.route("/list", methods=["GET"])
def list_reports():
    """查询：keyword 仅标题模糊匹配；report_type=word|ppt；日期 + 分页"""
    page = int(request.args.get("page", 1))
    size = int(request.args.get("size", 10))
    try:
        kw = validate_search_keyword(request.args.get("keyword"))
    except ValidationError as e:
        return jsonify({"code": 1, "msg": str(e)}), 400
    date_from = request.args.get("date_from")
    date_to = request.args.get("date_to")
    rt = (request.args.get("report_type") or "").strip()

    q = DutyReport.query
    if kw:
        like = "%" + kw.replace("%", "").replace("_", "") + "%"
        q = q.filter(DutyReport.title.ilike(like))
    if rt in _OFFICE_REPORT_TYPES:
        q = q.filter(DutyReport.report_type == rt)
    if date_from:
        try:
            q = q.filter(DutyReport.report_date >= datetime.strptime(date_from, "%Y-%m-%d").date())
        except Exception:
            pass
    if date_to:
        try:
            q = q.filter(DutyReport.report_date <= datetime.strptime(date_to, "%Y-%m-%d").date())
        except Exception:
            pass

    total = q.count()
    items = q.order_by(DutyReport.id.desc()).offset((page - 1) * size).limit(size).all()

    # 操作日志：仅保留实际填写过的筛选条件，避免出现「keyword=, range=[None,None]」这种空噪音
    cond_parts = []
    if kw:
        cond_parts.append(f'标题"{kw}"')
    if rt in _OFFICE_REPORT_TYPES:
        cond_parts.append(f"类型={'Word' if rt == 'word' else 'PPT'}")
    if date_from or date_to:
        cond_parts.append(f"日期 [{date_from or '不限'} ~ {date_to or '不限'}]")
    cond_text = "、".join(cond_parts) if cond_parts else "无筛选条件"

    page_text = ""
    if page > 1 or size != 10:
        page_text = f"（第 {page} 页 / 每页 {size} 条）"

    log_op(
        "报告管理",
        "报告查询",
        f"{cond_text}，命中 {total} 条{page_text}",
    )
    return jsonify({"code": 0, "data": {"total": total, "items": [r.to_dict() for r in items]}})


@bp.route("/from-compose-draft/<int:did>", methods=["POST"])
def publish_from_compose_draft(did):
    """合成草稿原样写入 duty_report：不做摘要、不改正文，仅入库。"""
    d = ReportComposeDraft.query.get(did)
    if not d:
        return jsonify({"code": 1, "msg": "草稿不存在"}), 404

    ok = d.office_kind()
    report_type = ok if ok in _OFFICE_REPORT_TYPES else "word"
    title = str(d.title or "").strip()[:255] or "未命名报告"
    rd = datetime.now().date()

    fb = d.file_blob
    fm = (d.file_mime or "").strip()[:128] if d.file_mime else None
    fn = (d.file_name or "").strip()[:255] if d.file_name else None

    try:
        rpt = DutyReport(
            title=title,
            report_type=report_type,
            content="" if d.content is None else d.content,
            template_id=d.template_id,
            report_date=rd,
            file_blob=fb,
            file_mime=fm,
            file_name=fn,
        )
        db.session.add(rpt)
        db.session.commit()
        log_op(
            "报告管理",
            "草稿转正",
            f"compose_draft_id={did} → duty_report id={rpt.id} title={rpt.title}",
        )
        return jsonify({"code": 0, "msg": "已直接保存至报告在线管理", "data": rpt.to_dict()})
    except Exception as e:
        db.session.rollback()
        log_op("报告管理", "草稿转正", str(e), success=False)
        return jsonify({"code": 1, "msg": f"归档失败: {e}"}), 500


@bp.route("/<int:rid>", methods=["GET"])
def get_report(rid):
    r = DutyReport.query.get_or_404(rid)
    return jsonify({"code": 0, "data": r.to_dict()})


@bp.route("/import-file", methods=["POST"])
def import_file():
    """从本地选择一个 Office 文件，直接入库为值勤报告。

    仅接受 .docx / .doc / .pptx / .ppt；扩展名经 ZIP 内容嗅探校正后写回 report_type；
    title 取表单 title 或文件名（去扩展名）；report_date 取表单或今日。
    OOXML 抽正文写入 content；旧版 .doc / .ppt 仅落 file_blob，content 为空。
    """
    if "file" not in request.files:
        return jsonify({"code": 1, "msg": "未上传文件"}), 400
    f = request.files["file"]
    raw_filename = (f.filename or "").strip()
    if not raw_filename:
        return jsonify({"code": 1, "msg": "文件名不能为空"}), 400

    ext = os.path.splitext(raw_filename)[1].lower()
    if ext not in _IMPORT_ALLOWED_EXT:
        allowed = " / ".join(sorted(_IMPORT_ALLOWED_EXT))
        return jsonify(
            {"code": 1, "msg": f"扩展名 {ext or '空'} 不在允许范围（{allowed}）"}
        ), 400

    try:
        blob = f.read()
    except Exception as e:
        return jsonify({"code": 1, "msg": f"读取上传内容失败: {e}"}), 400
    if not blob:
        return jsonify({"code": 1, "msg": "文件内容为空"}), 400
    if len(blob) > _IMPORT_MAX_BYTES:
        return jsonify(
            {"code": 1, "msg": f"文件过大（{len(blob)} 字节，>{_IMPORT_MAX_BYTES}）"}
        ), 400

    sniff = _sniff_office_zip_ext(blob)
    eff_ext = sniff if sniff in (".docx", ".pptx") else ext

    if eff_ext in (".docx", ".doc"):
        report_type = "word"
    elif eff_ext in (".pptx", ".ppt"):
        report_type = "ppt"
    else:
        return jsonify({"code": 1, "msg": "无法识别为 Word / PPT 文件"}), 400

    title_form = (request.form.get("title") or "").strip()
    if not title_form:
        title_form = os.path.splitext(raw_filename)[0].strip()
    try:
        title = require_str(title_form or "未命名报告", "标题", min_len=1, max_len=L_REPORT_TITLE)
    except ValidationError as e:
        return jsonify({"code": 1, "msg": str(e)}), 400

    rd = datetime.now().date()
    rd_str = (request.form.get("report_date") or "").strip()
    if rd_str:
        try:
            rd = datetime.strptime(rd_str, "%Y-%m-%d").date()
        except ValueError:
            pass

    mime = (f.mimetype or "").strip()
    if not mime:
        mime = mimetypes.guess_type(raw_filename)[0] or "application/octet-stream"
    mime = mime[:128]

    plain = _import_extract_plain(eff_ext, blob)

    try:
        rpt = DutyReport(
            title=title,
            report_type=report_type,
            content=plain,
            template_id=None,
            report_date=rd,
            file_blob=blob,
            file_mime=mime,
            file_name=raw_filename[:255],
        )
        db.session.add(rpt)
        db.session.commit()
        log_op(
            "报告管理",
            "报告导入",
            f"id={rpt.id} title={rpt.title} type={report_type} ext={eff_ext} size={len(blob)}B",
        )
        return jsonify({"code": 0, "msg": "导入成功", "data": rpt.to_dict()})
    except Exception as e:
        db.session.rollback()
        log_op("报告管理", "报告导入", str(e), success=False)
        return jsonify({"code": 1, "msg": f"导入失败: {e}"}), 500


@bp.route("/add", methods=["POST"])
def add_report():
    """值勤报告增加（手工新增 + 标签）"""
    data = request.get_json() or {}
    try:
        v = validate_report_payload(data)
        rpt = DutyReport(
            title=v["title"],
            report_type=v["report_type"],
            content=v.get("content") or "",
            template_id=data.get("template_id"),
            report_date=datetime.strptime(data["report_date"], "%Y-%m-%d").date()
                if data.get("report_date") else datetime.now().date(),
        )
        db.session.add(rpt); db.session.commit()
        log_op("报告管理", "报告增加", f"新增报告id={rpt.id}, 标题={rpt.title}")
        return jsonify({"code": 0, "msg": "新增成功", "data": rpt.to_dict()})
    except (ValueError, ValidationError) as e:
        return jsonify({"code": 1, "msg": str(e)}), 400
    except Exception as e:
        log_op("报告管理", "报告增加", str(e), success=False)
        return jsonify({"code": 1, "msg": f"新增失败: {e}"}), 500


@bp.route("/<int:rid>", methods=["PUT"])
def update_report(rid):
    rpt = DutyReport.query.get_or_404(rid)
    data = request.get_json() or {}
    try:
        v = validate_report_payload(data, for_update=True)
        for f in ("title", "report_type", "content"):
            if f in v:
                setattr(rpt, f, v[f])
    except (ValueError, ValidationError) as e:
        return jsonify({"code": 1, "msg": str(e)}), 400
    if data.get("report_date"):
        try:
            rpt.report_date = datetime.strptime(data["report_date"], "%Y-%m-%d").date()
        except Exception:
            pass
    db.session.commit()
    log_op("报告管理", "报告修改", f"修改报告id={rid}")
    return jsonify({"code": 0, "msg": "修改成功", "data": rpt.to_dict()})


@bp.route("/<int:rid>", methods=["DELETE"])
def delete_report(rid):
    rpt = DutyReport.query.get_or_404(rid)
    db.session.delete(rpt); db.session.commit()
    log_op("报告管理", "报告删除", f"删除报告id={rid}")
    return jsonify({"code": 0, "msg": "删除成功"})
