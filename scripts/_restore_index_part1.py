# -*- coding: utf-8 -*-
"""Restore Chinese labels in index.html (lost as ASCII ?)."""
from pathlib import Path

def main():
    p = Path("frontend/index.html")
    raw = p.read_text(encoding="utf-8")
    # Whole-file replacement: built from current skeleton + known strings
    out = """<!DOCTYPE html>
<html lang=\"zh-CN\" data-mode=\"light\">
<head>
  <meta charset=\"UTF-8\" />
  <title>综合信息服务中心 · Data Console</title>
  <link rel=\"stylesheet\" href=\"/css/main.css\" />
  <link rel=\"preconnect\" href=\"https://fonts.googleapis.com\">
  <link rel=\"preconnect\" href=\"https://fonts.gstatic.com\" crossorigin>
  <link href=\"https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;500;600&display=swap\" rel=\"stylesheet\">
  <script src=\"https://cdn.jsdelivr.net/npm/echarts@5.4.3/dist/echarts.min.js\"></script>
</head>
<body>
  <!-- Inline icon set (Lucide-flavored). Refer via <svg><use href=\"#i-xxx\"/></svg>. -->
  <svg width=\"0\" height=\"0\" style=\"position:absolute\" aria-hidden=\"true\">
    <defs>
      <symbol id=\"i-home\" viewBox=\"0 0 24 24\" fill=\"none\" stroke=\"currentColor\" stroke-width=\"1.8\" stroke-linecap=\"round\" stroke-linejoin=\"round\"><path d=\"M3 12L12 3l9 9\"/><path d=\"M5 10v10h14V10\"/></symbol>
      <symbol id=\"i-database\" viewBox=\"0 0 24 24\" fill=\"none\" stroke=\"currentColor\" stroke-width=\"1.8\" stroke-linecap=\"round\" stroke-linejoin=\"round\"><ellipse cx=\"12\" cy=\"5\" rx=\"8\" ry=\"3\"/><path d=\"M4 5v14c0 1.7 3.6 3 8 3s8-1.3 8-3V5\"/><path d=\"M4 12c0 1.7 3.6 3 8 3s8-1.3 8-3\"/></symbol>
      <symbol id=\"i-chart\" viewBox=\"0 0 24 24\" fill=\"none\" stroke=\"currentColor\" stroke-width=\"1.8\" stroke-linecap=\"round\" stroke-linejoin=\"round\"><path d=\"M3 3v18h18\"/><path d=\"M7 14l4-4 4 4 5-6\"/></symbol>
      <symbol id=\"i-edit\" viewBox=\"0 0 24 24\" fill=\"none\" stroke=\"currentColor\" stroke-width=\"1.8\" stroke-linecap=\"round\" stroke-linejoin=\"round\"><path d=\"M14 4l6 6L8 22H2v-6z\"/></symbol>
      <symbol id=\"i-folder\" viewBox=\"0 0 24 24\" fill=\"none\" stroke=\"currentColor\" stroke-width=\"1.8\" stroke-linecap=\"round\" stroke-linejoin=\"round\"><path d=\"M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v9a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z\"/></symbol>
      <symbol id=\"i-log\" viewBox=\"0 0 24 24\" fill=\"none\" stroke=\"currentColor\" stroke-width=\"1.8\" stroke-linecap=\"round\" stroke-linejoin=\"round\"><path d=\"M5 4h14v16H5z\"/><path d=\"M9 9h6M9 13h6M9 17h4\"/></symbol>
      <symbol id=\"i-plus\" viewBox=\"0 0 24 24\" fill=\"none\" stroke=\"currentColor\" stroke-width=\"1.8\" stroke-linecap=\"round\" stroke-linejoin=\"round\"><path d=\"M12 5v14M5 12h14\"/></symbol>
      <symbol id=\"i-refresh\" viewBox=\"0 0 24 24\" fill=\"none\" stroke=\"currentColor\" stroke-width=\"1.8\" stroke-linecap=\"round\" stroke-linejoin=\"round\"><path d=\"M3 12a9 9 0 0 1 15-6.7L21 8\"/><path d=\"M21 3v5h-5\"/><path d=\"M21 12a9 9 0 0 1-15 6.7L3 16\"/><path d=\"M3 21v-5h5\"/></symbol>
      <symbol id=\"i-play\" viewBox=\"0 0 24 24\" fill=\"none\" stroke=\"currentColor\" stroke-width=\"1.8\" stroke-linecap=\"round\" stroke-linejoin=\"round\"><path d=\"M6 4l14 8-14 8z\"/></symbol>
      <symbol id=\"i-link\" viewBox=\"0 0 24 24\" fill=\"none\" stroke=\"currentColor\" stroke-width=\"1.8\" stroke-linecap=\"round\" stroke-linejoin=\"round\"><path d=\"M10 14a5 5 0 0 0 7 0l3-3a5 5 0 0 0-7-7l-1 1\"/><path d=\"M14 10a5 5 0 0 0-7 0l-3 3a5 5 0 0 0 7 7l1-1\"/></symbol>
      <symbol id=\"i-sparkles\" viewBox=\"0 0 24 24\" fill=\"none\" stroke=\"currentColor\" stroke-width=\"1.8\" stroke-linecap=\"round\" stroke-linejoin=\"round\"><path d=\"M12 3l2 5 5 2-5 2-2 5-2-5-5-2 5-2z\"/><path d=\"M19 14l1 2 2 1-2 1-1 2-1-2-2-1 2-1z\"/></symbol>
      <symbol id=\"i-search\" viewBox=\"0 0 24 24\" fill=\"none\" stroke=\"currentColor\" stroke-width=\"1.8\" stroke-linecap=\"round\" stroke-linejoin=\"round\"><circle cx=\"11\" cy=\"11\" r=\"7\"/><path d=\"M21 21l-4.3-4.3\"/></symbol>
      <symbol id=\"i-upload\" viewBox=\"0 0 24 24\" fill=\"none\" stroke=\"currentColor\" stroke-width=\"1.8\" stroke-linecap=\"round\" stroke-linejoin=\"round\"><path d=\"M12 21V9\"/><path d=\"M7 14l5-5 5 5\"/><path d=\"M5 3h14\"/></symbol>
      <symbol id=\"i-download\" viewBox=\"0 0 24 24\" fill=\"none\" stroke=\"currentColor\" stroke-width=\"1.8\" stroke-linecap=\"round\" stroke-linejoin=\"round\"><path d=\"M12 3v12\"/><path d=\"M7 10l5 5 5-5\"/><path d=\"M5 21h14\"/></symbol>
      <symbol id=\"i-file\" viewBox=\"0 0 24 24\" fill=\"none\" stroke=\"currentColor\" stroke-width=\"1.8\" stroke-linecap=\"round\" stroke-linejoin=\"round\"><path d=\"M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z\"/><path d=\"M14 2v6h6\"/></symbol>
    </defs>
  </svg>

  <div class=\"layout\">
    <aside class=\"sidebar\">
      <div class=\"sidebar-brand\">
        <div class=\"logo\">数</div>
        <div class=\"name-block\">
          <div class=\"name\">综合信息服务中心</div>
          <div class=\"sub\">Data Console</div>
        </div>
      </div>

      <div class=\"menu-title\">主导航</div>
      <ul class=\"menu\">
        <li class=\"menu-item active\" data-page=\"dashboard\">
          <span class=\"icon\"><svg width=\"18\" height=\"18\"><use href=\"#i-home\"/></svg></span>
          <span class=\"label\">态势总览</span>
        </li>
        <li class=\"menu-item\" data-page=\"collect\">
          <span class=\"icon\"><svg width=\"18\" height=\"18\"><use href=\"#i-database\"/></svg></span>
          <span class=\"label\">数据采集</span>
        </li>
        <li class=\"menu-item\" data-page=\"analysis\">
          <span class=\"icon\"><svg width=\"18\" height=\"18\"><use href=\"#i-chart\"/></svg></span>
          <span class=\"label\">数据分析</span>
        </li>
        <li class=\"menu-item\" data-page=\"generate\">
          <span class=\"icon\"><svg width=\"18\" height=\"18\"><use href=\"#i-edit\"/></svg></span>
          <span class=\"label\">报告生成</span>
        </li>
        <li class=\"menu-item\" data-page=\"manage\">
          <span class=\"icon\"><svg width=\"18\" height=\"18\"><use href=\"#i-folder\"/></svg></span>
          <span class=\"label\">报告管理</span>
        </li>
        <li class=\"menu-item\" data-page=\"logs\">
          <span class=\"icon\"><svg width=\"18\" height=\"18\"><use href=\"#i-log\"/></svg></span>
          <span class=\"label\">操作日志</span>
        </li>
      </ul>

      <div class=\"sidebar-foot\">
        <span class=\"status-dot\"></span>
        <span class=\"foot-text\">B/S · Python 后端</span>
        <button class=\"theme-toggle\" type=\"button\" onclick=\"toggleTheme()\" title=\"切换深 / 浅色\">?</button>
      </div>
    </aside>

    <main class=\"main\">

      <!-- ========== 01. DASHBOARD ========== -->
      <div id=\"page-dashboard\" class=\"page active\">
        <div class=\"page-header\">
          <div>
            <div class=\"crumbs\">OVERVIEW · 总览</div>
            <h2>综合信息服务中心 · 实时态势</h2>
            <div class=\"desc\">展示当前数据采集、报告生成与系统运转情况</div>
          </div>
          <div class=\"actions\">
            <button class=\"btn\" onclick=\"Dashboard.refresh()\"><svg class=\"icon\" width=\"14\" height=\"14\"><use href=\"#i-refresh\"/></svg> 刷新</button>
          </div>
        </div>

        <!-- KPI -->
        <div class=\"kpi-grid\">
          <div class=\"kpi\">
            <div class=\"kpi-label\"><span class=\"dot\" style=\"background:var(--c1)\"></span>已入库数据</div>
            <div class=\"kpi-num\"><span id=\"kpi-clean\">-</span><span class=\"unit\">条</span></div>
            <span class=\"kpi-trend\" id=\"kpi-clean-trend\"></span>
            <div id=\"kpi-clean-spark\" class=\"kpi-spark\"></div>
          </div>
          <div class=\"kpi\">
            <div class=\"kpi-label\"><span class=\"dot\" style=\"background:var(--c2)\"></span>报告模板</div>
            <div class=\"kpi-num\"><span id=\"kpi-tpl\">-</span><span class=\"unit\">个</span></div>
            <span class=\"kpi-trend\" id=\"kpi-tpl-trend\"></span>
            <div id=\"kpi-tpl-spark\" class=\"kpi-spark\"></div>
          </div>
          <div class=\"kpi\">
            <div class=\"kpi-label\"><span class=\"dot\" style=\"background:var(--c3)\"></span>值勤报告</div>
            <div class=\"kpi-num\"><span id=\"kpi-rpt\">-</span><span class=\"unit\">份</span></div>
            <span class=\"kpi-trend\" id=\"kpi-rpt-trend\"></span>
            <div id=\"kpi-rpt-spark\" class=\"kpi-spark\"></div>
          </div>
          <div class=\"kpi\">
            <div class=\"kpi-label\"><span class=\"dot\" style=\"background:var(--c4)\"></span>今日日志</div>
            <div class=\"kpi-num\"><span id=\"kpi-log\">-</span><span class=\"unit\">条</span></div>
            <span class=\"kpi-trend\" id=\"kpi-log-trend\"></span>
            <div id=\"kpi-log-spark\" class=\"kpi-spark\"></div>
          </div>
        </div>

        <!-- Row 1: trend (2fr) + system health (1fr) -->
        <div class=\"chart-grid cols-3\">
          <div class=\"panel\">
            <div class=\"panel-head\">
              <h3>入库趋势 · 采集 · 模板 · 报告 <span class=\"panel-tag\">30 D</span></h3>
              <div class=\"actions\">
                <button class=\"btn small ghost\" data-range=\"day\" onclick=\"Dashboard.setRange('day')\">日</button>
                <button class=\"btn small\" data-range=\"week\" onclick=\"Dashboard.setRange('week')\">周</button>
                <button class=\"btn small ghost\" data-range=\"month\" onclick=\"Dashboard.setRange('month')\">月</button>
              </div>
            </div>
            <div class=\"panel-body flush\"><div id=\"chart-trend\" class=\"chart\"></div></div>
          </div>
          <div class=\"panel\">
            <div class=\"panel-head\">
              <h3>系统健康</h3>
              <span class=\"tag ok dot\" id=\"dash-health-tag\">运行正常</span>
            </div>
            <div class=\"panel-body\" style=\"padding-top:0;\">
              <div id=\"chart-gauge\" class=\"chart short\" style=\"height:170px; background:transparent; border:none; padding:0;\"></div>
              <div class=\"mini-stats\">
                <div class=\"mini-stat\"><div class=\"lbl\">API 可用</div><div class=\"val\" id=\"ms-api\">—</div></div>
                <div class=\"mini-stat\"><div class=\"lbl\">平均延迟</div><div class=\"val\" id=\"ms-latency\">—</div></div>
                <div class=\"mini-stat\"><div class=\"lbl\">今日采集</div><div class=\"val\" id=\"ms-today\">—</div></div>
                <div class=\"mini-stat\"><div class=\"lbl\">待处理</div><div class=\"val\" id=\"ms-pending\">—</div></div>
              </div>
            </div>
          </div>
        </div>

        <!-- Row 2: source pie + category bar -->
        <div class=\"chart-grid cols-2\">
          <div class=\"panel\">
            <div class=\"panel-head\"><h3>来源占比</h3><span class=\"tag accent\">分布</span></div>
            <div class=\"panel-body flush\"><div id=\"chart-source\" class=\"chart\"></div></div>
          </div>
          <div class=\"panel\">
            <div class=\"panel-head\"><h3>类别分布</h3></div>
            <div class=\"panel-body flush\"><div id=\"chart-cat\" class=\"chart\"></div></div>
          </div>
        </div>

        <!-- Row 3: realtime feed + 24h heatmap -->
        <div class=\"chart-grid cols-2\">
          <div class=\"panel\">
            <div class=\"panel-head\">
              <h3>实时操作流</h3>
              <button class=\"btn small ghost\" onclick=\"Dashboard.refresh()\" title=\"刷新\"><svg class=\"icon\" width=\"12\" height=\"12\"><use href=\"#i-refresh\"/></svg></button>
            </div>
            <div class=\"panel-body flush\"><div id=\"dash-feed\" class=\"feed\"></div></div>
          </div>
          <div class=\"panel\">
            <div class=\"panel-head\"><h3>24h 采集热度</h3><span class=\"muted\">端点 × 条数</span></div>
            <div class=\"panel-body flush\"><div id=\"dash-heatmap\" class=\"heatmap\"></div></div>
          </div>
        </div>
      </div>
"""
    # Append remainder from existing file: copy collect section onward from broken read — too long; continue in second write
    p.write_text(out, encoding="utf-8")
    print("wrote partial")

if __name__ == "__main__":
    main()
