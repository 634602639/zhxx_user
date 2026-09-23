"""草稿润色：大模型给出替换对，再写回正文与 Office 附件。"""
from __future__ import annotations

import json

from services.llm_service import chat, llm_config, parse_json_content
from services.office_text_replace import apply_replacements_to_office, apply_replacements_to_text, sanitize_replacements

# 展示版、未配置内网大模型时的保守用词替换（不含数字）
_DEMO_PAIRS = [
    {"from": "登陆", "to": "登录"},
    {"from": "起不来", "to": "无法启动"},
    {"from": "网内传播", "to": "网内扩散"},
]


def _apply_pairs(text: str, blob: bytes | None, pairs_raw: list, *, demo: bool) -> dict:
    pairs = sanitize_replacements(pairs_raw)
    new_text = apply_replacements_to_text(text or "", pairs)
    new_blob = apply_replacements_to_office(blob, pairs) if blob else blob
    return {
        "content": new_text,
        "file_blob": new_blob,
        "replacement_count": len(pairs),
        "replacements": [{"from": a, "to": b} for a, b in pairs],
        "demo_mode": demo,
    }


def polish_text_and_office(text: str, blob: bytes | None) -> dict:
    if not llm_config()["configured"]:
        return _apply_pairs(text, blob, _DEMO_PAIRS, demo=True)
    body = (text or "")[:24000]
    sys_p = (
        "你是公文润色与纠错助手。在不改变事实与数字的前提下，修正错别字、标点，使语句通顺，语气符合值勤报告。\n"
        "严禁改动任何数字、百分比、日期中的数字；严禁编造故障、战果或未出现的单位。\n"
        "不要增删表格结构。只输出 JSON：{\"replacements\":[{\"from\":\"原文片段\",\"to\":\"修订后\"}]}\n"
        "from 必须是原文中的连续子串；无需修改时 replacements 为空数组。"
    )
    raw = chat(
        [
            {"role": "system", "content": sys_p},
            {"role": "user", "content": json.dumps({"text": body}, ensure_ascii=False)},
        ],
        temperature=0.2,
        max_tokens=4096,
    )
    parsed = parse_json_content(raw)
    pairs_raw = []
    if isinstance(parsed, dict):
        pairs_raw = parsed.get("replacements") or parsed.get("edits") or []
    elif isinstance(parsed, list):
        pairs_raw = parsed
    return _apply_pairs(text, blob, pairs_raw, demo=False)
