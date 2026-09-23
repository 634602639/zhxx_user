"""在 OOXML（docx/pptx）文本节点上做精确子串替换，尽量不打乱版式。"""
from __future__ import annotations

import io
import re
import zipfile
from typing import List
from xml.etree import ElementTree as ET

from services.ooxml_preview_service import _NS_A, _NS_W, _local, _ns_el

_T_TAGS = {_ns_el(_NS_W, "t"), _ns_el(_NS_A, "t")}
_P_TAGS = {_ns_el(_NS_W, "p"), _ns_el(_NS_A, "p")}
_DIGIT_RE = re.compile(r"\d+(?:\.\d+)?")


def _digits(s: str) -> list[str]:
    return _DIGIT_RE.findall(s or "")


def sanitize_replacements(pairs: list) -> List[tuple[str, str]]:
    """过滤空替换、数字被改写的替换，按 from 长度降序避免短串误伤。"""
    out = []
    seen = set()
    for item in pairs or []:
        if isinstance(item, dict):
            frm = str(item.get("from") or item.get("old") or "")
            to = str(item.get("to") or item.get("new") or "")
        elif isinstance(item, (list, tuple)) and len(item) >= 2:
            frm, to = str(item[0]), str(item[1])
        else:
            continue
        frm, to = frm.strip(), to.strip()
        if not frm or frm == to:
            continue
        d_from, d_to = _digits(frm), _digits(to)
        if d_from and d_from != d_to:
            continue
        key = (frm, to)
        if key in seen:
            continue
        seen.add(key)
        out.append((frm, to))
    out.sort(key=lambda x: -len(x[0]))
    return out


def apply_replacements_to_text(text: str, pairs: List[tuple[str, str]]) -> str:
    s = text or ""
    for frm, to in pairs:
        if frm and frm in s:
            s = s.replace(frm, to)
    return s


def _replace_in_t_nodes(root: ET.Element, pairs: List[tuple[str, str]]) -> int:
    n = 0
    for el in root.iter():
        if el.tag not in _T_TAGS:
            continue
        orig = el.text or ""
        nxt = apply_replacements_to_text(orig, pairs)
        if nxt != orig:
            el.text = nxt
            n += 1
    return n


def _rewrite_paragraph_if_needed(p_el: ET.Element, pairs: List[tuple[str, str]]) -> int:
    """占位跨 run 时：拼接段落文本，整段写回第一个 t 节点。"""
    t_nodes = [t for t in p_el.iter() if t.tag in _T_TAGS]
    if len(t_nodes) < 2:
        return 0
    joined = "".join((t.text or "") for t in t_nodes)
    nxt = apply_replacements_to_text(joined, pairs)
    if nxt == joined:
        return 0
    t_nodes[0].text = nxt
    for t in t_nodes[1:]:
        t.text = ""
    return 1


def _replace_in_xml_bytes(data: bytes, pairs: List[tuple[str, str]]) -> bytes:
    try:
        root = ET.fromstring(data)
    except ET.ParseError:
        return data
    _replace_in_t_nodes(root, pairs)
    for el in root.iter():
        if el.tag in _P_TAGS:
            _rewrite_paragraph_if_needed(el, pairs)
    return ET.tostring(root, encoding="utf-8", xml_declaration=True)


def _is_target_xml(name: str) -> bool:
    n = name.replace("\\", "/")
    if not n.endswith(".xml"):
        return False
    return (
        n == "word/document.xml"
        or n.startswith("ppt/slides/slide")
        or n.startswith("ppt/notesSlides/")
    )


def _rewrite_office_xml_parts(blob: bytes, transform) -> bytes:
    if not blob:
        return blob
    buf = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(blob), "r") as zin, zipfile.ZipFile(buf, "w") as zout:
        for info in zin.infolist():
            data = zin.read(info.filename)
            if _is_target_xml(info.filename):
                data = transform(data)
            new_info = zipfile.ZipInfo(filename=info.filename, date_time=info.date_time)
            new_info.compress_type = info.compress_type
            new_info.external_attr = info.external_attr
            new_info.flag_bits = info.flag_bits
            zout.writestr(new_info, data)
    return buf.getvalue()


def apply_replacements_to_office(blob: bytes, pairs: List[tuple[str, str]]) -> bytes:
    if not blob or not pairs:
        return blob
    return _rewrite_office_xml_parts(blob, lambda data: _replace_in_xml_bytes(data, pairs))


def _para_plain(p_el: ET.Element) -> str:
    return "".join((t.text or "") for t in p_el.iter() if t.tag in _T_TAGS)


def _set_para_plain(p_el: ET.Element, text: str) -> bool:
    t_nodes = [t for t in p_el.iter() if t.tag in _T_TAGS]
    if not t_nodes:
        return False
    t_nodes[0].text = text
    if text[:1].isspace() or text[-1:].isspace():
        t_nodes[0].set("{http://www.w3.org/XML/1998/namespace}space", "preserve")
    for t in t_nodes[1:]:
        t.text = ""
    return True


def _iter_narrative_paragraphs(root: ET.Element) -> list:
    """正文块级段落。Word 跳过表格单元格，避免短文本干扰「进展/计划/建议」识别。"""
    if _local(root.tag) == "document":
        body = root.find(_ns_el(_NS_W, "body"))
        if body is None:
            return []
        out = []

        def walk(container):
            for child in list(container):
                ln = _local(child.tag)
                if ln == "p":
                    out.append(child)
                elif ln == "sdt":
                    sc = child.find(_ns_el(_NS_W, "sdtContent"))
                    if sc is not None:
                        walk(sc)

        walk(body)
        return out
    return [el for el in root.iter() if el.tag in _P_TAGS]


def _heading_with_trailing_empty(text: str, heading_key_fn, empty: set) -> tuple:
    """「二、本月进展无」写在同一段时，拆出章节 key。"""
    t = (text or "").strip()
    if not t or not heading_key_fn:
        return None, None
    for token in sorted(empty, key=len, reverse=True):
        if not token:
            continue
        for sep in ("", "：", ":", "，", ",", " "):
            suffix = sep + token
            if len(t) <= len(suffix) or not t.endswith(suffix):
                continue
            head = t[: -len(suffix)].rstrip("：:，,;； ")
            if not head:
                continue
            key = heading_key_fn(head)
            if key:
                return key, token
    return None, None


def replace_empty_narrative_paragraphs(blob: bytes, bodies_by_key: dict, heading_key_fn, empty_bodies) -> bytes:
    """标题段之后若正文仅为「无」等占位，则把该段换成 bodies_by_key[key]。"""
    if not blob or not bodies_by_key:
        return blob
    empty = {str(x).strip() for x in (empty_bodies or ())}

    def transform(data: bytes) -> bytes:
        try:
            root = ET.fromstring(data)
        except ET.ParseError:
            return data
        paras = _iter_narrative_paragraphs(root)
        waiting_key = None
        for p_el in paras:
            raw = _para_plain(p_el)
            t = (raw or "").strip()
            if not t:
                continue
            same_key, token = _heading_with_trailing_empty(t, heading_key_fn, empty)
            if same_key and same_key in bodies_by_key:
                body = str(bodies_by_key.get(same_key) or "").strip()
                if body:
                    head = t[: -len(token)].rstrip("：:，,;； ") if token else t
                    _set_para_plain(p_el, head + body)
                waiting_key = None
                continue
            key = heading_key_fn(t) if heading_key_fn else None
            if key:
                waiting_key = key
                continue
            if waiting_key and t in empty and waiting_key in bodies_by_key:
                body = str(bodies_by_key.get(waiting_key) or "").strip()
                if body:
                    _set_para_plain(p_el, body)
                waiting_key = None
                continue
            waiting_key = None
        return ET.tostring(root, encoding="utf-8", xml_declaration=True)

    return _rewrite_office_xml_parts(blob, transform)
