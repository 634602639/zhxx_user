// ========== 前端权限（RBAC：按当前用户的权限点隐藏菜单与按钮） ==========
// 登录态接口（/api/auth/status、/api/login）下发：
//   { is_super: bool, perms: ["collect:view", ...] }
// 约定：
//   - 菜单可见性看  <module>:view （module = li.menu-item 的 data-page）
//   - 写/导出按钮加属性  data-perm="<code>"，无权限则由动态样式表隐藏
//   - 超级管理员(is_super) 或权限含 "*" 时拥有全部权限

// 需要做「按钮级隐藏」的非 view 权限点（与后端 permissions.py 目录一致）。
// 列在这里，未具备时统一注入 display:none 规则——动态渲染出来的按钮也会被覆盖。
const PERM_GATED_CODES = [
  "collect:edit",
  "analysis:save",
  "generate:edit",
  "manage:edit",
  "manage:export",
  "users:edit",
  "roles:edit",
];

const Perm = {
  _set: new Set(),
  _super: false,
  _styleEl: null,

  /** 从登录态数据初始化（is_super / perms） */
  setFromStatus(data) {
    this._super = !!(data && data.is_super);
    this._set = new Set((data && data.perms) || []);
  },

  /** 是否拥有某权限点 */
  has(code) {
    return this._super || this._set.has("*") || this._set.has(code);
  },

  /** 模块（菜单）是否可见 */
  canModule(mod) {
    return this.has(mod + ":view");
  },

  /** 注入「拒绝样式」：对缺失的 data-perm 写 display:none，覆盖现有与将来渲染的按钮 */
  _injectDenyStyle() {
    const codes = new Set(PERM_GATED_CODES);
    // 兜底：把页面上已出现的 data-perm 也纳入（即便不在上面的列表）
    document.querySelectorAll("[data-perm]").forEach((el) => {
      const c = el.getAttribute("data-perm");
      if (c) codes.add(c);
    });
    const rules = [];
    codes.forEach((c) => {
      if (!this.has(c)) rules.push(`[data-perm="${c}"]{display:none!important;}`);
    });
    if (!this._styleEl) {
      this._styleEl = document.createElement("style");
      this._styleEl.id = "perm-deny-style";
      document.head.appendChild(this._styleEl);
    }
    this._styleEl.textContent = rules.join("\n");
  },

  /** 按权限隐藏菜单；若当前激活菜单不可见，则切到第一个可见菜单 */
  applyMenus() {
    const items = [...document.querySelectorAll(".menu-item[data-page]")];
    items.forEach((li) => {
      li.classList.toggle("perm-hidden", !this.canModule(li.dataset.page));
    });
    const active = document.querySelector(".menu-item.active");
    if (active && !active.classList.contains("perm-hidden")) return active.dataset.page;
    const first = items.find((li) => !li.classList.contains("perm-hidden"));
    document.querySelectorAll(".menu-item").forEach((i) => i.classList.remove("active"));
    document.querySelectorAll(".app-page").forEach((p) => p.classList.remove("active"));
    if (first) {
      first.classList.add("active");
      const pe = document.getElementById("page-" + first.dataset.page);
      if (pe) pe.classList.add("active");
      return first.dataset.page;
    }
    return null;  // 无任何可见菜单
  },

  /** 应用全部权限控制，返回当前应展示的页面 data-page（无可见菜单返回 null） */
  apply() {
    this._injectDenyStyle();
    return this.applyMenus();
  },
};
window.Perm = Perm;
