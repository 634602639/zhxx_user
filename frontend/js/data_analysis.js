// ========== 值勤数据分析（design 风格） ==========
const Analysis = {
  _ec: {},
  /** 时间趋势与相关 KPI 固定统计最近 N 个自然日（含今日） */
  RANGE_DAYS: 7,
  /** 最近一次刷新得到的 4 个 KPI，供「数据存储」按钮入库 */
  _kpi: null,

  async refresh() {
    try {
      // 强制重播一次入场动画：点"刷新"时即使数据没变也要有视觉反馈
      Object.values(this._ec || {}).forEach(ec => { try { ec && ec.clear(); } catch (_) {} });
      const r = (await API.get("/api/analysis/multi-dim")).data || {};
      const span = this.RANGE_DAYS;

      // 总计角标
      const totalEl = document.getElementById("ana-total");
      if (totalEl) totalEl.textContent = `共分析 ${(r.total || 0).toLocaleString()} 条数据`;

      // 时间序列对齐到指定窗口
      const series = this._zeroFill(r.by_date || [], span);

      // KPI
      this._setKpi("ana-kpi-total", r.total || 0, series.map(d => d.value), 0);
      const avg = series.length ? Math.round(series.reduce((s, d) => s + d.value, 0) / series.length) : 0;
      this._setKpi("ana-kpi-avg", avg, series.map(d => d.value), 1);
      const peak = series.reduce((m, d) => Math.max(m, d.value), 0);
      this._setKpi("ana-kpi-peak", peak, series.map(d => d.value), 3);
      const srcN = (r.by_source || []).length;
      this._setKpi("ana-kpi-src", srcN, this._fakeSpark(srcN, series.length), 2);

      // 缓存当前 KPI，供「数据存储」按钮入库
      this._kpi = { total: r.total || 0, daily_avg: avg, peak, source_count: srcN };

      // 图表
      this._renderPie("ana-source", r.by_source || []);
      this._renderBar("ana-cat", r.by_category || [], { horizontal: true, paletteIdx: 1 });
      this._renderTrend("ana-date", series);
      this._renderBar("ana-value", r.value_by_category || [], { horizontal: false, paletteIdx: 3 });
      this._renderBar("ana-source-h", r.by_source || [], { horizontal: true, paletteIdx: 2 });
    } catch (e) {
      toast(e.message, "error");
    }
  },

  /** 数据存储：确认后把当前 4 个 KPI（样本总量/日均采集/峰值/覆盖来源）存入数据库 */
  async save() {
    if (!this._kpi) {
      toast("请先点「刷新分析」生成数据", "error");
      return;
    }
    if (!confirm("确认存储数据？")) return;
    try {
      await API.post("/api/analysis/snapshot", this._kpi);
      toast("已存储", "success");
    } catch (e) {
      toast(e.message, "error");
    }
  },

  // ---------- KPI / Spark ----------
  _setKpi(id, value, sparkData, paletteIdx) {
    const numEl = document.getElementById(id);
    if (numEl) numEl.textContent = (value || 0).toLocaleString();
    // 环比趋势（▲/▼ X% vs 上周期）已按需求屏蔽，不再显示。
    const trendEl = document.getElementById(id + "-trend");
    if (trendEl) {
      trendEl.classList.remove("up", "down");
      trendEl.textContent = "";
    }
    const sparkHost = document.getElementById(id + "-spark");
    if (sparkHost && sparkData && sparkData.length) {
      const palette = _palette();
      const color = palette[paletteIdx % palette.length] || _accentOklch(1);
      this._renderSpark(sparkHost, sparkData, color);
    }
  },

  _renderSpark(host, data, color) {
    const seriesData = Array.isArray(data) ? data : [];
    const ec = this._ec[host.id] || (this._ec[host.id] = echarts.init(host));
    wireChartHoverClear(host, ec);
    ec.clear();
    ec.setOption({
      animation: false,
      grid: { left: 0, right: 0, top: 2, bottom: 2 },
      xAxis: { type: "category", show: false, data: seriesData.map((_, i) => i) },
      yAxis: { type: "value", show: false },
      tooltip: { show: false },
      series: [{
        type: "line", data: seriesData, smooth: true, symbol: "none",
        lineStyle: { width: 1.5, color },
        areaStyle: {
          color: {
            type: "linear", x: 0, y: 0, x2: 0, y2: 1,
            colorStops: [
              { offset: 0, color: this._withAlpha(color, 0.34) },
              { offset: 1, color: this._withAlpha(color, 0) },
            ],
          },
        },
      }],
    });
  },

  // ---------- Charts ----------
  _renderPie(id, data) {
    const host = document.getElementById(id);
    if (!host) return;
    const list = Array.isArray(data) ? data : [];
    const ec = this._ec[id] || (this._ec[id] = echarts.init(host));
    wireChartHoverClear(host, ec);
    const base = _baseEcharts();
    ec.setOption(Object.assign(_anim({
      animationDuration: 700,
      animationDurationUpdate: 500,
    }), {
      backgroundColor: "transparent",
      textStyle: base.text,
      color: base.palette.length ? base.palette : undefined,
      tooltip: _tooltip({ trigger: "item" }),
      legend: { orient: "vertical", right: 10, top: "center", icon: "circle", textStyle: { color: base.fgDim, fontSize: 11 } },
      series: [{
        type: "pie",
        radius: ["52%", "78%"],
        center: ["38%", "50%"],
        avoidLabelOverlap: false,
        itemStyle: { borderColor: base.bg1, borderWidth: 2 },
        label: { show: false },
        labelLine: { show: false },
        emphasis: { disabled: true },
        data: list,
      }],
    }), true);
  },

  _renderBar(id, data, opts = {}) {
    const host = document.getElementById(id);
    if (!host) return;
    const list = (Array.isArray(data) ? data : []).filter(d => d && d.name != null);
    const hasValue = list.some(d => Number(d.value) > 0);
    const ec = this._ec[id] || (this._ec[id] = echarts.init(host));
    wireChartHoverClear(host, ec);
    const base = _baseEcharts();
    if (!list.length || !hasValue) {
      ec.setOption(Object.assign(_anim(), {
        backgroundColor: "transparent",
        title: {
          text: list.length ? "暂无数值数据" : "暂无数据",
          left: "center", top: "center",
          textStyle: { color: base.fgDim, fontSize: 12, fontWeight: 400 },
        },
        xAxis: { show: false }, yAxis: { show: false },
        series: [],
      }), true);
      return;
    }
    const { horizontal = false, paletteIdx = 0 } = opts;
    const paletteN = (base.palette && base.palette.length) || 0;
    const color = paletteN ? (base.palette[paletteIdx % paletteN] || _accentOklch(1)) : _accentOklch(1);
    const cats = list.map(d => d.name);
    const vals = list.map(d => d.value);
    const cat = (axisDef) => Object.assign({
      type: "category", data: cats,
      axisLine: { lineStyle: { color: base.line } },
      axisLabel: { color: base.fgDim, fontSize: 11, rotate: horizontal ? 0 : 0 },
      axisTick: { show: false }, splitLine: { show: false },
    }, axisDef || {});
    const val = (axisDef) => Object.assign({
      type: "value",
      axisLine: { show: false }, axisTick: { show: false },
      axisLabel: { color: base.fgDim, fontSize: 11 },
      splitLine: { lineStyle: { color: base.line, type: "dashed" } },
    }, axisDef || {});
    ec.setOption(Object.assign(_anim(), {
      backgroundColor: "transparent",
      textStyle: base.text,
      grid: { left: 10, right: 18, top: 18, bottom: 24, containLabel: true },
      tooltip: _tooltip({ trigger: "axis", axisPointer: { type: "none" } }),
      xAxis: horizontal ? val() : cat(),
      yAxis: horizontal ? cat() : val(),
      series: [{
        type: "bar",
        data: vals,
        barMaxWidth: 22,
        itemStyle: {
          borderRadius: horizontal ? [0, 4, 4, 0] : [4, 4, 0, 0],
          color: {
            type: "linear",
            x: 0, y: horizontal ? 0 : 1, x2: horizontal ? 1 : 0, y2: 0,
            colorStops: [
              { offset: 0, color: this._withAlpha(color, 0.25) },
              { offset: 1, color },
            ],
          },
        },
        emphasis: { disabled: true },
      }],
    }), true);
  },

  _renderTrend(id, series) {
    const host = document.getElementById(id);
    if (!host) return;
    const list = Array.isArray(series) ? series : [];
    const ec = this._ec[id] || (this._ec[id] = echarts.init(host));
    wireChartHoverClear(host, ec);
    const base = _baseEcharts();
    const c0 = (base.palette && base.palette[0]) || _accentOklch(1);
    const values = list.map(d => d.value);
    ec.setOption(Object.assign(_anim(), {
      backgroundColor: "transparent",
      textStyle: base.text,
      color: [c0],
      grid: { left: 10, right: 18, top: 12, bottom: 24, containLabel: true },
      tooltip: _tooltip({
        trigger: "axis",
        axisPointer: {
          type: "line",
          snap: false,
          animation: false,
          lineStyle: { color: c0, opacity: 0.45, width: 1 },
        },
      }),
      xAxis: {
        type: "category", boundaryGap: false, data: list.map(d => d.date),
        axisLine: { lineStyle: { color: base.line } },
        axisLabel: { color: base.fgDim, fontSize: 11 },
        axisTick: { show: false }, splitLine: { show: false },
      },
      yAxis: {
        type: "value",
        axisLine: { show: false }, axisTick: { show: false },
        axisLabel: { color: base.fgDim, fontSize: 11 },
        splitLine: { lineStyle: { color: base.line, type: "dashed" } },
      },
      series: [{
        name: "入库量",
        type: "line",
        data: values,
        smooth: true,
        symbol: "none",
        lineStyle: { width: 2, color: c0 },
        areaStyle: {
          color: {
            type: "linear", x: 0, y: 0, x2: 0, y2: 1,
            colorStops: [
              { offset: 0, color: this._withAlpha(c0, 0.34) },
              { offset: 1, color: this._withAlpha(c0, 0) },
            ],
          },
        },
        emphasis: { disabled: true },
      }],
    }), true);
  },

  // ---------- helpers ----------
  _withAlpha(color, a) {
    if (!color) return `rgba(0,0,0,${a})`;
    const s = String(color).trim();
    // rgb(r,g,b) / rgba(r,g,b,x) -> rgba(r,g,b,a)
    const m = s.match(/^rgba?\(\s*([\d.]+)[,\s]+([\d.]+)[,\s]+([\d.]+)/i);
    if (m) return `rgba(${m[1]}, ${m[2]}, ${m[3]}, ${a})`;
    // 颜色统一为 rgb（见 app.js 的 _accentOklch/_palette），不再有 oklch；兜底直接返回原值。
    return s;
  },
  _zeroFill(byDate, span) {
    const map = Object.create(null);
    (byDate || []).forEach(d => { map[d.date] = d.value; });
    const out = [];
    const today = new Date();
    for (let i = span - 1; i >= 0; i--) {
      const d = new Date(today); d.setDate(today.getDate() - i);
      const k = d.toISOString().slice(0, 10);
      out.push({ date: `${d.getMonth() + 1}/${d.getDate()}`, value: map[k] || 0 });
    }
    return out;
  },
  _fakeSpark(seed, n) {
    const out = [];
    const s = (seed || 1) + n;
    for (let i = 0; i < n; i++) {
      out.push(Math.max(0, Math.round((seed || 0) * 0.5 + Math.sin(i * 0.5 + s) * Math.max(1, (seed || 1) * 0.08))));
    }
    return out;
  },
  _deltaFromSpark(arr) {
    if (!arr || arr.length < 4) return null;
    const half = Math.floor(arr.length / 2);
    const a = arr.slice(0, half).reduce((s, v) => s + v, 0);
    const b = arr.slice(half).reduce((s, v) => s + v, 0);
    if (a === 0 && b === 0) return null;
    if (a === 0) return { up: true, label: "+∞" };
    const pct = ((b - a) / a) * 100;
    return { up: pct >= 0, label: (pct >= 0 ? "+" : "") + pct.toFixed(1) + "%" };
  },
};

// 窗口 resize 由 app.js 的全局监听统一处理（只 resize 当前可见页的图表）。
