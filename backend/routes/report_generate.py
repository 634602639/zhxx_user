"""值勤报告辅助生成 路由（模板采集 / 关键词提取 / 文本总结 / 报告生成）

设计要点：
  - 文件名带时间戳前缀，避免同名覆盖。
  - 上传严格校验：扩展名白名单、内容非空。
  - 列表接口走 to_brief()，不返回模板正文，体积可控。
  - 删除模板时清理磁盘文件，避免 uploads 目录无限增长。
  - 报告生成时若指定不存在的 template_id 则 404，不再静默回退默认模板。
"""
import html
import io
import json
import mimetypes
import os
import zipfile
from datetime import datetime, time
from typing import Optional

from flask import Blueprint, jsonify, request, send_file
from sqlalchemy import or_

from models import CleanData, db, ReportComposeDraft, ReportTemplate
from services import report_service
from services.log_service import log_op
from services.ooxml_preview_service import (
    docx_zip_document_body_plain,
    docx_zip_plain_extract,
    docx_zip_to_html,
    ooxml_plain_preview_html,
    pptx_zip_plain_extract,
    pptx_zip_to_html,
)
from services.nlp_service import extract_keywords, summarize, extract_placeholders
from validators import (
    ValidationError,
    L_TEMPLATE_NAME,
    require_str,
    validate_compose_draft_content,
    validate_compose_draft_title,
    validate_search_keyword,
    validate_slot_manual,
)
from services.docx_fill_service import fill_docx_body_from_values, sniff_word_ext
from services.pptx_fill_service import (
    build_pptx_from_plain_fallback,
    fill_pptx_body_from_values,
    pptx_zip_slots_plain,
    sniff_pptx_ext,
)

# 让 mimetypes 认识 .docx / .pptx 等 Office 类型
mimetypes.add_type("application/vnd.openxmlformats-officedocument.wordprocessingml.document", ".docx")
mimetypes.add_type("application/msword", ".doc")
mimetypes.add_type("application/vnd.openxmlformats-officedocument.presentationml.presentation", ".pptx")
mimetypes.add_type("application/vnd.ms-powerpoint", ".ppt")

bp = Blueprint("report_generate", __name__, url_prefix="/api/template")

# ① 模板采集上传白名单（仅 .docx）
ALLOWED_EXT = {".docx"}
MAX_TEXT_BYTES = 200_000   # 摘要 / 关键词在线试用入参上限
MAX_TEMPLATE_BYTES = 500_000


@bp.route("/upload", methods=["POST"])
def upload_template():
    """报告模板采集：仅接受 .docx，上传后解析正文与占位符。"""
    if "file" not in request.files:
        return jsonify({"code": 1, "msg": "未上传文件"}), 400
    f = request.files["file"]
    raw_filename = (f.filename or "").strip()
    if not raw_filename:
        return jsonify({"code": 1, "msg": "文件名不能为空"}), 400

    ext = os.path.splitext(raw_filename)[1].lower()
    if not ext:
        return jsonify({"code": 1, "msg": "文件缺少扩展名，无法识别类型"}), 400
    if ext not in ALLOWED_EXT:
        allowed = " / ".join(sorted(ALLOWED_EXT))
        return jsonify({"code": 1, "msg": f"扩展名 {ext} 不在允许范围（{allowed}）"}), 400

    # 模板名取自表单或文件名（去扩展名），strip 后不能为空
    try:
        name = require_str(
            request.form.get("name") or os.path.splitext(raw_filename)[0],
            "模板名称",
            min_len=1,
            max_len=L_TEMPLATE_NAME,
        )
    except ValidationError as e:
        return jsonify({"code": 1, "msg": str(e)}), 400

    # 一次性读字节，全程在内存里处理
    try:
        blob = f.read()
    except Exception as e:
        return jsonify({"code": 1, "msg": f"读取上传内容失败: {e}"}), 400
    if not blob:
        return jsonify({"code": 1, "msg": "文件内容为空"}), 400

    mime = (f.mimetype or "").strip() or mimetypes.guess_type(raw_filename)[0] or "application/octet-stream"

    # 抽正文：按 zip 嗅探纠正误判扩展名（例如实为 docx 却写成 .doc）
    eff = _normalize_preview_ext(ext, blob)
    if eff != ".docx":
        return jsonify({"code": 1, "msg": "仅支持 .docx 模板文件"}), 400
    parsed = _decode_template_bytes(blob, ".docx") or ""
    if parsed and len(parsed) > MAX_TEMPLATE_BYTES:
        parsed = parsed[:MAX_TEMPLATE_BYTES]
    text = parsed
    keywords = ",".join(extract_keywords(text, top_k=10)) if text else ""
    placeholders = extract_placeholders(text)

    tpl = ReportTemplate(
        name=name,
        file_path=None,          # 不再依赖磁盘
        file_blob=blob,
        file_size=len(blob),
        mime_type=mime,
        original_filename=raw_filename[:255],
        content=text,
        keywords=keywords,
    )
    db.session.add(tpl)
    db.session.commit()
    log_op(
        "报告生成", "模板采集",
        f"上传 {name} ({ext}, {len(blob)} 字节, 占位符 {len(placeholders)} 个)",
    )
    payload = tpl.to_dict()
    payload["placeholders"] = placeholders
    return jsonify({"code": 0, "msg": "上传成功", "data": payload})


def _decode_template_bytes(blob: bytes, ext: str) -> Optional[str]:
    """从字节内容解析模板正文文本（仅对 .docx / .txt 有效）。"""
    if ext == ".docx":
        try:
            from docx import Document
            doc = Document(io.BytesIO(blob))
            return "\n".join(p.text for p in doc.paragraphs) or None
        except Exception:
            return None
    if ext == ".txt":
        for enc in ("utf-8", "utf-8-sig", "gbk"):
            try:
                return blob.decode(enc) or None
            except UnicodeDecodeError:
                continue
        return None
    return None


def _sniff_office_zip_ext(blob: bytes) -> Optional[str]:
    """根据 OOXML zip 包内目录识别真实 Office 类型。"""
    if not blob or len(blob) < 4 or blob[:2] != b"PK":
        return None
    try:
        with zipfile.ZipFile(io.BytesIO(blob)) as zf:
            names = zf.namelist()
        if any(n.startswith("word/") for n in names):
            return ".docx"
        if any(n.startswith("ppt/") for n in names):
            return ".pptx"
        if any(n.startswith("xl/") for n in names):
            return ".xlsx"
    except Exception:
        return None
    return None


def _normalize_preview_ext(ext: str, blob: bytes) -> str:
    """扩展名为空或与 zip 内容不一致时，以文件内容为准（修正 .ppt/.doc 误判为 pptx/docx）。"""
    ext = (ext or "").lower()
    sniff = _sniff_office_zip_ext(blob)
    if not sniff:
        return ext
    if ext in ("", ".bin", ".dat", ".tmp"):
        return sniff
    if sniff == ".pptx" and ext == ".ppt":
        return ".pptx"
    if sniff == ".docx" and ext == ".doc":
        return ".docx"
    return ext


def _template_blob_bytes(t: ReportTemplate) -> Optional[bytes]:
    if t.file_blob:
        return t.file_blob
    if t.file_path and os.path.isfile(t.file_path):
        try:
            with open(t.file_path, "rb") as f:
                return f.read()
        except OSError:
            return None
    return None


# mammoth：中文内置样式名映射，提升标题等还原度（仍弱于浏览器 docx-preview）
MAMMOTH_STYLE_MAP = """
p[style-name='Heading 1'] => h1:fresh
p[style-name='Heading 2'] => h2:fresh
p[style-name='Heading 3'] => h3:fresh
p[style-name='Title'] => h1:fresh
p[style-name='Subtitle'] => h2:fresh
p[style-name='标题'] => h1:fresh
p[style-name='标题 1'] => h1:fresh
p[style-name='标题 2'] => h2:fresh
p[style-name='标题 3'] => h3:fresh
p[style-name='副标题'] => h2:fresh
"""


def _ppt_shape_plain(shape) -> str:
    from pptx.enum.shapes import MSO_SHAPE_TYPE

    try:
        st = shape.shape_type
    except Exception:
        return ""
    if st == MSO_SHAPE_TYPE.GROUP:
        parts = []
        for s in shape.shapes:
            p = _ppt_shape_plain(s)
            if p:
                parts.append(p)
        return "\n".join(parts)
    if getattr(shape, "has_text_frame", False) and shape.has_text_frame:
        return (shape.text_frame.text or "").strip()
    if getattr(shape, "has_table", False) and shape.has_table:
        try:
            rows = []
            for row in shape.table.rows:
                cells = [(cell.text or "").strip() for cell in row.cells]
                rows.append("\t".join(cells))
            return "\n".join(rows)
        except Exception:
            return ""
    return ""


def _runs_to_html(paragraph) -> str:
    parts = []
    for run in paragraph.runs:
        t = html.escape(run.text)
        try:
            if run.font.bold:
                t = f"<strong>{t}</strong>"
            if run.font.italic:
                t = f"<em>{t}</em>"
            if run.font.underline:
                t = f"<u>{t}</u>"
        except Exception:
            pass
        parts.append(t)
    return "".join(parts).strip()


def _text_frame_to_html(tf) -> str:
    blocks = []
    for para in tf.paragraphs:
        line = _runs_to_html(para)
        if line:
            blocks.append(f"<p>{line}</p>")
    return "".join(blocks)


def _ppt_table_to_html(table) -> str:
    rows_html = []
    for row in table.rows:
        cells = []
        for cell in row.cells:
            inner = ""
            try:
                if cell.text_frame:
                    inner = _text_frame_to_html(cell.text_frame)
                elif (cell.text or "").strip():
                    inner = f"<p>{html.escape(cell.text.strip())}</p>"
            except Exception:
                if (cell.text or "").strip():
                    inner = f"<p>{html.escape(cell.text.strip())}</p>"
            cells.append(f"<td>{inner}</td>")
        rows_html.append("<tr>" + "".join(cells) + "</tr>")
    return '<table class="ppt-table">' + "".join(rows_html) + "</table>"


def _ppt_shape_to_html(shape) -> str:
    from pptx.enum.shapes import MSO_SHAPE_TYPE

    try:
        st = shape.shape_type
    except Exception:
        return ""

    if st == MSO_SHAPE_TYPE.GROUP:
        try:
            return "".join(_ppt_shape_to_html(s) for s in shape.shapes)
        except Exception:
            return ""

    chunks = []
    if getattr(shape, "has_text_frame", False) and shape.has_text_frame:
        h = _text_frame_to_html(shape.text_frame)
        if h:
            chunks.append(h)
    if getattr(shape, "has_table", False) and shape.has_table:
        try:
            chunks.append(_ppt_table_to_html(shape.table))
        except Exception:
            pass
    return "".join(chunks)


def _pptx_plain_text(blob: bytes) -> Optional[str]:
    """从 .pptx 抽取纯文本（含组合形状、表格），供关键词与 X 占位检测。未安装 python-pptx 时退回 Zip/OOXML 全文。"""
    try:
        from pptx import Presentation

        prs = Presentation(io.BytesIO(blob))
        lines = []
        for slide in prs.slides:
            for shape in slide.shapes:
                raw = _ppt_shape_plain(shape)
                if raw:
                    lines.append(raw)
        return "\n".join(lines) if lines else None
    except ImportError:
        t = (pptx_zip_plain_extract(blob) or "").strip()
        return t or None
    except Exception:
        return None


def _pptx_to_html(blob: bytes) -> str:
    """将 .pptx 转为 HTML：逐幻灯片、递归组合形状、表格、粗斜体下划线。无 python-pptx 时退回 OOXML 解析。"""
    try:
        from pptx import Presentation

        prs = Presentation(io.BytesIO(blob))
        if len(prs.slides) == 0:
            return '<p class="muted">（无幻灯片）</p>'
        sections = []
        for idx, slide in enumerate(prs.slides):
            sections.append(f'<article class="ppt-slide" data-slide="{idx + 1}">')
            sections.append(f'<header class="ppt-slide-head">幻灯片 {idx + 1}</header>')
            sections.append('<div class="ppt-slide-body">')
            inner = ""
            for shape in slide.shapes:
                inner += _ppt_shape_to_html(shape)
            if inner.strip():
                sections.append(inner)
            else:
                sections.append('<p class="muted ppt-slide-empty">（本页无文本或仅有图片等未解析对象）</p>')
            sections.append("</div></article>")
        return "\n".join(sections)
    except ImportError:
        inner = pptx_zip_to_html(blob).strip()
        if inner:
            return f'<div class="preview-pptx preview-ooxml-fallback">{inner}</div>'
        return (
            '<p class="muted">未安装 python-pptx，已尝试 OOXML 预览仍无内容。请在后端环境执行：'
            "<code>pip install python-pptx==0.6.23</code></p>"
        )
    except Exception as e:
        return f'<p class="muted">无法解析该演示文稿：{html.escape(str(e))}</p>'


@bp.route("/<int:tid>/preview-html", methods=["GET"])
def preview_html(tid: int):
    """将模板原件转为 HTML，便于前端保留 Word / PPT 的基本版式预览。"""
    t = ReportTemplate.query.get(tid)
    if not t:
        return jsonify({"code": 1, "msg": "模板不存在"}), 404
    blob = _template_blob_bytes(t)
    if not blob:
        return jsonify({"code": 1, "msg": "原始文件已不存在"}), 404

    fname = (t.original_filename or "").strip().lower()
    ext = os.path.splitext(fname)[1]
    if not ext:
        mime = (t.mime_type or "").lower()
        if "wordprocessingml.document" in mime:
            ext = ".docx"
        elif "presentationml.presentation" in mime:
            ext = ".pptx"
        elif mime in ("application/msword",) or "msword" in mime:
            ext = ".doc"
        elif "powerpoint" in mime:
            ext = ".ppt"
        elif mime.startswith("text/plain"):
            ext = ".txt"

    ext = _normalize_preview_ext(ext, blob)

    try:
        if ext == ".docx":
            plain = (docx_zip_plain_extract(blob) or "").strip()
            plain_body = (docx_zip_document_body_plain(blob) or "").strip()
            if plain:
                return jsonify(
                    {
                        "code": 0,
                        "data": {
                            "format": "docx",
                            "html": ooxml_plain_preview_html(plain),
                            "plain_text": plain,
                            "plain_text_body": plain_body,
                            "preview_engine": "ooxml-plain",
                        },
                    }
                )
            oox = docx_zip_to_html(blob).strip()
            if oox:
                return jsonify(
                    {
                        "code": 0,
                        "data": {
                            "format": "docx",
                            "html": f'<div class="preview-docx preview-ooxml">{oox}</div>',
                            "preview_engine": "ooxml-xml",
                        },
                    }
                )
            import mammoth

            result = mammoth.convert_to_html(
                io.BytesIO(blob),
                style_map=MAMMOTH_STYLE_MAP,
            )
            body = (result.value or "").strip()
            if not body:
                body = '<p class="muted">（未解析到正文）</p>'
            return jsonify(
                {
                    "code": 0,
                    "data": {
                        "format": "docx",
                        "html": f'<div class="preview-docx">{body}</div>',
                        "preview_engine": "mammoth",
                    },
                }
            )

        if ext == ".pptx":
            plain = (pptx_zip_plain_extract(blob) or "").strip()
            plain_body = (pptx_zip_slots_plain(blob) or "").strip()
            if plain:
                return jsonify(
                    {
                        "code": 0,
                        "data": {
                            "format": "pptx",
                            "html": ooxml_plain_preview_html(plain),
                            "plain_text": plain,
                            "plain_text_body": plain_body,
                            "preview_engine": "ooxml-plain",
                        },
                    }
                )
            oox_p = pptx_zip_to_html(blob).strip()
            if oox_p:
                return jsonify(
                    {
                        "code": 0,
                        "data": {
                            "format": "pptx",
                            "html": f'<div class="preview-pptx preview-ooxml">{oox_p}</div>',
                            "preview_engine": "ooxml-xml",
                        },
                    }
                )
            return jsonify(
                {
                    "code": 0,
                    "data": {
                        "format": "pptx",
                        "html": f'<div class="preview-pptx">{_pptx_to_html(blob)}</div>',
                        "preview_engine": "python-pptx",
                    },
                }
            )

        if ext == ".txt":
            raw = _decode_template_bytes(blob, ".txt") or ""
            esc = html.escape(raw)
            return jsonify(
                {
                    "code": 0,
                    "data": {
                        "format": "txt",
                        "html": f'<pre class="preview-txt">{esc}</pre>',
                        "plain_text": raw,
                    },
                }
            )

        if ext == ".doc":
            return jsonify(
                {
                    "code": 0,
                    "data": {
                        "format": "doc",
                        "html": None,
                        "hint": "旧版 .doc 无法在浏览器中还原版式，请另存为 .docx 后重新上传以预览。",
                    },
                }
            )

        if ext == ".ppt":
            return jsonify(
                {
                    "code": 0,
                    "data": {
                        "format": "ppt",
                        "html": None,
                        "hint": "旧版 .ppt 不支持在线版式预览，请另存为 .pptx 后重新上传。",
                    },
                }
            )

        return jsonify({"code": 0, "data": {"format": ext or "unknown", "html": None, "hint": "不支持该类型的版式预览。"}})
    except Exception as e:
        log_op("报告生成", "模板预览", str(e), success=False)
        return jsonify({"code": 1, "msg": f"预览转换失败: {e}"}), 500


def _resolve_template_fill_values(bindings) -> list:
    """与前端占位映射一致：解析 bindings 为替换字符串列表（顺序即占位 1..n）。"""
    vals = []
    for b in bindings or []:
        b = b or {}
        mode = b.get("mode")
        if mode == "clean" and b.get("cleanId"):
            cid = b.get("cleanId")
            try:
                cid = int(cid)
            except (TypeError, ValueError):
                cid = None
            row = CleanData.query.get(cid) if cid else None
            vals.append(
                str(row.content) if row and row.content is not None else "（未找到该条入库数据）"
            )
        else:
            vals.append(str(b.get("manual") or "").strip())
    return vals


def _filled_office_bytes_for_draft(t: ReportTemplate, bind_list: list, plain_content: str):
    """生成与「下载预览」一致的替换后 Office 字节流；版式替换失败时尽力回退为纯文本新建。"""
    blob = _template_blob_bytes(t)
    fname_lower = (t.original_filename or "").strip().lower()
    safe = "".join(c for c in (t.name or "draft") if c not in '\\/:*?"<>|')[:80] or "draft"
    vals = _resolve_template_fill_values(bind_list)
    text = (plain_content or "").strip()

    if blob:
        is_pptx = sniff_pptx_ext(blob, t.original_filename or "") == ".pptx"
        is_docx = sniff_word_ext(blob, t.original_filename or "") == ".docx"
        if is_pptx:
            try:
                out = fill_pptx_body_from_values(blob, vals)
                return (
                    out,
                    "application/vnd.openxmlformats-officedocument.presentationml.presentation",
                    f"{safe}_草稿.pptx",
                )
            except Exception:
                pass
        if is_docx:
            try:
                out = fill_docx_body_from_values(blob, vals)
                return (
                    out,
                    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                    f"{safe}_草稿.docx",
                )
            except Exception:
                pass

    if not text:
        return None, None, None

    if fname_lower.endswith(".pptx"):
        try:
            out = build_pptx_from_plain_fallback((t.name or "").strip() or "模板预览", text)
            return (
                out,
                "application/vnd.openxmlformats-officedocument.presentationml.presentation",
                f"{safe}_草稿.pptx",
            )
        except Exception:
            pass

    try:
        from docx import Document
        from docx.shared import Pt

        doc = Document()
        hd = (t.name or "").strip() or "模板预览"
        doc.add_heading(hd, level=1)
        for line in text.split("\n"):
            p = doc.add_paragraph(line)
            for run in p.runs:
                run.font.size = Pt(11)
        buf = io.BytesIO()
        doc.save(buf)
        return (
            buf.getvalue(),
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            f"{safe}_草稿.docx",
        )
    except Exception:
        return None, None, None


@bp.route("/<int:tid>/filled-docx", methods=["POST"])
def download_filled_docx(tid: int):
    """生成替换后的 Office 文件：.docx / .pptx 优先在原模板版式内替换；否则回退为新建文档。"""
    t = ReportTemplate.query.get(tid)
    if not t:
        return jsonify({"code": 1, "msg": "模板不存在"}), 404
    data = request.get_json(force=True, silent=True) or {}
    content = data.get("content")
    bind_list = data.get("bindings")
    if not isinstance(bind_list, list):
        bind_list = []

    blob = _template_blob_bytes(t)
    fname_lower = (t.original_filename or "").strip().lower()
    is_pptx = bool(blob) and sniff_pptx_ext(blob, t.original_filename or "") == ".pptx"
    is_docx = bool(blob) and sniff_word_ext(blob, t.original_filename or "") == ".docx"

    if is_pptx:
        try:
            vals = _resolve_template_fill_values(bind_list)
            out_bytes = fill_pptx_body_from_values(blob, vals)
            buf = io.BytesIO(out_bytes)
            buf.seek(0)
            safe = "".join(c for c in (t.name or "preview") if c not in '\\/:*?"<>|')[:80] or "preview"
            log_op("报告生成", "模板样式导出PPT", f"模板 id={tid}")
            return send_file(
                buf,
                mimetype="application/vnd.openxmlformats-officedocument.presentationml.presentation",
                as_attachment=True,
                download_name=f"{safe}_预览.pptx",
            )
        except Exception as e:
            log_op("报告生成", "模板样式导出PPT", str(e), success=False)
            return jsonify({"code": 1, "msg": f"PPT 版式内替换失败（不会改用简化模板）: {e}"}), 500

    if is_docx:
        try:
            vals = _resolve_template_fill_values(bind_list)
            out_bytes = fill_docx_body_from_values(blob, vals)
            buf = io.BytesIO(out_bytes)
            buf.seek(0)
            safe = "".join(c for c in (t.name or "preview") if c not in '\\/:*?"<>|')[:80] or "preview"
            log_op("报告生成", "模板样式导出Word", f"模板 id={tid}")
            return send_file(
                buf,
                mimetype="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                as_attachment=True,
                download_name=f"{safe}_预览.docx",
            )
        except Exception as e:
            log_op("报告生成", "模板样式导出Word（回退纯文本）", str(e), success=False)

    text = str(content or "").strip()
    if not text:
        return jsonify({"code": 1, "msg": "正文为空，请先填写占位或选择入库数据"}), 400
    if len(text) > 2_000_000:
        return jsonify({"code": 1, "msg": "正文过长"}), 400

    if is_pptx or fname_lower.endswith(".pptx"):
        try:
            buf = io.BytesIO(
                build_pptx_from_plain_fallback((t.name or "").strip() or "模板预览", text)
            )
            buf.seek(0)
            safe = "".join(c for c in (t.name or "preview") if c not in '\\/:*?"<>|')[:80] or "preview"
            log_op("报告生成", "纯文本新建PPT预览(内嵌模板)", f"模板 id={tid}")
            return send_file(
                buf,
                mimetype="application/vnd.openxmlformats-officedocument.presentationml.presentation",
                as_attachment=True,
                download_name=f"{safe}_预览.pptx",
            )
        except Exception as e:
            log_op("报告生成", "新建PPT预览", str(e), success=False)
            return jsonify({"code": 1, "msg": f"生成 PowerPoint 失败: {e}"}), 500

    try:
        from docx import Document
        from docx.shared import Pt

        doc = Document()
        title = (t.name or "").strip() or "模板预览"
        doc.add_heading(title, level=1)
        for line in text.split("\n"):
            p = doc.add_paragraph(line)
            for run in p.runs:
                run.font.size = Pt(11)
        buf = io.BytesIO()
        doc.save(buf)
        buf.seek(0)
        safe = "".join(c for c in (t.name or "preview") if c not in '\\/:*?"<>|')[:80] or "preview"
        return send_file(
            buf,
            mimetype="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            as_attachment=True,
            download_name=f"{safe}_预览.docx",
        )
    except Exception as e:
        log_op("报告生成", "替换正文导出Word", str(e), success=False)
        return jsonify({"code": 1, "msg": f"生成 Word 失败: {e}"}), 500


@bp.route("/list", methods=["GET"])
def list_templates():
    items = ReportTemplate.query.order_by(ReportTemplate.id.desc()).all()
    return jsonify({"code": 0, "data": [t.to_brief() for t in items]})


@bp.route("/<int:tid>", methods=["GET"])
def get_template(tid: int):
    t = ReportTemplate.query.get(tid)
    if not t:
        return jsonify({"code": 1, "msg": "模板不存在"}), 404
    return jsonify({"code": 0, "data": t.to_dict()})


@bp.route("/<int:tid>", methods=["DELETE"])
def del_template(tid: int):
    t = ReportTemplate.query.get(tid)
    if not t:
        return jsonify({"code": 1, "msg": "模板不存在"}), 404
    name = t.name
    legacy_path = t.file_path        # 旧数据可能落过盘，尽量顺手清理
    db.session.delete(t)
    db.session.commit()
    if legacy_path:
        try:
            if os.path.isfile(legacy_path):
                os.remove(legacy_path)
        except OSError as e:
            log_op("报告生成", "模板删除", f"DB 已删，但磁盘清理失败: {legacy_path} ({e})", success=False)
    log_op("报告生成", "模板删除", f"id={tid} {name}")
    return jsonify({"code": 0, "msg": "已删除"})


@bp.route("/<int:tid>/download", methods=["GET"])
def download_template(tid: int):
    """从 DB blob 直接回吐原始文件；旧数据若只有 file_path，则回退读盘。"""
    t = ReportTemplate.query.get(tid)
    if not t:
        return jsonify({"code": 1, "msg": "模板不存在"}), 404
    fname = t.original_filename or (t.name + os.path.splitext(t.file_path or "")[1] if t.file_path else (t.name or "template"))
    mime = t.mime_type or "application/octet-stream"

    if t.file_blob:
        return send_file(
            io.BytesIO(t.file_blob),
            mimetype=mime,
            as_attachment=True,
            download_name=fname,
        )
    if t.file_path and os.path.isfile(t.file_path):
        return send_file(
            t.file_path,
            mimetype=mime,
            as_attachment=True,
            download_name=fname,
        )
    return jsonify({"code": 1, "msg": "原始文件已不存在（DB 与磁盘均无）"}), 404


@bp.route("/compose-draft", methods=["POST"])
def save_compose_draft():
    """保存模板 X 占位替换后的合成草稿（待纠错润色；不计入 duty_report）"""
    data = request.get_json(silent=True) or {}
    try:
        content = validate_compose_draft_content(data.get("content"))
        bindings = data.get("bindings")
        if isinstance(bindings, list):
            for i, b in enumerate(bindings):
                if isinstance(b, dict) and "manual" in b:
                    validate_slot_manual(b.get("manual"))
    except ValidationError as e:
        return jsonify({"code": 1, "msg": str(e)}), 400

    try:
        tpl = None
        tid_int = None
        tid = data.get("template_id")
        try:
            if tid is not None and str(tid).strip() != "":
                tid_int = int(tid)
        except (TypeError, ValueError):
            tid_int = None
        if tid_int is not None:
            tpl = ReportTemplate.query.get(tid_int)

        title_raw = (data.get("title") or "").strip()
        if title_raw:
            title = validate_compose_draft_title(title_raw)
        else:
            tn = (tpl.name if tpl else "") or "未命名模板"
            title = validate_compose_draft_title(f"{tn} · 合成草稿")

        bindings = data.get("bindings")
        bindings_json = None
        if bindings is not None:
            try:
                bindings_json = json.dumps(bindings, ensure_ascii=False)
            except (TypeError, ValueError):
                bindings_json = None

        file_blob = None
        file_mime = None
        file_name_stored = None
        if tpl:
            fb, fm, fn = _filled_office_bytes_for_draft(tpl, data.get("bindings") or [], content)
            if fb:
                file_blob = fb
                file_mime = (fm or "")[:128] if fm else None
                file_name_stored = (fn or "")[:255] if fn else None

        draft = ReportComposeDraft(
            template_id=tid_int,
            template_name=(tpl.name[:128] if tpl and tpl.name else None),
            title=title[:255],
            content=content,
            status="pending_polish",
            bindings_json=bindings_json,
            file_blob=file_blob,
            file_mime=file_mime,
            file_name=file_name_stored,
        )
        db.session.add(draft)
        db.session.commit()
        log_op("报告生成", "合成草稿入库", f"id={draft.id} title={draft.title}")
        return jsonify({"code": 0, "msg": "已保存合成草稿", "data": draft.to_list_item()})
    except Exception as e:
        db.session.rollback()
        log_op("报告生成", "合成草稿入库", str(e), success=False)
        hint = ""
        err_s = str(e).lower()
        if "report_compose_draft" in err_s or "does not exist" in err_s or "relation" in err_s:
            hint = "（数据库缺少表或列：请重启后端并执行 sql/migrate_report_compose_draft.sql 与 migrate_report_compose_draft_add_file.sql）"
        return jsonify({"code": 1, "msg": f"保存合成草稿失败: {e}{hint}"}), 500


def _parse_iso_date(s):
    if not s or not str(s).strip():
        return None
    try:
        return datetime.strptime(str(s).strip()[:10], "%Y-%m-%d").date()
    except ValueError:
        return None


@bp.route("/compose-drafts", methods=["GET"])
def list_compose_drafts():
    """合成草稿列表（不含全文 content，仅列表展示）。

    查询参数：
      q — 仅标题模糊匹配（ILIKE）
      date_from, date_to — 按保存日（created_at 日期）闭区间，YYYY-MM-DD
      office — word | ppt | none | all（默认 all；none=无 Office 附件）
      limit — 条数上限
    """
    try:
        try:
            limit = min(100, max(1, int(request.args.get("limit", 40))))
        except (TypeError, ValueError):
            limit = 40

        q = ReportComposeDraft.query

        try:
            search = validate_search_keyword(request.args.get("q"))
        except ValidationError as e:
            return jsonify({"code": 1, "msg": str(e)}), 400
        if search:
            like = "%" + search.replace("%", "").replace("_", "") + "%"
            q = q.filter(ReportComposeDraft.title.ilike(like))

        df = _parse_iso_date(request.args.get("date_from"))
        dt = _parse_iso_date(request.args.get("date_to"))
        if df:
            q = q.filter(ReportComposeDraft.created_at >= datetime.combine(df, time.min))
        if dt:
            q = q.filter(ReportComposeDraft.created_at <= datetime.combine(dt, time(23, 59, 59)))

        office = (request.args.get("office") or "all").strip().lower()
        if office == "word":
            q = q.filter(
                ReportComposeDraft.file_blob.isnot(None),
                or_(
                    ReportComposeDraft.file_mime.ilike("%wordprocessingml%"),
                    ReportComposeDraft.file_name.ilike("%.docx"),
                ),
            )
        elif office == "ppt":
            q = q.filter(
                ReportComposeDraft.file_blob.isnot(None),
                or_(
                    ReportComposeDraft.file_mime.ilike("%presentationml%"),
                    ReportComposeDraft.file_name.ilike("%.pptx"),
                ),
            )
        elif office == "none":
            q = q.filter(ReportComposeDraft.file_blob.is_(None))

        total = q.count()
        rows = q.order_by(ReportComposeDraft.id.desc()).limit(limit).all()
        return jsonify(
            {
                "code": 0,
                "data": {
                    "items": [r.to_list_item() for r in rows],
                    "total": total,
                    "returned": len(rows),
                },
            }
        )
    except Exception as e:
        log_op("报告生成", "合成草稿列表", str(e), success=False)
        return jsonify({"code": 1, "msg": f"读取草稿列表失败: {e}"}), 500


@bp.route("/compose-draft/<int:did>/file", methods=["GET"])
def download_compose_draft_file(did: int):
    """下载草稿中保存的替换后 Office 文件（与保存时一致）。"""
    d = ReportComposeDraft.query.get(did)
    if not d:
        return jsonify({"code": 1, "msg": "草稿不存在"}), 404
    if not d.file_blob:
        return jsonify({"code": 1, "msg": "该草稿未生成可下载文件"}), 404
    buf = io.BytesIO(d.file_blob)
    buf.seek(0)
    mime = (d.file_mime or "application/octet-stream").strip() or "application/octet-stream"
    download_name = (d.file_name or f"compose_draft_{did}.bin").strip() or f"compose_draft_{did}.bin"
    log_op("报告生成", "合成草稿下载文件", f"id={did}")
    return send_file(
        buf,
        mimetype=mime[:128],
        as_attachment=True,
        download_name=download_name[:255],
    )


@bp.route("/compose-draft/<int:did>", methods=["DELETE"])
def delete_compose_draft(did: int):
    """删除合成草稿记录（正文与 file_blob 一并删除）"""
    d = ReportComposeDraft.query.get(did)
    if not d:
        return jsonify({"code": 1, "msg": "草稿不存在"}), 404
    db.session.delete(d)
    db.session.commit()
    log_op("报告生成", "合成草稿删除", f"id={did}")
    return jsonify({"code": 0, "msg": "已删除"})


@bp.route("/keywords", methods=["POST"])
def kw_extract():
    """关键词提取（独立接口，便于单元测试）"""
    data = request.get_json(silent=True) or {}
    text = (data.get("text") or "").strip()
    if not text:
        return jsonify({"code": 1, "msg": "请输入文本"}), 400
    if len(text) > MAX_TEXT_BYTES:
        text = text[:MAX_TEXT_BYTES]
    return jsonify({"code": 0, "data": extract_keywords(text, top_k=15)})


@bp.route("/summary", methods=["POST"])
def text_summary():
    """文本提炼总结"""
    data = request.get_json(silent=True) or {}
    text = (data.get("text") or "").strip()
    n = max(1, min(20, int(data.get("max_sentences") or 5)))
    if not text:
        return jsonify({"code": 1, "msg": "请输入文本"}), 400
    if len(text) > MAX_TEXT_BYTES:
        text = text[:MAX_TEXT_BYTES]
    return jsonify({"code": 0, "data": {"summary": summarize(text, n)}})


# ----------- 报告生成 -----------
gen_bp = Blueprint("report_generate_run", __name__, url_prefix="/api/report")

VALID_REPORT_TYPES = {"word", "ppt"}


@gen_bp.route("/generate", methods=["POST"])
def generate():
    """根据模板 + 多维数据 自动生成值勤报告。

    参数校验：
      - template_id 必须存在（若提供）；不存在直接 404，不再静默回退默认模板
      - report_type 为 word / ppt；省略时按模板扩展名或 MIME 推断，无模板则默认 word
      - days ∈ [1, 365]
    """
    data = request.get_json(silent=True) or {}
    try:
        template_id = data.get("template_id")
        tpl = None
        if template_id is not None and str(template_id) != "":
            tpl = ReportTemplate.query.get(int(template_id))
            if not tpl:
                return jsonify({"code": 1, "msg": "指定的模板不存在"}), 404

        report_type = (data.get("report_type") or "").strip()
        if not report_type:
            if tpl:
                fn = (tpl.original_filename or "").lower()
                mt = (tpl.mime_type or "").lower()
                report_type = (
                    "ppt"
                    if ("presentationml" in mt or fn.endswith(".pptx"))
                    else "word"
                )
            else:
                report_type = "word"
        elif report_type not in VALID_REPORT_TYPES:
            return jsonify({"code": 1, "msg": f"report_type 必须是 {' / '.join(VALID_REPORT_TYPES)}"}), 400

        try:
            days = int(data.get("days") or 1)
        except (TypeError, ValueError):
            return jsonify({"code": 1, "msg": "days 必须是整数"}), 400
        if not 1 <= days <= 365:
            return jsonify({"code": 1, "msg": "days 取值范围 1 ~ 365"}), 400

        rpt = report_service.generate_report(
            template=tpl,
            report_type=report_type,
            title=(data.get("title") or "").strip() or None,
            location=(data.get("location") or "综合信息服务中心").strip() or "综合信息服务中心",
            days=days,
        )
        log_op("报告生成", "值勤报告生成", f"id={rpt.id} {rpt.title}")
        return jsonify({"code": 0, "msg": "生成成功", "data": rpt.to_dict()})
    except ValueError as e:
        return jsonify({"code": 1, "msg": str(e)}), 400
    except Exception as e:
        log_op("报告生成", "值勤报告生成", str(e), success=False)
        return jsonify({"code": 1, "msg": f"生成失败: {e}"}), 500
