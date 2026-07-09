"""多源数据采集与管理 路由"""
import json
from datetime import datetime, timedelta

import requests
from flask import Blueprint, jsonify, request
from sqlalchemy import func
from sqlalchemy.exc import SQLAlchemyError

from models import CollectEndpoint, CleanData, CollectTaggedValue, db, utc_now_second
from services import data_service
from services.log_service import log_op
from validators import (
    ValidationError,
    L_EP_BODY,
    L_EP_FIELD_MAP_JSON,
    L_EP_HEADERS_JSON,
    L_EP_NAME,
    optional_str,
    optional_text,
    require_http_method,
    require_json_object_text,
    require_str,
    require_url,
    validate_clean_payload,
    validate_tagged_create,
    validate_tagged_update,
)

bp = Blueprint("data_collection", __name__, url_prefix="/api/data")


def _navigate_path(obj, path: str):
    if obj is None or path is None:
        return None
    cur = obj
    for part in str(path).split("."):
        key = part.strip()
        if not key:
            continue
        if isinstance(cur, dict):
            cur = cur.get(key)
        elif isinstance(cur, list) and key.isdigit():
            idx = int(key)
            cur = cur[idx] if 0 <= idx < len(cur) else None
        else:
            return None
    return cur


def _find_value_path(obj, target):
    """在 JSON 对象中查找与 target 相等的首个路径。"""
    tgt = str(target).strip()
    if tgt == "":
        return None

    def eq(v):
        if v is None:
            return False
        return str(v).strip() == tgt

    def walk(node, path_prefix=""):
        if isinstance(node, dict):
            for k, v in node.items():
                p = f"{path_prefix}.{k}" if path_prefix else str(k)
                if isinstance(v, (dict, list)):
                    hit = walk(v, p)
                    if hit:
                        return hit
                elif eq(v):
                    return p
        elif isinstance(node, list):
            for i, v in enumerate(node):
                p = f"{path_prefix}.{i}" if path_prefix else str(i)
                if isinstance(v, (dict, list)):
                    hit = walk(v, p)
                    if hit:
                        return hit
                elif eq(v):
                    return p
        return None

    return walk(obj, "")


def _next_collect_sort_order():
    """新建配置时排在末尾：当前最大 sort_order + 1。"""
    mx = db.session.query(func.max(CollectEndpoint.sort_order)).scalar()
    return (mx or 0) + 1


def _headers_to_store(raw):
    if raw is None:
        return None
    if isinstance(raw, dict):
        return json.dumps(raw, ensure_ascii=False)
    if isinstance(raw, str):
        s = raw.strip()
        if not s:
            return None
        json.loads(s)
        return s
    raise ValueError("请求头须为 JSON 对象或合法 JSON 字符串")


def _field_map_to_store(raw):
    """字段映射存库：合法 JSON 对象字符串；空则 None。"""
    if raw is None:
        return None
    if isinstance(raw, dict):
        if not raw:
            return None
        return json.dumps(raw, ensure_ascii=False)
    if isinstance(raw, str):
        s = raw.strip()
        if not s:
            return None
        json.loads(s)
        return s
    raise ValueError("字段映射须为 JSON 对象或合法 JSON 字符串")


_RAW_PREVIEW_ROWS = 200
_RAW_PREVIEW_CONTENT = 1200


def _preview_raw_rows(rows: list[dict]):
    """返回前端展示的原始数据预览（限制条数与正文长度）。"""
    if not rows:
        return [], False
    truncated = len(rows) > _RAW_PREVIEW_ROWS
    out = []
    for row in rows[:_RAW_PREVIEW_ROWS]:
        r = dict(row)
        c = r.get("content")
        if isinstance(c, str) and len(c) > _RAW_PREVIEW_CONTENT:
            r["content"] = c[:_RAW_PREVIEW_CONTENT] + "…"
        ir = r.get("item_raw_json")
        if isinstance(ir, str) and len(ir) > 16000:
            r["item_raw_json"] = ir[:16000] + "…"
        out.append(r)
    return out, truncated


@bp.route("/endpoints", methods=["GET"])
def list_endpoints():
    q = CollectEndpoint.query.order_by(
        CollectEndpoint.sort_order.asc(),
        CollectEndpoint.id.asc(),
    )
    return jsonify({"code": 0, "data": [e.to_dict() for e in q.all()]})


@bp.route("/endpoints", methods=["POST"])
def create_endpoint():
    data = request.get_json(silent=True) or {}
    try:
        name = require_str(data.get("name"), "配置名称", min_len=1, max_len=L_EP_NAME)
        url = require_url(data.get("url"))
        method = require_http_method(data.get("method") or "GET")
        optional_str(data.get("source"), "默认来源", max_len=64)
        optional_str(data.get("category"), "默认类别", max_len=64)
        optional_str(data.get("list_path"), "列表路径", max_len=512)
        if data.get("headers") is not None:
            require_json_object_text(data.get("headers"), "请求头", max_len=L_EP_HEADERS_JSON)
        body_raw = data.get("body")
        if isinstance(body_raw, str):
            body_raw = body_raw.strip() or None
        if body_raw is not None:
            optional_text(body_raw, "请求体", max_len=L_EP_BODY)
        if data.get("field_map") is not None:
            require_json_object_text(data.get("field_map"), "字段映射", max_len=L_EP_FIELD_MAP_JSON)
        ep = CollectEndpoint(
            name=name,
            method=method,
            url=url,
            headers_json=_headers_to_store(data.get("headers")),
            body=body_raw,
            source_label=optional_str(data.get("source"), "默认来源", max_len=64),
            category_label=optional_str(data.get("category"), "默认类别", max_len=64),
            list_path=optional_str(data.get("list_path"), "列表路径", max_len=512),
            field_map_json=_field_map_to_store(data.get("field_map")),
            sort_order=_next_collect_sort_order(),
        )
        db.session.add(ep)
        db.session.commit()
        log_op("数据采集", "新增采集配置", f"{name} id={ep.id}")
        return jsonify({"code": 0, "msg": "已保存", "data": ep.to_dict()})
    except (ValueError, ValidationError) as e:
        return jsonify({"code": 1, "msg": str(e)}), 400
    except Exception as e:
        db.session.rollback()
        return jsonify({"code": 1, "msg": str(e)}), 500


@bp.route("/endpoints/<int:eid>", methods=["PUT"])
def update_endpoint(eid):
    data = request.get_json(silent=True) or {}
    ep = CollectEndpoint.query.get(eid)
    if not ep:
        return jsonify({"code": 1, "msg": "配置不存在"}), 404
    try:
        if "name" in data:
            ep.name = require_str(data.get("name"), "配置名称", min_len=1, max_len=L_EP_NAME)
        if "url" in data:
            ep.url = require_url(data.get("url"))
        if "method" in data:
            ep.method = require_http_method(data.get("method"))
        if "headers" in data:
            if data.get("headers") is not None:
                require_json_object_text(data.get("headers"), "请求头", max_len=L_EP_HEADERS_JSON)
            ep.headers_json = _headers_to_store(data.get("headers"))
        if "body" in data:
            br = data.get("body")
            if br is None or br == "":
                ep.body = None
            elif isinstance(br, str):
                ep.body = optional_text(br.strip() or "", "请求体", max_len=L_EP_BODY) or None
            else:
                ep.body = optional_text(str(br), "请求体", max_len=L_EP_BODY)
        if "source" in data:
            ep.source_label = optional_str(data.get("source"), "默认来源", max_len=64)
        if "category" in data:
            ep.category_label = optional_str(data.get("category"), "默认类别", max_len=64)
        if "list_path" in data:
            ep.list_path = optional_str(data.get("list_path"), "列表路径", max_len=512)
        if "field_map" in data:
            if data.get("field_map") is not None:
                require_json_object_text(data.get("field_map"), "字段映射", max_len=L_EP_FIELD_MAP_JSON)
            ep.field_map_json = _field_map_to_store(data.get("field_map"))
        db.session.commit()
        log_op("数据采集", "修改采集配置", f"id={eid} {ep.name}")
        return jsonify({"code": 0, "msg": "已更新", "data": ep.to_dict()})
    except (ValueError, ValidationError) as e:
        return jsonify({"code": 1, "msg": str(e)}), 400
    except Exception as e:
        db.session.rollback()
        return jsonify({"code": 1, "msg": str(e)}), 500


@bp.route("/endpoints/<int:eid>", methods=["DELETE"])
def delete_endpoint(eid):
    ep = CollectEndpoint.query.get(eid)
    if not ep:
        return jsonify({"code": 1, "msg": "配置不存在"}), 404
    name = ep.name
    db.session.delete(ep)
    db.session.commit()
    log_op("数据采集", "删除采集配置", f"id={eid} {name}")
    return jsonify({"code": 0, "msg": "已删除"})


@bp.route("/extract", methods=["POST"])
def extract():
    """数据提取：endpoint_id / all_endpoints / 或请求体中的 url。"""
    data = request.get_json(silent=True) or {}
    url_inline = (data.get("url") or "").strip()
    try:
        if data.get("all_endpoints"):
            eps = CollectEndpoint.query.order_by(
                CollectEndpoint.sort_order.asc(),
                CollectEndpoint.id.asc(),
            ).all()
            if not eps:
                raise ValueError("暂无采集配置，请先新增远程采集条目")
            total = 0
            errs = []
            accum_raw: list[dict] = []
            http_parts: list[dict] = []
            for ep in eps:
                if not ep.url or not ep.url.strip():
                    errs.append(f"{ep.name}: URL 为空")
                    continue
                try:
                    kw = data_service.kw_from_collect_endpoint(ep)
                    n, raw_items, http_meta = data_service.extract_from_http(**kw)
                    total += n
                    # 为每条记录附加 endpoint 信息，便于前端暂存标签时回填来源
                    for r in raw_items:
                        if isinstance(r, dict):
                            r["endpoint_id"] = ep.id
                            r["endpoint_name"] = ep.name
                            r["endpoint_method"] = ep.method or "GET"
                    accum_raw.extend(raw_items)
                    if http_meta:
                        http_parts.append({"endpoint_name": ep.name, **http_meta})
                    log_op("数据采集", "URL采集(批量)", f"{ep.name} → {n}条")
                except Exception as ex:
                    errs.append(f"{ep.name}: {ex}")
            if total == 0 and errs:
                raise ValueError(
                    "批量采集失败：" + "；".join(errs[:5]) + ("…" if len(errs) > 5 else "")
                )
            preview_rows, trunc = _preview_raw_rows(accum_raw)
            msg = (
                "解析完成（仅预览，未入库）"
                if not errs
                else f"共解析 {total} 条（仅预览），部分失败"
            )
            payload = {
                "added": total,
                "errors": errs,
                "raw_items": preview_rows,
                "raw_truncated": trunc,
            }
            if http_parts:
                payload["http_responses"] = http_parts
            return jsonify({"code": 0, "msg": msg, "data": payload})

        ep_id = data.get("endpoint_id")
        if ep_id is not None:
            ep = CollectEndpoint.query.get(int(ep_id))
            if not ep:
                return jsonify({"code": 1, "msg": "采集配置不存在"}), 404
            kw = data_service.kw_from_collect_endpoint(ep)
            added, raw_items, http_meta = data_service.extract_from_http(**kw)
            for r in raw_items:
                if isinstance(r, dict):
                    r["endpoint_id"] = ep.id
                    r["endpoint_name"] = ep.name
                    r["endpoint_method"] = ep.method or "GET"
            preview_rows, trunc = _preview_raw_rows(raw_items)
            log_op("数据采集", "URL采集", f"[{ep.name}] {kw['method']} {ep.url[:120]}… → {added}条")
            payload = {
                "added": added,
                "errors": [],
                "raw_items": preview_rows,
                "raw_truncated": trunc,
            }
            if http_meta:
                payload["http_response"] = http_meta
            return jsonify({"code": 0, "msg": "解析完成（仅预览，未入库）", "data": payload})

        if url_inline:
            fm_inline = data.get("field_map")
            if isinstance(fm_inline, str) and fm_inline.strip():
                try:
                    fm_inline = json.loads(fm_inline)
                except json.JSONDecodeError:
                    raise ValueError("field_map 须为合法 JSON 对象")
            elif fm_inline is not None and not isinstance(fm_inline, dict):
                raise ValueError("field_map 须为 JSON 对象")
            added, raw_items, http_meta = data_service.extract_from_http(
                method=data.get("method") or "GET",
                url=url_inline,
                headers=data.get("headers"),
                body=data.get("body"),
                source_label=(data.get("source") or "").strip() or None,
                category_label=(data.get("category") or "").strip() or None,
                list_path=(data.get("list_path") or "").strip() or None,
                field_map=fm_inline if isinstance(fm_inline, dict) else None,
            )
            for r in raw_items:
                if isinstance(r, dict):
                    r["endpoint_id"] = None
                    r["endpoint_name"] = "(临时URL)"
                    r["endpoint_method"] = (data.get("method") or "GET").upper()
            log_op("数据采集", "URL采集", f"{data.get('method','GET')} {url_inline[:120]}… → {added}条")
        else:
            raise ValueError(
                "请指定采集方式：endpoint_id、all_endpoints，或为请求体提供 url"
            )
        preview_rows, trunc = _preview_raw_rows(raw_items)
        payload = {
            "added": added,
            "errors": [],
            "raw_items": preview_rows,
            "raw_truncated": trunc,
        }
        if http_meta:
            payload["http_response"] = http_meta
        return jsonify({"code": 0, "msg": "解析完成（仅预览，未入库）", "data": payload})
    except ValueError as e:
        log_op("数据采集", "数据提取", str(e), success=False)
        return jsonify({"code": 1, "msg": str(e)}), 400
    except requests.exceptions.RequestException as e:
        log_op("数据采集", "数据提取", str(e), success=False)
        return jsonify({"code": 1, "msg": f"HTTP 请求失败: {e}"}), 502
    except SQLAlchemyError as e:
        db.session.rollback()
        log_op("数据采集", "数据提取", str(e), success=False)
        return jsonify({"code": 1, "msg": f"数据库错误: {e}"}), 500
    except Exception as e:
        db.session.rollback()
        log_op("数据采集", "数据提取", str(e), success=False)
        return jsonify({"code": 1, "msg": f"提取失败: {e}"}), 500


@bp.route("/clean", methods=["GET"])
def list_clean():
    page = int(request.args.get("page", 1))
    size = int(request.args.get("size", 20))
    q = CleanData.query.order_by(CleanData.id.desc())
    total = q.count()
    items = q.offset((page - 1) * size).limit(size).all()
    return jsonify({"code": 0, "data": {"total": total, "items": [r.to_dict() for r in items]}})


@bp.route("/clean/by-day", methods=["GET"])
def list_clean_by_day():
    """按 occur_time（无 occur_time 则取 created_at）日期聚合 CleanData，每天 1 个分组。

    每条 item 额外带：
      - endpoint_source   : 通过名字回查 endpoint.source_label
      - endpoint_category : endpoint.category_label
    分组维度：endpoints / endpoint_sources / endpoint_categories / categories（CleanData.category）。
    """
    days_raw = request.args.get("days")
    q = CleanData.query.order_by(
        CleanData.occur_time.desc().nullslast(), CleanData.id.desc()
    )
    days = None
    if days_raw is not None and str(days_raw).strip() not in ("", "all"):
        try:
            days = max(1, min(365, int(days_raw)))
        except (TypeError, ValueError):
            days = 30
        cutoff = utc_now_second() - timedelta(days=days)
        q = q.filter((CleanData.occur_time >= cutoff) | (CleanData.created_at >= cutoff))
    rows = q.all()
    ep_by_name: dict = {ep.name: (ep.source_label, ep.category_label) for ep in CollectEndpoint.query.all()}

    groups: dict = {}
    for r in rows:
        ts = r.occur_time or r.created_at
        if not ts:
            continue
        k = ts.strftime("%Y-%m-%d")
        d = r.to_dict()
        # 手填的 endpoint_source / endpoint_category 优先；为空则按 source 反查 endpoint
        if not d.get("endpoint_source") or not d.get("endpoint_category"):
            src_lbl, cat_lbl = ep_by_name.get(d.get("source") or "", (None, None))
            if not d.get("endpoint_source"):
                d["endpoint_source"] = src_lbl or ""
            if not d.get("endpoint_category"):
                d["endpoint_category"] = cat_lbl or ""
        groups.setdefault(k, []).append(d)

    out = []
    for k in sorted(groups.keys(), reverse=True):
        items = groups[k]
        endpoints = sorted({(i.get("source") or "—") for i in items})
        endpoint_sources = sorted({(i.get("endpoint_source") or "—") for i in items if i.get("endpoint_source")})
        endpoint_categories = sorted({(i.get("endpoint_category") or "—") for i in items if i.get("endpoint_category")})
        categories = sorted({(i.get("category") or "—") for i in items})
        out.append({
            "date": k,
            "count": len(items),
            "endpoints": endpoints,
            "sources": endpoints,
            "endpoint_sources": endpoint_sources,
            "endpoint_categories": endpoint_categories,
            "categories": categories,
            "items": items,
        })
    return jsonify({
        "code": 0,
        "data": {
            "groups": out,
            "total": sum(g["count"] for g in out),
            "days": days,
            "all": days is None,
        }
    })


@bp.route("/clean", methods=["POST"])
def create_clean():
    data = request.get_json(silent=True) or {}
    try:
        v = validate_clean_payload(data)
        tags = v.get("tags")
        content = v.get("content") or ""
        cd = CleanData(
            source=v.get("source"),
            category=v.get("category"),
            title=(tags or "手工新增")[:255],
            content=content,
            metric_value=_coerce_metric(data.get("metric_value", content)),
            occur_time=utc_now_second(),
            tags=tags,
            endpoint_source=v.get("endpoint_source"),
            endpoint_category=v.get("endpoint_category"),
            created_at=utc_now_second(),
        )
        db.session.add(cd)
        db.session.commit()
        return jsonify({"code": 0, "msg": "已新增", "data": cd.to_dict()})
    except (ValueError, ValidationError) as e:
        db.session.rollback()
        return jsonify({"code": 1, "msg": str(e)}), 400
    except Exception as e:
        db.session.rollback()
        return jsonify({"code": 1, "msg": f"新增失败: {e}"}), 500


@bp.route("/clear", methods=["POST"])
def clear():
    """清空已入库业务数据（CleanData）"""
    CleanData.query.delete()
    db.session.commit()
    log_op("数据采集", "清空数据", "已清空已入库数据（CleanData）")
    return jsonify({"code": 0, "msg": "已清空"})


@bp.route("/clean/<int:cid>", methods=["DELETE"])
def delete_clean(cid: int):
    rec = CleanData.query.get(cid)
    if not rec:
        return jsonify({"code": 1, "msg": "记录不存在"}), 404
    db.session.delete(rec)
    db.session.commit()
    return jsonify({"code": 0, "msg": "已删除"})


@bp.route("/clean/by-day/<date>", methods=["DELETE"])
def delete_clean_by_day(date: str):
    """按日期（YYYY-MM-DD）删除所有 occur_time 在该天的 CleanData 行。"""
    try:
        day = datetime.strptime(date, "%Y-%m-%d").date()
    except ValueError:
        return jsonify({"code": 1, "msg": "日期格式应为 YYYY-MM-DD"}), 400
    day_start = datetime.combine(day, datetime.min.time())
    day_end = day_start + timedelta(days=1)
    n = (
        CleanData.query
        .filter(CleanData.occur_time >= day_start, CleanData.occur_time < day_end)
        .delete(synchronize_session=False)
    )
    db.session.commit()
    log_op("数据采集", "按天清除已入库", f"{date} 共 {n} 条")
    return jsonify({"code": 0, "msg": f"已删除 {n} 条", "data": {"deleted": n, "date": date}})


@bp.route("/clean/<int:cid>", methods=["PUT"])
def update_clean(cid: int):
    rec = CleanData.query.get(cid)
    if not rec:
        return jsonify({"code": 1, "msg": "记录不存在"}), 404
    data = request.get_json(silent=True) or {}
    try:
        v = validate_clean_payload(data, for_update=True)
        if "source" in v:
            rec.source = v["source"]
        if "category" in v:
            rec.category = v["category"]
        if "tags" in v:
            rec.tags = v["tags"]
        if "content" in v:
            rec.content = v["content"]
        if "endpoint_source" in v:
            rec.endpoint_source = v["endpoint_source"]
        if "endpoint_category" in v:
            rec.endpoint_category = v["endpoint_category"]
        db.session.commit()
        return jsonify({"code": 0, "msg": "已更新", "data": rec.to_dict()})
    except (ValueError, ValidationError) as e:
        db.session.rollback()
        return jsonify({"code": 1, "msg": str(e)}), 400
    except Exception as e:
        db.session.rollback()
        return jsonify({"code": 1, "msg": f"更新失败: {e}"}), 500


@bp.route("/tagged", methods=["GET"])
def list_tagged():
    size = max(1, min(200, int(request.args.get("size", 50))))
    rows = CollectTaggedValue.query.order_by(CollectTaggedValue.id.desc()).limit(size).all()
    ep_ids = {r.endpoint_id for r in rows if r.endpoint_id is not None}
    ep_map: dict = {}
    if ep_ids:
        for ep in CollectEndpoint.query.filter(CollectEndpoint.id.in_(ep_ids)).all():
            ep_map[ep.id] = (ep.source_label, ep.category_label)
    items = []
    for r in rows:
        d = r.to_dict()
        src, cat = ep_map.get(r.endpoint_id, (None, None))
        d["source"] = src or ""
        d["category"] = cat or ""
        items.append(d)
    return jsonify({"code": 0, "data": {"items": items}})


@bp.route("/tagged", methods=["POST"])
def create_tagged():
    data = request.get_json(silent=True) or {}
    try:
        v = validate_tagged_create(data)
        tag = v["tag"]
        val = v["value"]
        rec = CollectTaggedValue(
            endpoint_id=data.get("endpoint_id"),
            endpoint_name=v.get("endpoint_name"),
            tag=tag,
            value=val,
            value_path=(data.get("value_path") or "")[:512] or None,
            source_excerpt=(data.get("source_excerpt") or "")[:16000] or None,
            status="pending",
        )
        if not rec.value_path and rec.source_excerpt:
            try:
                js = json.loads(rec.source_excerpt)
                rec.value_path = (_find_value_path(js, rec.value) or "")[:512] or None
            except Exception:
                rec.value_path = None
        db.session.add(rec)
        db.session.commit()
        log_op("数据采集", "标签暂存", f"{tag} id={rec.id}")
        return jsonify({"code": 0, "msg": "已暂存", "data": rec.to_dict()})
    except (ValueError, ValidationError) as e:
        return jsonify({"code": 1, "msg": str(e)}), 400
    except Exception as e:
        db.session.rollback()
        return jsonify({"code": 1, "msg": f"暂存失败: {e}"}), 500


def _coerce_metric(v):
    """从标签 value 中尽量解析出一个 float 作为 metric_value。
    - 纯数字字符串："37.5" → 37.5
    - 末尾带单位："37.5℃" / "1024 m3" → 37.5 / 1024.0
    解析不出来就返回 None，让后端 metric_value 保持 NULL。
    """
    if v is None:
        return None
    if isinstance(v, (int, float)):
        try:
            f = float(v)
            return f if f == f else None  # 过滤 NaN
        except Exception:
            return None
    s = str(v).strip()
    if not s:
        return None
    try:
        return float(s)
    except ValueError:
        import re
        m = re.match(r"^[-+]?\d+(?:\.\d+)?", s)
        if not m:
            return None
        try:
            return float(m.group(0))
        except ValueError:
            return None


def _upsert_clean_for_tagged(rec: CollectTaggedValue, now):
    """以 (occur_time 当天, tags) 为唯一键 upsert 到 CleanData。

    - 已存在同日同标签 → 覆盖 source / content / category / occur_time
    - 不存在 → 新增
    返回 (CleanData 实例, 是否覆盖)。
    """
    day_start = datetime.combine(now.date(), datetime.min.time())
    day_end = day_start + timedelta(days=1)
    tag_key = (rec.tag or "")[:255]
    src = (rec.endpoint_name or (f"endpoint#{rec.endpoint_id}" if rec.endpoint_id else "远程采集"))[:64]

    cd = (
        CleanData.query
        .filter(
            CleanData.tags == tag_key,
            CleanData.occur_time >= day_start,
            CleanData.occur_time < day_end,
        )
        .order_by(CleanData.id.desc())
        .first()
    )
    metric = _coerce_metric(rec.value)
    if cd:
        cd.source = src
        cd.category = "标签入库"
        cd.title = tag_key
        cd.content = rec.value
        cd.metric_value = metric
        cd.occur_time = now
        return cd, True

    cd = CleanData(
        source=src,
        category="标签入库",
        title=tag_key,
        content=rec.value,
        metric_value=metric,
        occur_time=now,
        tags=tag_key,
        created_at=now,
    )
    db.session.add(cd)
    return cd, False


@bp.route("/tagged/<int:tid>/store", methods=["POST"])
def store_tagged(tid: int):
    rec = CollectTaggedValue.query.get(tid)
    if not rec:
        return jsonify({"code": 1, "msg": "记录不存在"}), 404
    try:
        now = utc_now_second()
        cd, updated = _upsert_clean_for_tagged(rec, now)
        rec_id = rec.id
        db.session.delete(rec)
        db.session.commit()
        log_op("数据采集", "标签入库", f"id={rec_id} -> clean_data id={cd.id} ({'覆盖' if updated else '新增'})")
        return jsonify({
            "code": 0,
            "msg": "已入库（同日同标签已覆盖）" if updated else "已入库",
            "data": {"clean_id": cd.id, "removed_id": rec_id, "updated": updated},
        })
    except Exception as e:
        db.session.rollback()
        return jsonify({"code": 1, "msg": f"入库失败: {e}"}), 500


@bp.route("/tagged/store_all", methods=["POST"])
def store_tagged_all():
    """一键入库：(同日 + 同标签) upsert 到 CleanData，并从暂存表移除。"""
    try:
        rows = CollectTaggedValue.query.order_by(CollectTaggedValue.id.asc()).all()
        if not rows:
            return jsonify({"code": 0, "msg": "暂无可入库记录", "data": {"stored": 0}})

        now = utc_now_second()
        inserted = 0
        updated = 0
        for rec in rows:
            _, was_update = _upsert_clean_for_tagged(rec, now)
            if was_update:
                updated += 1
            else:
                inserted += 1
            db.session.delete(rec)
        db.session.commit()
        log_op("数据采集", "标签一键入库", f"共 {len(rows)} 条（新增 {inserted}，覆盖 {updated}）")
        return jsonify({
            "code": 0,
            "msg": f"已完成入库 · 新增 {inserted}，覆盖 {updated}",
            "data": {"stored": len(rows), "inserted": inserted, "updated": updated},
        })
    except Exception as e:
        db.session.rollback()
        return jsonify({"code": 1, "msg": f"一键入库失败: {e}"}), 500


@bp.route("/tagged/<int:tid>", methods=["DELETE"])
def delete_tagged(tid: int):
    rec = CollectTaggedValue.query.get(tid)
    if not rec:
        return jsonify({"code": 1, "msg": "记录不存在"}), 404
    db.session.delete(rec)
    db.session.commit()
    return jsonify({"code": 0, "msg": "已删除"})


@bp.route("/tagged/<int:tid>", methods=["PUT"])
def update_tagged(tid: int):
    rec = CollectTaggedValue.query.get(tid)
    if not rec:
        return jsonify({"code": 1, "msg": "记录不存在"}), 404
    if (rec.status or "pending") == "stored":
        return jsonify({"code": 1, "msg": "已入库记录不允许修改"}), 400
    data = request.get_json(silent=True) or {}
    try:
        v = validate_tagged_update(data)
        if "tag" in v:
            rec.tag = v["tag"]
        if "value" in v:
            rec.value = v["value"]
        if "value_path" in data:
            rec.value_path = (data.get("value_path") or "")[:512] or None
        if "source_excerpt" in data:
            rec.source_excerpt = (data.get("source_excerpt") or "")[:16000] or None
        if not rec.value_path and rec.source_excerpt and rec.value:
            try:
                js = json.loads(rec.source_excerpt)
                rec.value_path = (_find_value_path(js, rec.value) or "")[:512] or None
            except Exception:
                rec.value_path = None
        db.session.commit()
        return jsonify({"code": 0, "msg": "已更新", "data": rec.to_dict()})
    except (ValueError, ValidationError) as e:
        return jsonify({"code": 1, "msg": str(e)}), 400
    except Exception as e:
        db.session.rollback()
        return jsonify({"code": 1, "msg": f"更新失败: {e}"}), 500


@bp.route("/tagged/clear", methods=["POST"])
def clear_tagged():
    """一键清空标签暂存区"""
    n = CollectTaggedValue.query.delete()
    db.session.commit()
    log_op("数据采集", "清空标签暂存", f"删除 {n} 条")
    return jsonify({"code": 0, "msg": "已清空", "data": {"deleted": n}})
