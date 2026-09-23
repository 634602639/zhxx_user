"""规则填表1/叙事 KPI；空着的进展/计划/建议等章节交大模型起草；再 OOXML 版式内替换。"""
from __future__ import annotations

import io
import json
import re
import zipfile
from datetime import date, datetime

from services.docx_fill_service import find_x_slots, fill_docx_body_from_values, sniff_word_ext
from services.llm_service import chat, llm_config, parse_json_content
from services.metric_catalog import TABLE1_COLUMN_CODES, UNIT_SHORT_LABELS, demo_metrics_map
from services.office_text_replace import replace_empty_narrative_paragraphs
from services.ooxml_preview_service import _docx_extract_word_xml
from services.pptx_fill_service import fill_pptx_body_from_values, pptx_zip_slots_plain, sniff_pptx_ext
from services.unit_metric_service import metrics_for_llm

_EMPTY_SECTION_BODIES = frozenset({"无", "无。", "暂无", "暂无。", "/", "—", "——"})
_SECTION_CANON = (
    ("本月进展", "本月进展"),
    ("工作进展", "本月进展"),
    ("下月计划", "下月计划"),
    ("下步计划", "下月计划"),
    ("下一步计划", "下月计划"),
    ("措施建议", "措施建议"),
    ("意见建议", "措施建议"),
)
_HEADING_PREFIX = re.compile(r"^[（(]?[一二三四五六七八九十百0-9]+[）)、.．、]?\s*")
_NARRATIVE_SLOT_KEYS = ("进展", "计划", "建议", "措施")


def _period_defaults(data: dict | None) -> dict:
    today = date.today()
    d = data or {}
    df = (d.get("date_from") or "").strip()
    dt = (d.get("date_to") or "").strip()
    if not dt:
        dt = today.strftime("%Y-%m-%d")
    if not df:
        df = date(today.year, today.month, 1).strftime("%Y-%m-%d")
    try:
        d0 = datetime.strptime(df[:10], "%Y-%m-%d").date()
    except ValueError:
        d0 = date(today.year, today.month, 1)
    try:
        d1 = datetime.strptime(dt[:10], "%Y-%m-%d").date()
    except ValueError:
        d1 = today
    if d1 < d0:
        d0, d1 = d1, d0
    # 年/月/周由时间范围推（优先截止日期）；请求里仍可显式覆盖
    try:
        year = int(d["year"]) if d.get("year") not in (None, "") else d1.year
    except (TypeError, ValueError, KeyError):
        year = d1.year
    try:
        month = int(d["month"]) if d.get("month") not in (None, "") else d1.month
    except (TypeError, ValueError, KeyError):
        month = d1.month
    month = min(12, max(1, month))
    try:
        week = int(d["week"]) if d.get("week") not in (None, "") else d1.isocalendar()[1]
    except (TypeError, ValueError, KeyError):
        week = d1.isocalendar()[1]
    return {
        "year": year,
        "month": month,
        "week": week,
        "date_from": d0,
        "date_to": d1,
    }


def _narrative_unit_code(data: dict | None) -> str:
    raw = str((data or {}).get("unit") or "").strip().lower()
    allowed = {c for c in TABLE1_COLUMN_CODES if c}
    if raw in allowed:
        return raw
    return "hq"


def template_plain_for_slots(blob: bytes, filename: str = "") -> tuple[str, str]:
    """返回 (plain, kind) kind=docx|pptx。plain 与版式内替换范围一致、不截断。"""
    if sniff_pptx_ext(blob, filename) == ".pptx":
        return pptx_zip_slots_plain(blob, truncate=False) or "", "pptx"
    if sniff_word_ext(blob, filename) == ".docx":
        try:
            with zipfile.ZipFile(io.BytesIO(blob)) as z:
                raw = z.read("word/document.xml")
        except (zipfile.BadZipFile, KeyError):
            return "", "docx"
        return (_docx_extract_word_xml(raw) or "").replace("\r", ""), "docx"
    return "", ""


def _metric(mmap: dict, code: str, key: str) -> str:
    info = (mmap.get(code) or {}).get(key) or {}
    return (info.get("display") or "").strip()


def _ctx(plain: str, start: int, end: int, n: int = 48) -> str:
    return plain[max(0, start - n) : min(len(plain), end + n)]


def _fill_table_rows(plain: str, slots: list, values: list, mmap: dict) -> None:
    """按行标签之后的连续占位，依 8 列顺序填本级+五大战区（后两列保持原占位）。"""
    row_specs = [
        ("在线节点数", "node_pair"),
        ("节点在线率", "node_online_rate"),
        ("设备完好率", "equipment_ok_rate"),
        ("计算资源使用率", "js_resource_pct"),
        ("存储空间使用率", "storage_resource_pct"),
    ]
    used = set()
    for label, kind in row_specs:
        pos = plain.find(label)
        if pos < 0:
            continue
        idxs = [i for i, sl in enumerate(slots) if sl["start"] > pos and i not in used]
        if not idxs:
            continue
        if kind == "node_pair":
            need = 16
            take = idxs[:need]
            for col, code in enumerate(TABLE1_COLUMN_CODES):
                a, b = col * 2, col * 2 + 1
                if a >= len(take):
                    break
                ia, ib = take[a], take[b] if b < len(take) else None
                used.add(ia)
                if ib is not None:
                    used.add(ib)
                if not code:
                    continue
                online = _metric(mmap, code, "online_counts")
                total = _metric(mmap, code, "all_counts")
                ratio = _metric(mmap, code, "node_ratio")
                if ratio and "/" in ratio:
                    left, right = ratio.split("/", 1)
                    values[ia] = left.strip()
                    if ib is not None:
                        values[ib] = right.strip()
                else:
                    if online:
                        values[ia] = online
                    if ib is not None and total:
                        values[ib] = total
        else:
            take = idxs[:8]
            for col, code in enumerate(TABLE1_COLUMN_CODES):
                if col >= len(take):
                    break
                i = take[col]
                used.add(i)
                if not code:
                    continue
                v = _metric(mmap, code, kind)
                if v:
                    values[i] = v.rstrip("%") if kind.endswith("_rate") or kind.endswith("_pct") else v


def _fill_narrative_and_period(plain: str, slots: list, values: list, mmap: dict, period: dict, unit_code: str = "hq") -> None:
    unit = mmap.get(unit_code) or mmap.get("hq") or {}
    d0, d1 = period["date_from"], period["date_to"]
    day_slots = []
    month_range_slots = []
    for i, sl in enumerate(slots):
        if values[i]:
            continue
        ctx = _ctx(plain, sl["start"], sl["end"])
        after = plain[sl["end"] : sl["end"] + 2]
        before = plain[max(0, sl["start"] - 8) : sl["start"]]

        if after.startswith("年"):
            values[i] = str(period["year"])
            continue
        if after.startswith("周") or (before.endswith("第") and "周" in ctx):
            values[i] = str(period["week"])
            continue
        if after.startswith("月"):
            if "至" in ctx or "日" in ctx:
                month_range_slots.append(i)
            else:
                values[i] = str(period["month"])
            continue
        if after.startswith("日"):
            day_slots.append(i)
            continue

        if "入网用户" in ctx:
            v = unit.get("access_network_user", {}).get("display")
            if v:
                values[i] = v
                continue
        if "在线率" in ctx:
            v = (unit.get("node_online_rate") or {}).get("display") or ""
            if v:
                values[i] = v.replace("%", "") if (after.startswith("%") or "%" in ctx[len(ctx) // 2 :]) else v
                continue
        if "中心/节点" in ctx or "中心、" in ctx or "信息服务中心" in ctx:
            v = unit.get("all_counts", {}).get("display")
            if v:
                values[i] = v
                continue
        if "信息节点" in ctx or "信息服务节点" in ctx:
            v = unit.get("online_counts", {}).get("display") or unit.get("all_counts", {}).get("display")
            if v:
                values[i] = v
                continue
        if "数据服" in ctx or "万兆" in ctx:
            v = unit.get("data_service_volume", {}).get("display")
            if v:
                values[i] = v
                continue
        if "文件交互" in ctx or "文档交互" in ctx:
            v = unit.get("doc_interaction", {}).get("display")
            if v:
                values[i] = v
                continue

    for j, i in enumerate(month_range_slots):
        values[i] = str(d0.month if j == 0 else d1.month)
    for j, i in enumerate(day_slots):
        values[i] = str(d0.day if j == 0 else d1.day)


def canonical_narrative_section_key(line: str) -> str | None:
    """识别「二、本月进展」这类章节标题，归一成 本月进展 / 下月计划 / 措施建议。"""
    t = re.sub(r"\s+", "", (line or "").strip())
    if not t or len(t) > 24:
        return None
    aliases = {
        "进展": "本月进展",
        "计划": "下月计划",
        "建议": "措施建议",
        "措施": "措施建议",
    }
    if t in aliases:
        return aliases[t]
    for needle, key in _SECTION_CANON:
        if needle in t:
            return key
    if _HEADING_PREFIX.match(t):
        if "进展" in t:
            return "本月进展"
        if "计划" in t:
            return "下月计划"
        if "建议" in t or "措施" in t:
            return "措施建议"
    return None


def _split_heading_empty_line(line: str) -> tuple[str | None, str | None, str]:
    """同一行「二、本月进展无」时拆出章节 key。"""
    t = (line or "").strip()
    if not t:
        return None, None, t
    for empty in sorted(_EMPTY_SECTION_BODIES, key=len, reverse=True):
        for sep in ("", "：", ":", "，", ",", " "):
            suffix = sep + empty
            if len(t) <= len(suffix) or not t.endswith(suffix):
                continue
            head = t[: -len(suffix)].rstrip("：:，,;； ")
            key = canonical_narrative_section_key(head) if head else None
            if key:
                return key, empty, t
    return None, None, t


def find_empty_narrative_sections(plain: str) -> list[dict]:
    found = []
    seen = set()
    parts = re.split(r"\n+", plain or "")
    waiting = None
    for line in parts:
        t = (line or "").strip()
        if not t:
            continue
        same_key, placeholder, raw = _split_heading_empty_line(t)
        if same_key and same_key not in seen:
            found.append({"title": raw, "key": same_key, "placeholder": placeholder})
            seen.add(same_key)
            waiting = None
            continue
        key = canonical_narrative_section_key(t)
        if key:
            waiting = {"title": t, "key": key}
            continue
        if waiting and t in _EMPTY_SECTION_BODIES and waiting["key"] not in seen:
            item = dict(waiting)
            item["placeholder"] = t
            found.append(item)
            seen.add(waiting["key"])
            waiting = None
            continue
        waiting = None
    return found


def _demo_fill_remaining(plain: str, slots: list, values: list) -> list[str]:
    """未接大模型时：故障等无素材填「无」；进展/计划/建议也暂填「无」。"""
    keys = ("进展", "计划", "建议", "存在问题", "故障", "DZT", "防护", "病毒", "告警", "应急", "保障", "措施")
    for i, sl in enumerate(slots):
        if (values[i] or "").strip():
            continue
        ctx = _ctx(plain, sl["start"], sl["end"], 60)
        if any(k in ctx for k in keys):
            values[i] = "无"
    return values


def _llm_fill_remaining(plain: str, slots: list, values: list, mmap: dict, period: dict, unit_code: str = "hq") -> list[str]:
    remaining = []
    for i, v in enumerate(values):
        if (v or "").strip():
            continue
        ctx = _ctx(plain, slots[i]["start"], slots[i]["end"], 80)
        if any(k in ctx for k in _NARRATIVE_SLOT_KEYS):
            remaining.append(i)
    if not remaining or not llm_config()["configured"]:
        return values
    payload_slots = []
    for i in remaining:
        sl = slots[i]
        payload_slots.append({
            "n": i + 1,
            "raw": sl["raw"],
            "context": _ctx(plain, sl["start"], sl["end"], 80),
        })
    unit_zh = UNIT_SHORT_LABELS.get(unit_code) or unit_code
    sys_p = (
        "你是值勤报告填表助手。根据已采集指标和报告期，为模板中尚未填写的 x/X 占位给出替换字符串。\n"
        "规则：\n"
        "1. 只输出 JSON 数组，与输入 slots 等长、顺序一致，元素为字符串。\n"
        "2. 数字必须来自「已采集指标」；没有对应数据时输出空字符串（保留原占位）。\n"
        "3. 上下文属于本月进展、下月计划、措施建议、工作安排等叙述章节时：根据指标写 2～6 句值勤公文，"
        "不要填「无」，不要重复章节标题；数字须来自指标，不编造故障、战果或未出现的单位。\n"
        "4. 故障、防护、DZT、病毒、告警等事件类占位，无素材时仍填「无」，禁止编造具体事件。\n"
        "5. 不要输出 markdown，不要解释。"
    )
    user_p = json.dumps(
        {
            "unit": unit_zh,
            "period": {
                "year": period["year"],
                "month": period["month"],
                "week": period["week"],
                "date_from": period["date_from"].strftime("%Y-%m-%d"),
                "date_to": period["date_to"].strftime("%Y-%m-%d"),
            },
            "metrics": metrics_for_llm(mmap),
            "slots": payload_slots,
        },
        ensure_ascii=False,
    )
    try:
        raw = chat(
            [{"role": "system", "content": sys_p}, {"role": "user", "content": user_p}],
            temperature=0.35,
            max_tokens=4096,
        )
        arr = parse_json_content(raw)
        if not isinstance(arr, list):
            return values
        for idx, slot_i in enumerate(remaining):
            if idx >= len(arr):
                break
            s = "" if arr[idx] is None else str(arr[idx]).strip()
            if s:
                values[slot_i] = s
    except Exception:
        return values
    return values


def _normalize_section_body(text: str, key: str) -> str:
    s = (text or "").strip()
    s = re.sub(r"^```(?:json)?|```$", "", s).strip()
    s = s.replace("\r\n", "\n").replace("\r", "\n")
    s = re.sub(r"\n+", "", s)
    for prefix in (key, f"{key}：", f"{key}:"):
        if s.startswith(prefix):
            s = s[len(prefix):].lstrip("：:，, ")
    if s in _EMPTY_SECTION_BODIES:
        return ""
    return s


def _parse_section_bodies(parsed, wanted_keys: list[str] | None = None) -> dict[str, str]:
    raw = parsed
    if isinstance(parsed, dict):
        if isinstance(parsed.get("sections"), dict):
            raw = parsed["sections"]
        elif isinstance(parsed.get("sections"), list):
            raw = parsed["sections"]
    items = []
    if isinstance(raw, dict):
        items = list(raw.items())
    elif isinstance(raw, list):
        for it in raw:
            if isinstance(it, dict):
                k = it.get("key") or it.get("title") or it.get("name")
                v = it.get("text") or it.get("body") or it.get("content") or it.get("value")
                if k is not None:
                    items.append((k, v))
            elif isinstance(it, str) and it.strip():
                items.append(("", it))
    out = {}
    for k, v in items:
        key = canonical_narrative_section_key(str(k)) if k else None
        if not key and k:
            key = canonical_narrative_section_key("一、" + str(k))
        if not key:
            continue
        body = _normalize_section_body("" if v is None else str(v), key)
        if body:
            out[key] = body
    wanted = [k for k in (wanted_keys or []) if k]
    if wanted and len(out) < len(wanted):
        leftover = []
        if isinstance(raw, dict):
            leftover = [str(v) for v in raw.values() if v is not None]
        elif isinstance(raw, list):
            leftover = [str(it) if not isinstance(it, dict) else "" for it in raw]
            leftover = [x for x in leftover if x.strip()]
        if len(leftover) == len(wanted):
            for key, raw_v in zip(wanted, leftover):
                if (out.get(key) or "").strip():
                    continue
                body = _normalize_section_body(raw_v, key)
                if body:
                    out[key] = body
    return out


def _safe_metrics_for_llm(mmap: dict) -> dict:
    try:
        return metrics_for_llm(mmap)
    except Exception:
        packed = {}
        for code, inner in (mmap or {}).items():
            name = UNIT_SHORT_LABELS.get(code) or code
            packed[name] = {
                (info.get("label") or k): (info.get("display") or "")
                for k, info in (inner or {}).items()
                if isinstance(info, dict)
            }
        return packed


def _join_zh_clauses(parts: list[str]) -> str:
    bits = [p.strip().rstrip("，,。；;") for p in parts if (p or "").strip()]
    if not bits:
        return ""
    text = "，".join(bits)
    if not text.endswith("。"):
        text += "。"
    return text


def _rule_write_empty_sections(mmap: dict, period: dict, unit_code: str, keys: list[str]) -> dict[str, str]:
    """大模型未返回时，用已采集指标起草空章节，不编造故障或战果。"""
    unit_zh = UNIT_SHORT_LABELS.get(unit_code) or unit_code
    d0, d1 = period["date_from"], period["date_to"]
    span = f"{d0.strftime('%Y年%m月%d日')}至{d1.strftime('%Y年%m月%d日')}"
    online = _metric(mmap, unit_code, "node_online_rate")
    ok_rate = _metric(mmap, unit_code, "equipment_ok_rate")
    users = _metric(mmap, unit_code, "access_network_user")
    data_vol = _metric(mmap, unit_code, "data_service_volume")
    docs = _metric(mmap, unit_code, "doc_interaction")
    js = _metric(mmap, unit_code, "js_resource_pct")
    storage = _metric(mmap, unit_code, "storage_resource_pct")
    node_ratio = _metric(mmap, unit_code, "node_ratio")
    if not node_ratio:
        oc, ac = _metric(mmap, unit_code, "online_counts"), _metric(mmap, unit_code, "all_counts")
        if oc and ac:
            node_ratio = f"{oc}/{ac}"

    templates = {
        "本月进展": _join_zh_clauses([
            f"{span}，{unit_zh}按计划组织业务信息系统值勤运行",
            f"在线节点{node_ratio}" if node_ratio else "",
            f"节点在线率{online}" if online else "",
            f"设备完好率{ok_rate}" if ok_rate else "",
            f"入网用户{users}" if users else "",
            f"累计数据服务{data_vol}" if data_vol else "",
            f"文件交互{docs}条" if docs else "",
            "建设与值勤保障按既定安排推进，本期叙述仅依据上述指标",
        ]),
        "下月计划": _join_zh_clauses([
            f"下一周期继续做好{unit_zh}节点巡检与在线监测",
            f"对照本期节点在线率{online}跟踪在线情况" if online else "",
            f"对照本期设备完好率{ok_rate}组织巡检" if ok_rate else "",
            f"统筹计算资源使用（本期{js}）" if js else "",
            f"统筹存储空间使用（本期{storage}）" if storage else "",
            "加强跨中心协同和日常值勤交接，确保运行指标平稳",
        ]),
        "措施建议": _join_zh_clauses([
            "建议持续核验节点在线与设备完好数据，按指标偏差安排巡检频次",
            f"结合本期计算资源使用率{js}做好资源监测" if js else "完善资源使用监测",
            f"结合本期存储空间使用率{storage}预留扩容余量" if storage else "",
            "值勤交接时核对关键指标，情况以采集数据为准",
        ]),
    }
    out = {}
    for key in keys:
        body = (templates.get(key) or "").strip()
        if body:
            out[key] = body
    return out


def _llm_write_empty_sections(plain: str, mmap: dict, period: dict, unit_code: str) -> dict[str, str]:
    sections = find_empty_narrative_sections(plain)
    if not sections or not llm_config()["configured"]:
        return {}
    unit_zh = UNIT_SHORT_LABELS.get(unit_code) or unit_code
    excerpt = plain or ""
    if len(excerpt) > 8000:
        excerpt = excerpt[:3500] + "\n…\n" + excerpt[-4500:]
    wanted = [s["key"] for s in sections]
    sys_p = (
        "你是值勤报告撰写助手。模板里「本月进展」「下月计划」「措施建议」等章节正文目前只有「无」或空白，"
        "需要根据已填入的运行指标把这些章节写上。\n"
        "规则：\n"
        "1. 只输出 JSON 对象，键必须是章节 key（本月进展 / 下月计划 / 措施建议），值为该节正文，不要重复标题。\n"
        "2. 每节 2～6 句，书面语，符合值勤报告语气。\n"
        "3. 「本月进展」概括本期运行、值勤保障与建设推进；「下月计划」写下一周期运维、巡检、资源与协同安排；"
        "「措施建议」写可落地的改进措施（监控、巡检、资源、协同等），勿空喊口号。\n"
        "4. 数字必须来自「已采集指标」或报告摘录中已出现的数字，不得改数字，不得编造故障、战果或未出现的单位。\n"
        "5. 不要输出 markdown，不要解释。"
    )
    user_p = json.dumps(
        {
            "unit": unit_zh,
            "period": {
                "year": period["year"],
                "month": period["month"],
                "week": period["week"],
                "date_from": period["date_from"].strftime("%Y-%m-%d"),
                "date_to": period["date_to"].strftime("%Y-%m-%d"),
            },
            "metrics": _safe_metrics_for_llm(mmap),
            "empty_sections": sections,
            "report_excerpt": excerpt,
        },
        ensure_ascii=False,
    )
    raw = chat(
        [{"role": "system", "content": sys_p}, {"role": "user", "content": user_p}],
        temperature=0.4,
        max_tokens=2048,
    )
    parsed = parse_json_content(raw)
    bodies = _parse_section_bodies(parsed, wanted)
    wanted_set = set(wanted)
    return {k: v for k, v in bodies.items() if k in wanted_set}


def _fill_empty_narrative_sections(
    out: bytes,
    filled_plain: str,
    mmap: dict,
    period: dict,
    unit_code: str,
    filename: str,
    *,
    use_llm: bool,
) -> tuple[bytes, str, list[str]]:
    sections = find_empty_narrative_sections(filled_plain)
    if not sections:
        return out, filled_plain, []
    wanted = [s["key"] for s in sections]
    bodies = _rule_write_empty_sections(mmap, period, unit_code, wanted)
    if use_llm and llm_config()["configured"]:
        try:
            llm_bodies = _llm_write_empty_sections(filled_plain, mmap, period, unit_code)
        except Exception:
            llm_bodies = {}
        for k, v in (llm_bodies or {}).items():
            if (v or "").strip():
                bodies[k] = v.strip()
    try:
        from models import to_db_text
        bodies = {k: to_db_text(v) for k, v in bodies.items() if to_db_text(v).strip()}
    except Exception:
        bodies = {k: v for k, v in bodies.items() if (v or "").strip()}
    if not bodies:
        return out, filled_plain, []
    out = replace_empty_narrative_paragraphs(
        out, bodies, canonical_narrative_section_key, _EMPTY_SECTION_BODIES
    )
    filled_plain, _ = template_plain_for_slots(out, filename)
    return out, filled_plain, list(bodies.keys())


def compute_slot_values(plain: str, mmap: dict, period: dict, *, use_llm: bool = True, unit_code: str = "hq") -> list[str]:
    slots = find_x_slots(plain or "")
    values = [""] * len(slots)
    _fill_table_rows(plain or "", slots, values, mmap)
    _fill_narrative_and_period(plain or "", slots, values, mmap, period, unit_code)
    if use_llm and llm_config()["configured"]:
        values = _llm_fill_remaining(plain or "", slots, values, mmap, period, unit_code)
    values = _demo_fill_remaining(plain or "", slots, values)
    return values


def autofill_template(
    blob: bytes,
    filename: str = "",
    *,
    period_data: dict | None = None,
    use_llm: bool = True,
    days: int = 7,
) -> dict:
    kind_plain = template_plain_for_slots(blob, filename)
    plain, kind = kind_plain
    if not kind:
        raise ValueError("仅支持 .docx / .pptx 模板")
    if not (plain or "").strip():
        raise ValueError("模板未解析到可替换正文")
    period = _period_defaults(period_data)
    unit_code = _narrative_unit_code(period_data)
    mmap = demo_metrics_map()
    slots = find_x_slots(plain)
    values = compute_slot_values(plain, mmap, period, use_llm=use_llm, unit_code=unit_code)
    if kind == "pptx":
        out = fill_pptx_body_from_values(blob, values)
        mime = "application/vnd.openxmlformats-officedocument.presentationml.presentation"
        ext = ".pptx"
    else:
        out = fill_docx_body_from_values(blob, values)
        mime = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        ext = ".docx"
    filled_plain, _ = template_plain_for_slots(out, filename or ("x" + ext))
    llm_used = bool(use_llm and llm_config()["configured"])
    out, filled_plain, narrative_filled = _fill_empty_narrative_sections(
        out,
        filled_plain,
        mmap,
        period,
        unit_code,
        filename or ("x" + ext),
        use_llm=use_llm,
    )
    bindings = [{"mode": "manual", "cleanId": None, "manual": v} for v in values]
    return {
        "kind": kind,
        "ext": ext,
        "mime": mime,
        "values": values,
        "bindings": bindings,
        "slot_count": len(slots),
        "filled_count": sum(1 for v in values if (v or "").strip()),
        "narrative_filled": narrative_filled,
        "plain_before": plain,
        "plain_after": filled_plain,
        "file_blob": out,
        "metrics": _safe_metrics_for_llm(mmap),
        "period": {
            "year": period["year"],
            "month": period["month"],
            "week": period["week"],
            "date_from": period["date_from"].strftime("%Y-%m-%d"),
            "date_to": period["date_to"].strftime("%Y-%m-%d"),
            "unit": unit_code,
            "unit_zh": UNIT_SHORT_LABELS.get(unit_code) or unit_code,
        },
        "llm_used": llm_used,
    }
