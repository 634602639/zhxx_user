// API 封装
const API = {
  base: "",

  async _req(url, opts = {}) {
    opts.headers = opts.headers || {};
    if (opts.body && typeof opts.body === "object" && !(opts.body instanceof FormData)) {
      opts.headers["Content-Type"] = "application/json";
      opts.body = JSON.stringify(opts.body);
    }
    const r = await fetch(this.base + url, opts);
    if (!r.ok) {
      let msg = "请求失败 " + r.status;
      try { const e = await r.json(); msg = e.msg || msg; } catch (_) {}
      // 会话失效：弹回登录页（状态接口本身不触发，避免循环）
      if (r.status === 401 && window.Auth && !url.includes("/api/auth/status")) {
        window.Auth.showLogin();
      }
      throw new Error(msg);
    }
    return r.json();
  },
  get(url) { return this._req(url); },
  post(url, body) { return this._req(url, { method: "POST", body: body || {} }); },
  put(url, body) { return this._req(url, { method: "PUT", body: body || {} }); },
  del(url) { return this._req(url, { method: "DELETE" }); },
  upload(url, formData) { return this._req(url, { method: "POST", body: formData }); },
};

function toast(msg, type = "info") {
  const el = document.getElementById("toast");
  el.textContent = msg;
  el.className = "toast " + (type === "error" ? "error" : type === "success" ? "success" : "");
  setTimeout(() => el.classList.add("hidden"), 2400);
  el.classList.remove("hidden");
}
