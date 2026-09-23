"""按单位基地 URL + 共享路径拉取指标，写入 CleanData。"""
from __future__ import annotations

import hashlib
import math
import re
from datetime import datetime, timedelta
from urllib.parse import urlparse

import requests

from models import CleanData, MetricSource, OrgUnit, db, utc_now_second
from services.data_service import _navigate_path
from services.metric_catalog import (
    CLEAN_CATEGORY,
    CLEAN_SOURCE,
    DEFAULT_ORG_UNITS,
    DEMO_UNIT_METRICS,
    TABLE1_COLUMN_CODES,
    demo_metrics_map,
)


def join_base_path(base_url: str, path: str) -> str:
    b = (base_url or "").strip().rstrip("/")
    p = (path or "").strip() or "/"
    if not p.startswith("/"):
        p = "/" + p
    return b + p


def _finite_float(v):
    if v is None or isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        x = float(v)
        if math.isnan(x) or math.isinf(x):
            return None
        return x
    s = str(v).strip().replace("%", "").replace(",", "")
    if not s:
        return None
    try:
        x = float(s)
    except ValueError:
        m = re.match(r"^[-+]?\d+(?:\.\d+)?", s)
        if not m:
            return None
        x = float(m.group(0))
    if math.isnan(x) or math.isinf(x):
        return None
    return x


def _format_value(raw, fmt: str) -> tuple[str | None, float | None]:
    if raw is None:
        return None, None
    if isinstance(raw, (dict, list)):
        return None, None
    num = _finite_float(raw)
    fmt = (fmt or "raw").lower()
    if fmt == "int":
        if num is None:
            s = str(raw).strip()
            return (s or None), None
        if abs(num - round(num)) < 1e-9:
            return str(int(round(num))), float(int(round(num)))
        return str(raw).strip(), num
    if fmt == "percent":
        s = str(raw).strip()
        if not s:
            return None, None
        if "%" in s:
            return s, num
        if num is None:
            return s, None
        if abs(num - round(num, 2)) < 1e-9:
            t = f"{num:.2f}".rstrip("0").rstrip(".")
            return f"{t}%", num
        return f"{s}%", num
    s = str(raw).strip()
    return (s or None), num


def _first_number(obj, paths: list[str]):
    for p in paths or []:
        v = _navigate_path(obj, p) if p else obj
        if isinstance(v, (int, float)) and not isinstance(v, bool):
            return v
        if isinstance(v, str) and v.strip():
            if _finite_float(v) is not None:
                return v
        if isinstance(v, dict):
            for k in ("number", "value", "count", "total", "data"):
                if k in v and not isinstance(v.get(k), (dict, list)):
                    return v.get(k)
    if isinstance(obj, (int, float)) and not isinstance(obj, bool):
        return obj
    return None


def _as_list(node):
    if node is None:
        return []
    if isinstance(node, list):
        return node
    if isinstance(node, dict):
        return [node]
    return []


def _key_field_value(payload, rule: dict):
    key_field = rule.get("key_field") or "keyField"
    key_values = rule.get("key_values") or []
    if isinstance(key_values, str):
        key_values = [key_values]
    want = {str(x) for x in key_values if x is not None}
    value_path = (rule.get("value_path") or "number").strip()
    for lp in rule.get("list_paths") or ["data", ""]:
        node = payload if not lp else _navigate_path(payload, lp)
        for item in _as_list(node):
            if not isinstance(item, dict):
                continue
            kf = item.get(key_field)
            if kf is not None and str(kf) in want:
                if not value_path:
                    return item.get("number")
                return _navigate_path(item, value_path)
        if isinstance(node, dict) and not isinstance(node.get("keyField"), (dict, list)):
            # 单个对象
            kf = node.get(key_field)
            if kf is not None and str(kf) in want:
                return _navigate_path(node, value_path) if value_path else node.get("number")
    return None


def extract_metrics_from_payload(payload, rules: list) -> list[dict]:
    out = []
    for rule in rules or []:
        if not isinstance(rule, dict):
            continue
        key = (rule.get("key") or "").strip()
        if not key:
            continue
        kind = (rule.get("kind") or "path").strip()
        raw = None
        if kind == "key_field":
            raw = _key_field_value(payload, rule)
        elif kind == "first_number":
            raw = _first_number(payload, rule.get("json_paths") or [])
        else:
            for p in rule.get("json_paths") or []:
                raw = _navigate_path(payload, p)
                if raw is not None and raw != "":
                    break
        display, metric = _format_value(raw, rule.get("fmt") or "raw")
        if display is None:
            continue
        out.append({
            "key": key,
            "label": (rule.get("label") or key).strip(),
            "display": display,
            "metric_value": metric,
        })
    return out


def _http_json(method: str, url: str, timeout: int = 20):
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        raise ValueError(f"无效 URL：{url}")
    m = (method or "GET").upper().strip()
    resp = requests.request(m, url, timeout=timeout)
    resp.raise_for_status()
    try:
        return resp.json()
    except ValueError as e:
        raise ValueError(f"响应不是 JSON：{e}") from e


def _upsert_metric_row(unit: OrgUnit, metric: dict, collected_at: datetime, data_time: datetime) -> tuple:
    tag = f"{unit.code}:{metric['key']}"[:255]
    day_start = datetime.combine(data_time.date(), datetime.min.time())
    day_end = day_start + timedelta(days=1)
    title = f"{unit.name} · {metric['label']}"[:255]
    cd = (
        CleanData.query.filter(
            CleanData.tags == tag,
            CleanData.occur_time >= day_start,
            CleanData.occur_time < day_end,
        )
        .order_by(CleanData.id.desc())
        .first()
    )
    if cd:
        cd.source = CLEAN_SOURCE[:64]
        cd.category = CLEAN_CATEGORY[:64]
        cd.title = title
        cd.content = str(metric["display"])
        cd.metric_value = metric.get("metric_value")
        cd.occur_time = data_time
        cd.created_at = collected_at
        cd.endpoint_source = (unit.name or "")[:64]
        cd.endpoint_category = (metric.get("label") or "")[:64]
        return cd, True
    cd = CleanData(
        source=CLEAN_SOURCE[:64],
        category=CLEAN_CATEGORY[:64],
        title=title,
        content=str(metric["display"]),
        metric_value=metric.get("metric_value"),
        occur_time=data_time,
        tags=tag,
        endpoint_source=(unit.name or "")[:64],
        endpoint_category=(metric.get("label") or "")[:64],
        created_at=collected_at,
    )
    db.session.add(cd)
    return cd, False


def _add_derived_ratio(extracted: list[dict]) -> list[dict]:
    by_key = {m["key"]: m for m in extracted}
    online = by_key.get("online_counts")
    total = by_key.get("all_counts")
    if not online or not total:
        return extracted
    o = online.get("display") or ""
    a = total.get("display") or ""
    if not o or not a:
        return extracted
    extracted.append({
        "key": "node_ratio",
        "label": "在线节点/节点数",
        "display": f"{o}/{a}",
        "metric_value": online.get("metric_value"),
    })
    return extracted


def fetch_all_unit_metrics(occur_at=None, date_from=None, date_to=None) -> dict:
    """展示版：不访问基地 URL，按预置演示数据写入 CleanData。

    所选时间范围内每一天都写入一条，便于分析页按日画图。
    """
    from validators import parse_time_range

    start, end = parse_time_range(date_from or occur_at, date_to or occur_at)

    units = OrgUnit.query.order_by(OrgUnit.sort_order.asc(), OrgUnit.id.asc()).all()
    collected_at = utc_now_second()
    stored = 0
    updated = 0
    unit_results = []
    mmap = demo_metrics_map()
    occur_times = []

    days = []
    cur = start.date()
    last = end.date()
    while cur <= last:
        days.append(datetime(cur.year, cur.month, cur.day, 10, 0, 0))
        cur += timedelta(days=1)
    if not days:
        days = [start]

    for unit in units:
        item = {
            "id": unit.id,
            "code": unit.code,
            "name": unit.name,
            "base_url": unit.base_url or "",
            "ok": True,
            "demo": True,
            "metrics": [],
            "errors": [],
        }
        last_ot = None
        for data_time in days:
            day_str = data_time.strftime("%Y-%m-%d")
            src = mmap.get(unit.code) or mmap.get("hq") or {}
            by_key = {}
            for key, info in src.items():
                base = info.get("metric_value")
                val = _seeded_metric_value(base, day_str, unit.code, key)
                by_key[key] = {
                    "key": key,
                    "label": info.get("label") or key,
                    "display": _seeded_display(key, val, info.get("display") or ""),
                    "metric_value": val,
                }
            online = by_key.get("online_counts")
            total = by_key.get("all_counts")
            if online and total:
                clamped = _clamp_online(online.get("metric_value"), total.get("metric_value"))
                if clamped is not None:
                    online["metric_value"] = clamped
                    online["display"] = _seeded_display("online_counts", clamped)
            if "node_ratio" in by_key and online and total:
                o = online.get("metric_value")
                a = total.get("metric_value")
                by_key["node_ratio"]["display"] = f"{_fmt_int(o)}/{_fmt_int(a)}"
                by_key["node_ratio"]["metric_value"] = o
            last_ot = data_time
            for met in by_key.values():
                occur_times.append(data_time)
                _, was_upd = _upsert_metric_row(unit, met, collected_at, data_time)
                stored += 1
                if was_upd:
                    updated += 1
        for key, info in (mmap.get(unit.code) or mmap.get("hq") or {}).items():
            item["metrics"].append({
                "key": key,
                "label": info.get("label") or key,
                "display": info.get("display") or "",
                "metric_value": info.get("metric_value"),
                "source": "demo",
                "occur_time": last_ot.strftime("%Y-%m-%d %H:%M:%S") if last_ot else None,
                "days": len(days),
            })
        unit_results.append(item)

    db.session.commit()
    occur_times.sort()
    return {
        "stored": stored,
        "updated": updated,
        "demo": True,
        "date_from": start.strftime("%Y-%m-%d %H:%M:%S"),
        "date_to": end.strftime("%Y-%m-%d %H:%M:%S"),
        "occur_time": occur_times[0].strftime("%Y-%m-%d %H:%M:%S") if occur_times else None,
        "occur_time_to": occur_times[-1].strftime("%Y-%m-%d %H:%M:%S") if occur_times else None,
        "created_at": collected_at.strftime("%Y-%m-%d %H:%M:%S"),
        "units": unit_results,
        "fetched_at": collected_at.strftime("%Y-%m-%d %H:%M:%S"),
    }


def latest_metrics_map(days: int = 7) -> dict:
    """展示版始终返回预置指标，忽略入库结果与 days。"""
    return demo_metrics_map()


def metrics_for_llm(mmap: dict) -> dict:
    """单位中文名 → {指标中文: 展示值}，供大模型填空。"""
    units = OrgUnit.query.order_by(OrgUnit.sort_order.asc()).all()
    packed = {}
    for u in units:
        inner = {}
        for key, info in (mmap.get(u.code) or {}).items():
            label = info.get("label") or key
            inner[label] = info.get("display") or ""
        packed[u.name] = inner
    return packed


ANALYSIS_UNIT_CODES = [c for c in TABLE1_COLUMN_CODES if c]
ANALYSIS_UNIT_SHORT = {
    "hq": "本级",
    "east": "东部",
    "south": "南部",
    "west": "西部",
    "north": "北部",
    "center": "中部",
}
RATE_METRIC_KEYS = [
    ("node_online_rate", "节点在线率"),
    ("equipment_ok_rate", "设备完好率"),
    ("js_resource_pct", "计算资源使用率"),
    ("storage_resource_pct", "存储空间使用率"),
]
VOLUME_METRIC_KEYS = [
    ("access_network_user", "入网用户"),
    ("data_service_volume", "数据服务量"),
    ("doc_interaction", "文档交互量"),
]


def _finite_or_none(v):
    x = _finite_float(v)
    return x


PERCENT_METRIC_KEYS = {
    "node_online_rate",
    "equipment_ok_rate",
    "js_resource_pct",
    "storage_resource_pct",
}


def _demo_base(code: str, key: str):
    item = (DEMO_UNIT_METRICS.get(code) or DEMO_UNIT_METRICS.get("hq") or {}).get(key) or {}
    return _finite_or_none(item.get("metric_value"))


def _day_unit_rand(day: str, unit: str, key: str) -> float:
    """同一天 + 单位 + 指标 → 固定 0～1，刷新不变。"""
    raw = f"zhxx-metric|{day}|{unit}|{key}".encode("utf-8")
    n = int.from_bytes(hashlib.sha256(raw).digest()[:8], "big")
    return n / 18446744073709551615.0


def _seeded_metric_value(base, day: str, unit: str, key: str):
    """缺日用日期种子在预置值附近抖动；百分率限制在 0～100。"""
    if base is None:
        return None
    factor = 0.90 + _day_unit_rand(str(day), unit, key) * 0.20
    val = float(base) * factor
    if key in PERCENT_METRIC_KEYS:
        return max(0.0, min(100.0, round(val, 2)))
    return max(0.0, float(int(round(val))))


def _seeded_display(key: str, val, orig: str = "") -> str:
    if val is None:
        return orig or ""
    if key in PERCENT_METRIC_KEYS:
        t = f"{float(val):.2f}".rstrip("0").rstrip(".")
        return f"{t}%"
    return str(int(round(float(val))))


def _is_placeholder_value(actual, base) -> bool:
    """无入库，或仍是预置原值（按日复制的相同数），视为缺数。"""
    if actual is None:
        return True
    if base is None:
        return False
    try:
        return abs(float(actual) - float(base)) < 1e-6
    except (TypeError, ValueError):
        return False


def _clamp_online(online, total):
    if online is None or total is None:
        return online
    if total >= 0 and online > total:
        return total
    return online


def _fmt_pct(v) -> str:
    if v is None:
        return "—"
    t = f"{float(v):.2f}".rstrip("0").rstrip(".")
    return f"{t}%"


def _fmt_int(v) -> str:
    if v is None:
        return "—"
    return str(int(round(float(v))))


def _unit_names() -> dict:
    names = {u["code"]: u["name"] for u in DEFAULT_ORG_UNITS}
    try:
        for u in OrgUnit.query.all():
            if u.code:
                names[u.code] = u.name or names.get(u.code, u.code)
    except Exception:
        pass
    return names


def _parse_metric_tag(tag: str):
    raw = (tag or "").strip()
    if ":" not in raw:
        return None, None
    code, key = raw.split(":", 1)
    code, key = code.strip(), key.strip()
    if not code or not key:
        return None, None
    return code, key


def _mean(vals):
    known = [v for v in vals if v is not None]
    if not known:
        return None
    return sum(known) / len(known)


def _sum_known(vals):
    known = [v for v in vals if v is not None]
    if not known:
        return None
    return sum(known)


def _weighted_mean(values, weights):
    num = den = 0.0
    has = False
    for v, w in zip(values, weights):
        if v is None:
            continue
        wt = w if w is not None and w > 0 else 1.0
        num += v * wt
        den += wt
        has = True
    if not has or den <= 0:
        return None
    return num / den


def theater_situation(date_from, date_to) -> dict:
    """六单位运行态势：按数据对应时间筛选战区入库，缺数时用预置指标兜底。"""
    from validators import parse_time_range

    start, end = parse_time_range(date_from, date_to)
    names = _unit_names()
    org_rows = OrgUnit.query.order_by(OrgUnit.sort_order.asc(), OrgUnit.id.asc()).all()
    unit_codes = [u.code for u in org_rows if u.code] or list(ANALYSIS_UNIT_CODES)
    units = [
        {
            "code": u.code,
            "name": u.name or names.get(u.code, u.code),
            "short": ANALYSIS_UNIT_SHORT.get(u.code) or u.name or names.get(u.code, u.code),
        }
        for u in org_rows
        if u.code
    ]
    if not units:
        units = [
            {
                "code": c,
                "name": names.get(c, c),
                "short": ANALYSIS_UNIT_SHORT.get(c) or names.get(c, c),
            }
            for c in unit_codes
        ]
    allowed = set(unit_codes)

    rows = CleanData.query.filter(
        CleanData.source == CLEAN_SOURCE,
        CleanData.occur_time.isnot(None),
        CleanData.occur_time >= start,
        CleanData.occur_time <= end,
    ).all()

    latest = {}
    daily = {}
    for r in rows:
        code, key = _parse_metric_tag(r.tags)
        if code not in allowed or not key:
            continue
        ot = r.occur_time
        rid = r.id or 0
        val = _finite_or_none(r.metric_value)
        disp = (r.content or "").strip()
        prev = latest.get((code, key))
        if prev is None or (ot, rid) > (prev[0], prev[1]):
            latest[(code, key)] = (ot, rid, val, disp)
        day = ot.strftime("%Y-%m-%d")
        dprev = daily.get((day, code, key))
        if dprev is None or (ot, rid) > (dprev[0], dprev[1]):
            daily[(day, code, key)] = (ot, rid, val)

    from_demo = not latest
    snapshot = {c: {} for c in unit_codes}
    if from_demo:
        mmap = demo_metrics_map()
        for code in unit_codes:
            src = mmap.get(code) or mmap.get("hq") or {}
            for key, info in src.items():
                snapshot[code][key] = {
                    "value": _finite_or_none(info.get("metric_value")),
                    "display": info.get("display") or "",
                }
    else:
        for (code, key), (_ot, _rid, val, disp) in latest.items():
            snapshot[code][key] = {"value": val, "display": disp}

    def num(code, key):
        item = (snapshot.get(code) or {}).get(key) or {}
        return _finite_or_none(item.get("value"))

    dates = []
    cur = start.date()
    last = end.date()
    while cur <= last:
        dates.append(cur.strftime("%Y-%m-%d"))
        cur += timedelta(days=1)

    def daily_val(day, code, key):
        item = daily.get((day, code, key))
        return item[2] if item else None

    DAILY_KEYS = (
        [k for k, _ in RATE_METRIC_KEYS]
        + [k for k, _ in VOLUME_METRIC_KEYS]
        + ["online_counts", "all_counts"]
    )

    def unit_series(code, key):
        base = _demo_base(code, key)
        if base is None:
            base = num(code, key)
        out = []
        for day in dates:
            actual = daily_val(day, code, key)
            if _is_placeholder_value(actual, base):
                out.append(_seeded_metric_value(base, day, code, key))
            else:
                out.append(actual)
        return out

    daily_by_unit = {}
    for u in units:
        daily_by_unit[u["code"]] = {k: unit_series(u["code"], k) for k in DAILY_KEYS}
        ons = daily_by_unit[u["code"]].get("online_counts") or []
        als = daily_by_unit[u["code"]].get("all_counts") or []
        for i in range(min(len(ons), len(als))):
            ons[i] = _clamp_online(ons[i], als[i])

    def day_vals(key):
        return [
            [daily_by_unit[c][key][i] for c in unit_codes]
            for i in range(len(dates))
        ]

    def day_weighted(rate_key, weight_key):
        out = []
        rates = day_vals(rate_key)
        weights = day_vals(weight_key)
        for r, w in zip(rates, weights):
            out.append(_weighted_mean(r, w))
        return out

    def day_mean(key):
        return [_mean(vs) for vs in day_vals(key)]

    def day_sum(key):
        return [_sum_known(vs) for vs in day_vals(key)]

    daily_all = {
        "node_online_rate": day_weighted("node_online_rate", "all_counts"),
        "equipment_ok_rate": day_mean("equipment_ok_rate"),
        "js_resource_pct": day_mean("js_resource_pct"),
        "storage_resource_pct": day_mean("storage_resource_pct"),
        "access_network_user": day_sum("access_network_user"),
        "data_service_volume": day_sum("data_service_volume"),
        "doc_interaction": day_sum("doc_interaction"),
        "online_counts": day_sum("online_counts"),
        "all_counts": day_sum("all_counts"),
    }

    trend_dates = dates
    kpi_sparks = {
        "node_online_rate": daily_all["node_online_rate"],
        "equipment_ok_rate": daily_all["equipment_ok_rate"],
        "access_network_user": daily_all["access_network_user"],
        "node_ratio": daily_all["online_counts"],
    }

    def _last(arr):
        return arr[-1] if arr else None

    latest = {}
    for code in unit_codes:
        latest[code] = {k: _last(daily_by_unit[code].get(k) or []) for k in DAILY_KEYS}

    node_rate = _last(daily_all["node_online_rate"])
    eq_avg = _last(daily_all["equipment_ok_rate"])
    user_sum = _last(daily_all["access_network_user"])
    online_sum = _last(daily_all["online_counts"])
    total_sum = _last(daily_all["all_counts"])

    ratio_disp = "—"
    if online_sum is not None or total_sum is not None:
        ratio_disp = f"{_fmt_int(online_sum)}/{_fmt_int(total_sum)}"

    return {
        "date_from": start.strftime("%Y-%m-%d %H:%M:%S"),
        "date_to": end.strftime("%Y-%m-%d %H:%M:%S"),
        "from_demo": from_demo,
        "units": units,
        "latest": latest,
        "daily": {"dates": trend_dates, "by_unit": daily_by_unit, "all": daily_all},
        "rate_keys": [{"key": k, "label": lab} for k, lab in RATE_METRIC_KEYS],
        "volume_keys": [{"key": k, "label": lab} for k, lab in VOLUME_METRIC_KEYS],
        "kpis": {
            "node_online_rate": {
                "display": _fmt_pct(node_rate),
                "value": node_rate,
                "unit": "%",
                "spark": kpi_sparks["node_online_rate"],
            },
            "equipment_ok_rate": {
                "display": _fmt_pct(eq_avg),
                "value": eq_avg,
                "unit": "%",
                "spark": kpi_sparks["equipment_ok_rate"],
            },
            "access_network_user": {
                "display": _fmt_int(user_sum),
                "value": user_sum,
                "unit": "",
                "spark": kpi_sparks["access_network_user"],
            },
            "node_ratio": {
                "display": ratio_disp,
                "value": online_sum,
                "unit": "",
                "spark": kpi_sparks["node_ratio"],
            },
        },
    }
