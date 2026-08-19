// OfferClaw 扩展 - 表单字段扫描器
// 在真实页面 DOM 上扫描 input/select/textarea/contenteditable，生成后端可匹配的字段结构
(function () {
  if (globalThis.OC && globalThis.OC.__loaded_scanner) return;
  const OC = globalThis.OC || (globalThis.OC = {});
  OC.__loaded_scanner = true;

  const FIELD_SELECTOR =
    "input:not([type=hidden]):not([type=submit]):not([type=button]):not([type=reset]):not([type=image]), select, textarea, [contenteditable=true]";

  function isVisible(el) {
    if (!el) return false;
    if (el.disabled) return false;
    const rect = el.getBoundingClientRect();
    if (rect.width === 0 && rect.height === 0) {
      // contenteditable 可能为 0 尺寸但仍可填
      return el.getAttribute("contenteditable") === "true";
    }
    const style = window.getComputedStyle(el);
    if (style.display === "none" || style.visibility === "hidden") return false;
    return true;
  }

  function buildSelector(el, idx) {
    if (el.id) return `#${CSS.escape(el.id)}`;
    if (el.name) {
      const tag = el.tagName.toLowerCase();
      return `${tag}[name="${CSS.escape(el.name)}"]`;
    }
    // 必须与 scan() 里 setAttribute("data-oc-idx", String(idx)) 完全一致
    return `[data-oc-idx="${idx}"]`;
  }

  function getLabel(el) {
    // 1. label[for=id]
    if (el.id) {
      const lbl = document.querySelector(`label[for="${CSS.escape(el.id)}"]`);
      if (lbl) return lbl.textContent.trim();
    }
    // 2. 包裹的 label
    const wrap = el.closest("label");
    if (wrap) return wrap.textContent.trim();
    // 3. aria-label
    if (el.getAttribute("aria-label")) return el.getAttribute("aria-label").trim();
    // 4. aria-labelledby
    const lb = el.getAttribute("aria-labelledby");
    if (lb) {
      const tgt = document.getElementById(lb);
      if (tgt) return tgt.textContent.trim();
    }
    // 5. 前一个 label 兄弟
    let prev = el.previousElementSibling;
    while (prev) {
      if (prev.tagName === "LABEL") return prev.textContent.trim();
      prev = prev.previousElementSibling;
    }
    // 7. 祖先容器内带 label 语义的元素（常见网申系统框架）
    //    element-ui: .el-form-item__label | iView: .ivu-form-item-label
    //    antd: .ant-form-item-label | 通用: .label / .form-label / .control-label
    //    结构形如：<div class="form-item"><span class="label">姓名</span><input>
    let anc = el.parentElement;
    for (let i = 0; i < 4 && anc; i++) {
      const lblEl = anc.querySelector(
        ".label, .form-label, .control-label, .el-form-item__label, " +
        ".ivu-form-item-label, .ant-form-item-label label, [class*=form-item-label]"
      );
      if (lblEl && lblEl !== el) {
        const t = (lblEl.textContent || "").trim();
        if (t) return t;
      }
      anc = anc.parentElement;
    }

    // 8. 紧邻的前一个文本节点（如 <span>姓名</span> <input> 或 纯文本+input）
    let sib = el.previousSibling;
    while (sib) {
      if (sib.nodeType === 3 && sib.textContent.trim()) return sib.textContent.trim();
      sib = sib.previousSibling;
    }

    // 9. placeholder
    if (el.placeholder) return el.placeholder.trim();
    return "";
  }

  function describe(el, idx) {
    const tag = el.tagName.toLowerCase();
    let type = (el.getAttribute("type") || "").toLowerCase();
    if (!type) {
      type = tag === "select" ? "select" : tag === "textarea" ? "textarea" : "text";
    }
    if (el.getAttribute("contenteditable") === "true") type = "contenteditable";

    const id = el.id || el.name || `oc_${idx}`;
    const label = getLabel(el);
    const name = el.name || "";
    const placeholder = el.placeholder || "";

    let current_value = "";
    let options = null;

    if (tag === "select") {
      current_value = el.value || "";
      options = Array.from(el.options).map((o) => ({
        value: o.value,
        label: o.text.trim()
      }));
    } else if (type === "radio") {
      // 同 name 单选组合并
      const group = document.querySelectorAll(`input[type=radio][name="${CSS.escape(name)}"]`);
      options = Array.from(group).map((r) => ({
        value: r.value,
        label: getLabel(r) || r.value,
        checked: r.checked
      }));
      const checked = Array.from(group).find((r) => r.checked);
      current_value = checked ? checked.value : "";
    } else if (type === "checkbox") {
      current_value = el.checked ? "true" : "false";
      options = [{ value: "true", label: "是" }, { value: "false", label: "否" }];
    } else if (type === "contenteditable") {
      current_value = (el.textContent || "").trim();
    } else {
      current_value = el.value || "";
    }

    return {
      id,
      name,
      label,
      type,
      placeholder,
      current_value,
      options,
      selector: buildSelector(el, idx),
      // 真实 DOM 元素引用：填表时用它直接定位，彻底避免 CSS 选择器漂移/失效
      el,
      _oc_idx: idx
    };
  }

  OC.scanner = {
    FIELD_SELECTOR,

    scan() {
      const fields = [];
      const all = document.querySelectorAll(FIELD_SELECTOR);
      let idx = 0;
      all.forEach((el) => {
        if (!isVisible(el)) return;
        // 标记 data-oc-idx 便于选择器兜底（值必须与 buildSelector 一致：String(idx)）
        if (!el.id && !el.name) {
          el.setAttribute("data-oc-idx", String(idx));
        }
        try {
          const f = describe(el, idx);
          if (f) fields.push(f);
        } catch (e) {
          console.warn("[OfferClaw] 字段描述失败:", e);
        }
        idx++;
      });
      return fields;
    },

    // 给字段附加区块上下文（section），便于后端匹配
    withContext(fields) {
      fields.forEach((f) => {
        try {
          const el = document.querySelector(f.selector);
          if (!el) return;
          // 向上找最近的有标题语义的容器
          let node = el.closest("fieldset, section, .section, [class*=section], [class*=block], form");
          if (node) {
            const h = node.querySelector("h1, h2, h3, h4, h5, .title, .section-title, legend");
            if (h) f.section = (h.textContent || "").trim();
          }
        } catch (e) {}
      });
      return fields;
    },

    // 生成页面结构签名（用于映射缓存键，非 URL 维度）
    pageSignature(fields) {
      const sig = fields.map((f) => `${f.type}|${f.label}|${f.name}`).join("||").toLowerCase();
      let hash = 0;
      for (let i = 0; i < sig.length; i++) {
        hash = ((hash << 5) - hash + sig.charCodeAt(i)) | 0;
      }
      return "pg_" + Math.abs(hash).toString(36);
    }
  };
})();
