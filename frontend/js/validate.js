/**
 * 与 backend/validators.py 对齐的前端字段校验与 maxlength 绑定
 */
const V = {
  L: {
    epName: 20,
    epMethod: 16,
    epUrl: 2048,
    epLabel: 64,
    epListPath: 512,
    epBody: 65536,
    epFieldMap: 32768,
    tag: 64,
    tagValue: 20000,
    cleanSource: 64,
    cleanTags: 255,
    cleanCategory: 64,
    cleanContent: 500000,
    reportTitle: 255,
    reportContent: 2000000,
    draftContent: 2000000,
    slotManual: 50,
    searchKeyword: 128,
  },

  str(value, label, opts = {}) {
    const min = opts.min != null ? opts.min : 0;
    const max = opts.max;
    const required = opts.required !== false;
    const s = String(value == null ? "" : value).trim();
    if (!s) {
      if (required) return { ok: false, msg: `请填写${label}` };
      return { ok: true, value: "" };
    }
    if (s.length < min) return { ok: false, msg: `${label}至少 ${min} 个字符` };
    if (max != null && s.length > max) return { ok: false, msg: `${label}不能超过 ${max} 个字符` };
    return { ok: true, value: s };
  },

  text(value, label, opts = {}) {
    const max = opts.max;
    const required = !!opts.required;
    const s = value == null ? "" : String(value);
    if (required && !s.trim()) return { ok: false, msg: `请填写${label}` };
    if (max != null && s.length > max) return { ok: false, msg: `${label}不能超过 ${max} 个字符` };
    return { ok: true, value: s };
  },

  url(value) {
    const r = this.str(value, "接口 URL", { min: 1, max: this.L.epUrl });
    if (!r.ok) return r;
    try {
      const u = new URL(r.value);
      if (u.protocol !== "http:" && u.protocol !== "https:") {
        return { ok: false, msg: "接口 URL 须为 http:// 或 https:// 开头" };
      }
    } catch (_) {
      return { ok: false, msg: "接口 URL 格式不正确" };
    }
    return r;
  },

  jsonObject(raw, label, maxLen) {
    if (raw == null || String(raw).trim() === "") return { ok: true, value: null };
    const text = typeof raw === "string" ? raw.trim() : JSON.stringify(raw);
    if (maxLen && text.length > maxLen) return { ok: false, msg: `${label}不能超过 ${maxLen} 个字符` };
    try {
      const obj = typeof raw === "string" ? JSON.parse(text) : raw;
      if (obj === null || typeof obj !== "object" || Array.isArray(obj)) {
        return { ok: false, msg: `${label}须为 JSON 对象` };
      }
    } catch (_) {
      return { ok: false, msg: `${label} JSON 格式不正确` };
    }
    return { ok: true, value: text };
  },

  fail(msg) {
    toast(msg, "error");
    return false;
  },

  ok(result) {
    return result && result.ok;
  },

  /** 将大数字格式化为易读上限（如 500000 → 50 万） */
  formatMaxChars(n) {
    if (n >= 1_000_000 && n % 1_000_000 === 0) return `${n / 1_000_000} 百万`;
    if (n >= 10_000 && n % 10_000 === 0) return `${n / 10_000} 万`;
    return String(n);
  },

  /** 生成输入限制备注文案 */
  limitHintText(opts = {}) {
    const parts = [];
    if (opts.required) parts.push("必填");
    else if (opts.optional !== false) parts.push("选填");
    const min = opts.min != null ? opts.min : 0;
    const max = opts.max;
    if (min > 0 && max != null) parts.push(`长度 ${min}–${this.formatMaxChars(max)} 字符`);
    else if (max != null) parts.push(`最多 ${this.formatMaxChars(max)} 字符`);
    if (opts.note) parts.push(opts.note);
    return parts.join("，");
  },

  /** 在输入框下方（或 label 内）插入/更新限制备注 */
  attachLimitHint(el, opts) {
    if (!el || el.dataset.limitHintWired === "1") return;
    el.dataset.limitHintWired = "1";
    const text = this.limitHintText(opts);
    if (!text) return;

    let hint;
    const inLabel = el.closest("label");
    if (inLabel && inLabel.contains(el)) {
      hint = inLabel.querySelector(":scope > .field-limit-hint");
      if (!hint) {
        hint = document.createElement("span");
        hint.className = "field-limit-hint muted";
        inLabel.appendChild(hint);
      }
      hint.textContent = text;
      return;
    }

    let host = el.closest(".field-with-hint");
    if (!host) {
      const wrap = document.createElement("span");
      wrap.className = "field-with-hint";
      if (el.classList.contains("slot-manual")) wrap.classList.add("slot-manual-wrap");
      el.parentNode.insertBefore(wrap, el);
      wrap.appendChild(el);
      host = wrap;
    }
    hint = host.querySelector(".field-limit-hint");
    if (!hint) {
      hint = document.createElement("span");
      hint.className = "field-limit-hint muted";
      host.appendChild(hint);
    }
    hint.textContent = text;
  },

  /** 静态表单：maxlength + 限制备注 */
  wireStaticLimits() {
    const L = this.L;
    const fields = {
      "ep-name": { min: 1, max: L.epName, required: true },
      "ep-url": { min: 1, max: L.epUrl, required: true, note: "须为 http:// 或 https:// 开头" },
      "ep-source": { max: L.epLabel, optional: true },
      "ep-category": { max: L.epLabel, optional: true },
      "tag-edit-tag": { min: 1, max: L.tag, required: true },
      "tag-edit-value": { min: 1, max: L.tagValue, required: true },
      "clean-edit-source": { max: L.cleanSource, optional: true },
      "clean-edit-tags": { max: L.cleanTags, optional: true },
      "clean-edit-endpoint-source": { max: L.epLabel, optional: true },
      "clean-edit-endpoint-category": { max: L.epLabel, optional: true },
      "clean-edit-category": { max: L.cleanCategory, optional: true },
      "clean-edit-content": { min: 1, max: L.cleanContent, required: true },
      "f-title": { min: 1, max: L.reportTitle, required: true },
      "f-content": { max: L.reportContent, optional: true },
      "mng-q": { max: L.searchKeyword, optional: true, note: "按标题模糊匹配" },
      "gen-compose-q": { max: L.searchKeyword, optional: true, note: "按标题模糊匹配" },
    };
    Object.entries(fields).forEach(([id, opts]) => {
      const el = document.getElementById(id);
      if (!el) return;
      if (opts.max != null) el.maxLength = opts.max;
      if (opts.min > 0 && el.tagName !== "TEXTAREA") el.minLength = opts.min;
      this.attachLimitHint(el, opts);
    });
  },

  /** 动态生成的带 maxlength 控件（预览标签、占位手填等） */
  wireDynamicLimitHint(el, opts) {
    if (!el) return;
    if (opts.max != null) el.maxLength = opts.max;
    if (opts.min > 0 && el.tagName !== "TEXTAREA") el.minLength = opts.min;
    this.attachLimitHint(el, opts);
  },

  validateEndpointForm(isUpdate) {
    const name = this.str(document.getElementById("ep-name")?.value, "配置名称", {
      min: 1,
      max: this.L.epName,
    });
    if (!this.ok(name)) return this.fail(name.msg);
    const url = this.url(document.getElementById("ep-url")?.value);
    if (!this.ok(url)) return this.fail(url.msg);
    const source = this.str(document.getElementById("ep-source")?.value, "默认来源", {
      required: false,
      max: this.L.epLabel,
    });
    if (!this.ok(source)) return this.fail(source.msg);
    const category = this.str(document.getElementById("ep-category")?.value, "默认类别", {
      required: false,
      max: this.L.epLabel,
    });
    if (!this.ok(category)) return this.fail(category.msg);
    return true;
  },

  validateTaggedFields(tag, value) {
    const t = this.str(tag, "标签", { min: 1, max: this.L.tag });
    if (!this.ok(t)) {
      if (!String(tag || "").trim()) return this.fail("标签值不能为空");
      if (String(tag).trim().length > this.L.tag) return this.fail("标签长度超出限制");
      return this.fail(t.msg);
    }
    const v = this.text(value, "值", { required: true, max: this.L.tagValue });
    if (!this.ok(v)) return this.fail(v.msg);
    if (!String(value || "").trim()) return this.fail("请填写或选中要暂存的内容");
    return true;
  },

  validateCleanForm(requireContent) {
    const source = this.str(document.getElementById("clean-edit-source")?.value, "所属配置", {
      required: false,
      max: this.L.cleanSource,
    });
    if (!this.ok(source)) return this.fail(source.msg);
    const tags = this.str(document.getElementById("clean-edit-tags")?.value, "标签", {
      required: false,
      max: this.L.cleanTags,
    });
    if (!this.ok(tags)) return this.fail(tags.msg);
    const category = this.str(document.getElementById("clean-edit-category")?.value, "入库类别", {
      required: false,
      max: this.L.cleanCategory,
    });
    if (!this.ok(category)) return this.fail(category.msg);
    const epSrc = this.str(
      document.getElementById("clean-edit-endpoint-source")?.value,
      "来源",
      { required: false, max: this.L.epLabel },
    );
    if (!this.ok(epSrc)) return this.fail(epSrc.msg);
    const epCat = this.str(
      document.getElementById("clean-edit-endpoint-category")?.value,
      "类别",
      { required: false, max: this.L.epLabel },
    );
    if (!this.ok(epCat)) return this.fail(epCat.msg);
    const content = this.text(document.getElementById("clean-edit-content")?.value, "值", {
      required: requireContent,
      max: this.L.cleanContent,
    });
    if (!this.ok(content)) return this.fail(content.msg);
    return true;
  },

  validateReportForm() {
    const title = this.str(document.getElementById("f-title")?.value, "标题", {
      min: 1,
      max: this.L.reportTitle,
    });
    if (!this.ok(title)) return this.fail(title.msg);
    const content = this.text(document.getElementById("f-content")?.value, "正文", {
      required: false,
      max: this.L.reportContent,
    });
    if (!this.ok(content)) return this.fail(content.msg);
    return true;
  },

  validateSearchKeyword(elId, label) {
    const el = document.getElementById(elId);
    if (!el) return true;
    const r = this.str(el.value, label || "搜索关键词", { required: false, max: this.L.searchKeyword });
    if (!r.ok) return this.fail(r.msg);
    return true;
  },

  validateSlotManual(value) {
    const r = this.str(value, "替换内容", { required: false, max: this.L.slotManual });
    if (!r.ok) return this.fail(r.msg);
    return true;
  },
};

/** 预览区「标签」输入限制（与暂存校验一致） */
V.PREVIEW_TAG_LIMIT = { min: 1, max: V.L.tag, required: true, note: "暂存前须在正文中选中一段文本" };

document.addEventListener("DOMContentLoaded", () => V.wireStaticLimits());
