const Generate = {
  _cleanById: {},
  _cleanList: [],
  _currentTemplate: null,
  /** 与 `_slots` 索引对应的替换底稿（优先 `plain_text_body` / `plain_text`，否则 DB content） */
  _slotSourceText: "",
  _slots: [],
  _bindings: [],
  _polishingIds: new Set(),
  _polishQueue: [],
  _polishRunning: false,
  _autofilling: false,
  _autofillTimer: null,
  _autofillBtnHtml: '<svg class="icon" width="14" height="14"><use href="#i-sparkles"/></svg> AI 自动填写',

  async init() {
    this._defaultReportDate();
    this._defaultAutofillPeriod();
    await this._loadAutofillUnits();
    this._wireAutofillFilters();
    await this.loadTemplates();
    await this.refreshCleanList({ quiet: true });
    await this.refreshComposeDraftList();
    await this._loadLlmStatus();
    this._wireComposeDraftFilters();
    this._wireUpload();
    const sel = document.getElementById("gen-template");
    if (sel && !sel._wiredTplChange) {
      sel._wiredTplChange = true;
      sel.addEventListener("change", () => this.onTemplateSelect());
    }
  },

  _defaultAutofillPeriod() {
    const now = new Date();
    const df = document.getElementById("gen-af-from");
    const dt = document.getElementById("gen-af-to");
    if (dt && !dt.value) dt.value = now.toISOString().slice(0, 10);
    if (df && !df.value) {
      const first = new Date(now.getFullYear(), now.getMonth(), 1);
      df.value = first.toISOString().slice(0, 10);
    }
  },

  async _loadAutofillUnits() {
    const sel = document.getElementById("gen-af-unit");
    if (!sel) return;
    const short = {
      hq: "空军本级",
      east: "东部",
      west: "西部",
      south: "南部",
      north: "北部",
      center: "中部",
    };
    const keep = sel.value || "hq";
    try {
      const r = await API.get("/api/data/org-units");
      const items = r.data || [];
      if (!items.length) return;
      const opts = [`<option value="all">全部</option>`].concat(
        items.map((u) => {
          const code = String(u.code || "").replace(/"/g, "");
          const label = short[code] || u.name || code;
          return `<option value="${code}">${escapeHtml(label)}</option>`;
        }),
      );
      sel.innerHTML = opts.join("");
      const ok = [...sel.options].some((o) => o.value === keep);
      sel.value = ok ? keep : "hq";
    } catch (_) {
      /* 保留页面预置六单位 */
    }
  },

  _wireAutofillFilters() {
    ["gen-af-from", "gen-af-to", "gen-af-unit", "gen-af-metric"].forEach((id) => {
      const el = document.getElementById(id);
      if (!el || el._wiredCleanFilter) return;
      el._wiredCleanFilter = true;
      el.addEventListener("change", () => this.refreshCleanList({ quiet: true }));
    });
  },

  _cleanQueryString() {
    const params = new URLSearchParams({ page: "1", size: "500" });
    const df = (document.getElementById("gen-af-from")?.value || "").trim();
    const dt = (document.getElementById("gen-af-to")?.value || "").trim();
    const unit = (document.getElementById("gen-af-unit")?.value || "").trim();
    const metric = (document.getElementById("gen-af-metric")?.value || "").trim();
    if (df) params.set("date_from", df);
    if (dt) params.set("date_to", dt);
    if (unit && unit !== "all") params.set("unit", unit);
    if (metric && metric !== "all") params.set("metric", metric);
    return params.toString();
  },

  async openLlmDrawer() {
    const el = document.getElementById("llm-drawer");
    if (el) el.classList.remove("hidden");
    await this._loadLlmStatus();
  },

  closeLlmDrawer() {
    const el = document.getElementById("llm-drawer");
    if (el) el.classList.add("hidden");
  },

  async _loadLlmStatus() {
    const el = document.getElementById("gen-llm-status");
    const baseEl = document.getElementById("gen-llm-base");
    const modelEl = document.getElementById("gen-llm-model");
    const keyEl = document.getElementById("gen-llm-key");
    const clearEl = document.getElementById("gen-llm-clear-key");
    try {
      const r = await API.get("/api/template/llm-config");
      const d = r.data || {};
      if (baseEl) baseEl.value = d.base_url || "";
      if (modelEl) modelEl.value = d.model || "";
      if (keyEl) {
        keyEl.value = "";
        keyEl.placeholder = d.has_api_key
          ? "已保存，留空则不修改"
          : "无需密钥可留空";
      }
      if (clearEl) clearEl.checked = false;
      if (el) {
        el.textContent = d.configured
          ? `已配置${d.model ? "（" + d.model + "）" : ""}`
          : "展示模式：未填地址和模型名";
      }
    } catch (_) {
      if (el) el.textContent = "";
    }
  },

  _llmFormPayload() {
    return {
      base_url: (document.getElementById("gen-llm-base")?.value || "").trim(),
      model: (document.getElementById("gen-llm-model")?.value || "").trim(),
      api_key: (document.getElementById("gen-llm-key")?.value || "").trim(),
      clear_api_key: !!(document.getElementById("gen-llm-clear-key") && document.getElementById("gen-llm-clear-key").checked),
    };
  },

  async saveLlmConfig() {
    const payload = this._llmFormPayload();
    if (payload.base_url) {
      try {
        const u = new URL(payload.base_url);
        if (u.protocol !== "http:" && u.protocol !== "https:") throw new Error();
      } catch (_) {
        toast("接口地址须为 http:// 或 https:// 开头", "error");
        return;
      }
    }
    try {
      const r = await API.put("/api/template/llm-config", payload);
      toast(r.msg || "已保存", "success");
      await this._loadLlmStatus();
      this.closeLlmDrawer();
    } catch (e) {
      toast(e.message || "保存失败", "error");
    }
  },

  async testLlmConfig() {
    const payload = this._llmFormPayload();
    if (!payload.base_url || !payload.model) {
      toast("请先填写接口地址和模型名", "error");
      return;
    }
    try {
      toast("正在测试连接…");
      const r = await API.post("/api/template/llm-config/test", payload);
      toast(r.msg || "连接正常", "success");
    } catch (e) {
      toast(e.message || "测试失败", "error");
    }
  },

  setFillTab(tab) {
    const which = tab === "ai" ? "ai" : "map";
    document.querySelectorAll(".gen-fill-tab").forEach((btn) => {
      const on = btn.getAttribute("data-tab") === which;
      btn.classList.toggle("active", on);
      btn.setAttribute("aria-selected", on ? "true" : "false");
    });
    const mapPane = document.getElementById("gen-fill-pane-map");
    const aiPane = document.getElementById("gen-fill-pane-ai");
    if (mapPane) mapPane.classList.toggle("hidden", which !== "map");
    if (aiPane) aiPane.classList.toggle("hidden", which !== "ai");
    const tag = document.getElementById("gen-fill-tag");
    if (tag) tag.textContent = which === "ai" ? "大模型填报" : "入库 / 手工";
  },

  _setAutofillBusy(busy, text) {
    this._autofilling = !!busy;
    const btn = document.getElementById("gen-ai-fill-btn");
    const banner = document.getElementById("gen-ai-fill-banner");
    const label = document.getElementById("gen-ai-fill-banner-text");
    if (btn) {
      btn.disabled = !!busy;
      btn.innerHTML = busy
        ? '<span class="gen-ai-spinner" aria-hidden="true"></span> 正在填写…'
        : this._autofillBtnHtml;
    }
    if (label && text) label.textContent = text;
    if (banner) {
      banner.classList.toggle("is-error", !busy && !!text);
      if (busy) {
        banner.classList.remove("hidden");
        banner.classList.remove("is-error");
      } else if (!text) {
        banner.classList.add("hidden");
      } else {
        banner.classList.remove("hidden");
      }
    }
    if (!busy && this._autofillTimer) {
      clearInterval(this._autofillTimer);
      this._autofillTimer = null;
    }
  },

  async autofillTemplate() {
    if (this._autofilling) return;
    if (!this._currentTemplate) {
      toast("请先选择模板", "error");
      return;
    }
    const payload = {
      date_from: document.getElementById("gen-af-from")?.value || "",
      date_to: document.getElementById("gen-af-to")?.value || "",
      unit: document.getElementById("gen-af-unit")?.value || "hq",
      save_draft: true,
      use_llm: true,
    };
    const started = Date.now();
    const tick = () => {
      const s = Math.max(0, Math.floor((Date.now() - started) / 1000));
      const hint = s < 15
        ? "正在填入指标并起草空章节"
        : "仍在生成文档，请勿关闭或重复点击";
      this._setAutofillBusy(true, `${hint}（已用时 ${s} 秒）`);
    };
    tick();
    this._autofillTimer = setInterval(tick, 1000);
    try {
      const r = await API.post(`/api/template/${this._currentTemplate.id}/autofill`, payload);
      const data = r.data || {};
      const filledPlain = String(data.plain_after || "").trim();
      if (filledPlain) {
        this._showAutofillPlainPreview(filledPlain);
      } else {
        const vals = data.values || [];
        if (this._slots.length && vals.length) {
          for (let i = 0; i < this._bindings.length; i++) {
            const v = i < vals.length ? String(vals[i] || "") : "";
            this._bindings[i] = { mode: "manual", cleanId: null, manual: v };
          }
          this._renderSlotEditors();
          await this.applyMappingToLeftPreview({ quiet: true });
        }
      }
      const filled = data.filled_count ?? 0;
      const total = data.slot_count ?? this._slots.length;
      const narr = (data.narrative_filled || []).length;
      const secs = Math.max(1, Math.round((Date.now() - started) / 1000));
      const done = narr
        ? `已填 ${filled}/${total} 处，并起草 ${narr} 个空章节，用时 ${secs} 秒`
        : `已填 ${filled}/${total} 处并保存草稿，用时 ${secs} 秒`;
      this._setAutofillBusy(false, "");
      toast(done, "success");
      this.setFillTab("map");
      this.setStep(3);
      await this.refreshComposeDraftList();
      await this.refreshCleanList({ quiet: true });
    } catch (e) {
      this._setAutofillBusy(false, e.message || "自动填报失败");
      toast(e.message || "自动填报失败", "error");
    }
  },

  _showAutofillPlainPreview(plain) {
    const text = String(plain || "");
    this._slotSourceText = text;
    this._slots = this._findXSlots(text);
    this._bindings = this._slots.map(() => ({ mode: "manual", cleanId: null, manual: "" }));
    this._renderSlotEditors();
    const prev = document.getElementById("gen-tpl-preview");
    const cnt = document.getElementById("gen-ph-count");
    const hint = document.getElementById("gen-tpl-hint");
    if (cnt) cnt.textContent = `${this._slots.length} 处`;
    if (!prev) return;
    const inner = this._buildXHighlightInnerHtml(text, this._slots);
    prev.innerHTML = `<div class="plain-tpl-fallback tpl-x-annot-body preview-ph-body preview-replaced" role="region" aria-label="全文预览：自动填写结果">${inner}</div>`;
    this._setPreviewBarTitle("全文预览（已自动填写）");
    if (hint) {
      hint.textContent = "左侧为自动填写后的正文；「本月进展」「下月计划」「措施建议」已按指标起草。可下载合成草稿核对 Word。";
    }
  },

  _composeStatusHtml(row) {
    const st = row.status || "pending_polish";
    const zh = row.status_zh || st;
    const detail = row.status_detail || "";
    let cls = "tag warn";
    if (st === "polishing") cls = "tag accent";
    else if (st === "queued_polish") cls = "tag warn";
    else if (st === "polished") cls = "tag ok";
    else if (st === "polish_error") cls = "tag danger";
    const title = detail ? ` title="${escapeHtml(detail)}"` : "";
    let extra = "";
    if (st === "polish_error" && detail) {
      extra = `<span class="muted" style="margin-left:6px;max-width:220px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;display:inline-block;vertical-align:middle;">${escapeHtml(detail)}</span>`;
    }
    return `<span class="${cls} dot"${title}>${escapeHtml(zh)}</span>${extra}`;
  },

  _paintComposeDraftStatus(id, patch) {
    const td = document.querySelector(`[data-compose-status="${id}"]`);
    if (td) td.innerHTML = this._composeStatusHtml(patch);
    const btn = document.querySelector(`[data-compose-polish="${id}"]`);
    if (btn) {
      const queued = patch.status === "queued_polish";
      const polishing = patch.status === "polishing" || queued;
      btn.disabled = polishing;
      btn.textContent = queued ? "排队中" : polishing ? "润色中…" : "润色纠错";
    }
  },

  _syncPolishQueueUi() {
    this._polishQueue.forEach((qid) => {
      this._paintComposeDraftStatus(qid, {
        status: "queued_polish",
        status_zh: "排队中",
        status_detail: "等待上一份润色完成",
      });
    });
  },

  polishComposeDraft(id) {
    if (this._polishingIds.has(id)) return;
    this._polishingIds.add(id);
    const waiting = this._polishRunning || this._polishQueue.length > 0;
    this._polishQueue.push(id);
    this._paintComposeDraftStatus(id, {
      status: waiting ? "queued_polish" : "polishing",
      status_zh: waiting ? "排队中" : "正在润色",
      status_detail: waiting ? "等待上一份润色完成" : "",
    });
    if (waiting) toast("已加入润色队列", "info");
    this._runPolishQueue();
  },

  async _runPolishQueue() {
    if (this._polishRunning) return;
    this._polishRunning = true;
    while (this._polishQueue.length) {
      const id = this._polishQueue.shift();
      this._paintComposeDraftStatus(id, {
        status: "polishing",
        status_zh: "正在润色",
        status_detail: "",
      });
      try {
        toast("正在润色…");
        const r = await API.post(`/api/template/compose-draft/${id}/polish`, {});
        const n = (r.data && r.data.replacement_count) || 0;
        toast(n ? `润色完成，替换 ${n} 处` : "润色完成（无需修改）", "success");
      } catch (e) {
        this._paintComposeDraftStatus(id, {
          status: "polish_error",
          status_zh: "润色失败",
          status_detail: e.message || "润色失败",
        });
        toast(e.message || "润色失败", "error");
      } finally {
        this._polishingIds.delete(id);
        await this.refreshComposeDraftList();
        this._syncPolishQueueUi();
      }
    }
    this._polishRunning = false;
  },

  _composeDraftQueryString() {
    const params = new URLSearchParams();
    params.set("limit", "50");
    const qEl = document.getElementById("gen-compose-q");
    const df = document.getElementById("gen-compose-date-from");
    const dt = document.getElementById("gen-compose-date-to");
    const off = document.getElementById("gen-compose-office");
    if (qEl && String(qEl.value || "").trim()) {
      if (!V.validateSearchKeyword("gen-compose-q", "搜索关键词")) return "";
      params.set("q", String(qEl.value || "").trim());
    }
    if (df && df.value) params.set("date_from", df.value);
    if (dt && dt.value) params.set("date_to", dt.value);
    if (off && off.value && off.value !== "all") params.set("office", off.value);
    return params.toString();
  },

  _wireComposeDraftFilters() {
    const qEl = document.getElementById("gen-compose-q");
    if (!qEl || qEl._wiredCompose) return;
    qEl._wiredCompose = true;
    qEl.addEventListener("keydown", (ev) => {
      if (ev.key === "Enter") {
        ev.preventDefault();
        this.refreshComposeDraftList();
      }
    });
  },

  _defaultReportDate() {
    const d = document.getElementById("gen-rpt-date");
    if (!d || d.value) return;
    try {
      d.value = new Date().toISOString().slice(0, 10);
    } catch (_) {}
  },

  async refreshCleanList(opts) {
    const quiet = opts && opts.quiet;
    try {
      const r = await API.get(`/api/data/clean?${this._cleanQueryString()}`);
      const items = (r.data && r.data.items) || [];
      this._cleanList = items;
      this._cleanById = Object.fromEntries(items.map((x) => [x.id, x]));
      if (this._slots.length) this._renderSlotEditors();
      if (!quiet) toast(`已加载 ${items.length} 条入库数据`, "success");
    } catch (e) {
      toast(e.message || "加载入库数据失败", "error");
    }
  },

  async saveComposeDraft() {
    if (!this._currentTemplate) {
      toast("请先选择模板", "error");
      return;
    }
    try {
      const content = await this.buildFilledBody();
      const contentCheck = V.text(content, "正文", { required: true, max: V.L.draftContent });
      if (!V.ok(contentCheck)) {
        V.fail(contentCheck.msg);
        return;
      }
      const bindings = (this._bindings || []).map((b) => ({
        mode: b.mode,
        cleanId: b.cleanId,
        manual: (b.manual || "").trim(),
      }));
      for (const b of bindings) {
        if (b.mode === "manual" && b.manual && !V.validateSlotManual(b.manual)) return;
      }
      const r = await API.post("/api/template/compose-draft", {
        template_id: this._currentTemplate.id,
        content,
        bindings,
      });
      toast("合成草稿已保存", "success");
      this.setStep(3);
      await this.refreshComposeDraftList();
    } catch (e) {
      toast(e.message || "保存失败", "error");
    }
  },

  async refreshComposeDraftList() {
    const tbody = document.getElementById("gen-compose-draft-tbody");
    const meta = document.getElementById("gen-compose-draft-meta");
    if (!tbody) return;
    try {
      const qs = this._composeDraftQueryString();
      const r = await API.get(`/api/template/compose-drafts?${qs}`);
      const items = (r.data && r.data.items) || [];
      const total =
        r.data && typeof r.data.total === "number" ? r.data.total : items.length;
      const returned =
        r.data && typeof r.data.returned === "number"
          ? r.data.returned
          : items.length;
      if (meta) {
        if (!items.length) {
          meta.textContent =
            total === 0
              ? "无匹配记录（可调整条件后查询）"
              : `共 ${total} 条匹配`;
        } else {
          meta.textContent =
            returned < total
              ? `共 ${total} 条匹配，当前显示 ${returned} 条（已达上限 50）`
              : `共 ${total} 条`;
        }
      }
      if (!items.length) {
          tbody.innerHTML =
          '<tr><td colspan="7" class="muted" style="text-align:center;padding:12px;">无匹配记录（可调整条件后查询）</td></tr>';
        return;
      }
      tbody.innerHTML = items
        .map((row) => {
          const typeZh = row.office_kind_zh || "—";
          const inQueue = this._polishQueue.includes(row.id);
          const busy = this._polishingIds.has(row.id);
          const polishBtn = busy
            ? `<button type="button" class="btn small" data-compose-polish="${row.id}" disabled>${inQueue ? "排队中" : "润色中…"}</button>`
            : `<button type="button" class="btn small" data-compose-polish="${row.id}" onclick="Generate.polishComposeDraft(${row.id})" title="大模型纠错润色，不改动数字">润色纠错</button>`;
          const dl = row.has_file
            ? `<button type="button" class="btn small" onclick="Generate.downloadComposeDraftFile(${row.id})">下载</button>`
            : "";
          return `<tr>
            <td class="cell-mono">${row.id}</td>
            <td>${escapeHtml(row.title || "")}</td>
            <td>${escapeHtml(row.template_name || "—")}</td>
            <td class="nowrap">${escapeHtml(typeZh)}</td>
            <td class="nowrap" data-compose-status="${row.id}">${this._composeStatusHtml(row)}</td>
            <td class="nowrap muted">${escapeHtml(row.created_at || "")}</td>
            <td class="nowrap">
              ${polishBtn}
              ${dl}
              <button type="button" class="btn small primary" onclick="Generate.publishComposeDraft(${row.id})" title="写入 duty_report，可在报告在线管理中查看">正式保存</button>
              <button type="button" class="btn small danger" onclick="Generate.deleteComposeDraft(${row.id})">删除</button>
            </td>
          </tr>`;
        })
        .join("");
    } catch (e) {
      if (meta)
        meta.textContent = "加载失败";
      tbody.innerHTML = `<tr><td colspan="7" class="muted" style="text-align:center;padding:12px;">${escapeHtml(
        e.message || "加载失败",
      )}</td></tr>`;
    }
  },

  downloadComposeDraftFile(id) {
    const base = typeof API !== "undefined" && API.base !== undefined ? API.base : "";
    window.open(`${base}/api/template/compose-draft/${id}/file`, "_blank", "noopener,noreferrer");
  },

  async deleteComposeDraft(id) {
    if (!confirm("确认删除合成草稿？删除后不可恢复。")) return;
    try {
      await API.del(`/api/template/compose-draft/${id}`);
      toast("已删除草稿", "success");
      await this.refreshComposeDraftList();
    } catch (e) {
      toast(e.message || "删除失败", "error");
    }
  },

  async publishComposeDraft(id) {
    const _t0 = performance.now();
    try {
      const r = await API.post(`/api/report/from-compose-draft/${id}`, {});
      const secs = ((performance.now() - _t0) / 1000).toFixed(2);
      toast(`已生成至报告在线管理（生成时间 ${secs} 秒）`, "success");
    } catch (e) {
      toast(e.message || "生成失败", "error");
    }
  },

  _wireUpload() {
    const form = document.getElementById("upload-form");
    const zone = document.getElementById("tpl-upload-zone");
    const input = document.getElementById("tpl-file-input");
    const name = document.getElementById("tpl-file-name");
    if (!form || !zone || !input) return;
    if (zone._wired) return;
    zone._wired = true;

    const showFile = (text, kind = "") => {
      zone.classList.remove("has-file", "is-error");
      if (text) {
        name.textContent = text;
        if (kind === "error") zone.classList.add("is-error");
        else zone.classList.add("has-file");
      } else {
        name.textContent = "";
      }
    };

    let _errClearTimer = null;
    const showError = (msg) => {
      if (_errClearTimer) clearTimeout(_errClearTimer);
      showFile(msg, "error");
      _errClearTimer = setTimeout(() => {
        if (zone.classList.contains("is-error")) showFile("");
      }, 4000);
    };

    const ALLOWED = [".docx", ".pptx"];

    const autoUpload = async (file) => {
      if (!file) return;
      const fname = (file.name || "").trim();
      if (!fname) {
        const m = "文件名不能为空";
        showError(m);
        toast(m, "error");
        return;
      }
      const dot = fname.lastIndexOf(".");
      const ext = dot >= 0 ? fname.slice(dot).toLowerCase() : "";
      if (!ext) {
        const m = `${fname} · 缺少扩展名，无法识别类型`;
        showError(m);
        toast("文件缺少扩展名", "error");
        return;
      }
      if (!ALLOWED.includes(ext)) {
        const m = `${fname} · 不支持 ${ext}（仅支持 ${ALLOWED.join(" / ")}）`;
        showError(m);
        toast(`扩展名 ${ext} 不在允许范围`, "error");
        return;
      }
      showFile(`${fname} · 上传中…`);
      zone.classList.add("dragover");
      try {
        const fd = new FormData();
        fd.append("file", file, fname);
        await API.upload("/api/template/upload", fd);
        toast(`模板上传成功`, "success");
        showFile(`${fname} · 已上传`);
        await this.loadTemplates();
      } catch (err) {
        showFile("");
        toast(err.message || "上传失败", "error");
      } finally {
        zone.classList.remove("dragover");
        input.value = "";
      }
    };

    zone.addEventListener("click", (e) => {
      if (e.target !== input) input.click();
    });
    zone.addEventListener("keydown", (e) => {
      if (e.key === "Enter" || e.key === " ") {
        e.preventDefault();
        input.click();
      }
    });
    input.addEventListener("change", () => {
      const f = input.files && input.files[0];
      if (f) autoUpload(f);
    });

    ["dragenter", "dragover"].forEach((ev) =>
      zone.addEventListener(ev, (e) => {
        e.preventDefault();
        e.stopPropagation();
        zone.classList.add("dragover");
      }),
    );
    ["dragleave", "drop"].forEach((ev) =>
      zone.addEventListener(ev, (e) => {
        e.preventDefault();
        e.stopPropagation();
        zone.classList.remove("dragover");
      }),
    );
    zone.addEventListener("drop", (e) => {
      const f = e.dataTransfer.files && e.dataTransfer.files[0];
      if (f) autoUpload(f);
    });

    form.addEventListener("submit", (e) => e.preventDefault());
  },

  setStep(n) {
    document.querySelectorAll("#gen-steps .step").forEach((el) => {
      const s = parseInt(el.dataset.step, 10);
      el.classList.toggle("done", s < n);
      el.classList.toggle("active", s === n);
    });
  },

  _tplOptionsHtml(data, emptyLabel) {
    return (
      `<option value="">${emptyLabel}</option>` +
      data.map((t) => `<option value="${t.id}">${escapeHtml(t.name)}</option>`).join("")
    );
  },

  async loadTemplates() {
    const r = await API.get("/api/template/list");
    const data = r.data || [];
    const tbody = document.querySelector("#tpl-table tbody");
    tbody.innerHTML = data.length
      ? data
          .map((t) => {
            const downloadable = t.has_blob || t.file_path;
            const dlBtn = downloadable
              ? `<a class="btn small" href="/api/template/${t.id}/download" download>下载</a>`
              : `<button class="btn small" disabled title="无原始文件">下载</button>`;
            const sizeStr = t.file_size ? ` · ${(t.file_size / 1024).toFixed(1)} KB` : "";
            const kwHtml =
              (t.keywords || "")
                .split(/[,，]/)
                .filter(Boolean)
                .map((k) => `<span class="tag">${escapeHtml(k.trim())}</span>`)
                .join(" ") || "—";
            return `
            <tr>
              <td class="cell-mono muted">#${t.id}</td>
              <td>${escapeHtml(t.name)}<div class="muted" style="font-size:11px;">${escapeHtml(t.original_filename || "")}${sizeStr}</div></td>
              <td class="tpl-keywords-cell">${kwHtml}</td>
              <td class="cell-mono">${t.created_at || ""}</td>
              <td class="nowrap">
                ${dlBtn}
                <button class="btn small danger" onclick="Generate.delTpl(${t.id})">删除</button>
              </td>
            </tr>`;
          })
          .join("")
      : `<tr><td colspan="5" class="muted" style="text-align:center;padding:18px;">暂无模板，先上传一个 .docx 或 .pptx 文件</td></tr>`;

    const sel = document.getElementById("gen-template");
    if (sel) {
      const prev = sel.value;
      sel.innerHTML = this._tplOptionsHtml(data, data.length ? "（请选择模板）" : "（请先上传模板）");
      if (prev && [...sel.options].some((o) => o.value === prev)) sel.value = prev;
    }

    const cnt = document.getElementById("tpl-count");
    if (cnt) cnt.textContent = data.length ? `共 ${data.length} 套` : "";

    this.setStep(data.length ? 2 : 1);
  },

  async delTpl(id) {
    if (!confirm("确认删除模板？")) return;
    await API.del(`/api/template/${id}`);
    toast("已删除", "success");
    const sel = document.getElementById("gen-template");
    if (sel && String(sel.value) === String(id)) {
      this._currentTemplate = null;
      this._slotSourceText = "";
      this._slots = [];
      this._bindings = [];
      this._clearMappingUi();
    }
    this.loadTemplates();
  },

  _clearMappingUi() {
    this._slotSourceText = "";
    const wrap = document.getElementById("gen-tpl-preview-wrap");
    const prev = document.getElementById("gen-tpl-preview");
    const list = document.getElementById("gen-slot-list");
    const hint = document.getElementById("gen-tpl-hint");
    if (wrap) wrap.classList.add("hidden");
    if (prev) prev.innerHTML = "";
    if (list) list.innerHTML = "";
    if (hint)
      hint.innerHTML =
        "选择模板后，服务端将 <strong>.docx 按 zip 解压</strong> 并抽取全文；<strong>左侧</strong>为全文预览（正文中标出 X），<strong>右侧</strong>为占位映射。连续 <code>X</code> 占位规则不变。";
  },

  onTemplateSelect() {
    const tid = document.getElementById("gen-template").value;
    if (!tid) {
      this._currentTemplate = null;
      this._slotSourceText = "";
      this._slots = [];
      this._bindings = [];
      this._clearMappingUi();
      return;
    }
    this.loadTemplateDetail(parseInt(tid, 10));
  },

  async loadTemplateDetail(tid) {
    try {
      const r = await API.get(`/api/template/${tid}`);
      this._currentTemplate = r.data;
      await this._renderPreview();
      this._renderSlotEditors();
      this.setStep(2);
    } catch (e) {
      toast(e.message, "error");
    }
  },

  /** 连续字母 x / X 组成的片段视为一处占位（最长连续段为一块）。 */
  _findXSlots(text) {
    const re = /[xX]+/g;
    const slots = [];
    let m;
    while ((m = re.exec(text)) !== null) {
      slots.push({
        n: slots.length + 1,
        start: m.index,
        end: m.index + m[0].length,
        raw: m[0],
      });
    }
    return slots;
  },

  /** 在解析出的纯文本上为连续 X 编号并包 mark，与占位映射表一致。 */
  _buildXHighlightInnerHtml(text, slots) {
    const t = text || "";
    if (!t.trim()) {
      return '<span class="muted" style="font-size:12px;">暂无解析文本，无法标注 X（请确认模板类型支持正文抽取）。</span>';
    }
    if (!slots || !slots.length) {
      return escapeHtml(t);
    }
    let i = 0;
    const parts = [];
    for (const s of slots) {
      if (s.start > i) parts.push(escapeHtml(t.slice(i, s.start)));
      parts.push(
        `<mark class="tpl-ph" title="占位 ${s.n}">${escapeHtml(s.raw)}<span class="tpl-ph-num">${s.n}</span></mark>`,
      );
      i = s.end;
    }
    if (i < t.length) parts.push(escapeHtml(t.slice(i)));
    return parts.join("") || escapeHtml(t);
  },

  /** 是否已配置替换：手动非空，或已选入库记录。 */
  _slotBindingFilled(binding) {
    if (!binding) return false;
    if (binding.mode === "clean") return !!binding.cleanId;
    return !!String(binding.manual || "").trim();
  },

  /**
   * 左侧「应用映射」预览：已填占位显示替换内容，未填仍显示带编号的 X（与初始标注一致）。
   * 使用底稿 `text` 与 `slots` 的区间，不先整段 replace，避免未填项失去位置。
   */
  _buildMixedReplaceHighlightInnerHtml(text, slots, bindings, resolvedVals) {
    const t = text || "";
    if (!t.trim()) {
      return '<span class="muted" style="font-size:12px;">暂无解析文本，无法标注 X（请确认模板类型支持正文抽取）。</span>';
    }
    if (!slots || !slots.length) {
      return escapeHtml(t);
    }
    let i = 0;
    const parts = [];
    for (let k = 0; k < slots.length; k++) {
      const s = slots[k];
      const val = resolvedVals[k] ?? "";
      const filled = this._slotBindingFilled(bindings[k]);
      if (s.start > i) parts.push(escapeHtml(t.slice(i, s.start)));
      if (filled) {
        parts.push(
          `<span class="tpl-ph-filled" title="占位 ${s.n}（已替换）">${escapeHtml(String(val))}</span>`,
        );
      } else {
        parts.push(
          `<mark class="tpl-ph" title="占位 ${s.n}（未填）">${escapeHtml(s.raw)}<span class="tpl-ph-num">${s.n}</span></mark>`,
        );
      }
      i = s.end;
    }
    if (i < t.length) parts.push(escapeHtml(t.slice(i)));
    return parts.join("") || escapeHtml(t);
  },

  _setPreviewBarTitle(text) {
    const el = document.getElementById("gen-tpl-preview-title");
    if (el) el.textContent = text;
  },

  /** 左侧全文预览区：外层 #gen-tpl-preview 与内层 .preview-ph-body 均可能滚动 */
  _snapshotPreviewScroll(prevEl) {
    const inner = prevEl && prevEl.querySelector(".preview-ph-body");
    return {
      outerTop: prevEl ? prevEl.scrollTop : 0,
      outerLeft: prevEl ? prevEl.scrollLeft : 0,
      innerTop: inner ? inner.scrollTop : 0,
      innerLeft: inner ? inner.scrollLeft : 0,
    };
  },

  _restorePreviewScroll(prevEl, snap) {
    if (!prevEl || !snap) return;
    prevEl.scrollTop = snap.outerTop;
    prevEl.scrollLeft = snap.outerLeft;
    const inner = prevEl.querySelector(".preview-ph-body");
    if (inner) {
      inner.scrollTop = snap.innerTop;
      inner.scrollLeft = snap.innerLeft;
    }
  },

  /** 按当前映射在左侧全文预览区写入替换结果（与③归档预览独立） */
  async applyMappingToLeftPreview(opts) {
    const quiet = opts && opts.quiet;
    if (!this._currentTemplate) {
      if (!quiet) toast("请先选择模板", "error");
      return;
    }
    const wrap = document.getElementById("gen-tpl-preview-wrap");
    const prev = document.getElementById("gen-tpl-preview");
    if (!prev || !wrap || wrap.classList.contains("hidden")) {
      if (!quiet) toast("请先等待模板预览加载完成", "error");
      return;
    }
    try {
      const scrollSnap = this._snapshotPreviewScroll(prev);
      const text =
        (this._slotSourceText && String(this._slotSourceText).length > 0
          ? this._slotSourceText
          : (this._currentTemplate && this._currentTemplate.content)) || "";
      const vals = await this._resolveBindingValues();
      const inner = this._buildMixedReplaceHighlightInnerHtml(
        text,
        this._slots,
        this._bindings,
        vals,
      );
      prev.innerHTML = `<div class="plain-tpl-fallback tpl-x-annot-body preview-ph-body preview-replaced" role="region" aria-label="全文预览：已填项为替换内容，未填项仍为 X 占位">${inner}</div>`;
      this._setPreviewBarTitle("全文预览（已填已替换，未填仍显示 X）");
      requestAnimationFrame(() => {
        this._restorePreviewScroll(prev, scrollSnap);
        requestAnimationFrame(() => this._restorePreviewScroll(prev, scrollSnap));
      });
      if (!quiet) toast("已在左侧更新预览：未填的占位仍带编号显示", "success");
    } catch (e) {
      toast(e.message || "替换失败", "error");
    }
  },

  /** 下载替换后的 Office 文件（.docx / .pptx），在本机用 Word 或 PowerPoint 打开 */
  async openPreviewInWord() {
    if (!this._currentTemplate) {
      toast("请先选择模板", "error");
      return;
    }
    try {
      const content = await this.buildFilledBody();
      if (!content || !String(content).trim()) {
        toast("正文为空，请先填写占位映射或入库选项", "error");
        return;
      }
      const tid = this._currentTemplate.id;
      const base = typeof API !== "undefined" && API.base !== undefined ? API.base : "";
      const bindings = (this._bindings || []).map((b) => ({
        mode: b.mode,
        cleanId: b.cleanId,
        manual: b.manual,
      }));
      const r = await fetch(`${base}/api/template/${tid}/filled-docx`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ content, bindings }),
      });
      if (!r.ok) {
        let msg = "生成预览文件失败";
        try {
          const err = await r.json();
          msg = err.msg || msg;
        } catch (_) {}
        throw new Error(msg);
      }
      const blob = await r.blob();
      const rawName = (this._currentTemplate.name || "模板").replace(/[\\/:*?"<>|]/g, "_");
      const fn = ((this._currentTemplate.original_filename || "") + "").toLowerCase();
      const ext = fn.endsWith(".pptx") ? "pptx" : "docx";
      const fname = `${rawName.slice(0, 80)}_预览.${ext}`;
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = fname;
      a.rel = "noopener";
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
      const okTip =
        fn.endsWith(".pptx")
          ? "已下载 PowerPoint 文件，请在文件夹中双击用 PowerPoint 打开"
          : "已下载 Word 文件，请在文件夹中双击用 Word 打开";
      toast(okTip, "success");
    } catch (e) {
      toast(e.message || "导出失败", "error");
    }
  },

  async _renderPreview() {
    const wrap = document.getElementById("gen-tpl-preview-wrap");
    const prev = document.getElementById("gen-tpl-preview");
    const cnt = document.getElementById("gen-ph-count");
    const hint = document.getElementById("gen-tpl-hint");

    if (!this._currentTemplate) return;

    const tid = this._currentTemplate.id;
    const contentFallback = (this._currentTemplate && this._currentTemplate.content) || "";

    wrap.classList.remove("hidden");
    prev.innerHTML = '<span class="muted">正在加载版式预览…</span>';

    let richHtml = null;
    let previewHint = null;
    let previewFormat = null;
    let plainFromApi = null;
    /** 与导出替换一致：仅 word/document.xml 正文（不含页眉/页脚/脚注等） */
    let plainBodyFromApi = null;
    try {
      const pr = await API.get(`/api/template/${tid}/preview-html`);
      if (pr.data) {
        previewFormat = pr.data.format || null;
        if (pr.data.html) richHtml = pr.data.html;
        if (pr.data.hint) previewHint = pr.data.hint;
        if (pr.data.plain_text != null && String(pr.data.plain_text).trim().length > 0) {
          plainFromApi = String(pr.data.plain_text);
        }
        if (pr.data.plain_text_body != null && String(pr.data.plain_text_body).trim().length > 0) {
          plainBodyFromApi = String(pr.data.plain_text_body);
        }
      }
    } catch (e) {
      previewHint = "预览接口暂不可用（" + (e.message || e) + "），已使用数据库中的解析文本。";
    }

    const baseText =
      plainBodyFromApi != null && String(plainBodyFromApi).trim()
        ? plainBodyFromApi
        : plainFromApi != null
          ? plainFromApi
          : contentFallback;

    this._slotSourceText = baseText;
    this._slots = this._findXSlots(baseText);
    this._bindings = this._slots.map(() => ({
      mode: "manual",
      cleanId: null,
      manual: "",
    }));

    if (cnt) cnt.textContent = `${this._slots.length} 处`;

    /** 与原先「下方标注条」同一套 class：div + pre-wrap，避免用 pre 包裹导致 mark/角标版式发闷 */
    const phWrap = (inner) =>
      `<div class="plain-tpl-fallback tpl-x-annot-body preview-ph-body" role="region" aria-label="模板全文与 X 占位标注">${inner}</div>`;

    if (!baseText.trim()) {
      let html = "";
      if (previewHint) {
        html += `<p class="preview-fallback-hint muted">${escapeHtml(previewHint)}</p>`;
      }
      if (richHtml) {
        html += `<div class="rich-tpl-preview alt-preview">${richHtml}</div>`;
      }
      if (!html.trim()) {
        html =
          '<span class="muted">该模板暂无解析出的正文，请确认文件为 .docx 且内容可读。</span>';
      }
      prev.innerHTML = html;
      this._setPreviewBarTitle("全文预览");
      if (hint) {
        hint.textContent =
          previewHint ||
          "当前模板无正文文本，无法进行 X 占位映射。";
      }
      return;
    }

    const highlighted = this._buildXHighlightInnerHtml(baseText, this._slots);
    let msg =
      previewFormat === "pptx"
        ? "左侧编号仅统计幻灯片与演讲者备注中的 X（与下载 .pptx 替换一致；不含预览里「幻灯片 N」标题行）。"
        : "左侧为正文内 X 占位（与导出替换范围一致；页眉/脚注等处的 X 不计入编号）。表格等多列内容以制表符分列。";
    if (this._slots.length) msg += " 请在右侧完成占位映射。";
    if (previewHint) msg += " " + previewHint;

    prev.innerHTML = phWrap(highlighted);
    this._setPreviewBarTitle("全文预览（X 已内联标注）");
    if (hint) hint.textContent = msg;
  },

  _cleanSelectOptions(selectedId) {
    const opts = ['<option value="">（选择入库记录）</option>'];
    const rows = this._cleanList || [];
    if (!rows.length) {
      opts.push('<option value="" disabled>（该时间范围无匹配入库数据）</option>');
      return opts.join("");
    }
    for (const row of rows) {
      const id = row.id;
      const when = (row.occur_time || row.data_time || "").slice(0, 10);
      const head = row.title || row.tags || row.source || "—";
      const num = this._numericFromClean(row);
      const bits = [head];
      if (num) bits.push(num);
      if (when) bits.push(when);
      const sel = selectedId && Number(selectedId) === id ? " selected" : "";
      const label = sel ? (num || bits.join(" · ")) : bits.join(" · ");
      opts.push(`<option value="${id}"${sel}>${escapeHtml(label)}</option>`);
    }
    return opts.join("");
  },

  /** 入库记录用于填 X：只要数值（93.00% → 93.00），模板里已有 %、万 等单位。 */
  _numericFromClean(row) {
    if (!row) return "";
    const content = String(row.content ?? "").trim();
    const stripped = content.replace(/[%％万个]/g, "").trim();
    const m = stripped.match(/-?\d+(?:\.\d+)?(?:\s*\/\s*-?\d+(?:\.\d+)?)?/);
    if (m) return m[0].replace(/\s+/g, "");
    const mv = row.metric_value;
    if (mv != null && Number.isFinite(Number(mv))) {
      const x = Number(mv);
      if (Number.isInteger(x) || Math.abs(x - Math.round(x)) < 1e-9) return String(Math.round(x));
      return String(x);
    }
    return content;
  },

  _renderSlotEditors() {
    const list = document.getElementById("gen-slot-list");
    if (!list) return;

    if (!this._slots.length) {
      list.innerHTML =
        '<p class="muted" style="margin:0;font-size:13px;">无 X 占位符，无需逐条映射。</p>';
      return;
    }

    list.innerHTML = this._slots
      .map((s, i) => {
        const b = this._bindings[i] || { mode: "manual", cleanId: null, manual: "" };
        const modeManual = b.mode === "manual";
        const modeClean = b.mode === "clean";
        return `
      <div class="slot-row slot-row--compact" data-slot="${i}">
        <div class="slot-row__line">
          <span class="slot-num">#${s.n}</span>
          <code class="slot-raw" title="${escapeHtml(s.raw)}">${escapeHtml(s.raw)}</code>
          <div class="slot-mode">
            <label class="inline-check"><input type="radio" name="slot-mode-${i}" ${modeManual ? "checked" : ""} onclick="Generate.setBindingMode(${i},'manual')" /> 手填</label>
            <label class="inline-check"><input type="radio" name="slot-mode-${i}" ${modeClean ? "checked" : ""} onclick="Generate.setBindingMode(${i},'clean')" /> 入库</label>
          </div>
          <input type="text" class="slot-manual" id="slot-manual-${i}" placeholder="替换为…（最多 50 字）" autocomplete="off"
            maxlength="${V.L.slotManual}" title="选填，最多 50 字符"
            style="display:${modeManual ? "block" : "none"}"
            oninput="Generate.setManual(${i},this.value)" />
          <select class="slot-clean" id="slot-clean-${i}"
            style="display:${modeClean ? "block" : "none"}"
            onchange="Generate.setClean(${i},this.value)">${this._cleanSelectOptions(b.cleanId)}</select>
        </div>
      </div>`;
      })
      .join("");
    this._slots.forEach((_, i) => {
      const el = document.getElementById(`slot-manual-${i}`);
      if (el) el.value = (this._bindings[i] && this._bindings[i].manual) || "";
    });
  },

  async setBindingMode(i, mode) {
    const b = this._bindings[i];
    if (!b) return;
    b.mode = mode;
    if (mode === "clean") {
      await this.refreshCleanList({ quiet: true });
      const sel = document.getElementById(`slot-clean-${i}`);
      const ta = document.getElementById(`slot-manual-${i}`);
      if (ta) ta.style.display = "none";
      if (sel) {
        sel.style.display = "block";
        sel.innerHTML = this._cleanSelectOptions(b.cleanId);
      }
      return;
    }
    const ta = document.getElementById(`slot-manual-${i}`);
    const sel = document.getElementById(`slot-clean-${i}`);
    if (ta) ta.style.display = "block";
    if (sel) sel.style.display = "none";
  },

  setManual(i, v) {
    if (v && v.length > V.L.slotManual) {
      v = v.slice(0, V.L.slotManual);
      const el = document.getElementById(`slot-manual-${i}`);
      if (el) el.value = v;
    }
    if (this._bindings[i]) this._bindings[i].manual = v;
  },

  setClean(i, v) {
    if (this._bindings[i]) this._bindings[i].cleanId = v ? parseInt(v, 10) : null;
    const sel = document.getElementById(`slot-clean-${i}`);
    if (sel) sel.innerHTML = this._cleanSelectOptions(this._bindings[i] && this._bindings[i].cleanId);
  },

  /** 自后向前替换，避免索引位移 */
  applyXReplacements(text, slots, valueStrings) {
    let out = text;
    const pairs = slots
      .map((s, i) => {
        const raw = String(s.raw ?? "");
        const v = valueStrings[i];
        const filled = v != null && String(v).trim() !== "";
        return { ...s, val: filled ? String(v) : raw };
      })
      .sort((a, b) => b.start - a.start);
    for (const s of pairs) {
      out = out.slice(0, s.start) + String(s.val) + out.slice(s.end);
    }
    return out;
  },

  async buildFilledBody() {
    const text =
      (this._slotSourceText && String(this._slotSourceText).length > 0
        ? this._slotSourceText
        : (this._currentTemplate && this._currentTemplate.content)) || "";
    const vals = await this._resolveBindingValues();
    if (!this._slots.length) return text;
    return this.applyXReplacements(text, this._slots, vals);
  },

  async _resolveBindingValues() {
    const vals = [];
    for (let i = 0; i < this._bindings.length; i++) {
      const b = this._bindings[i];
      if (b.mode === "clean" && b.cleanId) {
        let row = this._cleanById[b.cleanId];
        if (!row) {
          try {
            const r = await API.get(`/api/data/clean?${this._cleanQueryString()}`);
            const items = (r.data && r.data.items) || [];
            this._cleanList = items;
            this._cleanById = Object.fromEntries(items.map((x) => [x.id, x]));
            row = this._cleanById[b.cleanId];
          } catch (_) {}
        }
        vals.push(row ? this._numericFromClean(row) : "（未找到该条入库数据，请刷新入库列表）");
      } else {
        vals.push((b.manual || "").trim());
      }
    }
    return vals;
  },
};
