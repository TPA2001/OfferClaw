// OfferClaw 扩展 - 确定性填写运行时
// 在真实页面 DOM 上执行填写，兼容 React/Vue 受控组件（nativeInputValueSetter）
(function () {
  if (globalThis.OC && globalThis.OC.__loaded_filler) return;
  const OC = globalThis.OC || (globalThis.OC = {});
  OC.__loaded_filler = true;

  // 模拟 React/Vue 的事件触发，确保受控组件感知到值变化
  function fireEvents(el) {
    el.dispatchEvent(new Event("input", { bubbles: true }));
    el.dispatchEvent(new Event("change", { bubbles: true }));
    el.dispatchEvent(new Event("blur", { bubbles: true }));
  }

  function setNativeValue(el, value) {
    const proto =
      el.tagName === "TEXTAREA"
        ? HTMLTextAreaElement.prototype
        : el.tagName === "SELECT"
        ? HTMLSelectElement.prototype
        : HTMLInputElement.prototype;
    const desc = Object.getOwnPropertyDescriptor(proto, "value");
    if (desc && desc.set) {
      desc.set.call(el, value);
    } else {
      el.value = value;
    }
    fireEvents(el);
  }

  // 高亮已填字段（视觉反馈）
  function highlight(el, status) {
    el.classList.remove("oc-fill-ok", "oc-fill-warn", "oc-fill-skip");
    if (status === "ok") el.classList.add("oc-fill-ok");
    else if (status === "warn") el.classList.add("oc-fill-warn");
    else if (status === "skip") el.classList.add("oc-fill-skip");
  }

  OC.filler = {
    // 按 mapping 填写单个字段
    async fillOne(field, mapping) {
      // 元素定位优先级：① 扫描时挂的真实 DOM 引用（最稳）② 渲染器 fallback
      let el = field.el || null;
      if (!el && field.selector) {
        try { el = document.querySelector(field.selector); } catch (e) { el = null; }
      }
      if (!el && field.id) {
        el = document.getElementById(field.id) ||
          (field.name ? document.querySelector(`[name="${CSS.escape(field.name)}"]`) : null);
      }
      if (!el) return { ok: false, reason: "元素未找到", status: "skip" };

      const value = mapping.value;
      const action = mapping.action || "fill";

      if (action === "skip" || action === "manual") {
        highlight(el, "skip");
        return { ok: false, reason: mapping.reason || "跳过/人工", status: "skip" };
      }
      if (value == null || value === "") {
        highlight(el, "skip");
        return { ok: false, reason: "无值", status: "skip" };
      }

      try {
        if (field.type === "contenteditable") {
          el.textContent = value;
          fireEvents(el);
          highlight(el, "ok");
          return { ok: true, status: "ok" };
        }
        if (field.type === "select") {
          setNativeValue(el, value);
          highlight(el, "ok");
          return { ok: true, status: "ok" };
        }
        if (field.type === "radio") {
          const opt = (field.options || []).find(
            (o) => String(o.value) === String(value) || String(o.label) === String(value)
          );
          if (opt) {
            const r = document.querySelector(
              `input[type=radio][name="${CSS.escape(field.name)}"][value="${CSS.escape(opt.value)}"]`
            );
            if (r) {
              r.checked = true;
              fireEvents(r);
              highlight(el, "ok");
              return { ok: true, status: "ok" };
            }
          }
          highlight(el, "warn");
          return { ok: false, reason: "选项无匹配", status: "warn" };
        }
        if (field.type === "checkbox") {
          const v = String(value).toLowerCase();
          el.checked = v === "true" || v === "是" || v === "1" || v === "yes";
          fireEvents(el);
          highlight(el, "ok");
          return { ok: true, status: "ok" };
        }
        // 普通文本类
        setNativeValue(el, String(value));
        highlight(el, "ok");
        return { ok: true, status: "ok" };
      } catch (e) {
        highlight(el, "warn");
        return { ok: false, reason: String(e), status: "warn" };
      }
    },

    // 批量填写：mappings 含 field_id → 与 fields 对齐；
    // 兜底：field_id 对齐失败时（如表单字段无稳定 id/name，scan 时 idx 漂移），
    // 改用 mapping 自带的 selector 直接定位真实 DOM 元素
    async fillAll(fields, mappings) {
      const byId = {};
      fields.forEach((f) => {
        byId[f.id] = f;
        if (f.name) byId[f.name] = f;
      });
      const report = { filled: 0, skipped: 0, warn: 0, total: mappings.length, details: [] };
      for (const m of mappings) {
        const fid = m.field_id || m.id;
        let field = byId[fid] || fields[m._idx];
        // 兜底定位：field_id 找不到时，用 mapping 自带的 selector 直接定位 DOM
        if (!field && m.selector) {
          let el = null;
          try { el = document.querySelector(m.selector); } catch (e) { el = null; }
          if (el) field = { selector: m.selector, type: m.type, name: m.field_name, el };
        }
        if (!field) {
          report.skipped++;
          report.details.push({ field_id: fid, ok: false, reason: "字段未找到" });
          continue;
        }
        const r = await this.fillOne(field, m);
        if (r.status === "ok") report.filled++;
        else if (r.status === "warn") report.warn++;
        else report.skipped++;
        report.details.push({ field_id: fid, ok: r.ok, reason: r.reason, status: r.status });
      }
      return report;
    },

    // 清除高亮
    clearHighlight() {
      document.querySelectorAll(".oc-fill-ok,.oc-fill-warn,.oc-fill-skip").forEach((el) => {
        el.classList.remove("oc-fill-ok", "oc-fill-warn", "oc-fill-skip");
      });
    }
  };
})();
