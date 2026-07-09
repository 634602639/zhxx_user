"""
在保留原始 .docx 版式的前提下替换正文（word/document.xml）中的连续 X 占位。

正文拼接规则与 `_docx_container_plain` / `_docx_extract_word_xml` 一致（含表格、单元格内嵌套表）。
"""
from __future__ import annotations

import bisect
import io
import re
import zipfile
from typing import List, Optional, Tuple

from xml.etree import ElementTree as ET

from services.ooxml_preview_service import (
    _NS_W,
    _docx_extract_word_xml,
    _docx_p_plain,
    _docx_tbl_plain,
    _docx_tc_plain,
    _local,
    _ns_el,
)


def _norm_docx_plain_segment(s: str) -> str:
    if not s:
        return s
    t = s.replace("\r\n", "\n").replace("\r", "\n")
    return t.replace("\u2028", "\n").replace("\u2029", "\n")


def _docx_normalize_wt_under(el: ET.Element) -> None:
    for wt in el.iter(_ns_el(_NS_W, "t")):
        if wt.text:
            wt.text = _norm_docx_plain_segment(wt.text)
        if wt.tail:
            wt.tail = _norm_docx_plain_segment(wt.tail)


def effective_slot_replacement(value, slot_raw: str) -> str:
    """未填写或仅空白时保留模板中原占位字符（如 XX），避免导出后占位消失。"""
    s = "" if value is None else str(value).strip()
    return s if s else (slot_raw or "")


def find_x_slots(text: str) -> List[dict]:
    slots = []
    for m in re.finditer(r"[xX]+", text or ""):
        slots.append(
            {
                "n": len(slots) + 1,
                "start": m.start(),
                "end": m.end(),
                "raw": m.group(),
            }
        )
    return slots


class _Slice:
    """virtual 非空时表示正文中的一个字符（\\n / \\t / 空格等），不对应 w:t。"""

    __slots__ = ("wt", "lo", "hi", "virtual")

    def __init__(
        self,
        wt: Optional[ET.Element],
        lo: int,
        hi: int,
        *,
        virtual: Optional[str] = None,
    ):
        self.wt = wt
        self.lo = lo
        self.hi = hi
        self.virtual = virtual

    @property
    def text(self) -> str:
        if self.virtual is not None:
            return self.virtual
        tx = self.wt.text if self.wt is not None else None
        return (tx or "")[self.lo : self.hi]


def _segments_for_paragraph(p_el: ET.Element) -> List["_Slice"]:
    s = _docx_p_plain(p_el)
    if not s.strip():
        return []
    ls = len(s) - len(s.lstrip())
    rs = len(s) - len(s.rstrip())
    lo, hi = ls, len(s) - rs
    wts = [t for t in p_el.iter(_ns_el(_NS_W, "t"))]
    cum = 0
    spans = []
    for wt in wts:
        tx = wt.text or ""
        spans.append((wt, cum, cum + len(tx)))
        cum += len(tx)
    if cum != len(s):
        raise ValueError("段落 w:t 拼接与抽取不一致")

    segs: List[_Slice] = []
    pos = lo
    while pos < hi:
        wt_a_b = None
        for wt, a, b in spans:
            if a <= pos < b:
                wt_a_b = (wt, a, b)
                break
        if wt_a_b is None:
            raise ValueError("无法映射占位字符到 w:t")
        wt, a, b = wt_a_b
        end_same = min(hi, b)
        segs.append(_Slice(wt, pos - a, end_same - a))
        pos = end_same
    return segs


def _plain_from_slices(slices: List["_Slice"]) -> str:
    return "".join(sl.text for sl in slices)


def _normalize_tbl_seps_for_tc(slices: List["_Slice"]) -> List["_Slice"]:
    """单元格内：与 _docx_tc_plain 一致，将 \\t \\n 视作空格。"""
    out: List[_Slice] = []
    for sl in slices:
        if sl.virtual in ("\t", "\n"):
            out.append(_Slice(None, 0, 0, virtual=" "))
        else:
            out.append(sl)
    return out


def _trim_slices(slices: List["_Slice"], plain: str) -> Tuple[str, List["_Slice"]]:
    """对 plain 做 strip，并裁剪切片列表（仅去掉首尾空白对应的切片段）。"""
    stripped = plain.strip()
    if not stripped:
        return "", []
    ls = len(plain) - len(plain.lstrip())
    rs = len(plain) - len(plain.rstrip())
    end_pos = len(plain) - rs

    c = [0]
    for sl in slices:
        c.append(c[-1] + len(sl.text))
    if c[-1] != len(plain):
        raise ValueError("切片与 plain 长度不一致")

    i0 = bisect.bisect_right(c, ls) - 1
    i1 = bisect.bisect_right(c, end_pos - 1) - 1
    if i0 < 0:
        i0 = 0
    if i1 < i0:
        i1 = i0

    out: List[_Slice] = []
    for k in range(i0, i1 + 1):
        sl = slices[k]
        a, b = c[k], c[k + 1]
        seg_lo = max(ls, a)
        seg_hi = min(end_pos, b)
        if seg_lo >= seg_hi:
            continue
        if sl.virtual is not None:
            # 整段虚拟字符被部分包含时，strip 边界不应切开单个虚拟 char（长度均为 1）
            out.append(sl)
        else:
            lo2 = sl.lo + (seg_lo - a)
            hi2 = sl.lo + (seg_hi - a)
            out.append(_Slice(sl.wt, lo2, hi2))

    new_plain = _plain_from_slices(out)
    if new_plain != stripped:
        raise ValueError("strip 后正文与切片不一致")
    return new_plain, out


def _walk_table(tbl_el: ET.Element) -> List["_Slice"]:
    """与 `_docx_tbl_plain` 一致：行间 \\n、单元格间 \\t；单元格内规则见 `_walk_tc`。"""
    slices: List[_Slice] = []
    first_tr = True
    for tr in tbl_el:
        if _local(tr.tag) != "tr":
            continue
        if not first_tr:
            slices.append(_Slice(None, 0, 0, virtual="\n"))
        first_tr = False
        first_tc = True
        for tc in tr:
            if _local(tc.tag) != "tc":
                continue
            if not first_tc:
                slices.append(_Slice(None, 0, 0, virtual="\t"))
            first_tc = False
            slices.extend(_walk_tc(tc))
    return slices


def _walk_tc(tc_el: ET.Element) -> List["_Slice"]:
    """与 `_docx_tc_plain` 一致：bit 间空格、嵌套表内 \\t\\n 最终变为空格，再 strip。"""
    bits_plain: List[str] = []
    bits_slices: List[List[_Slice]] = []
    for child in tc_el:
        ln = _local(child.tag)
        if ln == "p":
            s = _docx_p_plain(child)
            if s.strip():
                bits_plain.append(s.strip())
                bits_slices.append(_segments_for_paragraph(child))
        elif ln == "tbl":
            tp = _docx_tbl_plain(child)
            bits_plain.append(tp)
            bits_slices.append(_walk_table(child))

    pairs = [(s, sl) for s, sl in zip(bits_plain, bits_slices) if s]
    if not pairs:
        return []

    merged: List[_Slice] = []
    for idx, (_, slist) in enumerate(pairs):
        if idx > 0:
            merged.append(_Slice(None, 0, 0, virtual=" "))
        merged.extend(slist)

    inner = _plain_from_slices(merged)
    ref_inner = " ".join(x for x in bits_plain if x)
    if inner != ref_inner:
        raise ValueError("单元格 inner 拼接不一致")

    norm = _normalize_tbl_seps_for_tc(merged)
    inner_norm = _plain_from_slices(norm)
    ref_tc = _docx_tc_plain(tc_el)
    if inner_norm.strip() != ref_tc:
        raise ValueError("单元格规范化后与 _docx_tc_plain 不一致")

    plain_stripped, slices_stripped = _trim_slices(norm, inner_norm)
    if plain_stripped != ref_tc:
        raise ValueError("单元格 strip 后与 _docx_tc_plain 不一致")
    return slices_stripped


def _walk_blocks(container: ET.Element) -> List[List["_Slice"]]:
    """与 `_docx_container_plain(container)` 的「块」划分一致。"""
    blk: List[List[_Slice]] = []
    for child in container:
        ln = _local(child.tag)
        if ln == "p":
            segs = _segments_for_paragraph(child)
            if segs:
                blk.append(segs)
        elif ln == "tbl":
            ts = _walk_table(child)
            if ts:
                blk.append(ts)
        elif ln == "sdt":
            sc = child.find(_ns_el(_NS_W, "sdtContent"))
            if sc is not None:
                inner_lists = _walk_blocks(sc)
                merged: List[_Slice] = []
                for idx, il in enumerate(inner_lists):
                    if idx > 0:
                        merged.append(_Slice(None, 0, 0, virtual="\n"))
                    merged.extend(il)
                if merged:
                    blk.append(merged)
        elif ln == "sectPr":
            continue
    return blk


def build_plain_slices_from_body(body: ET.Element) -> Tuple[str, List["_Slice"]]:
    block_lists = _walk_blocks(body)
    slices_flat: List[_Slice] = []
    plain_parts: List[str] = []
    for i, segs in enumerate(block_lists):
        if i > 0:
            slices_flat.append(_Slice(None, 0, 0, virtual="\n"))
            plain_parts.append("\n")
        for sl in segs:
            slices_flat.append(sl)
            plain_parts.append(sl.text)
    plain = "".join(plain_parts)
    return plain, slices_flat


def _cum_lens_slices(slices: List["_Slice"]) -> List[int]:
    c = [0]
    for sl in slices:
        c.append(c[-1] + len(sl.text))
    return c


def _replace_span_slices(slices: List["_Slice"], st: int, en: int, val: str) -> None:
    """按全局下标 [st,en) 替换为 val；修改底层 w:t.text。"""
    if st >= en:
        return
    c = _cum_lens_slices(slices)
    i = bisect.bisect_right(c, st) - 1
    j = bisect.bisect_right(c, en - 1) - 1
    if i < 0:
        i = 0
    if j < i:
        j = i

    abs_lo = slices[i].lo + (st - c[i])
    abs_hi = slices[j].lo + (en - c[j])

    if slices[i].virtual is not None or slices[j].virtual is not None:
        raise ValueError(
            "占位落在段落间换行、表格线或单元格分隔符上，请将 X 写在段落或单元格文字内"
        )

    if slices[i].wt is slices[j].wt:
        wt = slices[i].wt
        t = wt.text or ""
        wt.text = t[:abs_lo] + val + t[abs_hi:]
        return

    fw = slices[i].wt
    ft = fw.text or ""
    fw.text = ft[:abs_lo] + val

    for k in range(i + 1, j):
        sl = slices[k]
        if sl.virtual is not None:
            raise ValueError("占位跨越表格结构分隔符")
        tw = sl.wt
        tt = tw.text or ""
        tw.text = tt[: sl.lo] + tt[sl.hi :]

    lw = slices[j].wt
    lt = lw.text or ""
    lw.text = lt[: slices[j].lo] + lt[abs_hi:]


def fill_docx_body_from_values(blob: bytes, values: List[str]) -> bytes:
    try:
        with zipfile.ZipFile(io.BytesIO(blob)) as z:
            if "word/document.xml" not in z.namelist():
                raise ValueError("缺少 word/document.xml")
            raw_doc = z.read("word/document.xml")
    except zipfile.BadZipFile as e:
        raise ValueError(f"无效的 docx 文件: {e}") from e

    root = ET.fromstring(raw_doc)
    if _local(root.tag) != "document":
        raise ValueError("不是有效的 Word 文档根节点")
    body = root.find(_ns_el(_NS_W, "body"))
    if body is None:
        raise ValueError("缺少正文 body")

    _docx_normalize_wt_under(body)

    raw_roundtrip = ET.tostring(root, encoding="utf-8", xml_declaration=True)
    ref_xml = (_docx_extract_word_xml(raw_roundtrip) or "").replace("\r", "")
    plain, _s0 = build_plain_slices_from_body(body)
    plain = plain.replace("\r", "")
    if plain != ref_xml:
        raise ValueError("正文片段拼接与 OOXML 抽取不一致")

    slots = find_x_slots(plain)
    values = list(values)
    if len(values) > len(slots):
        values = values[: len(slots)]
    elif len(values) < len(slots):
        values = values + [""] * (len(slots) - len(values))

    cur = plain
    for slot, val in sorted(zip(slots, values), key=lambda x: -x[0]["start"]):
        st, en, raw = slot["start"], slot["end"], slot["raw"]
        plain_now, slices = build_plain_slices_from_body(body)
        plain_now = plain_now.replace("\r", "")
        if plain_now != cur:
            raise ValueError("正文状态不一致")
        if plain_now[st:en] != raw:
            raise ValueError("占位区间与正文不一致")
        replacement = effective_slot_replacement(val, raw)
        _replace_span_slices(slices, st, en, replacement)
        cur = plain_now[:st] + replacement + plain_now[en:]

    out_xml = ET.tostring(root, encoding="utf-8", xml_declaration=True)

    buf_in = io.BytesIO(blob)
    zin = zipfile.ZipFile(buf_in, "r")
    zout = io.BytesIO()
    with zipfile.ZipFile(zout, "w", zipfile.ZIP_DEFLATED) as zf:
        for item in zin.infolist():
            data = zin.read(item.filename)
            if item.filename == "word/document.xml":
                data = out_xml
            zi = zipfile.ZipInfo(filename=item.filename)
            zi.compress_type = item.compress_type
            zi.external_attr = item.external_attr
            zf.writestr(zi, data)
    zin.close()
    return zout.getvalue()


def sniff_word_ext(blob: bytes, filename: str = "") -> str:
    fn = (filename or "").lower()
    if fn.endswith(".docx"):
        return ".docx"
    if blob and len(blob) >= 4 and blob[:2] == b"PK":
        try:
            with zipfile.ZipFile(io.BytesIO(blob)) as zf:
                if "[Content_Types].xml" in zf.namelist() and any(
                    n.startswith("word/") for n in zf.namelist()
                ):
                    return ".docx"
        except zipfile.BadZipFile:
            pass
    return ""
