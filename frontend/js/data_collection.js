function escapeHtml(s) {
  return String(s ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
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
      if (hint) hint.textContent = "暂无解析预览。点采集后会展示原文，可在每条下方选中文本后入库。";
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
        : `共解析 ${added} 条（不入库）。每条下方默认折叠；选中文字并填写标签后可直接入库。`;
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
        <td title="采集 ${escapeHtml(i.created_at || "")}">${escapeHtml(i.occur_time || "—")}</td>
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
              <button type="button" class="btn small primary btn-tag-save" data-row-idx="${idx}">入库选中</button>
              ${helpTip("在下方原文中拖选一段文字，填写标签后点此写入已入库数据。")}
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

      tbody.querySelectorAll(".btn-tag-save").forEach((btn) => {
        btn.addEventListener("click", async (ev) => {
          const rowIdx = parseInt(ev.currentTarget.getAttribute("data-row-idx"), 10);
          const row = rows[rowIdx] || {};
          const tagEl = tbody.querySelector(`.item-tag-input[data-row-idx="${rowIdx}"]`);
          const tag = (tagEl ? tagEl.value : "").trim();
          const pre = tbody.querySelector(`.item-raw-pre[data-row-idx="${rowIdx}"]`);
          const sel = window.getSelection ? window.getSelection() : null;
          const selected = sel ? String(sel.toString() || "").trim() : "";

          if (!V.validateTaggedFields(tag, selected)) return;
          if (pre && sel && sel.anchorNode && !pre.contains(sel.anchorNode)) {
            toast("选中的内容不在当前这条采集原文内", "error");
            return;
          }
          try {
            const resp = await API.post("/api/data/clean", {
              source: row.endpoint_name || "",
              tags: tag,
              category: "标签入库",
              content: selected,
              endpoint_source: row.source || "",
              endpoint_category: row.category || "",
              occur_time: row.occur_time || "",
            });
            toast(resp.msg || "已入库", "success");
            if (tagEl) tagEl.value = "";
            await DataCollect.loadClean();
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
    if (hint) hint.textContent = "暂无解析预览。点采集后会展示原文，可在每条下方选中文本后入库。";
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

  _decodeHtml(s) {
    const decode = (s) => String(s || "")
      .replace(/&quot;/g, "\"")
      .replace(/&lt;/g, "<")
      .replace(/&gt;/g, ">")
      .replace(/&amp;/g, "&");
    return decode(s);
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
            <td class="cell-mono">${escapeHtml(i.created_at || i.collect_time || "")}</td>
            <td class="cell-mono">${escapeHtml(i.occur_time || i.data_time || "—")}</td>
            <td class="nowrap">
              <button type="button" class="btn small" onclick="DataCollect.openCleanEditModal(${i.id}, '${escapeHtml(i.source || "")}', '${escapeHtml(i.tags || "")}', '${escapeHtml(i.category || "")}', '${escapeHtml(content)}', '${escapeHtml(i.endpoint_source || "")}', '${escapeHtml(i.endpoint_category || "")}', '${escapeHtml(i.occur_time || "")}', '${escapeHtml(i.created_at || "")}')">修改</button>
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
                <th>所属配置</th><th>标签</th><th>值</th><th>来源</th><th>类别</th><th>采集时间</th><th>数据时间</th><th>操作</th>
              </tr></thead>
              <tbody>${subRows}</tbody>
            </table>
          </td>
        </tr>`,
      ];
    }).join("");
  },

  async deleteCleanByDay(date) {
    if (!confirm(`确认删除数据日期 ${date} 的全部已入库标签数据？此操作不可恢复。`)) return;
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

  _toDatetimeLocal(s) {
    const t = String(s || "").trim();
    if (!t) return "";
    return t.replace(" ", "T").slice(0, 16);
  },

  openCleanEditModal(id, sourceEsc, tagsEsc, categoryEsc, contentEsc, epSourceEsc, epCategoryEsc, occurEsc, collectedEsc) {
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
    const occurEl = document.getElementById("clean-edit-occur-time");
    const colEl = document.getElementById("clean-edit-collect-time");
    if (occurEl) occurEl.value = this._toDatetimeLocal(this._decodeHtml(occurEsc || ""));
    if (colEl) colEl.value = this._decodeHtml(collectedEsc || "") || "入库时自动记录";
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
    const occurEl = document.getElementById("clean-edit-occur-time");
    const colEl = document.getElementById("clean-edit-collect-time");
    if (occurEl) occurEl.value = "";
    if (colEl) colEl.value = "入库时自动记录";
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
      occur_time: (document.getElementById("clean-edit-occur-time")?.value || "").trim(),
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
    this._defaultOrgRange();
    await this.loadOrgUnits();
    await this.loadEndpoints();
    await this.loadClean();
  },

  async loadOrgUnits() {
    const tbody = document.querySelector("#org-unit-table tbody");
    if (!tbody) return;
    try {
      const r = await API.get("/api/data/org-units");
      const rows = r.data || [];
      tbody.innerHTML = rows.length
        ? rows.map((u) => `
          <tr>
            <td>
              <input class="input org-unit-name" data-id="${u.id}" value="${escapeHtml(u.name || u.code || "")}"
                placeholder="单位名称" maxlength="${V.L.orgName || 64}" autocomplete="off" spellcheck="false" />
            </td>
            <td>
              <input class="input org-unit-url" data-id="${u.id}" value="${escapeHtml(u.base_url || "")}"
                placeholder="http://主机:端口" maxlength="2048" autocomplete="off" spellcheck="false" />
            </td>
            <td>
              <input class="input org-unit-remark" data-id="${u.id}" value="${escapeHtml(u.remark || "运维、安防数据")}"
                placeholder="运维、安防数据" maxlength="${V.L.orgRemark || 64}" autocomplete="off" spellcheck="false" />
            </td>
            <td class="nowrap">
              <button type="button" class="btn small primary" onclick="DataCollect.saveOrgUnit(${u.id})">保存</button>
              <button type="button" class="btn small danger" onclick="DataCollect.deleteOrgUnit(${u.id})">删除</button>
            </td>
          </tr>`).join("")
        : `<tr><td colspan="4" class="muted" style="text-align:center;padding:18px;">暂无单位配置</td></tr>`;
    } catch (e) {
      tbody.innerHTML = `<tr><td colspan="4" class="muted" style="text-align:center;padding:18px;">${escapeHtml(e.message || "加载失败")}</td></tr>`;
    }
  },

  _orgUnitPayload(id) {
    const nameEl = document.querySelector(`#org-unit-table input.org-unit-name[data-id="${id}"]`);
    const input = document.querySelector(`#org-unit-table input.org-unit-url[data-id="${id}"]`);
    const remarkEl = document.querySelector(`#org-unit-table input.org-unit-remark[data-id="${id}"]`);
    const nameCheck = V.str(nameEl ? nameEl.value : "", "单位", {
      min: 1,
      max: V.L.orgName || 64,
    });
    if (!V.ok(nameCheck)) return { error: nameCheck.msg };
    const remarkCheck = V.str(remarkEl ? remarkEl.value : "", "备注", {
      required: false,
      max: V.L.orgRemark || 64,
    });
    if (!V.ok(remarkCheck)) return { error: remarkCheck.msg };
    const url = (input ? input.value : "").trim();
    if (url) {
      try {
        const u = new URL(url);
        if (u.protocol !== "http:" && u.protocol !== "https:") throw new Error();
      } catch (_) {
        return { error: "基地 URL 须为 http:// 或 https:// 开头" };
      }
    }
    return {
      name: nameCheck.value,
      base_url: url,
      remark: remarkCheck.value || "运维、安防数据",
    };
  },

  async saveOrgUnit(id) {
    const payload = this._orgUnitPayload(id);
    if (payload.error) {
      toast(payload.error, "error");
      return;
    }
    try {
      await API.put(`/api/data/org-units/${id}`, payload);
      const remarkEl = document.querySelector(`#org-unit-table input.org-unit-remark[data-id="${id}"]`);
      if (remarkEl && !(remarkEl.value || "").trim()) remarkEl.value = "运维、安防数据";
      toast("已保存", "success");
    } catch (e) {
      toast(e.message || "保存失败", "error");
    }
  },

  async deleteOrgUnit(id) {
    if (!confirm("确认删除该单位接口？")) return;
    try {
      await API.del(`/api/data/org-units/${id}`);
      toast("已删除", "success");
      await this.loadOrgUnits();
    } catch (e) {
      toast(e.message || "删除失败", "error");
    }
  },

  _defaultOrgRange() {
    const fromEl = document.getElementById("org-date-from");
    const toEl = document.getElementById("org-date-to");
    if (!fromEl || !toEl) return;
    const pad = (n) => String(n).padStart(2, "0");
    const fmt = (d) => `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
    const to = new Date();
    const from = new Date(to.getTime() - 7 * 24 * 3600 * 1000);
    if (!fromEl.value) fromEl.value = fmt(from);
    if (!toEl.value) toEl.value = fmt(to);
  },

  async fetchOrgMetrics() {
    const from = (document.getElementById("org-date-from")?.value || "").trim();
    const to = (document.getElementById("org-date-to")?.value || "").trim();
    if (!from || !to) {
      toast("请填写时间范围", "error");
      return;
    }
    if (from > to) {
      toast("结束时间不能早于起始时间", "error");
      return;
    }
    try {
      toast("正在按时间范围采集…");
      const r = await API.post("/api/data/org-units/fetch", { date_from: from, date_to: to });
      const stored = (r.data && r.data.stored) || 0;
      toast(`已入库该时段指标 ${stored} 条`, "success");
      await this.loadClean();
    } catch (e) {
      toast(e.message || "拉取失败", "error");
    }
  },
};
