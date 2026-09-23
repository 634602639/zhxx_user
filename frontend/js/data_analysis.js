// ========== 值勤数据分析（六单位运行态势） ==========
const Analysis = {
  _ec: {},
  _data: null,

  async refresh() {
    try {
      this._ensureRange();
      const from = (document.getElementById("ana-date-from")?.value || "").trim();
      const to = (document.getElementById("ana-date-to")?.value || "").trim();
      if (!from || !to) {
        toast("请填写时间范围", "error");
        return;
      }
      if (from > to) {
        toast("结束时间不能早于起始时间", "error");
        return;
      }
      const qs = new URLSearchParams({ date_from: from, date_to: to });
      const r = (await API.get(`/api/analysis/theater?${qs}`)).data || {};
      this._data = r;
      this._fillUnitOptions(r.units || []);
      const tag = document.getElementById("ana-trend-tag");
      if (tag) tag.textContent = r.from_demo ? "预置指标" : "数据对应时间";
      this._paint();
    } catch (e) {
      toast(e.message, "error");
    }
  },

  onFilterChange() {
    if (!this._data) return;
    this._paint();
  },

  _paint() {
    Object.values(this._ec || {}).forEach((ec) => { try { ec && ec.clear(); } catch (_) {} });
    const kpis = this._kpisForFilter();
    this._setKpi("ana-kpi-rate", kpis.node_online_rate, 0);
    this._setKpi("ana-kpi-eq", kpis.equipment_ok_rate, 1);
    this._setKpi("ana-kpi-user", kpis.access_network_user, 3);
    this._setKpi("ana-kpi-nodes", kpis.node_ratio, 2);

    const kind = this._chartKind();
    const dates = ((this._data || {}).daily || {}).dates || [];
    const rateKeys = (this._data.rate_keys || []).length
      ? this._data.rate_keys
      : [
        { key: "node_online_rate", label: "节点在线率" },
        { key: "equipment_ok_rate", label: "设备完好率" },
        { key: "js_resource_pct", label: "计算资源使用率" },
        { key: "storage_resource_pct", label: "存储空间使用率" },
      ];
    const volKeys = (this._data.volume_keys || []).length
      ? this._data.volume_keys
      : [
        { key: "access_network_user", label: "入网用户" },
        { key: "data_service_volume", label: "数据服务量" },
        { key: "doc_interaction", label: "文档交互量" },
      ];

    if (kind === "pie") {
      this._renderPie("ana-rates", this._pieRates(rateKeys), { percent: true });
      this._renderPie("ana-volumes", this._pieVolumes(volKeys), { percent: false });
      this._renderPie("ana-trend", this._pieOnline(), { percent: false });
    } else {
      this._renderTime("ana-rates", dates, this._timeRates(rateKeys), { percent: true, kind });
      this._renderTime("ana-volumes", dates, this._timeVolumes(volKeys), { percent: false, kind });
      this._renderTime("ana-trend", dates, this._timeNodes(), { percent: false, kind });
    }
  },

  _unit() {
    return (document.getElementById("ana-unit")?.value || "all").trim() || "all";
  },

  _chartKind() {
    const v = document.getElementById("ana-chart-type")?.value || "bar";
    if (v === "line" || v === "pie") return v;
    return "bar";
  },

  _fillUnitOptions(units) {
    const sel = document.getElementById("ana-unit");
    if (!sel) return;
    const keep = sel.value || "all";
    const opts = [`<option value="all">全部</option>`].concat(
      (units || []).map((u) => `<option value="${String(u.code || "").replace(/"/g, "")}">${this._esc(u.name || u.short || u.code)}</option>`)
    );
    sel.innerHTML = opts.join("");
    const ok = [...sel.options].some((o) => o.value === keep);
    sel.value = ok ? keep : "all";
  },

  _esc(s) {
    return String(s ?? "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;");
  },

  _ensureRange() {
    const fromEl = document.getElementById("ana-date-from");
    const toEl = document.getElementById("ana-date-to");
    if (!fromEl || !toEl) return;
    const pad = (n) => String(n).padStart(2, "0");
    const fmt = (d) => `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
    const to = new Date();
    const from = new Date(to.getTime() - 7 * 24 * 3600 * 1000);
    if (!fromEl.value) fromEl.value = fmt(from);
    if (!toEl.value) toEl.value = fmt(to);
  },

  _dailySrc() {
    const daily = (this._data || {}).daily || {};
    const unit = this._unit();
    if (unit === "all") return daily.all || {};
    return (daily.by_unit || {})[unit] || {};
  },

  _timeRates(keys) {
    const src = this._dailySrc();
    return (keys || []).map((k) => ({
      name: k.label || k.key,
      values: (src[k.key] || []).map((v) => this._roundPct(v)),
    }));
  },

  _timeVolumes(keys) {
    const src = this._dailySrc();
    return (keys || []).map((k) => ({ name: k.label || k.key, values: src[k.key] || [] }));
  },

  _timeOnline() {
    const daily = (this._data || {}).daily || {};
    const unit = this._unit();
    if (unit !== "all") {
      const src = (daily.by_unit || {})[unit] || {};
      return [
        { name: "在线节点", values: src.online_counts || [] },
        { name: "节点总数", values: src.all_counts || [] },
      ];
    }
    return (this._data.units || []).map((u) => ({
      name: u.short || u.name || u.code,
      values: ((daily.by_unit || {})[u.code] || {}).online_counts || [],
    }));
  },

  _timeNodes() {
    return this._timeOnline();
  },

  _latestNum(code, key) {
    const row = ((this._data || {}).latest || {})[code] || {};
    const v = row[key];
    return v == null || v === "" ? null : Number(v);
  },

  _pieItems(pairs) {
    return (pairs || [])
      .map(([name, value]) => ({ name, value: value == null ? 0 : Number(value) }))
      .filter((d) => Number.isFinite(d.value) && d.value > 0);
  },

  _aggLatest(key, mode) {
    const units = (this._data || {}).units || [];
    const vals = units.map((u) => this._latestNum(u.code, key));
    const known = vals.filter((v) => v != null && Number.isFinite(v));
    if (!known.length) return null;
    if (mode === "sum") return known.reduce((s, v) => s + v, 0);
    if (mode === "weighted") {
      const weights = units.map((u) => this._latestNum(u.code, "all_counts"));
      let num = 0, den = 0;
      units.forEach((u, i) => {
        if (vals[i] == null) return;
        const w = weights[i] != null && weights[i] > 0 ? weights[i] : 1;
        num += vals[i] * w;
        den += w;
      });
      return den ? num / den : null;
    }
    return known.reduce((s, v) => s + v, 0) / known.length;
  },

  _pieRates(keys) {
    const unit = this._unit();
    return this._pieItems((keys || []).map((k) => {
      const v = unit === "all"
        ? this._aggLatest(k.key, k.key === "node_online_rate" ? "weighted" : "mean")
        : this._latestNum(unit, k.key);
      return [k.label || k.key, this._roundPct(v)];
    }));
  },

  _pieVolumes(keys) {
    const unit = this._unit();
    return this._pieItems((keys || []).map((k) => {
      const v = unit === "all" ? this._aggLatest(k.key, "sum") : this._latestNum(unit, k.key);
      return [k.label || k.key, v];
    }));
  },

  _pieOnline() {
    const unit = this._unit();
    const units = (this._data || {}).units || [];
    if (unit === "all") {
      return this._pieItems(units.map((u) => [u.short || u.name, this._latestNum(u.code, "online_counts")]));
    }
    const online = this._latestNum(unit, "online_counts");
    const all = this._latestNum(unit, "all_counts");
    const off = (online != null && all != null) ? Math.max(0, all - online) : null;
    return this._pieItems([["在线节点", online], ["离线节点", off]]);
  },

  _kpisForFilter() {
    const unit = this._unit();
    if (unit === "all") return (this._data || {}).kpis || {};
    const L = ((this._data || {}).latest || {})[unit] || {};
    const D = ((((this._data || {}).daily || {}).by_unit) || {})[unit] || {};
    const online = L.online_counts;
    const all = L.all_counts;
    const ratio = (online == null && all == null)
      ? "—"
      : `${this._fmtInt(online)}/${this._fmtInt(all)}`;
    return {
      node_online_rate: { display: this._fmtPct(L.node_online_rate), spark: D.node_online_rate || [] },
      equipment_ok_rate: { display: this._fmtPct(L.equipment_ok_rate), spark: D.equipment_ok_rate || [] },
      access_network_user: { display: this._fmtInt(L.access_network_user), spark: D.access_network_user || [] },
      node_ratio: { display: ratio, spark: D.online_counts || [] },
    };
  },

  _fmtPct(v) {
    if (v == null || v === "" || Number.isNaN(Number(v))) return "—";
    return `${Number(v).toFixed(2)}%`;
  },

  _roundPct(v) {
    if (v == null || v === "" || Number.isNaN(Number(v))) return null;
    return Number(Number(v).toFixed(2));
  },

  _fmtInt(v) {
    if (v == null || v === "" || Number.isNaN(Number(v))) return "—";
    return String(Math.round(Number(v)));
  },

  _dateLabels(dates) {
    return (dates || []).map((d) => {
      const m = String(d).match(/(\d{4})-(\d{2})-(\d{2})/);
      return m ? `${Number(m[2])}/${Number(m[3])}` : d;
    });
  },

  _setKpi(id, kpi, paletteIdx) {
    const info = kpi || {};
    const numEl = document.getElementById(id);
    if (numEl) numEl.textContent = info.display || "—";
    const unitEl = document.getElementById(id + "-unit");
    if (unitEl) unitEl.textContent = "";
    const sparkHost = document.getElementById(id + "-spark");
    const spark = Array.isArray(info.spark) ? info.spark.filter((v) => v != null) : [];
    if (sparkHost && spark.length) {
      const palette = _palette();
      const color = palette[paletteIdx % palette.length] || _accentOklch(1);
      this._renderSpark(sparkHost, info.spark, color);
    } else if (sparkHost) {
      const ec = this._ec[sparkHost.id];
      if (ec) { try { ec.clear(); } catch (_) {} }
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

  _emptyChart(ec, base, text) {
    ec.setOption(Object.assign(_anim(), {
      backgroundColor: "transparent",
      title: {
        text: text || "暂无数据",
        left: "center", top: "center",
        textStyle: { color: base.fgDim, fontSize: 12, fontWeight: 400 },
      },
      legend: { show: false },
      xAxis: { show: false }, yAxis: { show: false },
      series: [],
    }), true);
  },

  _collectSeriesNums(list) {
    const nums = [];
    for (const s of list || []) {
      for (const v of s.values || []) {
        const n = Number(v);
        if (Number.isFinite(n)) nums.push(n);
      }
    }
    return nums;
  },

  /**
   * 百分率若锁死 0～100，88% 与 94% 柱高几乎一样。
   * 按本期数据收窄纵轴（略低于最小值），把日间差异拉开；不从 100 起，以免柱子被截没。
   */
  _yAxisRange(list, percent) {
    const nums = this._collectSeriesNums(list);
    if (!nums.length) {
      return percent ? { min: 0, max: 100 } : { min: 0, max: null };
    }
    const dmin = Math.min.apply(null, nums);
    const dmax = Math.max.apply(null, nums);
    if (percent) {
      const span = Math.max(6, dmax - dmin);
      const pad = Math.max(1.5, span * 0.18);
      let min = Math.floor((dmin - pad) / 5) * 5;
      let max = Math.ceil((dmax + pad) / 5) * 5;
      min = Math.max(0, min);
      max = Math.min(100, Math.max(max, min + 5));
      if (dmax >= 96) max = 100;
      if (max - min < 5) min = Math.max(0, max - 5);
      return { min, max };
    }
    const span = dmax - dmin;
    const rel = dmax > 0 ? span / dmax : 1;
    if (dmin <= 0 || rel >= 0.22) {
      return { min: 0, max: null };
    }
    const pad = Math.max(span * 0.22, dmax * 0.04, 1);
    let min = dmin - pad;
    if (min < 0) min = 0;
    const mag = Math.pow(10, Math.max(0, Math.floor(Math.log10(Math.max(min, 1))) - 1));
    min = Math.floor(min / mag) * mag;
    return { min, max: null };
  },

  _renderTime(id, dates, seriesIn, opts = {}) {
    const host = document.getElementById(id);
    if (!host) return;
    const ec = this._ec[id] || (this._ec[id] = echarts.init(host));
    wireChartHoverClear(host, ec);
    const base = _baseEcharts();
    const kind = opts.kind === "line" ? "line" : "bar";
    const list = Array.isArray(seriesIn) ? seriesIn : [];
    const hasValue = dates.length && list.some((s) => (s.values || []).some((v) => v != null));
    if (!hasValue) {
      this._emptyChart(ec, base, "该范围内暂无按日数据");
      return;
    }
    const percent = !!opts.percent;
    const palette = base.palette && base.palette.length ? base.palette : _palette();
    const labels = this._dateLabels(dates);
    const c0 = palette[0] || _accentOklch(1);
    const series = list.map((s, i) => {
      const color = palette[i % palette.length] || c0;
      const item = {
        name: s.name || "",
        type: kind,
        data: s.values || [],
      };
      if (kind === "bar") {
        item.barMaxWidth = list.length >= 4 ? 12 : 18;
        item.barGap = "28%";
        item.barCategoryGap = "42%";
        item.showBackground = true;
        item.backgroundStyle = {
          color: "rgba(128,128,128,0.07)",
          borderRadius: [8, 8, 2, 2],
        };
        item.itemStyle = {
          borderRadius: [8, 8, 2, 2],
          color: {
            type: "linear", x: 0, y: 0, x2: 0, y2: 1,
            colorStops: [
              { offset: 0, color },
              { offset: 1, color: this._withAlpha(color, 0.38) },
            ],
          },
          shadowBlur: 6,
          shadowColor: this._withAlpha(color, 0.22),
          shadowOffsetY: 2,
        };
        item.emphasis = {
          focus: "self",
          itemStyle: {
            shadowBlur: 12,
            shadowColor: this._withAlpha(color, 0.4),
          },
        };
      } else {
        const fillTop = this._withAlpha(color, list.length > 3 ? 0.14 : 0.28);
        item.smooth = 0.4;
        item.smoothMonotone = "x";
        item.symbol = "emptyCircle";
        item.symbolSize = 8;
        item.showSymbol = false;
        item.connectNulls = true;
        item.z = list.length - i;
        item.lineStyle = {
          width: 2.5,
          color,
          cap: "round",
          join: "round",
          shadowBlur: 10,
          shadowColor: this._withAlpha(color, 0.35),
          shadowOffsetY: 4,
        };
        item.itemStyle = {
          color,
          borderColor: base.bg1,
          borderWidth: 2,
        };
        item.areaStyle = {
          color: {
            type: "linear", x: 0, y: 0, x2: 0, y2: 1,
            colorStops: [
              { offset: 0, color: fillTop },
              { offset: 1, color: this._withAlpha(color, 0) },
            ],
          },
        };
        item.emphasis = {
          focus: "series",
          scale: true,
          itemStyle: { borderWidth: 2 },
          lineStyle: { width: 3.2 },
        };
      }
      return item;
    });
    const yRange = this._yAxisRange(list, percent);
    const yAxis = {
      type: "value",
      min: yRange.min,
      scale: !percent && yRange.min > 0,
      axisLine: { show: false }, axisTick: { show: false },
      axisLabel: {
        color: base.fgDim, fontSize: 11,
        formatter: percent ? "{value}%" : undefined,
      },
      splitLine: { lineStyle: { color: base.line, type: "dashed" } },
    };
    if (yRange.max != null) yAxis.max = yRange.max;
    ec.setOption(Object.assign(_anim(), {
      backgroundColor: "transparent",
      textStyle: base.text,
      color: palette,
      legend: {
        top: 0, right: 8, icon: "roundRect", itemWidth: 12, itemHeight: 6, itemGap: 12,
        textStyle: { color: base.fgDim, fontSize: 11 },
      },
      grid: { left: 10, right: 16, top: 36, bottom: 24, containLabel: true },
      tooltip: _tooltip(kind === "line"
        ? {
            trigger: "axis",
            axisPointer: {
              type: "line",
              snap: true,
              animation: false,
              lineStyle: { color: c0, opacity: 0.28, width: 1.5, type: "solid" },
            },
            valueFormatter: percent
              ? (v) => (v == null || v === "" ? "—" : `${Number(v).toFixed(2)}%`)
              : undefined,
          }
        : {
            trigger: "item",
            axisPointer: { type: "none" },
            formatter: (p) => {
              if (!p) return "";
              const raw = p.value;
              const val = (raw == null || raw === "")
                ? "—"
                : (percent ? `${Number(raw).toFixed(2)}%` : raw);
              return `${p.marker}${p.seriesName}<br/>${p.name}：${val}`;
            },
          }),
      xAxis: {
        type: "category",
        data: labels,
        boundaryGap: kind === "bar",
        axisLine: { lineStyle: { color: base.line } },
        axisLabel: { color: base.fgDim, fontSize: 11 },
        axisTick: { show: false }, splitLine: { show: false },
      },
      yAxis,
      series,
    }), true);
  },

  _renderPie(id, data, opts = {}) {
    const host = document.getElementById(id);
    if (!host) return;
    const ec = this._ec[id] || (this._ec[id] = echarts.init(host));
    wireChartHoverClear(host, ec);
    const base = _baseEcharts();
    const list = Array.isArray(data) ? data : [];
    const hasValue = list.some((d) => Number(d.value) > 0);
    if (!list.length || !hasValue) {
      this._emptyChart(ec, base, "暂无数据");
      return;
    }
    const percent = !!opts.percent;
    const palette = base.palette && base.palette.length ? base.palette : _palette();
    ec.setOption(Object.assign(_anim({
      animationDuration: 700,
      animationDurationUpdate: 500,
    }), {
      backgroundColor: "transparent",
      textStyle: base.text,
      color: palette,
      tooltip: _tooltip({
        trigger: "item",
        formatter: percent
          ? (p) => `${p.marker}${p.name} ${Number(p.value).toFixed(2)}%`
          : undefined,
      }),
      legend: {
        bottom: 8, left: "center", orient: "horizontal", icon: "circle",
        itemGap: 16, itemWidth: 10, itemHeight: 10,
        textStyle: { color: base.fgDim, fontSize: 11 },
      },
      series: [{
        type: "pie",
        radius: ["46%", "70%"],
        center: ["50%", "46%"],
        avoidLabelOverlap: false,
        itemStyle: { borderColor: base.bg1, borderWidth: 2 },
        label: { show: false },
        labelLine: { show: false },
        emphasis: { disabled: true },
        data: list,
      }],
    }), true);
  },

  _withAlpha(color, a) {
    if (!color) return `rgba(0,0,0,${a})`;
    const s = String(color).trim();
    const m = s.match(/^rgba?\(\s*([\d.]+)[,\s]+([\d.]+)[,\s]+([\d.]+)/i);
    if (m) return `rgba(${m[1]}, ${m[2]}, ${m[3]}, ${a})`;
    return s;
  },
};
