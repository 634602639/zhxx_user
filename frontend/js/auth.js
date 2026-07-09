// ========== 登录鉴权 ==========
const Auth = {
  _booted: false,

  /** 页面加载时调用：已登录则进入系统，否则显示登录页 */
  async boot() {
    try {
      const r = await API.get("/api/auth/status");
      if (r && r.data && r.data.logged_in) {
        this.enterApp(r.data.user);
        return;
      }
    } catch (_) { /* 状态接口异常时也回落到登录页 */ }
    this.showLogin();
  },

  showLogin() {
    const ov = document.getElementById("login-overlay");
    if (ov) ov.classList.remove("hidden");
    const u = document.getElementById("login-user");
    if (u) setTimeout(() => u.focus(), 50);
  },

  /** 隐藏登录页并首次加载主界面数据（只加载一次） */
  enterApp(user) {
    const ov = document.getElementById("login-overlay");
    if (ov) ov.classList.add("hidden");
    const who = document.getElementById("login-who");
    if (who) who.textContent = user ? `${user}` : "";
    if (!this._booted) {
      this._booted = true;
      if (window.PAGE_HOOKS && window.PAGE_HOOKS.collect) window.PAGE_HOOKS.collect();
    }
  },

  async login(ev) {
    if (ev) ev.preventDefault();
    const user = (document.getElementById("login-user")?.value || "").trim();
    const pass = document.getElementById("login-pass")?.value || "";
    const err = document.getElementById("login-err");
    if (err) err.textContent = "";
    if (!user || !pass) {
      if (err) err.textContent = "请输入用户名和密码";
      return;
    }
    try {
      const r = await API.post("/api/login", { username: user, password: pass });
      this.enterApp((r.data && r.data.user) || user);
      const p = document.getElementById("login-pass");
      if (p) p.value = "";
    } catch (e) {
      if (err) err.textContent = e.message || "登录失败";
    }
  },

  async logout() {
    try { await API.post("/api/logout", {}); } catch (_) {}
    location.reload();
  },
};
window.Auth = Auth;
