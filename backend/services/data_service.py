"""
多源数据采集与管理服务
- 远程请求 URL，解析 JSON 为预览结构（不落库）
- 多维分析等仍基于 CleanData
"""
import json
import math
from datetime import datetime
from urllib.parse import urlparse

import requests

from models import CollectEndpoint, CleanData, AnalysisSnapshot, db


ALLOWED_HTTP_METHODS = frozenset({"GET", "POST", "PUT", "PATCH", "DELETE"})
_ITEM_PREVIEW_CHARS = 16000


def _serialize_item_preview(it) -> str:
    """单条采集对应的原文（用于预览区展示，过长截断）。"""
    try:
        if isinstance(it, (dict, list)):
            s = json.dumps(it, ensure_ascii=False)
        elif isinstance(it, str):
            s = it
        else:
            s = repr(it)
        if len(s) > _ITEM_PREVIEW_CHARS:
            return s[: _ITEM_PREVIEW_CHARS] + "…"
        return s
    except Exception:
        s = str(it)
        return (s[: _ITEM_PREVIEW_CHARS] + "…") if len(s) > _ITEM_PREVIEW_CHARS else s


def _preview_row_dict(
    source,
    category,
    title,
    content,
    raw_value,
    occur_time,
    item_source=None,
):
    """与前端预览表格字段一致；item_source 为本条对应的原始片段（子对象或文本）。"""
    d = {
        "id": None,
        "source": source,
        "category": category,
        "title": title,
        "content": content,
        "raw_value": _finite_float_or_none(raw_value),
        "occur_time": occur_time,
        "created_at": datetime.now().replace(microsecond=0).strftime("%Y-%m-%d %H:%M:%S"),
    }
    if item_source is not None:
        d["item_raw_json"] = _serialize_item_preview(item_source)
    return d


def _finite_float_or_none(v):
    """入库用的数值：排除 nan/inf，非法则 None。"""
    if v is None:
        return None
    try:
        x = float(v)
    except (TypeError, ValueError):
        return None
    if math.isnan(x) or math.isinf(x):
        return None
    return x


HTTP_REPLY_PREVIEW_CHARS = 120000


def _http_response_preview(resp):
    """供前端展示的 HTTP 响应原文（过长截断）。"""
    text = resp.text if resp.text is not None else ""
    cap = HTTP_REPLY_PREVIEW_CHARS
    truncated = len(text) > cap
    body = text[:cap] if truncated else text
    return {
        "status_code": resp.status_code,
        "content_type": resp.headers.get("Content-Type") or "",
        "encoding": getattr(resp, "encoding", None) or "",
        "body": body,
        "body_truncated": truncated,
    }


def kw_from_collect_endpoint(ep: CollectEndpoint):
    """从持久化配置构造 extract_from_http 的关键字参数。"""
    hdrs = None
    if ep.headers_json and str(ep.headers_json).strip():
        hdrs = _parse_headers(ep.headers_json)
    fm = None
    if ep.field_map_json and str(ep.field_map_json).strip():
        try:
            fm = json.loads(ep.field_map_json)
        except json.JSONDecodeError:
            fm = None
    lp = (ep.list_path or "").strip() or None
    return {
        "method": ep.method or "GET",
        "url": ep.url.strip(),
        "headers": hdrs,
        "body": (ep.body or "").strip() or None,
        "source_label": (ep.source_label or "").strip() or None,
        "category_label": (ep.category_label or "").strip() or None,
        "list_path": lp,
        "field_map": fm if isinstance(fm, dict) else None,
    }


def _parse_headers(raw):
    """从前端传入的对象或 JSON 字符串解析为 dict[str,str]。"""
    if raw is None:
        return {}
    if isinstance(raw, dict):
        return {str(k): str(v) for k, v in raw.items()}
    if isinstance(raw, str) and raw.strip():
        try:
            h = json.loads(raw)
        except json.JSONDecodeError as e:
            raise ValueError("请求头 JSON 格式无效") from e
        if not isinstance(h, dict):
            raise ValueError("请求头须为 JSON 对象")
        return {str(k): str(v) for k, v in h.items()}
    return {}


def _navigate_path(obj, path: str):
    """按点号路径取值；支持 list 的数字下标片段（如 items.0.name）。"""
    if obj is None or path is None:
        return None
    path = str(path).strip()
    if not path:
        return obj
    cur = obj
    for part in path.split("."):
        part = part.strip()
        if part == "":
            continue
        if cur is None:
            return None
        if isinstance(cur, dict):
            cur = cur.get(part)
        elif isinstance(cur, list):
            if part.isdigit():
                idx = int(part)
                cur = cur[idx] if 0 <= idx < len(cur) else None
            else:
                return None
        else:
            return None
    return cur


def _resolve_items(payload, list_path: str | None):
    """解析出待入库的子项列表。list_path 为空时用原有自动识别。"""
    lp = (list_path or "").strip()
    if not lp:
        return _items_from_payload(payload)
    node = _navigate_path(payload, lp)
    if node is None:
        raise ValueError(f'列表路径「{lp}」在响应 JSON 中不存在或为 null')
    if isinstance(node, list):
        return node
    if isinstance(node, dict):
        return [node]
    raise ValueError(f'列表路径「{lp}」须指向数组或对象，当前类型：{type(node).__name__}')


def _dict_from_field_map(obj: dict, fm: dict, source_default: str, category_default: str):
    """按配置的字段路径从单条 JSON 对象映射为预览字典。"""
    fm = fm or {}

    def pick(path_key: str, fallbacks):
        p = fm.get(path_key)
        if p is not None and str(p).strip():
            v = _navigate_path(obj, str(p).strip())
            if v is not None and v != "":
                return v
        for fb in fallbacks:
            if fb in obj:
                return obj.get(fb)
        return None

    title_v = pick("title", [])
    if title_v is None:
        title_v = (
            obj.get("title")
            or obj.get("name")
            or obj.get("subject")
            or (str(obj["id"]) if obj.get("id") is not None else None)
        )
    title = str(title_v if title_v is not None else "未命名记录")[:255]

    content_v = pick("content", [])
    if content_v is None:
        content_v = (
            obj.get("content")
            or obj.get("body")
            or obj.get("description")
            or obj.get("text")
            or obj.get("message")
        )
    content = str(content_v if content_v is not None else "")

    rv = pick("raw_value", [])
    if rv is None:
        rv = obj.get("raw_value")
        if rv is None:
            rv = obj.get("value") or obj.get("metric") or obj.get("score")
    raw_value = _finite_float_or_none(rv)

    ot = pick("occur_time", [])
    if ot is None:
        ot = (
            obj.get("occur_time")
            or obj.get("time")
            or obj.get("timestamp")
            or obj.get("created_at")
            or obj.get("date")
        )
    occur_time = str(ot)[:64] if ot is not None else None

    src = pick("source", [])
    if src is None:
        src = obj.get("source")
    src = str(src if src is not None else source_default or "远程接口")[:64]

    cat = pick("category", [])
    if cat is None:
        cat = obj.get("category")
    cat = str(cat if cat is not None else category_default or "未分类")[:64]

    return _preview_row_dict(src, cat, title, content, raw_value, occur_time, item_source=obj)


def _items_from_payload(payload):
    """将接口返回的 JSON 转为记录列表。"""
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict):
        for key in ("data", "items", "records", "list", "results", "rows"):
            v = payload.get(key)
            if isinstance(v, list):
                return v
        return [payload]
    raise ValueError("响应 JSON 无法解析为对象列表")


def _dict_from_obj(obj, source_default: str, category_default: str):
    """将 dict 映射为预览字典；兼容常见字段名。"""
    if not isinstance(obj, dict):
        raise ValueError("单条记录须为 JSON 对象")
    title = (
        obj.get("title")
        or obj.get("name")
        or obj.get("subject")
        or (str(obj["id"]) if obj.get("id") is not None else None)
        or "未命名记录"
    )
    title = str(title)[:255]
    content = str(
        obj.get("content")
        or obj.get("body")
        or obj.get("description")
        or obj.get("text")
        or obj.get("message")
        or ""
    )
    rv = obj.get("raw_value")
    if rv is None:
        rv = obj.get("value") or obj.get("metric") or obj.get("score")
    raw_value = _finite_float_or_none(rv)
    ot = (
        obj.get("occur_time")
        or obj.get("time")
        or obj.get("timestamp")
        or obj.get("created_at")
        or obj.get("date")
    )
    occur_time = str(ot)[:64] if ot is not None else None
    src = obj.get("source") or source_default or "远程接口"
    cat = obj.get("category") or category_default or "未分类"
    return _preview_row_dict(
        str(src)[:64],
        str(cat)[:64],
        title,
        content,
        raw_value,
        occur_time,
        item_source=obj,
    )


def extract_from_http(
    method: str,
    url: str,
    headers=None,
    body=None,
    source_label: str | None = None,
    category_label: str | None = None,
    list_path: str | None = None,
    field_map: dict | None = None,
):
    """请求 URL，将响应解析为预览记录字典列表（不入库）。
    list_path：点号路径指向数组（或单对象）；为空则自动识别 data/items 等。
    field_map：各预览字段对应的 JSON 路径（与顶层键同名）；为空则用默认规则。"""
    m = (method or "GET").upper().strip()
    if m not in ALLOWED_HTTP_METHODS:
        raise ValueError(f"不支持的 HTTP 方法: {method}，可选: {', '.join(sorted(ALLOWED_HTTP_METHODS))}")
    url = (url or "").strip()
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise ValueError("URL 须以 http:// 或 https:// 开头")
    if not parsed.netloc:
        raise ValueError("URL 格式无效")

    hdrs = _parse_headers(headers)
    timeout = 45
    kw = {"timeout": timeout, "headers": hdrs}

    if m in ("POST", "PUT", "PATCH"):
        body_str = (body or "").strip()
        if body_str:
            try:
                kw["json"] = json.loads(body_str)
            except json.JSONDecodeError:
                kw["data"] = body_str.encode("utf-8")
    elif m == "GET" and body and str(body).strip():
        raise ValueError("GET 请求不应携带请求体，请将参数写在 URL 查询串中")

    resp = requests.request(m, url, **kw)
    resp.raise_for_status()
    http_meta = _http_response_preview(resp)

    ct = (resp.headers.get("Content-Type") or "").lower()
    src_def = (source_label or "").strip() or parsed.netloc[:64]
    cat_def = (category_label or "").strip() or "未分类"

    if "json" in ct or (resp.text or "").lstrip().startswith(("{", "[")):
        try:
            payload = resp.json()
        except ValueError:
            payload = None
        if payload is not None:
            items = _resolve_items(payload, list_path)
            rows = []
            fm = field_map if isinstance(field_map, dict) else None
            for it in items:
                if isinstance(it, dict):
                    if fm:
                        rows.append(_dict_from_field_map(it, fm, src_def, cat_def))
                    else:
                        rows.append(_dict_from_obj(it, src_def, cat_def))
                else:
                    rows.append(
                        _preview_row_dict(
                            src_def[:64],
                            cat_def[:64],
                            f"非对象项-{len(rows)+1}"[:255],
                            str(it)[:5000],
                            None,
                            None,
                            item_source=it,
                        )
                    )
            if not rows:
                raise ValueError("响应中无有效记录")
            return len(rows), rows, http_meta

    text = (resp.text or "")[:100000]
    one = _preview_row_dict(
        src_def[:64],
        cat_def[:64],
        (url[:200] + ("…" if len(url) > 200 else ""))[:255],
        text,
        None,
        None,
        item_source=text,
    )
    return 1, [one], http_meta


def multi_dim_analysis():
    """多维数据分析：按来源 / 类别 / 日期 / 数值聚合。

    口径说明：
      - by_source / by_category 优先取每条数据自身的 endpoint_source / endpoint_category
        （入库时填写、列表中展示的来源/类别）；为空时回退到所属采集配置的
        source_label / category_label，最后回退到配置名 / 未分类。
      - by_endpoint 单独提供按所属配置（CleanData.source，即 endpoint name）的分布。
      - by_clean_category 提供 CleanData.category 字段（标签入库流程下基本恒为"标签入库"），仅备查。
    """
    rows = CleanData.query.all()
    ep_by_name: dict = {
        ep.name: (ep.source_label, ep.category_label)
        for ep in CollectEndpoint.query.all()
    }

    by_endpoint, by_source, by_category, by_clean_cat, by_date, value_by_cat = {}, {}, {}, {}, {}, {}
    for r in rows:
        ep_name = r.source or "未知"
        ep_src, ep_cat = ep_by_name.get(r.source or "", (None, None))
        # 优先用每条数据自身的来源/类别（入库时填写、列表中展示的就是它）；
        # 为空时再回退到所属配置的默认来源/类别，最后回退到配置名 / 未分类。
        src_lbl = r.endpoint_source or ep_src or ep_name
        cat_lbl = r.endpoint_category or ep_cat or "未分类"
        clean_cat = r.category or "未分类"

        by_endpoint[ep_name] = by_endpoint.get(ep_name, 0) + 1
        by_source[src_lbl] = by_source.get(src_lbl, 0) + 1
        by_category[cat_lbl] = by_category.get(cat_lbl, 0) + 1
        by_clean_cat[clean_cat] = by_clean_cat.get(clean_cat, 0) + 1

        d = r.occur_time.strftime("%Y-%m-%d") if r.occur_time else "未知"
        by_date[d] = by_date.get(d, 0) + 1

        value_by_cat[cat_lbl] = value_by_cat.get(cat_lbl, 0.0) + (r.metric_value or 0)

    return {
        "total": len(rows),
        "by_source": [{"name": k, "value": v} for k, v in by_source.items()],
        "by_category": [{"name": k, "value": v} for k, v in by_category.items()],
        "by_endpoint": [{"name": k, "value": v} for k, v in by_endpoint.items()],
        "by_clean_category": [{"name": k, "value": v} for k, v in by_clean_cat.items()],
        "by_date": sorted([{"date": k, "value": v} for k, v in by_date.items()], key=lambda x: x["date"]),
        # 若所有 metric_value 都为 NULL（历史数据），回退用条目数，让"按数值"面板有可视化
        "value_by_category": (
            [{"name": k, "value": round(v, 2)} for k, v in value_by_cat.items()]
            if any(v for v in value_by_cat.values())
            else [{"name": k, "value": by_category.get(k, 0)} for k in value_by_cat.keys()]
        ),
    }


def _to_non_negative_int(val, label: str) -> int:
    """KPI 存储用：转非负整数，非法值报错。"""
    try:
        n = int(round(float(val)))
    except (TypeError, ValueError):
        raise ValueError(f"{label}须为数字")
    if n < 0:
        raise ValueError(f"{label}不能为负数")
    return n


def save_analysis_snapshot(data: dict) -> dict:
    """把前端展示的 4 个 KPI（样本总量/日均采集/峰值/覆盖来源）存为一条快照。"""
    snap = AnalysisSnapshot(
        total=_to_non_negative_int(data.get("total"), "样本总量"),
        daily_avg=_to_non_negative_int(data.get("daily_avg"), "日均采集"),
        peak=_to_non_negative_int(data.get("peak"), "峰值"),
        source_count=_to_non_negative_int(data.get("source_count"), "覆盖来源"),
    )
    db.session.add(snap)
    db.session.commit()
    return snap.to_dict()
