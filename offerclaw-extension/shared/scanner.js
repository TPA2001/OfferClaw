// OfferClaw 扩展 - 表单字段扫描器
// 在真实页面 DOM 上扫描 input/select/textarea/contenteditable，生成后端可匹配的字段结构
// 增强：自定义下拉(custom_select)/日期(date_picker)分类、邻近标签(nearbyLabels)、readOnly/inputType、单选组元素引用
(function () {
  if (globalThis.OC && globalThis.OC.__loaded_scanner) return;
  const OC = globalThis.OC || (globalThis.OC = {});
  OC.__loaded_scanner = true;

  const FIELD_SELECTOR =
    "input:not([type=hidden]):not([type=submit]):not([type=button]):not([type=reset]):not([type=image]), select, textarea, [contenteditable=true]";

  // 常见自研/UI 框架的下拉选择容器类名 / role
  const CUSTOM_SELECT_HINT_CLASSES = [
    "el-select", "ant-select", "ivu-select", "n-select", "van-dropdown-item",
    "el-cascader", "ant-cascader", "ivu-cascader",
    "MuiAutocomplete-root", "moka-select", "chips",
    "select2", "vue-select", "multiselect"
  ].join(",");

  function isVisible(el) {
    if (!el) return false;
    if (el.disabled) return false;
    const rect = el.getBoundingClientRect();
    if (rect.width === 0 && rect.height === 0) {
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
    return `[data-oc-idx="${idx}"]`;
  }

  // 相邻下拉箭头图标（自研组件常以 addon/caret 图标标识下拉）
  function hasSelectIndicator(el) {
    for (let i = 0, node = el; i < 3 && node; i++, node = node.parentElement) {
      const sib = node.querySelector
        ? Array.from(node.querySelectorAll("[class*=icon], [class*=addon], [class*=caret], [class*=arrow], [class*=suffix]"))
        : [];
      for (const s of sib) {
        const cls = (s.className || "") + " " + (s.getAttribute("aria-label") || "");
        if (/caret|caretsvg|-down|chevron|arrow.?down/i.test(cls)) return true;
      }
    }
    return false;
  }

  // 判断元素是否位于受 UI 框架控制的自定义下拉内
  function insideCustomSelect(el) {
    if (!el || el.tagName !== "INPUT") return false;
    const role = el.getAttribute("role") || "";
    if (role === "combobox" || role === "combobox-input" || role === "listbox") return true;
    // 输入框后有下拉箭头图标：强下拉信号
    if (hasSelectIndicator(el)) return true;
    let node = el;
    // 向上找 6 层
    for (let i = 0; i < 6 && node; i++) {
      const cls = (node.getAttribute && node.getAttribute("class")) || "";
      if (cls) {
        if (CUSTOM_SELECT_HINT_CLASSES.split(",").some((c) => cls.trim().split(/\s+/).includes(c.trim()) || cls.includes(c.trim().replace(/^\./, "")))) {
          return true;
        }
        // 通用结构信号：祖先类名含 select/dropdown/cascader/combobox 的下拉容器
        if (/(select|dropdown|cascader|combobox)[-_\s]/i.test(cls) && /container|wrapper|dropdown|select/i.test(cls)) {
          return true;
        }
      }
      node = node.parentElement;
    }
    return false;
  }

  // ===== 移植自 AI-Resume-Form-Filling-Assistant：强健 label 提取（多候选打分选最优）=====
  // 覆盖 Moka/sd 这类"标题在独立 .title-* 容器"的自研组件，并避免误抓页面级大标题。
  const _LABEL_LIKE_SEL =
    '[class*="label"],[class*="Label"],[class*="title"],[class*="Title"],[class*="name"],[class*="Name"],' +
    '[class*="caption"],[class*="Caption"],[class*="header"],[class*="Header"],label,legend,dt,th';
  const _STRUCTURAL_SEL =
    '[class*="form"],[class*="Form"],[class*="field"],[class*="Field"],[class*="item"],[class*="Item"],' +
    '[class*="row"],[class*="Row"],[class*="group"],[class*="Group"],[class*="cell"],[class*="Cell"],' +
    'fieldset,section,article,tr,li,td,th,dl';
  const _CONTROL_SEL =
    'input, textarea, select, button, option, svg, style, script, noscript, [contenteditable="true"], [aria-hidden="true"]';

  function _norm(t) {
    return String(t || "").replace(/\s+/g, " ").replace(/[\r\n]+/g, " ").replace(/[＊*]+\s*$/g, "").trim();
  }
  function _meaningful(t) {
    const n = _norm(t);
    if (!n) return false;
    if (n.length <= 1) return false;
    if (/^[+()\-.\s\d/]+$/.test(n)) return false;
    return true;
  }
  function _fieldScore(t) {
    const n = _norm(t);
    if (!_meaningful(n)) return Number.NEGATIVE_INFINITY;
    let s = 0;
    const L = n.length;
    if (L >= 2 && L <= 16) s += 12; else if (L <= 32) s += 8; else if (L <= 60) s += 3; else s -= 8;
    if (/[：:？?]$/.test(n)) s += 4;
    if (/(姓名|名字|邮箱|邮件|手机|电话|联系方式|证件|身份证|学历|学位|学校|专业|毕业|培养|项目|经历|描述|亮点|成绩|职位|公司|时间|日期)/.test(n)) s += 10;
    if ((n.match(/[：:]/g) || []).length >= 2) s -= 8;
    if (/年\s*月\s*至\s*年\s*月/.test(n)) s -= 10;
    if (/^\+?\d[\d\s\-()]{3,}$/.test(n)) s -= 15;
    if (/^[\u4e00-\u9fa5a-zA-Z]+(?:\s*-\s*[\u4e00-\u9fa5a-zA-Z]+)+$/.test(n)) s -= 4;
    if (/(本科|硕士|博士|大专|高中|统招全日制|中国 - 居民身份证|中国大陆居民|男|女|是|否)$/.test(n)) s -= 6;
    return s;
  }
  function _bestFieldText(cands) {
    let b = "", bs = Number.NEGATIVE_INFINITY;
    for (const c of (Array.isArray(cands) ? cands : [])) {
      const n = _norm(c), sc = _fieldScore(n);
      if (sc > bs) { bs = sc; b = n; }
    }
    return Number.isFinite(bs) ? b : "";
  }
  function _pushUniq(list, value) {
    const t = _norm(value);
    if (_meaningful(t) && !list.includes(t)) list.push(t);
  }
  function _nodeTextNoControls(node, skipNode) {
    if (!node) return "";
    try {
      const clone = node.cloneNode(true);
      const sels = [_CONTROL_SEL];
      if (skipNode && skipNode.id) sels.push("#" + CSS.escape(skipNode.id));
      clone.querySelectorAll(sels.join(",")).forEach((c) => { try { c.remove(); } catch (e) {} });
      const t = _norm(clone.textContent || "");
      return _meaningful(t) ? t : "";
    } catch (e) { return ""; }
  }
  function _structuralContainers(el) {
    const out = [];
    let cur = el.parentElement;
    while (cur && out.length < 4) {
      if (cur.matches && cur.matches(_STRUCTURAL_SEL)) out.push(cur);
      cur = cur.parentElement;
    }
    if (out.length === 0 && el.parentElement) out.push(el.parentElement);
    return out;
  }
  function _directLabelCandidates(el) {
    const c = [];
    _pushUniq(c, el.getAttribute && el.getAttribute("aria-label"));
    const lb = el.getAttribute && el.getAttribute("aria-labelledby");
    if (lb) {
      lb.split(/\s+/).map((id) => document.getElementById(id)).filter(Boolean)
        .forEach((n) => _pushUniq(c, n.textContent || ""));
    }
    if (el.id) {
      const fl = document.querySelector('label[for="' + CSS.escape(el.id) + '"]');
      _pushUniq(c, fl && fl.textContent || "");
    }
    const wrap = el.closest && el.closest("label");
    _pushUniq(c, wrap && wrap.textContent || "");
    _pushUniq(c, el.getAttribute && el.getAttribute("placeholder") || "");
    _pushUniq(c, el.getAttribute && el.getAttribute("name") || "");
    return c;
  }
  function _nearbyLabelCandidates(el) {
    const c = [];
    for (const container of _structuralContainers(el)) {
      for (const child of Array.from(container.children || [])) {
        if (child === el || (child.contains && child.contains(el))) continue;
        _pushUniq(c, _nodeTextNoControls(child, el));
        if (child.querySelectorAll) {
          child.querySelectorAll(_LABEL_LIKE_SEL).forEach((n) => _pushUniq(c, _nodeTextNoControls(n, el)));
        }
      }
    }
    let cur = el;
    for (let d = 0; cur && d < 4; d++) {
      _pushUniq(c, _nodeTextNoControls(cur.previousElementSibling, el));
      _pushUniq(c, _nodeTextNoControls(cur.nextElementSibling, el));
      cur = cur.parentElement;
    }
    return c;
  }

  // 收集元素邻近的标签候选文本（不重复、不含控件自身值）
  function collectNearbyLabels(el) {
    const out = [];
    const pushText = (node) => {
      const t = (node && node.textContent ? node.textContent : "").trim().replace(/\s+/g, " ");
      if (!t || t.length > 60) return;
      if (el.value && t === String(el.value).trim()) return;
      if (!out.includes(t) && t.length <= 40) out.push(t);
    };
    // 0. 参考插件式强健候选（结构容器 children + 邻近兄弟，剔控件文本）
    for (const l of _nearbyLabelCandidates(el)) {
      if (!out.includes(l)) out.push(l);
    }
    // 1. label[for]
    if (el.id) {
      const lbl = document.querySelector(`label[for="${CSS.escape(el.id)}"]`);
      if (lbl) pushText(lbl);
    }
    // 2. 前呼后应 label 兄弟
    let prev = el.previousElementSibling;
    let hops = 0;
    while (prev && hops < 3) {
      if (prev.tagName === "LABEL") { pushText(prev); break; }
      prev = prev.previousElementSibling;
      hops++;
    }
    // 3. 祖先容器里 .label/.form-label/.xxx-form-item-label/title 等
    //    （覆盖 Moka/sd 自研的表单标题容器，如 .apply-field > .title-xxx）
    let anc = el.parentElement;
    for (let i = 0; i < 6 && anc; i++) {
      const lblEl = anc.querySelector([
        ".label", ".form-label", ".control-label",
        ".el-form-item__label", ".ivu-form-item-label",
        ".ant-form-item-label", ".ant-col label",
        "[class*=form-item-label]", "[class*=field-label]",
        "[class*=field-title]", "[class*=form-title]", "[class*=item-title]",
        "[class^=title-]", "[class*=title]" // Moka：title-xxxx
      ].join(","));
      if (lblEl && lblEl !== el) pushText(lblEl);
      anc = anc.parentElement;
    }
    return out.slice(0, 6);
  }

  // 元素是否带日历图标（日期选择器的常见特征）
  function hasCalendarHint(el) {
    if (!el || el.tagName !== "INPUT") return false;
    const iconSel = ".el-input__icon, .el-date-editor, .ant-picker, .ivu-date-picker, .n-date-picker, [class*=calendar-main]";
    let node = el.parentElement;
    for (let i = 0; i < 3 && node; i++) {
      if (node.querySelector(iconSel)) return true;
      const sib = node.querySelector("[class*=icon]");
      if (sib) {
        const scls = (sib.getAttribute && sib.getAttribute("class")) || "";
        if (/calendar|date|range|picker/i.test(scls)) return true;
      }
      node = node.parentElement;
    }
    return false;
  }

  function getLabel(el) {
    if (!el) return "";
    // 强健路径：直接候选 → 邻近候选，均用打分选最优（参考 AI-Resume 插件）
    const direct = _directLabelCandidates(el);
    const directBest = _bestFieldText(direct);
    if (directBest) return directBest;

    const nearby = _nearbyLabelCandidates(el);
    const nearbyBest = _bestFieldText(nearby);
    if (nearbyBest) return nearbyBest;

    // 兜底：placeholder
    return el.placeholder ? el.placeholder.trim() : "";
  }

  function describe(el, idx) {
    const tag = el.tagName.toLowerCase();
    const inputType = (el.getAttribute("type") || "").toLowerCase();
    let type = inputType;
    if (!type) {
      type = tag === "select" ? "select" : tag === "textarea" ? "textarea" : "text";
    }
    if (el.getAttribute("contenteditable") === "true") type = "contenteditable";

    const id = el.id || el.name || `oc_${idx}`;
    const label = getLabel(el);
    const name = el.name || "";
    const placeholder = el.placeholder || "";
    const readOnly = Boolean(el.readOnly) || el.hasAttribute("readonly") || el.getAttribute("aria-readonly") === "true";

    // 权重：contenteditable/原生控件 > 日期 > 自定义下拉 > readonly
    if (type === "text" && el.tagName === "INPUT") {
      const inCustom = insideCustomSelect(el);
      const dateHint = hasCalendarHint(el) || /(出生|生日|毕业|入学|在校|时间|日期|年月|date|month)/i.test(`${label} ${placeholder}`);
      if (dateHint) type = "date_picker";          // 日期优先，即便位于自研下拉容器内（如 Moka 出生日期）
      else if (inCustom) type = "custom_select";
      else if (readOnly) type = "custom_select";   // readonly 文本多是需要点击的下拉
    }

    let current_value = "";
    let options = null;

    if (tag === "select") {
      current_value = el.value || "";
      options = Array.from(el.options).map((o) => ({
        value: o.value,
        label: o.text.trim()
      }));
    } else if (inputType === "radio") {
      const group = document.querySelectorAll(`input[type=radio][name="${CSS.escape(name)}"]`);
      options = Array.from(group).map((r) => ({
        value: r.value,
        label: getLabel(r) || r.value,
        checked: r.checked,
        el: r
      }));
      const checked = Array.from(group).find((r) => r.checked);
      current_value = checked ? checked.value : "";
    } else if (inputType === "checkbox") {
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
      inputType,
      readOnly,
      placeholder,
      current_value,
      options,
      nearbyLabels: collectNearbyLabels(el),
      selector: buildSelector(el, idx),
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

    withContext(fields) {
      fields.forEach((f) => {
        try {
          const el = document.querySelector(f.selector);
          if (!el) return;
          let node = el.closest("fieldset, section, .section, [class*=section], [class*=block], form");
          if (node) {
            const h = node.querySelector("h1, h2, h3, h4, h5, .title, .section-title, legend");
            if (h) f.section = (h.textContent || "").trim();
          }
        } catch (e) {}
      });
      return fields;
    },

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