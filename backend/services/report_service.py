"""
值勤报告辅助生成服务

职责：
  - 接收路由层已校验过的 template 对象 + 时间窗口
  - 按窗口拉 CleanData，做轻量聚合（来源/类别/数量/数值合计）
  - 对正文做素材整理与摘要（限长，避免大文本拖慢 jieba）
  - 把聚合结果填入模板占位符，保存 DutyReport 并返回
"""
from datetime import datetime, date, timedelta
from typing import Optional

from models import db, ReportTemplate, DutyReport, CleanData, CollectEndpoint
from services.nlp_service import (
    extract_keywords, summarize, fill_template, extract_placeholders,
)

# 单次报告的"原文素材"硬上限，避免上万条记录拼起来卡死 jieba
_RAW_TEXT_CAP = 80_000
# 单条 CleanData 用作素材时截断的字符数
_PER_ROW_CAP = 800


_RT_DISPLAY = {"word": "Word", "ppt": "PPT"}


def generate_report(
    template: Optional[ReportTemplate],
    report_type: str = "word",
    title: Optional[str] = None,
    location: str = "综合信息服务中心",
    days: int = 1,
) -> DutyReport:
    """根据模板 + 多维数据 自动生成值勤报告。

    生成时间通常 < 1 秒，符合"耗时 < 1 分钟"的需求。
    """
    tpl_text = (template.content if template else None) or _default_template()

    # 1. 拉时间窗内的 CleanData
    since = datetime.now().replace(microsecond=0) - timedelta(days=days)
    rows = (
        CleanData.query
        .filter(CleanData.occur_time >= since)
        .order_by(CleanData.occur_time.desc())
        .all()
    )

    # 2. endpoint name → (source_label, category_label) 映射，用于来源/类别口径与 by-day 一致
    ep_by_name: dict = {
        ep.name: (ep.source_label, ep.category_label)
        for ep in CollectEndpoint.query.all()
    }

    # 3. 聚合
    cat_count: dict = {}
    src_count: dict = {}
    metric_total = 0.0
    metric_n = 0
    accumulated_text = []
    text_len = 0

    for r in rows:
        # 来源 / 类别口径：手填 endpoint_source/category 优先；否则 endpoint name 反查
        src_lbl = (r.endpoint_source or "").strip() or None
        cat_lbl = (r.endpoint_category or "").strip() or None
        if not src_lbl or not cat_lbl:
            es, ec = ep_by_name.get(r.source or "", (None, None))
            src_lbl = src_lbl or es or (r.source or "未知")
            cat_lbl = cat_lbl or ec or (r.category or "未分类")

        cat_count[cat_lbl] = cat_count.get(cat_lbl, 0) + 1
        src_count[src_lbl] = src_count.get(src_lbl, 0) + 1
        if r.metric_value is not None:
            try:
                metric_total += float(r.metric_value)
                metric_n += 1
            except (TypeError, ValueError):
                pass

        if r.content and text_len < _RAW_TEXT_CAP:
            chunk = (r.content[:_PER_ROW_CAP]).strip()
            if chunk:
                accumulated_text.append(chunk)
                text_len += len(chunk) + 1   # +1 for the joining newline

    raw_text = "\n".join(accumulated_text)[:_RAW_TEXT_CAP]

    # 4. 摘要 / 关键词
    summary = summarize(raw_text, max_sentences=5) if raw_text else "本周期无重点事件。"
    if raw_text:
        keywords = extract_keywords(raw_text, top_k=10)
    else:
        # 没有正文时退而求其次用类别/来源词作关键词
        keywords = extract_keywords(" ".join(list(cat_count.keys()) + list(src_count.keys())), top_k=10)

    # 5. 标题：传入优先；否则按日期 + Office 类型（Word/PPT）
    today = date.today()
    type_label = _RT_DISPLAY.get(report_type, report_type)
    rpt_title = title or f"{today.strftime('%Y-%m-%d')} 综合信息服务中心 · {type_label}"

    # 6. 占位符表
    mapping = {
        "title": rpt_title,
        "report_type": type_label,
        "report_date": today.strftime("%Y-%m-%d"),
        "location": location,
        "days": days,
        "total_events": len(rows),
        "category_summary": "；".join(f"{k}: {v}条" for k, v in cat_count.items()) or "无",
        "source_summary": "；".join(f"{k}: {v}条" for k, v in src_count.items()) or "无",
        "metric_total": f"{metric_total:.2f}" if metric_n else "—",
        "metric_avg": f"{(metric_total / metric_n):.2f}" if metric_n else "—",
        "summary": summary,
        "keywords": "、".join(keywords) if keywords else "无",
    }
    body = fill_template(tpl_text, mapping)

    # 7. 入库 DutyReport
    rpt = DutyReport(
        title=rpt_title,
        report_type=report_type,
        content=body,
        template_id=(template.id if template else None),
        report_date=today,
    )
    db.session.add(rpt)
    db.session.commit()
    return rpt


def _default_template() -> str:
    return (
        "【{{title}}】\n"
        "报告类型（Office）：{{report_type}}\n"
        "报告日期：{{report_date}}\n"
        "值勤地点：{{location}}\n"
        "采集时间窗：近 {{days}} 天\n"
        "涉及来源：{{source_summary}}\n\n"
        "一、数据概览\n"
        "本周期共采集事件 {{total_events}} 条。\n"
        "分类统计：{{category_summary}}\n"
        "数值合计 / 均值：{{metric_total}} / {{metric_avg}}\n\n"
        "二、内容提炼\n"
        "{{summary}}\n\n"
        "三、关键词\n"
        "{{keywords}}\n\n"
        "（本报告由值勤报告辅助生成模块自动生成）"
    )
