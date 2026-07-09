// ========== 深色 / 浅色模式 ==========
// CSS：:root 为默认深色令牌；:root[data-mode="light"] 为浅色。
// 首屏的 data-mode 由 index.html <head> 内联脚本按本地/系统偏好提前设置（防闪烁）。
window.Theme = (function () {
  const KEY = "app-theme";
  const root = document.documentElement;

  function current() {
    return root.getAttribute("data-mode") === "dark" ? "dark" : "light";
  }

  function redrawCharts() {
    requestAnimationFrame(() => {
      const active = document.querySelector(".menu-item.active");
      if (active && active.dataset.page === "analysis" &&
          window.Analysis && typeof Analysis.refresh === "function") {
        try { Analysis.refresh(); } catch (_) {}
      }
    });
  }

  function apply(mode, persist) {
    mode = mode === "dark" ? "dark" : "light";
    root.setAttribute("data-mode", mode);
    if (persist !== false) {
      try { localStorage.setItem(KEY, mode); } catch (_) {}
    }
    redrawCharts();
  }

  function toggle() {
    apply(current() === "dark" ? "light" : "dark");
  }

  (function watchSystem() {
    if (!window.matchMedia) return;
    const mq = window.matchMedia("(prefers-color-scheme: dark)");
    const handler = (e) => {
      let saved = null;
      try { saved = localStorage.getItem(KEY); } catch (_) {}
      if (saved !== "light" && saved !== "dark") {
        apply(e.matches ? "dark" : "light", false);
      }
    };
    if (mq.addEventListener) mq.addEventListener("change", handler);
    else if (mq.addListener) mq.addListener(handler);
  })();

  return { toggle, apply, current };
})();
