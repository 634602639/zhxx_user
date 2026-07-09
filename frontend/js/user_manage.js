// ========== 用户管理 ==========
const Users = {
  _items: [],

  async refresh() {
    try {
      const kw = (document.getElementById("user-q")?.value || "").trim();
      const qs = kw ? "?keyword=" + encodeURIComponent(kw) : "";
      const r = (await API.get("/api/users" + qs)).data || {};
      this._items = r.items || [];

      const meta = document.getElementById("user-meta");
      if (meta) meta.textContent = `共 ${r.total || 0} 个用户`;

      const tbody = document.querySelector("#user-table tbody");
      if (!tbody) return;
      if (!this._items.length) {
        tbody.innerHTML =
          '<tr><td colspan="5" class="muted" style="text-align:center;padding:12px;">无匹配用户</td></tr>';
        return;
      }
      tbody.innerHTML = this._items.map(u => {
        const cur = u.is_current
          ? ' <span class="tag accent" style="margin-left:4px;">当前</span>'
          : "";
        const delBtn = u.is_current
          ? '<button class="btn small danger" onclick="Users.delCurrentBlocked()">删除</button>'
          : `<button class="btn small danger" onclick="Users.del(${u.id})">删除</button>`;
        return `
        <tr>
          <td>${u.id}</td>
          <td>${escapeHtml(String(u.username || ""))}${cur}</td>
          <td>${u.created_at || ""}</td>
          <td>${u.updated_at || ""}</td>
          <td>
            <button class="btn small" onclick="Users.openEdit(${u.id})">编辑</button>
            ${delBtn}
          </td>
        </tr>`;
      }).join("");
    } catch (e) {
      toast(e.message, "error");
    }
  },

  _show() {
    document.getElementById("user-edit-modal")?.classList.remove("hidden");
    const err = document.getElementById("user-edit-err");
    if (err) err.textContent = "";
    setTimeout(() => document.getElementById("user-edit-name")?.focus(), 50);
  },
  closeModal() {
    document.getElementById("user-edit-modal")?.classList.add("hidden");
  },

  openCreate() {
    document.getElementById("user-edit-id").value = "";
    document.getElementById("user-edit-name").value = "";
    document.getElementById("user-edit-name").removeAttribute("readonly");
    const pass = document.getElementById("user-edit-pass");
    pass.value = "";
    pass.placeholder = "请输入密码";
    const pass2 = document.getElementById("user-edit-pass2");
    pass2.value = "";
    pass2.placeholder = "请再次输入密码";
    document.getElementById("user-edit-title").textContent = "新增用户";
    this._show();
  },

  openEdit(id) {
    const u = this._items.find(x => x.id === id);
    if (!u) return;
    document.getElementById("user-edit-id").value = u.id;
    document.getElementById("user-edit-name").value = u.username || "";
    const pass = document.getElementById("user-edit-pass");
    pass.value = "";
    pass.placeholder = "留空则不修改密码";
    const pass2 = document.getElementById("user-edit-pass2");
    pass2.value = "";
    pass2.placeholder = "留空则不修改密码";
    document.getElementById("user-edit-title").textContent = "编辑用户";
    this._show();
  },

  async save() {
    const id = document.getElementById("user-edit-id").value;
    const username = (document.getElementById("user-edit-name").value || "").trim();
    const password = document.getElementById("user-edit-pass").value || "";
    const password2 = document.getElementById("user-edit-pass2").value || "";
    const err = document.getElementById("user-edit-err");
    if (err) err.textContent = "";
    if (!username) { if (err) err.textContent = "请输入用户名"; return; }
    if (!id && !password) { if (err) err.textContent = "请输入密码"; return; }
    // 只要填了新密码，就要求两次一致（编辑时密码留空表示不修改）
    if (password || password2) {
      if (password !== password2) { if (err) err.textContent = "两次输入的密码不一致"; return; }
    }
    try {
      if (id) {
        const body = { username };
        if (password) body.password = password;
        await API.put(`/api/users/${id}`, body);
      } else {
        await API.post("/api/users", { username, password });
      }
      this.closeModal();
      toast("已保存", "success");
      this.refresh();
    } catch (e) {
      if (err) err.textContent = e.message || "保存失败";
    }
  },

  delCurrentBlocked() {
    toast("不能删除当前登录用户", "error");
  },

  async del(id) {
    const u = this._items.find(x => x.id === id);
    if (!confirm(`确认删除用户「${u ? u.username : id}」？`)) return;
    try {
      await API.del(`/api/users/${id}`);
      toast("已删除", "success");
      this.refresh();
    } catch (e) {
      toast(e.message, "error");
    }
  },
};

// 回车即查询
(function wireUserSearch() {
  const q = document.getElementById("user-q");
  if (!q || q._wiredUsers) return;
  q._wiredUsers = true;
  q.addEventListener("keydown", (ev) => {
    if (ev.key === "Enter") { ev.preventDefault(); Users.refresh(); }
  });
})();
