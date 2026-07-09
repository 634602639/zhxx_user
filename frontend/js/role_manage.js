// ========== 角色与权限管理 ==========
const Roles = {
  _items: [],
  _catalog: null,   // 权限点目录（懒加载，缓存）

  async refresh() {
    try {
      const kw = (document.getElementById("role-q")?.value || "").trim();
      const qs = kw ? "?keyword=" + encodeURIComponent(kw) : "";
      const r = (await API.get("/api/roles" + qs)).data || {};
      this._items = r.items || [];

      const meta = document.getElementById("role-meta");
      if (meta) meta.textContent = `共 ${r.total || 0} 个角色`;

      const tbody = document.querySelector("#role-table tbody");
      if (!tbody) return;
      if (!this._items.length) {
        tbody.innerHTML =
          '<tr><td colspan="6" class="muted" style="text-align:center;padding:12px;">暂无角色</td></tr>';
        return;
      }
      tbody.innerHTML = this._items.map(r => {
        const tags = [];
        if (r.is_super) tags.push('<span class="tag accent">全部权限</span>');
        if (r.is_builtin) tags.push('<span class="tag">内置</span>');
        const permView = r.is_super
          ? "全部权限"
          : (r.perms && r.perms.length ? `${r.perms.length} 项权限` : "无权限");
        const delBtn = r.is_builtin
          ? '<button class="btn btn-sm btn-outline-danger" data-perm="roles:edit" disabled title="内置角色不可删除">删除</button>'
          : `<button class="btn btn-sm btn-outline-danger" data-perm="roles:edit" onclick="Roles.del(${r.id})">删除</button>`;
        return `
        <tr>
          <td>${r.id}</td>
          <td>${escapeHtml(String(r.name || ""))} ${tags.join(" ")}</td>
          <td><span class="cell-mono muted">${escapeHtml(String(r.code || ""))}</span></td>
          <td>${permView}<div class="muted" style="font-size:12px;">${escapeHtml(String(r.description || ""))}</div></td>
          <td>${r.user_count != null ? r.user_count : 0}</td>
          <td>
            <button class="btn btn-sm" data-perm="roles:edit" onclick="Roles.openEdit(${r.id})">编辑</button>
            ${delBtn}
          </td>
        </tr>`;
      }).join("");
    } catch (e) {
      toast(e.message, "error");
    }
  },

  /** 懒加载权限点目录 */
  async _ensureCatalog() {
    if (this._catalog) return this._catalog;
    const r = (await API.get("/api/permissions")).data || {};
    this._catalog = r.catalog || [];
    return this._catalog;
  },

  /** 渲染权限复选树；checked 为已勾选的 code 集合（Set） */
  _renderTree(checked, locked) {
    const host = document.getElementById("role-perm-tree");
    if (!host) return;
    host.innerHTML = (this._catalog || []).map(grp => {
      const acts = grp.actions.map(a => {
        const on = locked || checked.has(a.code) ? "checked" : "";
        const dis = locked ? "disabled" : "";
        return `
          <label class="checkbox perm-act">
            <input type="checkbox" class="perm-cb" data-module="${grp.module}" value="${a.code}" ${on} ${dis} />
            <span>${escapeHtml(a.name)}</span>
          </label>`;
      }).join("");
      const allOn = locked || grp.actions.every(a => checked.has(a.code)) ? "checked" : "";
      const dis = locked ? "disabled" : "";
      return `
        <div class="perm-group">
          <label class="checkbox perm-group-head">
            <input type="checkbox" class="perm-module-cb" data-module="${grp.module}" ${allOn} ${dis} />
            <strong>${escapeHtml(grp.module_name)}</strong>
          </label>
          <div class="perm-acts">${acts}</div>
        </div>`;
    }).join("");

    // 模块表头复选：联动该模块下所有动作
    host.querySelectorAll(".perm-module-cb").forEach(mc => {
      mc.addEventListener("change", () => {
        const mod = mc.getAttribute("data-module");
        host.querySelectorAll(`.perm-cb[data-module="${mod}"]`).forEach(cb => { cb.checked = mc.checked; });
      });
    });
    // 动作复选：回写模块表头的勾选态
    host.querySelectorAll(".perm-cb").forEach(cb => {
      cb.addEventListener("change", () => {
        const mod = cb.getAttribute("data-module");
        const all = [...host.querySelectorAll(`.perm-cb[data-module="${mod}"]`)];
        const head = host.querySelector(`.perm-module-cb[data-module="${mod}"]`);
        if (head) head.checked = all.every(x => x.checked);
      });
    });
  },

  checkAll(on) {
    document.querySelectorAll("#role-perm-tree input[type=checkbox]").forEach(cb => {
      if (!cb.disabled) cb.checked = !!on;
    });
  },

  _show() {
    if (window.UI) UI.showModal("role-edit-modal");
    else document.getElementById("role-edit-modal")?.classList.remove("hidden");
    const err = document.getElementById("role-edit-err");
    if (err) err.textContent = "";
  },
  closeModal() {
    if (window.UI) UI.hideModal("role-edit-modal");
    else document.getElementById("role-edit-modal")?.classList.add("hidden");
  },

  async openCreate() {
    try { await this._ensureCatalog(); } catch (e) { toast(e.message, "error"); return; }
    document.getElementById("role-edit-id").value = "";
    document.getElementById("role-edit-name").value = "";
    const code = document.getElementById("role-edit-code");
    code.value = ""; code.disabled = false;
    document.getElementById("role-edit-desc").value = "";
    document.getElementById("role-edit-title").textContent = "新增角色";
    this._renderTree(new Set(), false);
    this._show();
    setTimeout(() => document.getElementById("role-edit-name")?.focus(), 50);
  },

  async openEdit(id) {
    try { await this._ensureCatalog(); } catch (e) { toast(e.message, "error"); return; }
    const r = this._items.find(x => x.id === id);
    if (!r) return;
    document.getElementById("role-edit-id").value = r.id;
    document.getElementById("role-edit-name").value = r.name || "";
    const code = document.getElementById("role-edit-code");
    code.value = r.code || ""; code.disabled = true;  // 标识创建后不可改
    document.getElementById("role-edit-desc").value = r.description || "";
    document.getElementById("role-edit-title").textContent = r.is_super ? "查看超级管理员（权限不可改）" : "编辑角色";
    this._renderTree(new Set(r.perms || []), !!r.is_super);
    this._show();
  },

  async save() {
    const id = document.getElementById("role-edit-id").value;
    const name = (document.getElementById("role-edit-name").value || "").trim();
    const code = (document.getElementById("role-edit-code").value || "").trim();
    const description = (document.getElementById("role-edit-desc").value || "").trim();
    const err = document.getElementById("role-edit-err");
    if (err) err.textContent = "";
    if (name.length < 2) { if (err) err.textContent = "角色名称至少 2 个字符"; return; }
    const perms = [...document.querySelectorAll("#role-perm-tree .perm-cb:checked")].map(cb => cb.value);
    try {
      if (id) {
        await API.put(`/api/roles/${id}`, { name, description, perms });
      } else {
        if (code.length < 2) { if (err) err.textContent = "角色标识至少 2 个字符"; return; }
        await API.post("/api/roles", { name, code, description, perms });
      }
      this.closeModal();
      toast("已保存", "success");
      this.refresh();
    } catch (e) {
      if (err) err.textContent = e.message || "保存失败";
    }
  },

  async del(id) {
    const r = this._items.find(x => x.id === id);
    if (!confirm(`确认删除角色「${r ? r.name : id}」？`)) return;
    try {
      await API.del(`/api/roles/${id}`);
      toast("已删除", "success");
      this.refresh();
    } catch (e) {
      toast(e.message, "error");
    }
  },
};
window.Roles = Roles;

// 回车即查询
(function wireRoleSearch() {
  const q = document.getElementById("role-q");
  if (!q || q._wiredRoles) return;
  q._wiredRoles = true;
  q.addEventListener("keydown", (ev) => {
    if (ev.key === "Enter") { ev.preventDefault(); Roles.refresh(); }
  });
})();
