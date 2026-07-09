"""
轻量级 NLP 服务：关键词提取 + 文本提炼总结。
- 关键词提取：使用 jieba.analyse.extract_tags（TF-IDF）
- 文本摘要：基于句子关键词重合度的简单 TextRank 思路
"""
import re

try:
    import jieba
    import jieba.analyse
    _JIEBA_OK = True
except Exception:
    _JIEBA_OK = False


_STOPWORDS = set("的 了 和 是 与 或 也 而 在 及 从 到 等 中 对 被 由 把 将 以 为 以及 但是 因此 所以 这 那 此".split())


def extract_keywords(text: str, top_k: int = 10):
    """从文本中提取关键词"""
    if not text:
        return []
    if _JIEBA_OK:
        try:
            kws = jieba.analyse.extract_tags(text, topK=top_k)
            return kws
        except Exception:
            pass
    # 兜底：按非中文字符分割后取词频
    tokens = [t for t in re.findall(r"[一-龥A-Za-z0-9]+", text) if len(t) > 1 and t not in _STOPWORDS]
    freq = {}
    for t in tokens:
        freq[t] = freq.get(t, 0) + 1
    return [w for w, _ in sorted(freq.items(), key=lambda x: -x[1])[:top_k]]


def split_sentences(text: str):
    parts = re.split(r"(?<=[。！？!?\n])", text)
    return [p.strip() for p in parts if p and p.strip()]


def summarize(text: str, max_sentences: int = 5):
    """对文本进行提炼总结：取与全文关键词重合度最高的若干句子"""
    if not text:
        return ""
    sentences = split_sentences(text)
    if len(sentences) <= max_sentences:
        return "".join(sentences)
    keywords = set(extract_keywords(text, top_k=15))
    scored = []
    for idx, s in enumerate(sentences):
        score = sum(1 for k in keywords if k in s)
        scored.append((score, idx, s))
    scored.sort(key=lambda x: (-x[0], x[1]))
    chosen = sorted(scored[:max_sentences], key=lambda x: x[1])
    return "".join(s for _, _, s in chosen)


_PLACEHOLDER_RE = re.compile(r"\{\{\s*([\w\-]+)\s*\}\}")


def extract_placeholders(template_text: str) -> list:
    """扫描模板里的 {{xxx}} 占位符，返回去重后保持出现顺序的列表。"""
    if not template_text:
        return []
    seen = []
    for m in _PLACEHOLDER_RE.finditer(template_text):
        k = m.group(1).strip()
        if k and k not in seen:
            seen.append(k)
    return seen


def fill_template(template_text: str, mapping: dict) -> str:
    """填充 {{key}} 形式占位符；忽略未提供的占位符（保持原文）。"""
    if not template_text:
        return ""

    def repl(m):
        k = m.group(1).strip()
        if k in mapping:
            return str(mapping[k])
        return m.group(0)

    return _PLACEHOLDER_RE.sub(repl, template_text)
