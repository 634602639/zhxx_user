"""表单字段长度与格式校验（与 models 列宽及业务约定一致）。"""
from __future__ import annotations

import json
import random
from datetime import datetime, timedelta
from typing import Any, Optional
from urllib.parse import urlparse

# —— 字符串长度 ——
L_EP_NAME = 20
L_EP_METHOD = 16
L_EP_URL = 2048
L_EP_LABEL = 64
L_EP_LIST_PATH = 512
L_EP_HEADERS_JSON = 8192
L_EP_BODY = 65536
L_EP_FIELD_MAP_JSON = 32768

L_TAG = 64
L_TAG_VALUE = 20000
L_TAG_VALUE_PATH = 512
L_TAG_SOURCE_EXCERPT = 16000
L_ENDPOINT_NAME = 128

L_CLEAN_SOURCE = 64
L_CLEAN_TAGS = 255
L_CLEAN_CATEGORY = 64
L_CLEAN_LABEL = 64
L_ORG_REMARK = 64
L_ORG_NAME = 64
L_CLEAN_TITLE = 255
L_CLEAN_CONTENT = 500_000

L_REPORT_TITLE = 255
L_REPORT_CONTENT = 2_000_000

L_DRAFT_TITLE = 255
L_DRAFT_CONTENT = 2_000_000
L_SLOT_MANUAL = 50

L_SEARCH_KEYWORD = 128
L_TEMPLATE_NAME = 128

L_USERNAME = 64
L_PASSWORD = 64

L_ROLE_NAME = 64
L_ROLE_CODE = 64
L_ROLE_DESC = 255

ALLOWED_HTTP_METHODS = frozenset({"GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"})
OFFICE_REPORT_TYPES = frozenset({"word", "ppt"})


class ValidationError(ValueError):
    pass


def _s(val: Any) -> str:
    if val is None:
        return ""
    return str(val).strip()


def parse_time_range(date_from: Any, date_to: Any) -> tuple[datetime, datetime]:
    """解析采集时间范围。仅填日期的结束日含当天 23:59:59。"""
    start = parse_datetime_value(date_from, "起始时间", required=True)
    end = parse_datetime_value(date_to, "结束时间", required=True)
    raw_to = str(date_to or "").strip().replace("T", " ")
    if end is not None and len(raw_to) <= 10:
        end = end.replace(hour=23, minute=59, second=59)
    if start is None or end is None:
        raise ValidationError("请填写时间范围")
    if end < start:
        raise ValidationError("结束时间不能早于起始时间")
    return start, end


def parse_datetime_value(val: Any, label: str = "数据对应时间", *, required: bool = False) -> Optional[datetime]:
    """解析 YYYY-MM-DD[ HH:MM[:SS]] 或 ISO T 分隔。仅日期时取当天 00:00:00。"""
    if val is None or val == "":
        if required:
            raise ValidationError(f"请填写{label}")
        return None
    if isinstance(val, datetime):
        return val.replace(microsecond=0)
    s = str(val).strip().replace("T", " ").replace("Z", "")
    if "." in s:
        s = s.split(".", 1)[0]
    for n, fmt in ((19, "%Y-%m-%d %H:%M:%S"), (16, "%Y-%m-%d %H:%M"), (10, "%Y-%m-%d")):
        chunk = s[:n]
        if len(chunk) < n:
            continue
        try:
            dt = datetime.strptime(chunk, fmt)
            return dt.replace(microsecond=0)
        except ValueError:
            continue
    raise ValidationError(f"{label}格式无效，应为 YYYY-MM-DD 或 YYYY-MM-DD HH:MM:SS")


def default_data_occur_time() -> datetime:
    """演示用数据对应时间：过去 1～6 天、白天时段随机，避免与采集当天相同。"""
    return random_demo_occur_time()


def random_demo_occur_time(start: Optional[datetime] = None, end: Optional[datetime] = None) -> datetime:
    """在给定时间范围内随机一个数据对应时间；未给范围时取过去 1～6 天白天。"""
    if start is not None and end is not None:
        a, b = start, end
        if b < a:
            a, b = b, a
        span = (b - a).total_seconds()
        if span <= 0:
            return a.replace(microsecond=0)
        return (a + timedelta(seconds=random.uniform(0, span))).replace(microsecond=0)
    now = datetime.now().replace(microsecond=0)
    d = (now - timedelta(days=random.randint(1, 6))).date()
    return datetime(
        d.year, d.month, d.day,
        random.randint(8, 21),
        random.randint(0, 59),
        random.randint(0, 59),
    )


def require_str(
    val: Any,
    label: str,
    *,
    min_len: int = 1,
    max_len: int,
    required: bool = True,
) -> str:
    s = _s(val)
    if not s:
        if required:
            raise ValidationError(f"请填写{label}")
        return ""
    if len(s) < min_len:
        raise ValidationError(f"{label}至少 {min_len} 个字符")
    if len(s) > max_len:
        raise ValidationError(f"{label}不能超过 {max_len} 个字符")
    return s


def optional_str(val: Any, label: str, *, max_len: int, min_len: int = 0) -> Optional[str]:
    s = _s(val)
    if not s:
        return None
    if len(s) < min_len:
        raise ValidationError(f"{label}至少 {min_len} 个字符")
    if len(s) > max_len:
        raise ValidationError(f"{label}不能超过 {max_len} 个字符")
    return s


def optional_text(val: Any, label: str, *, max_len: int) -> Optional[str]:
    """允许空字符串入库（与 optional_str 不同：空串保留为 ''）。"""
    if val is None:
        return None
    s = str(val)
    if len(s) > max_len:
        raise ValidationError(f"{label}不能超过 {max_len} 个字符")
    return s


def require_http_method(val: Any) -> str:
    m = require_str(val, "请求方式", min_len=1, max_len=L_EP_METHOD).upper()
    if m not in ALLOWED_HTTP_METHODS:
        raise ValidationError(f"请求方式不支持：{m}")
    return m


def require_url(val: Any) -> str:
    url = require_str(val, "接口 URL", min_len=1, max_len=L_EP_URL)
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        raise ValidationError("接口 URL 须为 http:// 或 https:// 开头的有效地址")
    return url


def require_json_object_text(raw: Any, label: str, *, max_len: int) -> Optional[str]:
    if raw is None:
        return None
    if isinstance(raw, dict):
        if not raw:
            return None
        text = json.dumps(raw, ensure_ascii=False)
    else:
        text = _s(raw)
        if not text:
            return None
    if len(text) > max_len:
        raise ValidationError(f"{label}不能超过 {max_len} 个字符")
    try:
        obj = json.loads(text) if isinstance(raw, str) else raw
    except json.JSONDecodeError:
        raise ValidationError(f"{label}须为合法 JSON")
    if not isinstance(obj, dict):
        raise ValidationError(f"{label}须为 JSON 对象")
    return text if isinstance(raw, str) else json.dumps(obj, ensure_ascii=False)


def validate_tagged_create(data: dict) -> dict:
    tag = require_str(data.get("tag"), "标签", min_len=1, max_len=L_TAG)
    val = data.get("value")
    if val is None:
        val = ""
    val = str(val)
    if not val.strip():
        raise ValidationError("请先在「本条采集内容」中选中要暂存的中间部分")
    if len(val) > L_TAG_VALUE:
        raise ValidationError(f"选中内容不能超过 {L_TAG_VALUE} 个字符")
    ep_name = optional_str(data.get("endpoint_name"), "配置名称", max_len=L_ENDPOINT_NAME)
    occur = parse_datetime_value(data.get("occur_time"), "数据对应时间")
    return {"tag": tag, "value": val, "endpoint_name": ep_name, "occur_time": occur}


def validate_tagged_update(data: dict) -> dict:
    out = {}
    if "tag" in data:
        out["tag"] = require_str(data.get("tag"), "标签", min_len=1, max_len=L_TAG)
    if "value" in data:
        val = str(data.get("value") or "")
        if not val.strip():
            raise ValidationError("值不能为空")
        if len(val) > L_TAG_VALUE:
            raise ValidationError(f"值不能超过 {L_TAG_VALUE} 个字符")
        out["value"] = val
    return out


def validate_clean_payload(data: dict, *, for_update: bool = False) -> dict:
    out = {}
    if not for_update or "source" in data:
        out["source"] = optional_str(data.get("source"), "所属配置", max_len=L_CLEAN_SOURCE)
    if not for_update or "tags" in data:
        out["tags"] = optional_str(data.get("tags"), "标签", max_len=L_CLEAN_TAGS)
    if not for_update or "category" in data:
        out["category"] = optional_str(data.get("category"), "入库类别", max_len=L_CLEAN_CATEGORY)
    if not for_update or "content" in data:
        out["content"] = optional_text(data.get("content"), "值", max_len=L_CLEAN_CONTENT) or ""
    if not for_update or "endpoint_source" in data:
        out["endpoint_source"] = optional_str(
            data.get("endpoint_source"), "来源", max_len=L_CLEAN_LABEL
        )
    if not for_update or "endpoint_category" in data:
        out["endpoint_category"] = optional_str(
            data.get("endpoint_category"), "类别", max_len=L_CLEAN_LABEL
        )
    if "occur_time" in data:
        out["occur_time"] = parse_datetime_value(data.get("occur_time"), "数据对应时间")
    if not for_update:
        if not _s(out.get("content")):
            raise ValidationError("请填写值")
        if "occur_time" not in out:
            out["occur_time"] = parse_datetime_value(data.get("occur_time"), "数据对应时间")
    return out


def validate_report_payload(data: dict, *, for_update: bool = False) -> dict:
    out = {}
    if not for_update or "title" in data:
        out["title"] = require_str(data.get("title"), "标题", min_len=1, max_len=L_REPORT_TITLE)
    if not for_update or "content" in data:
        out["content"] = optional_text(data.get("content"), "正文", max_len=L_REPORT_CONTENT) or ""
    if not for_update or "report_type" in data:
        rt = _s(data.get("report_type") or "word")
        if rt not in OFFICE_REPORT_TYPES:
            raise ValidationError("报告类型须为 word 或 ppt")
        out["report_type"] = rt
    return out


def validate_search_keyword(val: Any) -> str:
    return optional_str(val, "搜索关键词", max_len=L_SEARCH_KEYWORD) or ""


def validate_compose_draft_content(val: Any) -> str:
    return require_str(val, "正文", min_len=1, max_len=L_DRAFT_CONTENT)


def validate_compose_draft_title(val: Any) -> str:
    return require_str(val, "标题", min_len=1, max_len=L_DRAFT_TITLE)


def validate_slot_manual(val: Any) -> str:
    return optional_str(val, "替换内容", max_len=L_SLOT_MANUAL) or ""


def validate_username(val: Any) -> str:
    return require_str(val, "用户名", min_len=2, max_len=L_USERNAME)


def validate_password(val: Any, *, required: bool = True) -> Optional[str]:
    if required:
        return require_str(val, "密码", min_len=1, max_len=L_PASSWORD)
    return optional_str(val, "密码", max_len=L_PASSWORD)


# —— 角色 ——
import re

_ROLE_CODE_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_]*$")


def validate_role_name(val: Any) -> str:
    return require_str(val, "角色名称", min_len=2, max_len=L_ROLE_NAME)


def validate_role_code(val: Any) -> str:
    code = require_str(val, "角色标识", min_len=2, max_len=L_ROLE_CODE)
    if not _ROLE_CODE_RE.match(code):
        raise ValidationError("角色标识须以字母开头，仅含字母、数字、下划线")
    return code


def validate_role_desc(val: Any) -> Optional[str]:
    return optional_str(val, "角色描述", max_len=L_ROLE_DESC)


def validate_role_perms(val: Any) -> list:
    """权限点列表：必须是字符串数组（合法性由 permissions.normalize_perms 进一步过滤）。"""
    if val is None:
        return []
    if not isinstance(val, (list, tuple)):
        raise ValidationError("权限须为数组")
    out = []
    for x in val:
        if not isinstance(x, str):
            raise ValidationError("权限项须为字符串")
        s = x.strip()
        if s:
            out.append(s)
    return out
