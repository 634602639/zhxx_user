function escapeHtml(s) {
  return String(s ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function zhStatus(s) {
  const v = String(s || "").toLowerCase();
  if (v === "stored") return "已入库";
  if (v === "pending" || v === "") return "待入库";
  return s || "";
}

const DataCollect = {
  _eps: [],
  _previewRows: [],

  showRawPreview(data, opts = {}) {
    const incomingRows = data.raw_items || [];
    const append = !!opts.append;
    if (append) {
      this._previewRows = (this._previewRows || []).concat(incomingRows);
    } else {
      this._previewRows = incomingRows.slice();
    }
    const rows = this._previewRows;
    const sec = document.getElementById("raw-preview-section");
    const hint = document.getElementById("raw-preview-hint");
    const tbody = document.querySelector("#raw-preview-table tbody");
    const tableBlock = document.getElementById("raw-preview-table-block");
    if (!sec) return;

    const hasRows = rows.length > 0;

    if (tableBlock) {
      tableBlock.classList.remove("hidden");
    }
    if (tbody) {
      tbody.innerHTML = "";
    }

    if (!hasRows) {
      if (hint) hint.textContent = "暂无解析预览。点采集后会展示原文，可在每条下方选中文本暂存为标签。";
      if (tbody) {
        tbody.innerHTML = `<tr><td colspan="7" class="muted" style="text-align:center;padding:24px;">暂无数据</td></tr>`;
      }
      return;
    }

    if (hasRows && tbody && hint) {
      const added = rows.length;
      const trunc = !!data.raw_truncated;
      hint.textContent = trunc
        ? `共解析 ${added} 条（不入库）；预览已达条数/正文长度上限。每条下方可展开查看采集原文。`
        : `共解析 ${added} 条（不入库）。每条下方默认折叠；选中"中间部分值"后可暂存并打标签，供后续入库。`;
      tbody.innerHTML = rows
        .flatMap((i, idx) => {
          const main = `
      <tr class="preview-main-row">
        <td>${idx + 1}</td>
        <td>${escapeHtml(i.endpoint_name || "")}</td>
        <td>${escapeHtml(i.endpoint_method || "")}</td>
        <td>${escapeHtml(i.source || "")}</td>
        <td>${escapeHtml(i.category || "")}</td>
        <td class="cell-preview-title" title="${escapeHtml(i.title || "")}">${escapeHtml(i.title || "")}</td>
        <td>${escapeHtml(i.created_at || i.occur_time || "—")}</td>
      </tr>`;
          const raw = i.item_raw_json != null && String(i.item_raw_json).trim() !== ""
            ? `
      <tr class="preview-item-raw-row">
        <td colspan="7">
          <details class="item-raw-details">
            <summary class="item-raw-summary">本条采集内容</summary>
            <div class="item-extract-bar">
              <span class="field-with-hint">
                <input class="input item-tag-input" data-row-idx="${idx}" type="text" maxlength="64" placeholder="标签（如：IP/告警码/单位/人员）" />
              </span>
              <button type="button" class="btn small primary btn-tag-save" data-row-idx="${idx}">暂存选中</button>
              <span class="muted item-extract-hint">先在下方原文中选中一段文本</span>
            </div>
            <pre class="item-raw-pre" data-row-idx="${idx}">${escapeHtml(String(i.item_raw_json))}</pre>
          </details>
        </td>
      </tr>`
            : "";
          return raw ? [main, raw] : [main];
        })
        .join("");

      tbody.querySelectorAll(".item-tag-input").forEach((inp) => {
        V.wireDynamicLimitHint(inp, V.PREVIEW_TAG_LIMIT);
      });

      // 绑定“暂存选中”
      tbody.querySelectorAll(".btn-tag-save").forEach((btn) => {
        btn.addEventListener("click", async (ev) => {
          const rowIdx = parseInt(ev.currentTarget.getAttribute("data-row-idx"), 10);
          const row = rows[rowIdx] || {};
          const tagEl = tbody.querySelector(`.item-tag-input[data-row-idx="${rowIdx}"]`);
          const tag = (tagEl ? tagEl.value : "").trim();
          const pre = tbody.querySelector(`.item-raw-pre[data-row-idx="${rowIdx}"]`);
          const sel = window.getSelection ? window.getSelection() : null;
          const selected = sel ? String(sel.toString() || "") : "";

          if (!V.validateTaggedFields(tag, selected)) return;
          if (pre && sel && sel.anchorNode && !pre.contains(sel.anchorNode)) {
            toast("选中的内容不在当前这条采集原文内", "error");
            return;
          }
          try {
            const resp = await API.post("/api/data/tagged", {
              endpoint_id: row.endpoint_id ?? null,
              endpoint_name: row.endpoint_name ?? "",
              tag,
              value: selected,
              source_excerpt: row.item_raw_json ?? "",
            });
            toast(resp.msg || "已暂存", "success");
            if (tagEl) tagEl.value = "";
            await DataCollect.loadTagged();
          } catch (e) {
            toast(e.message, "error");
          }
        });
      });
    }
    sec.scrollIntoView({ behavior: "smooth", block: "nearest" });
  },

  clearRawPreview() {
    const hint = document.getElementById("raw-preview-hint");
    const tbody = document.querySelector("#raw-preview-table tbody");
    this._previewRows = [];
    if (hint) hint.textContent = "暂无解析预览。点采集后会展示原文，可在每条下方选中文本暂存为标签。";
    if (tbody) tbody.innerHTML = `<tr><td colspan="7" class="muted" style="text-align:center;padding:24px;">暂无数据</td></tr>`;
    toast("解析预览已清空", "success");
  },

  collapseRawPreview() {
    const sec = document.getElementById("raw-preview-section");
    if (!sec) return;
    const details = sec.querySelectorAll(".item-raw-details[open]");
    details.forEach((d) => d.removeAttribute("open"));
    toast("已折叠全部采集内容", "success");
  },


  async extractByEndpoint(id) {
    try {
      const r = await API.post("/api/data/extract", { endpoint_id: parseInt(id, 10) });
      let msg = `解析成功，共 ${r.data.added} 条（未入库）`;
      if (r.data.errors && r.data.errors.length) {
        msg += `（${r.data.errors.join("；")}）`;
      }
      toast(msg, "success");
      this.showRawPreview(r.data, { append: true });
      this.loadTagged();
    } catch (e) {
      toast(e.message, "error");
    }
  },

  async extractAll() {
    try {
      const r = await API.post("/api/data/extract", { all_endpoints: true });
      let msg = r.msg || `共解析 ${r.data.added} 条（未入库）`;
      if (r.data.errors && r.data.errors.length) {
        msg += `；部分失败：${r.data.errors.slice(0, 4).join("；")}${r.data.errors.length > 4 ? "…" : ""}`;
        toast(msg, "info");
      } else {
        toast(msg, "success");
      }
      this.showRawPreview(r.data);
      this.loadTagged();
    } catch (e) {
      toast(e.message, "error");
    }
  },

  async loadEndpoints() {
    try {
      const r = await API.get("/api/data/endpoints");
      this._eps = r.data || [];
      const tbody = document.querySelector("#endpoint-table tbody");
      tbody.innerHTML = this._eps.length
        ? this._eps.map((i) => `
      <tr>
        <td>${escapeHtml(i.sort_order)}</td>
        <td>${escapeHtml(i.name)}</td>
        <td class="cell-url" title="${escapeHtml(i.url)}">${escapeHtml(i.url.length > 56 ? i.url.slice(0, 56) + "…" : i.url)}</td>
        <td>${escapeHtml(i.source || "")}</td>
        <td>${escapeHtml(i.category || "")}</td>
        <td class="nowrap">
          <button type="button" class="btn small primary" onclick="DataCollect.extractByEndpoint(${i.id})">采集</button>
          <button type="button" class="btn small" onclick="DataCollect.openDrawer(${i.id})">编辑</button>
          <button type="button" class="btn small danger" onclick="DataCollect.deleteEndpoint(${i.id})">删除</button>
        </td>
      </tr>`).join("")
        : `<tr><td colspan="6" class="muted">暂无配置，请点击「新增配置」添加远程采集条目。</td></tr>`;
    } catch (e) {
      toast(e.message, "error");
    }
  },

  openDrawer(epId) {
    document.getElementById("ep-drawer").classList.remove("hidden");
    const title = document.getElementById("ep-drawer-title");
    if (epId == null) {
      title.textContent = "新增采集配置";
      document.getElementById("ep-id").value = "";
      document.getElementById("ep-name").value = "";
      document.getElementById("ep-url").value = "";
      document.getElementById("ep-source").value = "";
      document.getElementById("ep-category").value = "";
      return;
    }
    title.textContent = "编辑采集配置";
    const ep = this._eps.find((x) => x.id === epId);
    if (!ep) {
      toast("找不到该配置", "error");
      return;
    }
    document.getElementById("ep-id").value = String(ep.id);
    document.getElementById("ep-name").value = ep.name || "";
    document.getElementById("ep-url").value = ep.url || "";
    document.getElementById("ep-source").value = ep.source || "";
    document.getElementById("ep-category").value = ep.category || "";
  },

  closeDrawer() {
    document.getElementById("ep-drawer").classList.add("hidden");
  },

  async saveEndpoint() {
    const id = document.getElementById("ep-id").value.trim();
    if (!V.validateEndpointForm(!!id)) return;
    const name = document.getElementById("ep-name").value.trim();
    const url = document.getElementById("ep-url").value.trim();
    const payload = {
      name,
      method: "GET",
      url,
      source: document.getElementById("ep-source").value.trim(),
      category: document.getElementById("ep-category").value.trim(),
    };
    try {
      if (id) {
        await API.put(`/api/data/endpoints/${id}`, payload);
        toast("已更新", "success");
      } else {
        await API.post("/api/data/endpoints", payload);
        toast("已新增", "success");
      }
      this.closeDrawer();
      await this.loadEndpoints();
    } catch (e) {
      toast(e.message, "error");
    }
  },

  async deleteEndpoint(id) {
    if (!confirm("确认删除该采集配置？")) return;
    try {
      await API.del(`/api/data/endpoints/${id}`);
      toast("已删除", "success");
      await this.loadEndpoints();
    } catch (e) {
      toast(e.message, "error");
    }
  },

  async loadTagged() {
    const tbody = document.querySelector("#tagged-table tbody");
    if (!tbody) return;
    try {
      const r = await API.get("/api/data/tagged?size=80");
      const items = (r.data && r.data.items) ? r.data.items : [];
      tbody.innerHTML = items.length
        ? items.map((x, idx) => `
      <tr>
        <td>${idx + 1}</td>
        <td title="${escapeHtml(x.endpoint_name || "")}">${escapeHtml(x.endpoint_name || (x.endpoint_id ? ("#" + x.endpoint_id) : ""))}</td>
        <td>${escapeHtml(x.tag || "")}</td>
        <td title="${escapeHtml(x.value || "")}">${escapeHtml(String(x.value || "").slice(0, 80))}${String(x.value || "").length > 80 ? "…" : ""}</td>
        <td>${escapeHtml(x.source || "")}</td>
        <td>${escapeHtml(x.category || "")}</td>
        <td>${escapeHtml(zhStatus(x.status))}</td>
        <td>${escapeHtml(x.created_at || "")}</td>
        <td class="cell-mono muted">#${escapeHtml(x.id)}</td>
        <td class="nowrap">
          <button type="button" class="btn small btn-tag-edit" data-id="${x.id}" data-tag="${escapeHtml(x.tag || "")}" data-value="${escapeHtml(String(x.value || ""))}">修改</button>
          <button type="button" class="btn small primary" onclick="DataCollect.storeTagged(${x.id})">入库</button>
          <button type="button" class="btn small danger" onclick="DataCollect.deleteTagged(${x.id})">删除</button>
        </td>
      </tr>`).join("")
        : `<tr><td colspan="10" class="muted">暂无暂存记录。可在解析预览中选中文本并"暂存选中"。</td></tr>`;

      tbody.querySelectorAll(".btn-tag-edit").forEach((btn) => {
        btn.addEventListener("click", async (ev) => {
          const el = ev.currentTarget;
          const id = parseInt(el.getAttribute("data-id"), 10);
          const oldTag = el.getAttribute("data-tag") || "";
          const oldVal = el.getAttribute("data-value") || "";
          DataCollect.openTagEditModal(id, oldTag, oldVal);
        });
      });
    } catch (e) {
      tbody.innerHTML = `<tr><td colspan="10" class="muted">${escapeHtml(e.message || "加载失败")}</td></tr>`;
    }
  },

  async storeTagged(id) {
    try {
      await API.post(`/api/data/tagged/${id}/store`, {});
      toast("已入库", "success");
      await this.loadTagged();
      await this.loadClean();
    } catch (e) {
      toast(e.message, "error");
    }
  },

  async storeAllTagged() {
    try {
      const r = await API.post("/api/data/tagged/store_all", {});
      toast(`已入库 ${r.data.stored ?? 0} 条`, "success");
      await this.loadTagged();
      await this.loadClean();
    } catch (e) {
      toast(e.message, "error");
    }
  },

  async deleteTagged(id) {
    if (!confirm("确认删除该暂存记录？")) return;
    try {
      await API.del(`/api/data/tagged/${id}`);
      toast("已删除", "success");
      await this.loadTagged();
    } catch (e) {
      toast(e.message, "error");
    }
  },

  _decodeHtml(s) {
    const decode = (s) => String(s || "")
      .replace(/&quot;/g, "\"")
      .replace(/&lt;/g, "<")
      .replace(/&gt;/g, ">")
      .replace(/&amp;/g, "&");
    return decode(s);
  },

  openTagEditModal(id, oldTagEsc, oldValEsc) {
    const modal = document.getElementById("tag-edit-modal");
    if (!modal) return;
    document.getElementById("tag-edit-id").value = String(id);
    document.getElementById("tag-edit-tag").value = this._decodeHtml(oldTagEsc);
    document.getElementById("tag-edit-value").value = this._decodeHtml(oldValEsc);
    modal.classList.remove("hidden");
  },

  closeTagEditModal() {
    const modal = document.getElementById("tag-edit-modal");
    if (modal) modal.classList.add("hidden");
  },

  async saveTagEdit() {
    const id = (document.getElementById("tag-edit-id").value || "").trim();
    const tag = (document.getElementById("tag-edit-tag").value || "").trim();
    const value = document.getElementById("tag-edit-value").value || "";
    if (!id) return;
    if (!V.validateTaggedFields(tag, value)) return;
    try {
      await API.put(`/api/data/tagged/${id}`, { tag, value: value.trim() });
      toast("已更新", "success");
      this.closeTagEditModal();
      await this.loadTagged();
    } catch (e) {
      toast(e.message, "error");
    }
  },

  async clearTagged() {
    if (!confirm("确认一键清空标签暂存区？")) return;
    try {
      const r = await API.post("/api/data/tagged/clear", {});
      toast(`已清空 ${r.data.deleted ?? 0} 条`, "success");
      await this.loadTagged();
    } catch (e) {
      toast(e.message, "error");
    }
  },




  async clear() {
    if (!confirm("确认清空「已入库标签数据」(CleanData)？采集预览本来就不入库。")) return;
    try {
      await API.post("/api/data/clear", {});
      toast("已清空", "success");
      this.refresh();
    } catch (e) {
      toast(e.message, "error");
    }
  },

  async loadClean() {
    const tbody = document.querySelector("#clean-table tbody");
    if (!tbody) return;
    let groups = [];
    try {
      const r = await API.get("/api/data/clean/by-day");
      groups = (r.data && r.data.groups) || [];
    } catch (e) {
      tbody.innerHTML = `<tr><td colspan="6" class="muted" style="text-align:center;padding:24px;">${escapeHtml(e.message || "加载失败")}</td></tr>`;
      return;
    }
    if (!groups.length) {
      tbody.innerHTML = `<tr><td colspan="6" class="muted" style="text-align:center;padding:24px;">暂无数据</td></tr>`;
      return;
    }

    const briefList = (arr, n = 3) => {
      const a = (arr || []).filter(Boolean);
      if (!a.length) return "—";
      const head = a.slice(0, n).join("、");
      return a.length > n ? `${head}…+${a.length - n}` : head;
    };

    tbody.innerHTML = groups.flatMap((g, idx) => {
      const subRows = (g.items || []).map(i => {
        const content = String(i.content || "");
        const short = content.length > 80 ? content.slice(0, 80) + "…" : content;
        return `
          <tr>
            <td>${escapeHtml(i.source || "")}</td>
            <td>${escapeHtml(i.tags || i.title || "")}</td>
            <td title="${escapeHtml(content)}">${escapeHtml(short)}</td>
            <td>${escapeHtml(i.endpoint_source || "")}</td>
            <td>${escapeHtml(i.endpoint_category || "")}</td>
            <td class="cell-mono">${escapeHtml(i.occur_time || i.created_at || "")}</td>
            <td class="nowrap">
              <button type="button" class="btn small" onclick="DataCollect.openCleanEditModal(${i.id}, '${escapeHtml(i.source || "")}', '${escapeHtml(i.tags || "")}', '${escapeHtml(i.category || "")}', '${escapeHtml(content)}', '${escapeHtml(i.endpoint_source || "")}', '${escapeHtml(i.endpoint_category || "")}')">修改</button>
              <button type="button" class="btn small danger" onclick="DataCollect.deleteClean(${i.id})">删除</button>
            </td>
          </tr>`;
      }).join("");
      const dateAttr = escapeHtml(g.date);
      const endpoints = g.endpoints || g.sources || [];
      const epSources = g.endpoint_sources || [];
      const epCategories = g.endpoint_categories || [];
      const cleanCats = g.categories || [];
      return [
        `<tr class="day-row" data-date="${dateAttr}" onclick="DataCollect.toggleDay('${dateAttr}')">
          <td>${idx + 1}</td>
          <td><span class="chev">▶</span> <span class="cell-mono">${escapeHtml(g.date)}</span></td>
          <td><span class="tag accent">${g.count}</span></td>
          <td title="${escapeHtml(epSources.join('、'))}">${escapeHtml(briefList(epSources))}</td>
          <td title="${escapeHtml(epCategories.join('、'))}">${escapeHtml(briefList(epCategories))}</td>
          <td class="nowrap">
            <button type="button" class="btn small danger" onclick="event.stopPropagation(); DataCollect.deleteCleanByDay('${dateAttr}')">删除当天</button>
          </td>
        </tr>`,
        `<tr class="day-sub" data-date="${dateAttr}" hidden>
          <td colspan="6" style="padding:0; background:var(--bg-2);">
            <table class="sub-table">
              <thead><tr>
                <th>所属配置</th><th>标签</th><th>值</th><th>来源</th><th>类别</th><th>时间</th><th>操作</th>
              </tr></thead>
              <tbody>${subRows}</tbody>
            </table>
          </td>
        </tr>`,
      ];
    }).join("");
  },

  async deleteCleanByDay(date) {
    if (!confirm(`确认删除 ${date} 当天全部已入库标签数据？此操作不可恢复。`)) return;
    try {
      const r = await API.del(`/api/data/clean/by-day/${encodeURIComponent(date)}`);
      toast(`已删除 ${(r.data && r.data.deleted) || 0} 条`, "success");
      await this.loadClean();
    } catch (e) {
      toast(e.message, "error");
    }
  },

  toggleDay(date) {
    const sel = (cls) => document.querySelector(`#clean-table tr.${cls}[data-date="${(window.CSS && CSS.escape) ? CSS.escape(date) : date}"]`);
    const sub = sel("day-sub");
    const day = sel("day-row");
    if (!sub || !day) return;
    const opening = sub.hasAttribute("hidden");
    if (opening) { sub.removeAttribute("hidden"); day.classList.add("expanded"); }
    else { sub.setAttribute("hidden", ""); day.classList.remove("expanded"); }
  },

  expandAllDays() {
    document.querySelectorAll("#clean-table tr.day-sub").forEach(t => t.removeAttribute("hidden"));
    document.querySelectorAll("#clean-table tr.day-row").forEach(t => t.classList.add("expanded"));
  },

  collapseAllDays() {
    document.querySelectorAll("#clean-table tr.day-sub").forEach(t => t.setAttribute("hidden", ""));
    document.querySelectorAll("#clean-table tr.day-row").forEach(t => t.classList.remove("expanded"));
  },

  openCleanEditModal(id, sourceEsc, tagsEsc, categoryEsc, contentEsc, epSourceEsc, epCategoryEsc) {
    const modal = document.getElementById("clean-edit-modal");
    if (!modal) return;
    const title = document.getElementById("clean-edit-title");
    if (title) title.textContent = "修改已入库标签数据";
    document.getElementById("clean-edit-id").value = String(id);
    document.getElementById("clean-edit-source").value = this._decodeHtml(sourceEsc);
    document.getElementById("clean-edit-tags").value = this._decodeHtml(tagsEsc);
    document.getElementById("clean-edit-category").value = this._decodeHtml(categoryEsc);
    document.getElementById("clean-edit-content").value = this._decodeHtml(contentEsc);
    const esEl = document.getElementById("clean-edit-endpoint-source");
    const ecEl = document.getElementById("clean-edit-endpoint-category");
    if (esEl) esEl.value = this._decodeHtml(epSourceEsc || "");
    if (ecEl) ecEl.value = this._decodeHtml(epCategoryEsc || "");
    modal.classList.remove("hidden");
  },

  openCleanCreateModal() {
    const modal = document.getElementById("clean-edit-modal");
    if (!modal) return;
    const title = document.getElementById("clean-edit-title");
    if (title) title.textContent = "新增已入库标签数据";
    document.getElementById("clean-edit-id").value = "";
    document.getElementById("clean-edit-source").value = "";
    document.getElementById("clean-edit-tags").value = "用户自增";
    document.getElementById("clean-edit-category").value = "标签入库";
    document.getElementById("clean-edit-content").value = "";
    const esEl = document.getElementById("clean-edit-endpoint-source");
    const ecEl = document.getElementById("clean-edit-endpoint-category");
    if (esEl) esEl.value = "";
    if (ecEl) ecEl.value = "";
    modal.classList.remove("hidden");
  },

  closeCleanEditModal() {
    const modal = document.getElementById("clean-edit-modal");
    if (modal) modal.classList.add("hidden");
  },

  async saveCleanEdit() {
    const id = (document.getElementById("clean-edit-id").value || "").trim();
    if (!V.validateCleanForm(!id)) return;
    const payload = {
      source: (document.getElementById("clean-edit-source").value || "").trim(),
      tags: (document.getElementById("clean-edit-tags").value || "").trim(),
      category: (document.getElementById("clean-edit-category").value || "").trim(),
      content: document.getElementById("clean-edit-content").value || "",
      endpoint_source: (document.getElementById("clean-edit-endpoint-source")?.value || "").trim(),
      endpoint_category: (document.getElementById("clean-edit-endpoint-category")?.value || "").trim(),
    };
    try {
      if (id) {
        await API.put(`/api/data/clean/${id}`, payload);
        toast("已更新", "success");
      } else {
        await API.post("/api/data/clean", payload);
        toast("已新增", "success");
      }
      this.closeCleanEditModal();
      await this.loadClean();
    } catch (e) {
      toast(e.message, "error");
    }
  },

  async deleteClean(id) {
    if (!confirm("确认删除该已入库记录？")) return;
    try {
      await API.del(`/api/data/clean/${id}`);
      toast("已删除", "success");
      await this.loadClean();
    } catch (e) {
      toast(e.message, "error");
    }
  },

  async refresh() {
    await this.loadEndpoints();
    await this.loadTagged();
    await this.loadClean();
  },
};
