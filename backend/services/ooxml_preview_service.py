"""
基于 OOXML：将 .docx / .pptx 视为 zip，解析内部 XML。

预览默认输出「全文纯文本」（遍历 w:t / a:t 等），表格、幻灯片表格一并抽出；
另保留 HTML 拼装函数仅作兜底。
"""
from __future__ import annotations

import html
import io
import re
import zipfile
from typing import Callable, List, Optional
from xml.etree import ElementTree as ET

_NS_W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
_NS_A = "http://schemas.openxmlformats.org/drawingml/2006/main"


def _local(tag: str) -> str:
    if not tag:
        return ""
    return tag.split("}")[-1] if "}" in tag else tag


def _ns_el(uri: str, local: str) -> str:
    return f"{{{uri}}}{local}"


def _walk_para_children(el: ET.Element, emit_run: Callable[[ET.Element], str]) -> str:
    parts: List[str] = []
    for child in el:
        ln = _local(child.tag)
        if ln == "r":
            parts.append(emit_run(child))
        elif ln == "hyperlink":
            for sub in child:
                if _local(sub.tag) == "r":
                    parts.append(emit_run(sub))
        elif ln == "sdt":
            parts.append(_docx_sdt_block(child, emit_run))
        elif ln == "fldSimple":
            inner = "".join(emit_run(sub) for sub in child if _local(sub.tag) == "r")
            parts.append(inner or "")
        elif ln in ("bookmarkStart", "bookmarkEnd", "proofErr"):
            continue
        else:
            parts.append(_walk_para_children(child, emit_run))
    return "".join(parts)


def _run_text_and_style(run_el: ET.Element) -> str:
    rpr = run_el.find(_ns_el(_NS_W, "rPr"))
    bold = italic = underline = strike = False
    if rpr is not None:
        bold = rpr.find(_ns_el(_NS_W, "b")) is not None or rpr.find(_ns_el(_NS_W, "bCs")) is not None
        italic = rpr.find(_ns_el(_NS_W, "i")) is not None or rpr.find(_ns_el(_NS_W, "iCs")) is not None
        underline = rpr.find(_ns_el(_NS_W, "u")) is not None
        strike = rpr.find(_ns_el(_NS_W, "strike")) is not None

    chunks: List[str] = []
    for sub in run_el:
        sn = _local(sub.tag)
        if sn == "t":
            tx = sub.text or ""
            space = sub.attrib.get("{http://www.w3.org/XML/1998/namespace}space")
            if space != "preserve":
                tx = tx.strip()
            chunks.append(html.escape(tx))
        elif sn == "tab":
            chunks.append('<span class="ooxml-tab">\t</span>')
        elif sn == "br":
            chunks.append("<br/>")
        elif sn == "drawing":
            chunks.append('<span class="ooxml-placeholder">[图片/图表]</span>')
        elif sn == "pict":
            chunks.append('<span class="ooxml-placeholder">[对象]</span>')

    inner = "".join(chunks)
    if not inner.strip() and not chunks:
        return ""
    if strike:
        inner = f"<s>{inner}</s>"
    if underline:
        inner = f"<u>{inner}</u>"
    if italic:
        inner = f"<em>{inner}</em>"
    if bold:
        inner = f"<strong>{inner}</strong>"
    return inner


def _docx_p_wrap_tag(el_p: ET.Element) -> str:
    ppr = el_p.find(_ns_el(_NS_W, "pPr"))
    val = ""
    if ppr is not None:
        ps = ppr.find(_ns_el(_NS_W, "pStyle"))
        if ps is not None:
            val = ""
            for k, v in ps.attrib.items():
                if k.endswith("}val") or k == "val":
                    val = v
                    break
    if not val:
        return "p"
    v = val.lower().replace(" ", "")
    if v in ("heading1", "标题1", "title"):
        return "h1"
    if v in ("heading2", "标题2", "subtitle"):
        return "h2"
    if v in ("heading3", "标题3"):
        return "h3"
    if v.startswith("heading") or v.startswith("标题"):
        return "h4"
    return "p"


def _docx_paragraph(el_p: ET.Element) -> str:
    wrap = _docx_p_wrap_tag(el_p)
    inner = _walk_para_children(el_p, _run_text_and_style)
    if not inner.strip():
        inner = "&nbsp;"
    cls = ' class="ooxml-p-empty"' if inner.strip() == "&nbsp;" else ""
    return f"<{wrap}{cls}>{inner}</{wrap}>"


def _docx_tbl(el_tbl: ET.Element) -> str:
    rows: List[str] = []
    for tr in el_tbl:
        if _local(tr.tag) != "tr":
            continue
        cells: List[str] = []
        for tc in tr:
            if _local(tc.tag) != "tc":
                continue
            cell_parts: List[str] = []
            for cel in tc:
                ln = _local(cel.tag)
                if ln == "p":
                    cell_parts.append(_docx_paragraph(cel))
                elif ln == "tbl":
                    cell_parts.append(_docx_tbl(cel))
                elif ln == "sdt":
                    cell_parts.append(_docx_sdt_block(cel, _run_text_and_style))
            cells.append("<td>" + "".join(cell_parts) + "</td>")
        rows.append("<tr>" + "".join(cells) + "</tr>")
    return '<table class="ooxml-table">' + "".join(rows) + "</table>"


def _docx_sdt_block(el: ET.Element, emit_run: Callable[[ET.Element], str]) -> str:
    content = el.find(_ns_el(_NS_W, "sdtContent"))
    if content is None:
        return ""
    parts: List[str] = []
    for child in content:
        ln = _local(child.tag)
        if ln == "p":
            parts.append(_docx_paragraph(child))
        elif ln == "tbl":
            parts.append(_docx_tbl(child))
        elif ln == "sdt":
            parts.append(_docx_sdt_block(child, emit_run))
    return "".join(parts)


def _docx_body_fragment(body_el: ET.Element) -> str:
    parts: List[str] = []
    for child in body_el:
        ln = _local(child.tag)
        if ln == "p":
            parts.append(_docx_paragraph(child))
        elif ln == "tbl":
            parts.append(_docx_tbl(child))
        elif ln == "sdt":
            parts.append(_docx_sdt_block(child, _run_text_and_style))
        elif ln == "sectPr":
            continue
    return "".join(parts)


def _docx_part_to_html(z: zipfile.ZipFile, path: str, title: Optional[str] = None) -> str:
    if path not in z.namelist():
        return ""
    try:
        root = ET.fromstring(z.read(path))
    except ET.ParseError:
        return ""
    doc = root if _local(root.tag) == "document" else root.find(".//" + _ns_el(_NS_W, "document"))
    if doc is None:
        return ""
    body = doc.find(_ns_el(_NS_W, "body"))
    if body is None:
        return ""
    inner = _docx_body_fragment(body)
    if not inner.strip():
        return ""
    head = ""
    if title:
        head = f'<div class="ooxml-part-title">{html.escape(title)}</div>'
    return f'<section class="ooxml-doc-part">{head}{inner}</section>'


def docx_zip_to_html(blob: bytes) -> str:
    """解析 word/document.xml 及页眉、页脚、脚注、尾注、批注等部件。"""
    if not blob or len(blob) < 4 or blob[:2] != b"PK":
        return ""
    try:
        z = zipfile.ZipFile(io.BytesIO(blob))
    except zipfile.BadZipFile:
        return ""

    chunks: List[str] = []
    main = _docx_part_to_html(z, "word/document.xml", None)
    if main:
        chunks.append(f'<div class="ooxml-document-main">{main}</div>')

    extra_paths = sorted(
        n
        for n in z.namelist()
        if re.match(r"word/(header|footer|endnotes|footnotes|comments)\d*\.xml$", n, re.I)
    )
    for path in extra_paths:
        label = path.replace("word/", "").replace(".xml", "")
        frag = _docx_part_to_html(z, path, title=f"「{label}」")
        if frag:
            chunks.append(frag)

    return "".join(chunks)


def _ppt_a_run_to_html(run_el: ET.Element) -> str:
    rpr = run_el.find(_ns_el(_NS_A, "rPr"))
    bold = italic = underline = False
    if rpr is not None:
        bold = rpr.find(_ns_el(_NS_A, "b")) is not None
        italic = rpr.find(_ns_el(_NS_A, "i")) is not None
        underline = rpr.find(_ns_el(_NS_A, "u")) is not None

    texts: List[str] = []
    for sub in run_el:
        sl = _local(sub.tag)
        if sl == "t":
            texts.append(html.escape(sub.text or ""))
        elif sl == "br":
            texts.append("<br/>")

    inner = "".join(texts)
    if not inner:
        return ""
    if underline:
        inner = f"<u>{inner}</u>"
    if italic:
        inner = f"<em>{inner}</em>"
    if bold:
        inner = f"<strong>{inner}</strong>"
    return inner


def _ppt_a_paragraph(el_p: ET.Element) -> str:
    parts: List[str] = []
    for child in el_p:
        ln = _local(child.tag)
        if ln == "r":
            parts.append(_ppt_a_run_to_html(child))
        elif ln == "fld":
            for sub in child.iter():
                if _local(sub.tag) == "t" and sub.text:
                    parts.append(html.escape(sub.text))
    inner = "".join(parts).strip()
    if not inner:
        return ""
    return f"<p>{inner}</p>"


def _ppt_a_table(el_tbl: ET.Element) -> str:
    rows_html: List[str] = []
    for tr in el_tbl:
        if _local(tr.tag) != "tr":
            continue
        tds: List[str] = []
        for tc in tr:
            if _local(tc.tag) != "tc":
                continue
            cell_html: List[str] = []
            for p in tc.findall(_ns_el(_NS_A, "p")):
                cell_html.append(_ppt_a_paragraph(p))
            for nested_tbl in tc:
                if _local(nested_tbl.tag) == "tbl":
                    cell_html.append(_ppt_a_table(nested_tbl))
            tds.append("<td>" + "".join(cell_html) + "</td>")
        rows_html.append("<tr>" + "".join(tds) + "</tr>")
    return '<table class="ooxml-table ppt-ooxml-table">' + "".join(rows_html) + "</table>"


def _ppt_slide_xml_to_html(xml_bytes: bytes) -> str:
    try:
        root = ET.fromstring(xml_bytes)
    except ET.ParseError:
        return ""

    tbl_elems = list(root.iter(_ns_el(_NS_A, "tbl")))
    in_table_p_ids = set()
    for tbl in tbl_elems:
        for p in tbl.iter(_ns_el(_NS_A, "p")):
            in_table_p_ids.add(id(p))

    parts: List[str] = []
    for tbl in tbl_elems:
        parts.append(_ppt_a_table(tbl))

    for el_p in root.iter(_ns_el(_NS_A, "p")):
        if id(el_p) in in_table_p_ids:
            continue
        h = _ppt_a_paragraph(el_p)
        if h:
            parts.append(h)

    if not parts:
        texts = []
        for t_el in root.iter(_ns_el(_NS_A, "t")):
            if t_el.text and t_el.text.strip():
                texts.append(html.escape(t_el.text.strip()))
        if texts:
            return "<p>" + " · ".join(texts) + "</p>"
        return ""

    return "".join(parts)


def _sorted_slide_xml_paths(z: zipfile.ZipFile) -> List[str]:
    paths = [n for n in z.namelist() if re.match(r"ppt/slides/slide\d+\.xml$", n, re.I)]

    def slide_key(p: str) -> int:
        m = re.search(r"slide(\d+)", p, re.I)
        return int(m.group(1)) if m else 0

    return sorted(paths, key=slide_key)


def _notes_xml_paths(z: zipfile.ZipFile) -> List[str]:
    paths = [n for n in z.namelist() if re.match(r"ppt/notesSlides/notesSlide\d+\.xml$", n, re.I)]

    def nk(p: str) -> int:
        m = re.search(r"(\d+)", p)
        return int(m.group(1)) if m else 0

    return sorted(paths, key=nk)


def pptx_zip_to_html(blob: bytes) -> str:
    """解析 ppt/slides/slide*.xml 与演讲者备注 notesSlides。"""
    if not blob or len(blob) < 4 or blob[:2] != b"PK":
        return ""
    try:
        z = zipfile.ZipFile(io.BytesIO(blob))
    except zipfile.BadZipFile:
        return ""

    sections: List[str] = []

    for path in _sorted_slide_xml_paths(z):
        raw = z.read(path)
        inner = _ppt_slide_xml_to_html(raw)
        m = re.search(r"slide(\d+)", path, re.I)
        idx = int(m.group(1)) if m else 0
        body = inner or '<p class="muted ppt-slide-empty">（本页未解析到文本，可能仅有图片/图表）</p>'
        sections.append(
            f'<article class="ppt-slide ooxml-slide" data-slide="{idx}">'
            f'<header class="ppt-slide-head">幻灯片 {idx}</header>'
            f'<div class="ppt-slide-body">{body}</div></article>'
        )

    for npath in _notes_xml_paths(z):
        try:
            raw = z.read(npath)
        except KeyError:
            continue
        inner = _ppt_slide_xml_to_html(raw)
        if inner.strip():
            m = re.search(r"(\d+)", npath)
            nid = m.group(1) if m else ""
            sections.append(
                f'<aside class="ppt-notes ooxml-notes" data-notes="{nid}">'
                f'<div class="ppt-notes-title">演讲者备注 {nid}</div>'
                f'<div class="ppt-notes-body">{inner}</div></aside>'
            )

    return "".join(sections)


# ------------- 纯文本全文提取（ZIP 内 XML 遍历，用于预览）-------------

_MAX_PLAIN_PREVIEW_CHARS = 600_000


def _truncate_preview_text(s: str, limit: int = _MAX_PLAIN_PREVIEW_CHARS) -> str:
    if len(s) <= limit:
        return s
    return s[:limit] + "\n\n…（以下为预览长度上限截断）"


def _docx_p_plain(el_p: ET.Element) -> str:
    parts: List[str] = []
    for t in el_p.iter(_ns_el(_NS_W, "t")):
        if t.text:
            parts.append(t.text)
    return "".join(parts).replace("\x00", "").replace("\r", "")


def _docx_tc_plain(tc_el: ET.Element) -> str:
    bits: List[str] = []
    for child in tc_el:
        ln = _local(child.tag)
        if ln == "p":
            s = _docx_p_plain(child)
            if s.strip():
                bits.append(s.strip())
        elif ln == "tbl":
            bits.append(_docx_tbl_plain(child))
    inner = " ".join(x for x in bits if x)
    return inner.replace("\t", " ").replace("\n", " ").strip()


def _docx_tbl_plain(tbl_el: ET.Element) -> str:
    rows: List[str] = []
    for tr in tbl_el:
        if _local(tr.tag) != "tr":
            continue
        cells: List[str] = []
        for tc in tr:
            if _local(tc.tag) != "tc":
                continue
            cells.append(_docx_tc_plain(tc))
        rows.append("\t".join(cells))
    return "\n".join(rows)


def _docx_container_plain(container: ET.Element) -> str:
    blocks: List[str] = []
    for child in container:
        ln = _local(child.tag)
        if ln == "p":
            s = _docx_p_plain(child)
            if s.strip():
                blocks.append(s.strip())
        elif ln == "tbl":
            blocks.append(_docx_tbl_plain(child))
        elif ln == "sdt":
            sc = child.find(_ns_el(_NS_W, "sdtContent"))
            if sc is not None:
                inner = _docx_container_plain(sc)
                if inner.strip():
                    blocks.append(inner)
        elif ln == "sectPr":
            continue
    return "\n".join(blocks)


def _docx_extract_word_xml(raw: bytes) -> str:
    try:
        root = ET.fromstring(raw)
    except ET.ParseError:
        return ""
    tag = _local(root.tag)
    if tag == "document":
        body = root.find(_ns_el(_NS_W, "body"))
        return _docx_container_plain(body) if body is not None else ""
    if tag in ("hdr", "ftr"):
        return _docx_container_plain(root)
    if tag == "footnotes":
        parts = []
        for fn in root:
            if _local(fn.tag) == "footnote":
                parts.append(_docx_container_plain(fn))
        return "\n".join(p for p in parts if p.strip())
    if tag == "endnotes":
        parts = []
        for fn in root:
            if _local(fn.tag) == "endnote":
                parts.append(_docx_container_plain(fn))
        return "\n".join(p for p in parts if p.strip())
    if tag == "comments":
        parts = []
        for cm in root:
            if _local(cm.tag) == "comment":
                parts.append(_docx_container_plain(cm))
        return "\n".join(p for p in parts if p.strip())
    return ""


def docx_zip_plain_extract(blob: bytes) -> str:
    """解压 docx，遍历 word 部件 XML，抽取全部 w:t（含表格单元格、页眉页脚、脚注等）。"""
    if not blob or len(blob) < 4 or blob[:2] != b"PK":
        return ""
    try:
        z = zipfile.ZipFile(io.BytesIO(blob))
    except zipfile.BadZipFile:
        return ""

    sections: List[str] = []

    def add(title: str, text: str) -> None:
        text = (text or "").strip()
        if text:
            sections.append(f"{title}\n{text}")

    if "word/document.xml" in z.namelist():
        add("【正文】", _docx_extract_word_xml(z.read("word/document.xml")))

    for path in sorted(z.namelist()):
        if re.match(r"word/header\d+\.xml$", path, re.I):
            add(f"【{path.replace('word/', '')}】", _docx_extract_word_xml(z.read(path)))
    for path in sorted(z.namelist()):
        if re.match(r"word/footer\d+\.xml$", path, re.I):
            add(f"【{path.replace('word/', '')}】", _docx_extract_word_xml(z.read(path)))

    for extra in ("word/footnotes.xml", "word/endnotes.xml", "word/comments.xml"):
        if extra in z.namelist():
            add(f"【{extra.replace('word/', '')}】", _docx_extract_word_xml(z.read(extra)))

    return _truncate_preview_text("\n\n".join(sections))


def docx_zip_document_body_plain(blob: bytes) -> str:
    """仅 `word/document.xml` 正文纯文本，与 `filled-docx` 替换范围、占位统计一致（不含页眉/页脚/脚注等）。"""
    if not blob or len(blob) < 4 or blob[:2] != b"PK":
        return ""
    try:
        z = zipfile.ZipFile(io.BytesIO(blob))
    except zipfile.BadZipFile:
        return ""
    if "word/document.xml" not in z.namelist():
        return ""
    raw = _docx_extract_word_xml(z.read("word/document.xml")) or ""
    return _truncate_preview_text(raw.strip())


def _pptx_xml_plain_from_root(root: ET.Element) -> str:
    """与 `_pptx_xml_plain` 相同规则，但使用已有 Element 树根（避免与切片遍历不是同一棵树）。"""
    lines: List[str] = []
    for ap in root.iter(_ns_el(_NS_A, "p")):
        ts: List[str] = []
        for at in ap.iter(_ns_el(_NS_A, "t")):
            if at.text:
                ts.append(at.text)
        line = "".join(ts).strip().replace("\x00", "")
        if line:
            lines.append(line)
    if lines:
        return "\n".join(lines)
    fallback: List[str] = []
    for at in root.iter(_ns_el(_NS_A, "t")):
        if at.text and at.text.strip():
            fallback.append(at.text.strip())
    return "\n".join(fallback)


def _pptx_xml_plain(raw: bytes) -> str:
    """遍历 DrawingML 段落 a:p / 文本 a:t（含表格内单元格），按 XML 文档顺序输出。"""
    try:
        root = ET.fromstring(raw)
    except ET.ParseError:
        return ""
    return _pptx_xml_plain_from_root(root)


def pptx_zip_plain_extract(blob: bytes) -> str:
    """解压 pptx，按幻灯片 / 备注等部件遍历 XML，抽取全部可见文本。"""
    if not blob or len(blob) < 4 or blob[:2] != b"PK":
        return ""
    try:
        z = zipfile.ZipFile(io.BytesIO(blob))
    except zipfile.BadZipFile:
        return ""

    sections: List[str] = []

    for path in _sorted_slide_xml_paths(z):
        try:
            raw = z.read(path)
        except KeyError:
            continue
        body = _pptx_xml_plain(raw)
        m = re.search(r"slide(\d+)", path, re.I)
        idx = int(m.group(1)) if m else 0
        label = f"【幻灯片 {idx}】"
        if body.strip():
            sections.append(f"{label}\n{body.strip()}")
        else:
            sections.append(f"{label}\n（本页未解析到文本节点，可能仅有图片/图表）")

    for npath in _notes_xml_paths(z):
        try:
            raw = z.read(npath)
        except KeyError:
            continue
        body = _pptx_xml_plain(raw)
        if body.strip():
            m = re.search(r"(\d+)", npath)
            nid = m.group(1) if m else ""
            sections.append(f"【演讲者备注 {nid}】\n{body.strip()}")

    return _truncate_preview_text("\n\n".join(sections))


def ooxml_plain_preview_html(text: str) -> str:
    """将纯文本预览包进 pre，供前端直接 innerHTML（已 escape）。"""
    esc = html.escape(text or "")
    return f'<div class="preview-plain-wrap"><pre class="preview-plain-extract">{esc}</pre></div>'
