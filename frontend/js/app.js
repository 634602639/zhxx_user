// 菜单切换 + 仪表盘
document.querySelectorAll(".menu-item").forEach(item => {
  item.addEventListener("click", () => {
    document.querySelectorAll(".menu-item").forEach(i => i.classList.remove("active"));
    document.querySelectorAll(".page").forEach(p => p.classList.remove("active"));
    item.classList.add("active");
    const page = item.dataset.page;
    const pageEl = document.getElementById("page-" + page);
    if (pageEl) pageEl.classList.add("active");
    if (window.PAGE_HOOKS && window.PAGE_HOOKS[page]) window.PAGE_HOOKS[page]();
    // 切页后让新激活页的图表 resize，纠正之前隐藏期间被压扁的尺寸
    requestAnimationFrame(() => {
      if (pageEl) resizeChartsIn(pageEl);
    });
  });
});

// 给定根元素，对其下所有 ECharts 容器执行 resize（只对当前可见、有尺寸的节点）。
function resizeChartsIn(scope) {
  const root = typeof scope === "string" ? document.getElementById(scope) : scope;
  if (!root || !window.echarts) return;
  root.querySelectorAll(".chart, .kpi-spark").forEach(host => {
    if (!host.offsetWidth || !host.offsetHeight) return;
    const ec = echarts.getInstanceByDom(host);
    if (ec) { try { ec.resize(); } catch (_) {} }
  });
}
window.resizeChartsIn = resizeChartsIn;

// ECharts hover 兜底清除：鼠标快速离开时，ECharts 的 `globalout` 偶发不触发，
// 导致 axisPointer.type=shadow 的柱状图阴影、line 的十字线一直留着。
// 同时绑定 echarts 的 globalout 与 DOM 的 mouseleave，重复但成本极低，能稳定复位。
function clearChartHoverState(ec) {
  if (!ec) return;
  try { ec.dispatchAction({ type: "hideTip" }); } catch (_) {}
  try { ec.dispatchAction({ type: "updateAxisPointer", currTrigger: "leave" }); } catch (_) {}
  try { ec.dispatchAction({ type: "downplay" }); } catch (_) {}
}
function wireChartHoverClear(host, ec) {
  if (!host || !ec || host._hoverClearWired) return;
  host._hoverClearWired = true;
  try { ec.on("globalout", () => clearChartHoverState(ec)); } catch (_) {}
  host.addEventListener("mouseleave", () => clearChartHoverState(ec));
}
window.clearChartHoverState = clearChartHoverState;
window.wireChartHoverClear = wireChartHoverClear;

window.PAGE_HOOKS = {
  collect: () => DataCollect.refresh(),
  analysis: () => Analysis.refresh(),
  generate: () => Generate.init(),
  manage: () => {
    Manage.ensureFilterDates();
    Manage.search();
  },
  logs: () => Logs.refresh(),
  users: () => Users.refresh(),
};

// ========== Theme helpers (read live CSS vars; OK across light/dark) ==========
function _cssVar(name) {
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
}
// oklch -> rgb：旧浏览器的 canvas(addColorStop) 不认 oklch，图表颜色统一转成 rgb。
function _oklchToRgb(L, C, H) {
  const hr = (H * Math.PI) / 180;
  const a = C * Math.cos(hr), b = C * Math.sin(hr);
  const l_ = L + 0.3963377774 * a + 0.2158037573 * b;
  const m_ = L - 0.1055613458 * a - 0.0638541728 * b;
  const s_ = L - 0.0894841775 * a - 1.2914855480 * b;
  const l = l_ * l_ * l_, m = m_ * m_ * m_, s = s_ * s_ * s_;
  const lr = 4.0767416621 * l - 3.3077115913 * m + 0.2309699292 * s;
  const lg = -1.2684380046 * l + 2.6097574011 * m - 0.3413193965 * s;
  const lb = -0.0041960863 * l - 0.7034186147 * m + 1.7076147010 * s;
  const f = (x) => {
    x = x <= 0.0031308 ? 12.92 * x : 1.055 * Math.pow(x, 1 / 2.4) - 0.055;
    return Math.round(Math.max(0, Math.min(1, x)) * 255);
  };
  return `rgb(${f(lr)}, ${f(lg)}, ${f(lb)})`;
}
window._oklchToRgb = _oklchToRgb;

// 对应 CSS --c1..c6 的 L/C/色相偏移；按当前 --accent-h 实时算成 rgb（不经过带 calc 的 CSS 变量）
function _palette(n = 6) {
  const h = parseFloat(_cssVar("--accent-h")) || 150;
  const defs = [
    [0.78, 0.15, 0], [0.74, 0.16, 60], [0.78, 0.15, 120],
    [0.76, 0.16, 180], [0.76, 0.15, 240], [0.78, 0.14, 300],
  ];
  return defs.slice(0, n).map(([L, C, off]) => _oklchToRgb(L, C, h + off));
}
function _accentOklch(alpha = 1, hueOffset = 0) {
  const h = parseFloat(_cssVar("--accent-h")) || 150;
  const c = parseFloat(_cssVar("--accent-c")) || 0.14;
  const l = parseFloat(_cssVar("--accent-l")) || 0.62;
  const rgb = _oklchToRgb(l, c, h + hueOffset);
  if (alpha >= 1) return rgb;
  const p = rgb.match(/\d+/g);
  return `rgba(${p[0]}, ${p[1]}, ${p[2]}, ${alpha})`;
}
function _baseEcharts() {
  return {
    fg: _cssVar("--fg") || "#0f172a",
    fgDim: _cssVar("--fg-dim") || "#475569",
    line: _cssVar("--line") || "rgba(15,30,60,0.08)",
    bg1: _cssVar("--bg-1") || "#fff",
    palette: _palette(),
    text: { color: _cssVar("--fg-dim") || "#64748b", fontFamily: "inherit" },
  };
}

// 图表入场/更新动画基准：入场略长一点带 cubicOut 缓动；更新走 cubicInOut 让数据形变更顺滑；
// stateAnimation 关 0 是为了 hover 状态切换不带过渡（配合各 series 的 emphasis.disabled 防抖动）。
function _anim(extra = {}) {
  return Object.assign({
    animation: true,
    animationThreshold: 4000,
    animationDuration: 600,
    animationEasing: "cubicOut",
    animationDurationUpdate: 450,
    animationEasingUpdate: "cubicInOut",
    stateAnimation: { duration: 0 },
  }, extra);
}
window._anim = _anim;

// 共享 tooltip 配置：pointer-events:none 防 cursor 擦到 tooltip 触发 mouseleave 抖动；
// transitionDuration:0 关掉 200ms 渐隐；confine:true 不让 tooltip 跑出图表外。
function _tooltip(extra = {}) {
  const base = _baseEcharts();
  return Object.assign({
    backgroundColor: base.bg1,
    borderColor: base.line,
    textStyle: { color: base.fg, fontSize: 12 },
    confine: true,
    transitionDuration: 0,
    extraCssText: "pointer-events:none; box-shadow:0 4px 16px rgba(0,0,0,0.18);",
  }, extra);
}




// 全局错误捕获：把任何冒泡未处理的异常打到控制台，附带 toast 定位
window.addEventListener("error", (ev) => {
  const e = ev && ev.error ? ev.error : ev;
  if (!e) return;
  const msg = (e && e.message) || String(e);
  if (!/length/i.test(msg)) return;
  console.error("[GlobalError]", e, "at", ev.filename + ":" + ev.lineno + ":" + ev.colno);
  try { toast(`${msg} @ ${ev.filename}:${ev.lineno}`, "error"); } catch (_) {}
});
window.addEventListener("unhandledrejection", (ev) => {
  const e = ev && ev.reason ? ev.reason : ev;
  console.error("[UnhandledRejection]", e);
});

function helpTip(text) {
  const raw = String(text || "");
  const esc = raw
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
  return `<span class="help-tip" tabindex="0" data-tip="${esc}" aria-label="${esc}"></span>`;
}
window.helpTip = helpTip;

const HelpTip = {
  el: null,
  _on: null,
  init() {
    if (this.el) return;
    this.el = document.createElement("div");
    this.el.id = "help-tip-float";
    this.el.className = "help-tip-float hidden";
    this.el.setAttribute("role", "tooltip");
    document.body.appendChild(this.el);
    const showFrom = (e) => {
      const t = e.target && e.target.closest ? e.target.closest(".help-tip") : null;
      if (t) this.show(t);
    };
    const hideFrom = (e) => {
      const t = e.target && e.target.closest ? e.target.closest(".help-tip") : null;
      if (!t) return;
      const next = e.relatedTarget;
      if (next && t.contains(next)) return;
      this.hide();
    };
    document.addEventListener("mouseover", showFrom);
    document.addEventListener("mouseout", hideFrom);
    document.addEventListener("focusin", showFrom);
    document.addEventListener("focusout", hideFrom);
    document.addEventListener("click", (e) => {
      const t = e.target && e.target.closest ? e.target.closest(".help-tip") : null;
      if (!t) return;
      e.preventDefault();
      e.stopPropagation();
      this.show(t);
    }, true);
    window.addEventListener("scroll", () => this.hide(), true);
    window.addEventListener("resize", () => this.hide());
  },
  show(t) {
    const text = (t.getAttribute("data-tip") || t.getAttribute("aria-label") || "").trim();
    if (!text || !this.el) return;
    this._on = t;
    this.el.textContent = text;
    this.el.classList.remove("hidden");
    const r = t.getBoundingClientRect();
    const w = this.el.offsetWidth;
    const h = this.el.offsetHeight;
    const gap = 8;
    let top = r.top - h - gap;
    if (top < 8) top = r.bottom + gap;
    let left = r.left + r.width / 2 - w / 2;
    left = Math.max(8, Math.min(left, window.innerWidth - w - 8));
    this.el.style.top = `${Math.round(top)}px`;
    this.el.style.left = `${Math.round(left)}px`;
  },
  hide() {
    if (!this.el) return;
    this._on = null;
    this.el.classList.add("hidden");
  },
};
window.HelpTip = HelpTip;

window.addEventListener("load", () => {
  HelpTip.init();
  // 先校验登录：已登录则进入并加载首页数据，否则显示登录页
  if (window.Auth) window.Auth.boot();
  else if (window.PAGE_HOOKS && window.PAGE_HOOKS.collect) window.PAGE_HOOKS.collect();
});

// 全局窗口 resize：只 resize 当前可见页里有尺寸的图表，
// 隐藏页（display:none，offsetWidth=0）跳过；切回该页时 menu 点击处理会补一次 resize。
let _resizeRaf = null;
window.addEventListener("resize", () => {
  if (_resizeRaf) cancelAnimationFrame(_resizeRaf);
  _resizeRaf = requestAnimationFrame(() => {
    document.querySelectorAll(".page.active").forEach(p => resizeChartsIn(p));
  });
});
