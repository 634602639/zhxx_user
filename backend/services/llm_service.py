"""OpenAI 兼容 Chat Completions 客户端（内网大模型）。

优先级：页面保存的配置 > 环境变量 LLM_BASE_URL / LLM_API_KEY / LLM_MODEL。
密钥写入 data/llm_config.json，接口不回显明文。
"""
from __future__ import annotations

import json
import os
import re

import requests

from config import BASE_DIR

_STORE_NAME = "llm_config.json"


def _store_path() -> str:
    return os.path.join(BASE_DIR, "data", _STORE_NAME)


def _load_stored() -> dict:
    path = _store_path()
    if not os.path.isfile(path):
        return {}
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError, TypeError):
        return {}


def _write_stored(payload: dict) -> None:
    path = _store_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)


def _pick(stored: dict, key: str, env_name: str) -> str:
    if key in stored:
        return str(stored.get(key) or "").strip()
    return (os.environ.get(env_name) or "").strip()


def llm_config() -> dict:
    stored = _load_stored()
    base = _pick(stored, "base_url", "LLM_BASE_URL")
    key = _pick(stored, "api_key", "LLM_API_KEY")
    model = _pick(stored, "model", "LLM_MODEL")
    return {
        "base_url": base,
        "api_key": key,
        "model": model,
        "configured": bool(base and model),
        "has_api_key": bool(key),
        "from_ui": "base_url" in stored or "model" in stored or "api_key" in stored,
    }


def llm_status_public() -> dict:
    c = llm_config()
    demo = not c["configured"]
    return {
        "configured": c["configured"],
        "demo_mode": demo,
        "base_url": c["base_url"],
        "model": c["model"],
        "has_api_key": c["has_api_key"],
        "from_ui": c["from_ui"],
    }


def save_llm_config(*, base_url: str, model: str, api_key: str | None = None, clear_api_key: bool = False) -> dict:
    stored = _load_stored()
    prev_key = str(stored.get("api_key") or "").strip()
    if not prev_key and "api_key" not in stored:
        prev_key = (os.environ.get("LLM_API_KEY") or "").strip()
    if clear_api_key:
        new_key = ""
    elif api_key is not None and str(api_key).strip():
        new_key = str(api_key).strip()
    else:
        new_key = prev_key
    _write_stored({
        "base_url": (base_url or "").strip(),
        "model": (model or "").strip(),
        "api_key": new_key,
    })
    return llm_config()


def overlay_config(data: dict | None) -> dict:
    """用请求体覆盖当前配置（测试未保存的表单），空密钥沿用已保存值。"""
    c = llm_config()
    if not data:
        return c
    base = data.get("base_url")
    model = data.get("model")
    key = data.get("api_key")
    if base is not None:
        c["base_url"] = str(base).strip()
    if model is not None:
        c["model"] = str(model).strip()
    if key is not None and str(key).strip():
        c["api_key"] = str(key).strip()
    c["configured"] = bool(c["base_url"] and c["model"])
    c["has_api_key"] = bool(c["api_key"])
    return c


def _chat_url(base: str) -> str:
    b = base.rstrip("/")
    if b.endswith("/chat/completions"):
        return b
    if b.endswith("/v1"):
        return b + "/chat/completions"
    return b + "/v1/chat/completions"


def chat(messages: list, *, temperature: float = 0.2, max_tokens: int = 4096, cfg: dict | None = None) -> str:
    c = cfg or llm_config()
    if not c.get("configured"):
        raise RuntimeError("未配置大模型：请在「报告辅助生成」页填写接口地址与模型名")
    headers = {"Content-Type": "application/json"}
    if c.get("api_key"):
        headers["Authorization"] = f"Bearer {c['api_key']}"
    body = {
        "model": c["model"],
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    resp = requests.post(_chat_url(c["base_url"]), headers=headers, json=body, timeout=300)
    resp.raise_for_status()
    data = resp.json()
    try:
        return (data["choices"][0]["message"]["content"] or "").strip()
    except (KeyError, IndexError, TypeError) as e:
        raise RuntimeError(f"大模型响应格式无法解析: {data}") from e


def probe_chat(cfg: dict | None = None) -> dict:
    c = cfg or llm_config()
    if not c.get("configured"):
        raise RuntimeError("请先填写接口地址和模型名")
    reply = chat(
        [{"role": "user", "content": "只回复两个字：正常"}],
        temperature=0,
        max_tokens=32,
        cfg=c,
    )
    return {"ok": True, "reply": (reply or "")[:200]}


def parse_json_content(text: str):
    """从模型输出中取出 JSON（允许 markdown 代码块包裹）。"""
    s = (text or "").strip()
    if not s:
        raise ValueError("模型返回为空")
    m = re.search(r"```(?:json)?\s*([\s\S]*?)```", s)
    if m:
        s = m.group(1).strip()
    try:
        return json.loads(s)
    except json.JSONDecodeError:
        pass
    i, j = s.find("["), s.rfind("]")
    if i >= 0 and j > i:
        try:
            return json.loads(s[i : j + 1])
        except json.JSONDecodeError:
            pass
    i, j = s.find("{"), s.rfind("}")
    if i >= 0 and j > i:
        try:
            return json.loads(s[i : j + 1])
        except json.JSONDecodeError:
            pass
    raise ValueError("模型未返回合法 JSON")
