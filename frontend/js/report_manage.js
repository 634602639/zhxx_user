const Manage = {
  _listPageSize: 20,

  _todayYmd() {
    const d = new Date();
    const pad = (n) => String(n).padStart(2, "0");
    return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
  },

  ensureFilterDates() {
    const today = this._todayYmd();
    const df = document.getElementById("mng-date-from");
    const dt = document.getElementById("mng-date-to");
    if (df && !df.value) df.value = today;
    if (dt && !dt.value) dt.value = today;
  },

  _queryString() {
    const params = new URLSearchParams();
    params.set("page", "1");
    params.set("size", String(this._listPageSize));
    const qEl = document.getElementById("mng-q");
    const df = document.getElementById("mng-date-from");
    const dt = document.getElementById("mng-date-to");
    const off = document.getElementById("mng-office");
    if (qEl && String(qEl.value || "").trim()) {
      if (!V.validateSearchKeyword("mng-q", "搜索关键词")) return "";
      params.set("keyword", String(qEl.value || "").trim());
    }
    if (df && df.value) params.set("date_from", df.value);
    if (dt && dt.value) params.set("date_to", dt.value);
    if (off && off.value && off.value !== "all") params.set("report_type", off.value);
    return params.toString();
  },

  async search() {
    const meta = document.getElementById("mng-rpt-meta");
    const qs = this._queryString();
    try {
      const r = (await API.get("/api/report/list?" + qs)).data;
      const tbody = document.querySelector("#rpt-table tbody");
      const total = typeof r.total === "number" ? r.total : 0;
      const items = r.items || [];
      const n = items.length;

      if (meta) {
        if (!n) {
          meta.textContent =
            total === 0
              ? "无匹配记录（可调整条件后查询）"
              : `共 ${total} 条匹配`;
        } else {
          meta.textContent =
            n < total
              ? `共 ${total} 条匹配，当前显示 ${n} 条（第 1 页，每页 ${this._listPageSize} 条）`
              : `共 ${total} 条`;
        }
      }

      if (!n) {
        tbody.innerHTML =
          '<tr><td colspan="5" class="muted" style="text-align:center;padding:12px;">无匹配记录（可调整条件后查询）</td></tr>';
        return;
      }

      tbody.innerHTML = items.map(i => {
        const rt =
          i.report_type === "word"
            ? "Word"
            : i.report_type === "ppt"
              ? "PPT"
              : i.report_type || "—";
        const isPpt = i.report_type === "ppt";
        const officeFmt = isPpt ? "ppt" : "word";
        const officeLabel = isPpt ? "PPT" : "Word";
        return `
        <tr>
          <td>${i.id}</td>
          <td>${escapeHtml(String(i.title || ""))}</td>
          <td>${rt}</td>
          <td>${i.report_date||""}</td>
          <td>
            <button class="btn small" onclick="Manage.openEdit(${i.id})">编辑</button>
            <button class="btn small" onclick="Manage.exportItem(${i.id},'${officeFmt}')">${officeLabel}</button>
            <button class="btn small" onclick="Manage.exportItem(${i.id},'pdf')">PDF</button>
            <button class="btn small danger" onclick="Manage.del(${i.id})">删除</button>
          </td>
        </tr>`;
      }).join("");
    } catch (e) {
      if (meta) meta.textContent = "加载失败";
      toast(e.message, "error");
    }
  },

  // 仅允许 Word / PPT；与后端 _IMPORT_ALLOWED_EXT 对齐
  _IMPORT_EXT: [".docx", ".doc", ".pptx", ".ppt"],

  openImport() {
    let inp = document.getElementById("mng-import-input");
    if (!inp) {
      inp = document.createElement("input");
      inp.type = "file";
      inp.id = "mng-import-input";
      inp.accept = this._IMPORT_EXT.join(",");
      inp.hidden = true;
      document.body.appendChild(inp);
    }
    if (!inp._wiredImport) {
      inp._wiredImport = true;
      inp.addEventListener("change", () => {
        const f = inp.files && inp.files[0];
        inp.value = "";
        if (f) this.importFile(f);
      });
    }
    inp.click();
  },

  async importFile(file) {
    const fname = (file.name || "").trim();
    if (!fname) {
      toast("文件名不能为空", "error");
      return;
    }
    const dot = fname.lastIndexOf(".");
    const ext = dot >= 0 ? fname.slice(dot).toLowerCase() : "";
    if (!this._IMPORT_EXT.includes(ext)) {
      toast(
        `仅支持 Word / PPT 文件（${this._IMPORT_EXT.join(" / ")}），收到 ${ext || "无扩展名"}`,
        "error",
      );
      return;
    }
    try {
      const fd = new FormData();
      fd.append("file", file, fname);
      const r = await API.upload("/api/report/import-file", fd);
      const item = r.data || {};
      toast("模板上传成功", "success");
      await this.search();
    } catch (e) {
      toast(e.message || "导入失败", "error");
    }
  },

  // 锁定/解锁 标题、文稿类型、报告日期（编辑时仅允许改正文）
  _setMetaLocked(locked) {
    const title = document.getElementById("f-title");
    const type = document.getElementById("f-type");
    const date = document.getElementById("f-date");
    if (title) title.readOnly = locked;
    if (type) type.disabled = locked;
    if (date) date.readOnly = locked;
  },

  openAdd() {
    this._fillForm({});
    this._setMetaLocked(false);
    document.getElementById("drawer-title").textContent = "新增值勤报告";
    document.getElementById("rpt-drawer").classList.remove("hidden");
  },

  async openEdit(id) {
    try {
      const r = (await API.get(`/api/report/${id}`)).data || {};
      this._fillForm(r);
      this._setMetaLocked(true);
      document.getElementById("drawer-title").textContent = `编辑值勤报告 #${id}`;
      document.getElementById("rpt-drawer").classList.remove("hidden");
    } catch (e) {
      toast(e.message || "加载失败", "error");
    }
  },

  closeDrawer() {
    document.getElementById("rpt-drawer").classList.add("hidden");
  },

  _fillForm(r) {
    document.getElementById("f-id").value = r.id || "";
    document.getElementById("f-title").value = r.title || "";
    document.getElementById("f-type").value = r.report_type || "word";
    document.getElementById("f-date").value = r.report_date || this._todayYmd();
    document.getElementById("f-content").value = r.content || "";
  },

  async save() {
    if (!V.validateReportForm()) return;
    const id = document.getElementById("f-id").value;
    const body = {
      title: document.getElementById("f-title").value,
      report_type: document.getElementById("f-type").value,
      report_date: document.getElementById("f-date").value,
      content: document.getElementById("f-content").value,
    };
    try {
      if (id) await API.put(`/api/report/${id}`, body);
      else await API.post("/api/report/add", body);
      toast(id ? "修改成功" : "新增成功", "success");
      this.closeDrawer();
      this.search();
    } catch (e) { toast(e.message, "error"); }
  },

  async del(id) {
    if (!confirm("确认删除该值勤报告？")) return;
    try {
      await API.del(`/api/report/${id}`);
      toast("已删除", "success");
      this.search();
    } catch (e) { toast(e.message, "error"); }
  },

  exportFmt(fmt) {
    const id = document.getElementById("f-id").value;
    if (!id) return toast("请先保存报告", "error");
    this.exportItem(parseInt(id), fmt);
  },

  exportItem(id, fmt) {
    window.open(`/api/report/${id}/export?format=${fmt}`, "_blank");
  },
};

(function wireManageReportFilters() {
  const q = document.getElementById("mng-q");
  if (!q || q._wiredManage) return;
  q._wiredManage = true;
  q.addEventListener("keydown", (ev) => {
    if (ev.key === "Enter") {
      ev.preventDefault();
      Manage.search();
    }
  });
})();
