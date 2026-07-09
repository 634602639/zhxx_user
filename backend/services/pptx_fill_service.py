"""
在保留原始 .pptx 版式的前提下替换幻灯片 / 备注 XML 中 a:t 文本里的连续 X 占位。

与 Word（docx）流程对齐（见 `docx_fill_service.fill_docx_body_from_values`）：
- 预览：`plain_text` 用全文抽取；占位映射用 `plain_text_body`（仅替换范围，docx 为 document body，
  pptx 为各 slide + notes 部件拼接，不含「幻灯片 N」标签行）。
- 导出：同一套「加载 zip → 规范化文本节点 → 拼正文与切片 → find_x_slots → 按切片写回 w:t/a:t → 重打包」，
  不改变版式，仅改文本节点内容。
- 正文串必须与 `"".join(slice.text)` 完全一致，禁止再对整串单独规范化，否则占位下标与 bisect 切片错位。
"""
from __future__ import annotations

import bisect
import io
import os
import xml.sax.saxutils as xu
import zipfile
from typing import Dict, List, Optional, Tuple

from xml.etree import ElementTree as ET

from services.docx_fill_service import effective_slot_replacement, find_x_slots
from services.ooxml_preview_service import (
    _NS_A,
    _notes_xml_paths,
    _ns_el,
    _pptx_xml_plain_from_root,
    _sorted_slide_xml_paths,
    _truncate_preview_text,
)


class _Slice:
    __slots__ = ("at_el", "lo", "hi", "virtual")

    def __init__(
        self,
        at_el: Optional[ET.Element],
        lo: int,
        hi: int,
        *,
        virtual: Optional[str] = None,
    ):
        self.at_el = at_el
        self.lo = lo
        self.hi = hi
        self.virtual = virtual

    @property
    def text(self) -> str:
        if self.virtual is not None:
            return self.virtual
        tx = self.at_el.text if self.at_el is not None else None
        return (tx or "")[self.lo : self.hi]


def sniff_pptx_ext(blob: bytes, filename: str = "") -> str:
    fn = (filename or "").lower()
    if fn.endswith(".pptx"):
        return ".pptx"
    if blob and len(blob) >= 4 and blob[:2] == b"PK":
        try:
            with zipfile.ZipFile(io.BytesIO(blob)) as zf:
                if any(
                    n.startswith("ppt/slides/slide") and n.endswith(".xml")
                    for n in zf.namelist()
                ):
                    return ".pptx"
        except zipfile.BadZipFile:
            pass
    return ""


def _norm_pptx_plain(s: str) -> str:
    """与占位比对一致：统一换行与常见分隔符。"""
    if not s:
        return ""
    t = s.replace("\r\n", "\n").replace("\r", "\n")
    t = t.replace("\u2028", "\n").replace("\u2029", "\n")
    if t.startswith("\ufeff"):
        t = t[1:]
    return t


def _norm_pptx_plain_segment(s: str) -> str:
    """单节点 a:t 文本规范化（填充前写入树，使重建串与切片累积一致）。"""
    if not s:
        return s
    t = s.replace("\r\n", "\n").replace("\r", "\n")
    t = t.replace("\u2028", "\n").replace("\u2029", "\n")
    if t.startswith("\ufeff"):
        t = t[1:]
    return t


def _pptx_normalize_roots_at(roots: Dict[str, ET.Element]) -> None:
    for root in roots.values():
        for at in root.iter(_ns_el(_NS_A, "t")):
            if at.text:
                at.text = _norm_pptx_plain_segment(at.text)
            if at.tail:
                at.tail = _norm_pptx_plain_segment(at.tail)


def _canonical_index_to_core_offset(core: str, idx: int) -> int:
    """
    core 为段落 strip 后的中间段；idx 为 canonical_line（即 core.replace('\\x00','')）中的下标；
    返回该字符在 core 中的起始下标。idx == len(canonical) 时返回 len(core)。
    """
    if idx < 0:
        raise ValueError("索引无效")
    c = 0
    for j, ch in enumerate(core):
        if ch == "\x00":
            continue
        if c == idx:
            return j
        c += 1
    if idx == c:
        return len(core)
    raise ValueError("canonical 索引越界")


def _pptx_ap_plain_slices(ap_el: ET.Element) -> Tuple[str, List[_Slice]]:
    """单段 a:p：与 `ooxml_preview_service._pptx_xml_plain` 中单段字符串完全一致。"""
    parts: List[str] = []
    spans: List[Tuple[ET.Element, int, int]] = []
    cum = 0
    for at in ap_el.iter(_ns_el(_NS_A, "t")):
        if at.text:
            tx = at.text
            parts.append(tx)
            spans.append((at, cum, cum + len(tx)))
            cum += len(tx)
    raw_concat = "".join(parts)
    canonical_line = raw_concat.strip().replace("\x00", "")
    if not canonical_line:
        return "", []

    ls = len(raw_concat) - len(raw_concat.lstrip())
    rs = len(raw_concat) - len(raw_concat.rstrip())
    lo_raw = ls
    core = raw_concat[lo_raw : len(raw_concat) - rs]
    if core.replace("\x00", "") != canonical_line:
        raise ValueError("段落文本与 canonical 不一致")

    clen = len(canonical_line)
    segs: List[_Slice] = []
    pos = 0
    while pos < clen:

        def _abs_for(ci: int) -> int:
            return lo_raw + _canonical_index_to_core_offset(core, ci)

        abs_pos = _abs_for(pos)
        at_hit = None
        a = b = 0
        for at, ta, tb in spans:
            if ta <= abs_pos < tb:
                at_hit, a, b = at, ta, tb
                break
        if at_hit is None:
            raise ValueError("无法将占位映射到 a:t")
        end_same = pos + 1
        while end_same < clen:
            if not (a <= _abs_for(end_same) < b):
                break
            end_same += 1
        rel_lo = _abs_for(pos) - a
        rel_hi_excl = _abs_for(end_same) - a
        segs.append(_Slice(at_hit, rel_lo, rel_hi_excl))
        pos = end_same

    return canonical_line, segs


def _pptx_slide_paragraph_slices(root: ET.Element) -> Tuple[str, List[_Slice]]:
    """与 `_pptx_xml_plain` 的主路径一致：按 a:p 遍历。"""
    lines_blocks: List[Tuple[str, List[_Slice]]] = []
    for ap in root.iter(_ns_el(_NS_A, "p")):
        ln, segs = _pptx_ap_plain_slices(ap)
        if ln:
            lines_blocks.append((ln, segs))
    if not lines_blocks:
        return "", []
    slices_flat: List[_Slice] = []
    plain_parts: List[str] = []
    for i, (ln, segs) in enumerate(lines_blocks):
        if i > 0:
            slices_flat.append(_Slice(None, 0, 0, virtual="\n"))
            plain_parts.append("\n")
        for sl in segs:
            slices_flat.append(sl)
            plain_parts.append(sl.text)
    return "".join(plain_parts), slices_flat


def _pptx_slide_fallback_at_slices(root: ET.Element) -> Tuple[str, List[_Slice]]:
    """与 `_pptx_xml_plain` 兜底分支一致：文档序非空 a:t，每项为 at.text.strip()。"""
    slices_flat: List[_Slice] = []
    plain_parts: List[str] = []
    first = True
    for at in root.iter(_ns_el(_NS_A, "t")):
        if not at.text:
            continue
        tx = at.text
        if not tx.strip():
            continue
        ls = len(tx) - len(tx.lstrip())
        rs = len(tx) - len(tx.rstrip())
        lo, hi = ls, len(tx) - rs
        if lo >= hi:
            continue
        piece = tx[lo:hi]
        if not first:
            slices_flat.append(_Slice(None, 0, 0, virtual="\n"))
            plain_parts.append("\n")
        first = False
        slices_flat.append(_Slice(at, lo, hi))
        plain_parts.append(piece)
    return "".join(plain_parts), slices_flat


def _pptx_slide_plain_slices(root: ET.Element, raw: bytes) -> Tuple[str, List[_Slice]]:
    """切片与占位遍历必须用同一棵 XML 树计算 ref，避免重复 parse 导致细微不一致。"""
    del raw  # 保留签名兼容；正文以 root 为准
    ref = _norm_pptx_plain(_pptx_xml_plain_from_root(root))
    if not ref.strip():
        return "", []
    pm_raw, ps = _pptx_slide_paragraph_slices(root)
    if _norm_pptx_plain(pm_raw) == ref:
        # 必须用切片累积串作为正文，不能用 ref：规范化可能缩短长度，否则占位下标与切片错位。
        return pm_raw, ps
    fm_raw, fs = _pptx_slide_fallback_at_slices(root)
    if _norm_pptx_plain(fm_raw) == ref:
        return fm_raw, fs
    raise ValueError(
        "幻灯片文本切片与 OOXML 抽取不一致（请反馈模板样本）；"
        f" len段落={len(pm_raw)} len兜底={len(fm_raw)} len参照={len(ref)}"
    )


def _load_pptx_roots(blob: bytes) -> Tuple[List[str], Dict[str, ET.Element], Dict[str, bytes]]:
    if not blob or len(blob) < 4 or blob[:2] != b"PK":
        return [], {}, {}
    try:
        z = zipfile.ZipFile(io.BytesIO(blob))
    except zipfile.BadZipFile:
        return [], {}, {}
    paths: List[str] = []
    roots: Dict[str, ET.Element] = {}
    raws: Dict[str, bytes] = {}
    for p in _sorted_slide_xml_paths(z):
        paths.append(p)
        raws[p] = z.read(p)
        roots[p] = ET.fromstring(raws[p])
    for p in _notes_xml_paths(z):
        if p in z.namelist():
            paths.append(p)
            raws[p] = z.read(p)
            roots[p] = ET.fromstring(raws[p])
    z.close()
    return paths, roots, raws


def build_pptx_plain_slices_from_roots(
    paths: List[str],
    roots: Dict[str, ET.Element],
    raws: Dict[str, bytes],
) -> Tuple[str, List[_Slice]]:
    """多块之间为 \\n\\n（两片虚拟 \\n）。正文串必须与切片累积一致，供占位下标与 bisect 使用。"""
    slices_all: List[_Slice] = []
    first = True
    for path in paths:
        root = roots.get(path)
        raw = raws.get(path)
        if root is None or raw is None:
            continue
        frag, sl = _pptx_slide_plain_slices(root, raw)
        if not frag.strip():
            continue
        if not first:
            slices_all.append(_Slice(None, 0, 0, virtual="\n"))
            slices_all.append(_Slice(None, 0, 0, virtual="\n"))
        first = False
        slices_all.extend(sl)
    plain = "".join(s.text for s in slices_all)
    return plain, slices_all


def pptx_zip_slots_plain(blob: bytes, *, truncate: bool = True) -> str:
    """与 `fill_pptx_body_from_values` 占位范围一致（不含【幻灯片 N】）；用于预览 plain_text_body。"""
    paths, roots, raws = _load_pptx_roots(blob)
    _pptx_normalize_roots_at(roots)
    plain, _ = build_pptx_plain_slices_from_roots(paths, roots, raws)
    if truncate:
        return _truncate_preview_text(plain)
    return plain


def _cum_lens_slices(slices: List[_Slice]) -> List[int]:
    c = [0]
    for sl in slices:
        c.append(c[-1] + len(sl.text))
    return c


def _replace_span_slices(slices: List[_Slice], st: int, en: int, val: str) -> None:
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
            "占位落在幻灯片块分隔换行处，请将 X 写在文本框或表格单元格文字内"
        )

    if slices[i].at_el is slices[j].at_el:
        at = slices[i].at_el
        t = at.text or ""
        at.text = t[:abs_lo] + val + t[abs_hi:]
        return

    fa = slices[i].at_el
    ft = fa.text or ""
    fa.text = ft[:abs_lo] + val

    for k in range(i + 1, j):
        sl = slices[k]
        if sl.virtual is not None:
            raise ValueError("占位跨越块分隔符")
        ax = sl.at_el
        tx = ax.text or ""
        ax.text = tx[: sl.lo] + tx[sl.hi :]

    la = slices[j].at_el
    lt = la.text or ""
    la.text = lt[: slices[j].lo] + lt[abs_hi:]


def fill_pptx_body_from_values(blob: bytes, values: List[str]) -> bytes:
    paths, roots, raws = _load_pptx_roots(blob)
    if not paths or not roots:
        raise ValueError("无效的 pptx：无可编辑幻灯片部件")

    _pptx_normalize_roots_at(roots)

    plain, _ = build_pptx_plain_slices_from_roots(paths, roots, raws)
    slots = find_x_slots(plain)
    vals = list(values)
    if len(vals) > len(slots):
        vals = vals[: len(slots)]
    elif len(vals) < len(slots):
        vals = vals + [""] * (len(slots) - len(vals))

    # 从右向左替换，slot 下标始终对应「当前 XML 拼出的正文」（不在内存里做字符串拼接更新 cur：
    # 否则某页被替换为空后 build 会跳过该页，与「保留 \\n\\n 边界的切片拼接」不一致，触发假阳性「正文状态不一致」。）
    for slot, val in sorted(zip(slots, vals), key=lambda x: -x[0]["start"]):
        st, en, raw = slot["start"], slot["end"], slot["raw"]
        plain_now, slices = build_pptx_plain_slices_from_roots(paths, roots, raws)
        if plain_now[st:en] != raw:
            raise ValueError("占位区间与正文不一致")
        _replace_span_slices(slices, st, en, effective_slot_replacement(val, raw))

    buf_in = io.BytesIO(blob)
    zin = zipfile.ZipFile(buf_in, "r")
    zout = io.BytesIO()
    with zipfile.ZipFile(zout, "w", zipfile.ZIP_DEFLATED) as zf:
        for item in zin.infolist():
            data = zin.read(item.filename)
            if item.filename in roots:
                root_el = roots[item.filename]
                data = ET.tostring(root_el, encoding="utf-8", xml_declaration=True)
            zi = zipfile.ZipInfo(filename=item.filename)
            zi.compress_type = item.compress_type
            zi.external_attr = item.external_attr
            zf.writestr(zi, data)
    zin.close()
    return zout.getvalue()


_MINIMAL_PPTX_ASSET = "minimal_fallback.pptx"


def build_pptx_from_plain_fallback(title: str, body: str) -> bytes:
    """
    不依赖 python-pptx：使用内嵌最小 pptx（ppt/slides/slide1.xml 中含占位符 __BODY__），
    写入标题+正文后重新打包。供服务器无法 pip 安装 python-pptx 时的预览回退。
    """
    base = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "assets"))
    path = os.path.join(base, _MINIMAL_PPTX_ASSET)
    if not os.path.isfile(path):
        raise FileNotFoundError(f"缺少内嵌模板文件: {path}")

    with open(path, "rb") as f:
        raw_zip = f.read()

    title_s = (title or "").strip()
    body_s = body or ""
    block = f"{title_s}\n\n{body_s}" if title_s else body_s
    injected = xu.escape(block)

    zin = zipfile.ZipFile(io.BytesIO(raw_zip), "r")
    zout = io.BytesIO()
    with zipfile.ZipFile(zout, "w", zipfile.ZIP_DEFLATED) as zf:
        for item in zin.infolist():
            data = zin.read(item.filename)
            if item.filename == "ppt/slides/slide1.xml":
                s = data.decode("utf-8")
                if "__BODY__" not in s:
                    raise ValueError("内嵌 pptx 模板缺少占位符 __BODY__")
                s = s.replace("__BODY__", injected)
                data = s.encode("utf-8")
            zi = zipfile.ZipInfo(filename=item.filename)
            zi.compress_type = item.compress_type
            zi.external_attr = item.external_attr
            zf.writestr(zi, data)
    zin.close()
    return zout.getvalue()
