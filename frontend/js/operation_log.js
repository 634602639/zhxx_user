// ========== 操作日志 ==========
const Logs = {
  async refresh() {
    try {
      const kw = (document.getElementById("log-q")?.value || "").trim();
      const qs = new URLSearchParams({ size: "300" });
      if (kw) qs.set("keyword", kw);
      const r = (await API.get("/api/logs?" + qs.toString())).data || {};
      const items = r.items || [];
      const total = r.total || 0;

      const meta = document.getElementById("log-meta");
      if (meta) {
        meta.textContent = items.length < total
          ? `共 ${total} 条，显示最近 ${items.length} 条`
          : `共 ${total} 条`;
      }

      const tbody = document.querySelector("#log-table tbody");
      if (!tbody) return;
      if (!items.length) {
        tbody.innerHTML =
          '<tr><td colspan="6" class="muted" style="text-align:center;padding:12px;">暂无日志记录</td></tr>';
        return;
      }
      tbody.innerHTML = items.map(i => `
        <tr>
          <td>${i.id}</td>
          <td>${escapeHtml(String(i.module || ""))}</td>
          <td>${escapeHtml(String(i.action || ""))}</td>
          <td>${escapeHtml(String(i.detail || ""))}</td>
          <td>${i.success
            ? '<span class="tag ok">成功</span>'
            : '<span class="tag danger">失败</span>'}</td>
          <td>${i.created_at || ""}</td>
        </tr>`).join("");
    } catch (e) {
      toast(e.message, "error");
    }
  },
};

// 回车即查询
(function wireLogSearch() {
  const q = document.getElementById("log-q");
  if (!q || q._wiredLogs) return;
  q._wiredLogs = true;
  q.addEventListener("keydown", (ev) => {
    if (ev.key === "Enter") { ev.preventDefault(); Logs.refresh(); }
  });
})();
