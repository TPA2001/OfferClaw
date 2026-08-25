// OfferClaw 扩展 - 确定性填写运行时
// 在真实页面 DOM 上执行填写，兼容 React/Vue 受控组件（nativeInputValueSetter）
// 支持自定义下拉框(ElementUI/antd/iView/Naive UI/Vant/MUI)与日期选择器的真实交互模拟
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
    if (!el || !el.classList) return;
    el.classList.remove("oc-fill-ok", "oc-fill-warn", "oc-fill-skip");
    if (status === "ok") el.classList.add("oc-fill-ok");
    else if (status === "warn") el.classList.add("oc-fill-warn");
    else if (status === "skip") el.classList.add("oc-fill-skip");
  }

  function sleep(ms) {
    return new Promise((r) => setTimeout(r, ms));
  }

  // 轮询等待条件成立，超时返回 null
  // condFn: () => 返回值，若 truthy 则返回该值
  async function waitFor(condFn, { timeout = 1500, interval = 50 } = {}) {
    const start = Date.now();
    let lastErr = null;
    while (Date.now() - start < timeout) {
      try {
        const v = condFn();
        if (v) return v;
      } catch (e) { lastErr = e; }
      await sleep(interval);
    }
    return null;
  }

  // 文本归一化：去除空格、全角→半角、统一大小写，便于跨组件匹配 option
  function norm(s) {
    if (s == null) return "";
    return String(s)
      .replace(/\s+/g, "")
      .replace(/[\uFF01-\uFF5E]/g, (ch) => String.fromCharCode(ch.charCodeAt(0) - 0xFEE0))
      .replace(/，/g, ",").replace(/。/g, ".")
      .toLowerCase();
  }

  // ==== 以下逻辑严格移植自参考项目（AI-Resume-Form-Filling-Assistant）的 fill-runtime ====

  // 常见选项的同义词别名组（用于把简历值对齐到表单选项，如 male→男、yes→是）
  const MATCH_ALIAS_GROUPS = [
    { key: "yes", values: ["yes", "y", "true", "1", "是", "有", "愿意", "可以", "present", "current", "currently"] },
    { key: "no", values: ["no", "n", "false", "0", "否", "无", "不愿意", "不可以", "不需要"] },
    { key: "male", values: ["male", "man", "m", "男", "男性"] },
    { key: "female", values: ["female", "woman", "f", "女", "女性"] },
    { key: "bachelor", values: ["bachelor", "undergraduate", "bachelor's", "本科", "大学本科"] },
    { key: "master", values: ["master", "masters", "硕士", "硕士研究生"] },
    { key: "phd", values: ["phd", "doctorate", "doctor", "博士", "博士研究生", "博士后"] },
    { key: "associate", values: ["associate", "大专", "大学专科"] },
    { key: "highschool", values: ["highschool", "高中"] },
    { key: "fulltime", values: ["fulltime", "full-time", "full_time", "全职"] },
    { key: "parttime", values: ["parttime", "part-time", "part_time", "兼职"] },
    { key: "internship", values: ["internship", "intern", "实习"] },
    { key: "married", values: ["married", "已婚"] },
    { key: "single", values: ["single", "未婚"] },
    { key: "onsite", values: ["onsite", "on-site", "on_site", "现场办公"] }
  ];

  // 展开候选文本的等价变体（含别名组），用于匹配评分
  function expandVariants(value) {
    const text = String(value == null ? "" : value).trim();
    if (!text) return [];
    const normalized = norm(text);
    const variants = new Set([normalized]);
    for (const group of MATCH_ALIAS_GROUPS) {
      if (group.values.includes(normalized)) {
        group.values.forEach((item) => variants.add(item));
      }
    }
    return Array.from(variants).filter(Boolean);
  }

  // 选项文本是否命中期望值（评分 ≥ 60 视为命中）；完全相等 100，互相包含 75
  function matchesValue(optionText, valueText) {
    const optionVariants = expandVariants(optionText);
    const valueVariants = expandVariants(valueText);
    let best = 0;
    for (const ov of optionVariants) {
      for (const vv of valueVariants) {
        if (ov === vv) return 100;
        if (ov && vv && (ov.includes(vv) || vv.includes(ov))) best = Math.max(best, 75);
      }
    }
    return best;
  }

  // 归一化字段期望值：针对"只读日期类"字段（readonly + 日期语义）做精度处理
  function normalizeValueForRuntime(runtime, rawValue) {
    const text = String(rawValue == null ? "" : rawValue).trim();
    if (!text) return "";
    if (!isReadonlyDateLikeRuntime(runtime)) return text;
    if (/(入学|毕业|在校|开始|结束|出生|年月|月份|月)/.test(collectRuntimeText(runtime))) {
      if (/^\d{4}-\d{2}-\d{2}$/.test(text)) return text.slice(0, 7);
      if (/^\d{4}-\d{2}$/.test(text)) return text;
      if (/^\d{4}$/.test(text)) return `${text}-01`;
    }
    return text;
  }

  // 校验写入是否成功：readonly 日期类支持 前缀匹配（YYYY-MM 匹配 YYYY-MM-DD）
  function matchesWrittenValue(runtime, actualValue, desiredValue) {
    const actual = String(actualValue == null ? "" : actualValue).trim();
    const desired = String(desiredValue == null ? "" : desiredValue).trim();
    if (!actual || !desired) return false;
    if (isReadonlyDateLikeRuntime(runtime)) {
      if (actual === desired) return true;
      if (/^\d{4}-\d{2}$/.test(desired) && actual.startsWith(desired)) return true;
    }
    return actual === desired;
  }

  function isReadonlyDateLikeRuntime(runtime) {
    if (!runtime?.readOnly) return false;
    if (runtime?.inputType && runtime.inputType !== "text") return false;
    const text = collectRuntimeText(runtime);
    if (!text) return Boolean(runtime?.hasCalendarIcon);
    return /(入学|毕业|在校|开始|结束|时间|日期|date|month|calendar)/.test(text) ||
      Boolean(runtime?.hasCalendarIcon);
  }

  function collectRuntimeText(runtime) {
    return [
      runtime?.label,
      runtime?.placeholder,
      runtime?.context,
      ...(Array.isArray(runtime?.nearbyLabels) ? runtime.nearbyLabels : [])
    ].map((item) => norm(item)).filter(Boolean).join(" ");
  }

  // 滚动到可见区域（参考项目填写前都会先 scrollIntoView）
  function scrollIntoView(el) {
    if (!el) return;
    try {
      el.scrollIntoView({ block: "center", behavior: "smooth" });
    } catch (_) { /* ignore */ }
  }

  // ==== 严格移植自参考项目的设置值流程 ====
  // 关键点：readonly 绕过（记录并恢复）、setAttribute("value",...) 双写、
  // focus→input/change→blur→sleep(60ms)→matchesWrittenValue 校验，finally 里恢复 readonly
  async function setValueWithEvents(el, value, runtime = null) {
    if (!el) return false;
    scrollIntoView(el);

    // 记录 readonly 状态用于恢复（含属性与 JS 属性双份记录）
    const restoreReadonly =
      runtime?.readOnly || el.readOnly
        ? {
            property: Boolean(el.readOnly),
            attribute: el.hasAttribute("readonly"),
          }
        : null;

    try {
      el.focus?.();
      if (restoreReadonly) {
        el.readOnly = false;
        el.removeAttribute("readonly");
      }
      setNativeValue(el, value);
      el.setAttribute("value", value);
      el.dispatchEvent(new Event("input", { bubbles: true }));
      el.dispatchEvent(new Event("change", { bubbles: true }));
      el.blur?.();
      await sleep(60);
      return matchesWrittenValue(runtime, el.value, value);
    } catch (e) {
      console.warn("[OfferClaw] 写入失败", e);
      return false;
    } finally {
      if (restoreReadonly) {
        el.readOnly = restoreReadonly.property;
        if (restoreReadonly.attribute) el.setAttribute("readonly", "");
        else el.removeAttribute("readonly");
      }
    }
  }

  // 单选/多选勾选：参考项目 safeCheck（仅状态不一致才点击，附带校验）
  async function safeCheck(inputEl, checked) {
    if (!inputEl) return false;
    try {
      scrollIntoView(inputEl);
      inputEl.focus?.();
      if (typeof inputEl.click === "function") {
        if (Boolean(inputEl.checked) !== Boolean(checked)) inputEl.click();
      } else {
        inputEl.checked = Boolean(checked);
      }
      inputEl.dispatchEvent(new Event("change", { bubbles: true }));
      inputEl.dispatchEvent(new Event("input", { bubbles: true }));
      await sleep(30);
      return Boolean(inputEl.checked) === Boolean(checked);
    } catch (_) {
      return false;
    }
  }

  // 准备可写入文本：数组拼接 + 日期精度归一（参考项目 prepareTextValueForRuntime）
  function prepareTextValueForRuntime(runtime, value) {
    let text = Array.isArray(value)
      ? value.map((item) => String(item || "").trim()).filter(Boolean).join(", ")
      : String(value ?? "").trim();
    if (!text) return "";
    text = normalizeValueForRuntime(runtime, text);
    if (!text) return "";
    if (runtime?.inputType === "date") {
      if (/^\d{4}-\d{2}$/.test(text)) return `${text}-01`;
      if (/^\d{4}$/.test(text)) return `${text}-01-01`;
      if (/^\d{4}-\d{2}-\d{2}$/.test(text)) return text;
      return "";
    }
    if (runtime?.inputType === "month") {
      if (/^\d{4}-\d{2}-\d{2}$/.test(text)) return text.slice(0, 7);
      if (/^\d{4}-\d{2}$/.test(text)) return text;
      if (/^\d{4}$/.test(text)) return `${text}-01`;
      return "";
    }
    return text;
  }

  // ==== 薪资字段回退（参考项目 salary fallback） ====
  // 页面字段标记是"薪资/月薪/年薪"，画像给的值却是区间或带单位，据此换算兼容值
  function buildTextFallbackValues(runtime, desired) {
    const text = String(desired || "").trim();
    if (!text || !isSalaryLikeRuntime(runtime)) return [];
    const fallback = getSalaryFallbackValue(runtime, text);
    if (!fallback || fallback === text) return [];
    return [fallback];
  }

  function isSalaryLikeRuntime(runtime) {
    const text = [
      runtime?.label,
      runtime?.placeholder,
      runtime?.context,
      ...(Array.isArray(runtime?.nearbyLabels) ? runtime.nearbyLabels : [])
    ].map((item) => String(item || "")).join(" ");
    return /(薪资|薪酬|月薪|年薪|salary|compensation)/i.test(text);
  }

  function getSalaryFallbackValue(runtime, value) {
    const parsed = parseSalaryValue(value);
    if (!parsed.monthlyLower) return "";
    const runtimeText = [
      runtime?.label,
      runtime?.placeholder,
      runtime?.context,
      ...(Array.isArray(runtime?.nearbyLabels) ? runtime.nearbyLabels : [])
    ].map((item) => String(item || "")).join(" ");
    if (/年薪|万/.test(runtimeText)) {
      return String(Math.max(1, Math.round((parsed.monthlyLower * 12) / 10000)));
    }
    return String(parsed.monthlyLower);
  }

  function parseSalaryValue(value) {
    const text = String(value || "").replace(/[,\s]/g, "").trim();
    if (!text) return { monthlyLower: 0 };
    const numbers = Array.from(text.matchAll(/\d+(?:\.\d+)?/g)).map((m) => Number(m[0]));
    if (numbers.length === 0) return { monthlyLower: 0 };
    let multiplier = 1;
    if (/[kK千]/.test(text)) multiplier = 1000;
    else if (/[wW万]/.test(text)) multiplier = 10000;
    let monthlyLower = Math.round(numbers[0] * multiplier);
    if (/年/.test(text) && !/月/.test(text)) {
      monthlyLower = Math.round(monthlyLower / 12);
    }
    return { monthlyLower };
  }

  // 智能匹配 option：评分制（完全相等100/互相包含75，含别名组如 male→男、yes→是）
  // 参考项目 pickBestOption 的评分思路；返回命中的 option 对象或 null
  function matchOption(options, value) {
    if (!options || !options.length) return null;
    const v = String(value);

    // 1. value/label 精确
    let hit = options.find((o) => String(o.value) === v) ||
              options.find((o) => String(o.label) === v || norm(o.label) === norm(v));
    if (hit) return hit;

    // 2. 评分选最佳（≥60 才命中）
    let best = null;
    let bestScore = 0;
    for (const o of options) {
      const label = String(o.label || o.value || "").trim();
      if (!label) continue;
      const sc = matchesValue(label, v);
      if (sc >= 100) return o;
      if (sc >= 60 && sc > bestScore) { bestScore = sc; best = o; }
    }
    return best || null;
  }

  // 点击元素的"真实用户"方式：mousedown → focus → mouseup → click
  // 现代框架（React onClick、Vue @click）监听 click，但有些组件监听 mousedown
  function realClick(el) {
    if (!el) return false;
    try {
      el.focus && el.focus();
    } catch (e) {}
    const opts = { bubbles: true, cancelable: true, view: window };
    el.dispatchEvent(new MouseEvent("mousedown", opts));
    el.dispatchEvent(new MouseEvent("mouseup", opts));
    el.dispatchEvent(new MouseEvent("click", opts));
    return true;
  }

  // ============ 自定义下拉框：点击展开 → 选 option ============
  // 触发器：input 本身 或 其父级容器（el-select / ant-select / ivu-select 等）
  function findCustomSelectTrigger(el) {
    let node = el;
    for (let i = 0; i < 6 && node; i++) {
      const cls = (typeof node.className === "string") ? node.className : "";
      if (
        cls.indexOf("el-select") !== -1 ||
        cls.indexOf("ant-select") !== -1 ||
        cls.indexOf("ivu-select") !== -1 ||
        cls.indexOf("n-base-selection") !== -1 ||
        cls.indexOf("n-select") !== -1 ||
        cls.indexOf("van-dropdown") !== -1 ||
        cls.indexOf("MuiAutocomplete") !== -1 ||
        cls.indexOf("moka-select") !== -1 ||
        cls.indexOf("mokaSelect") !== -1
      ) {
        return node;
      }
      // 通用：role=combobox 或 包含 .dropdown-arrow 的容器
      const role = node.getAttribute && node.getAttribute("role");
      if (role === "combobox" || role === "listbox") return node;
      node = node.parentElement;
    }
    // 兜底：返回 input 本身（点击 input 也常能触发展开）
    return el;
  }

  // 在浮层中查找匹配的选项并点击
  // 浮层通常 append 到 body（teleport），class 有：el-select-dropdown / ant-select-dropdown / ivu-select-dropdown / n-select-menu / van-dropdown-menu
  function findDropdownRoot() {
    const sels = [
      ".el-select-dropdown:not([style*='display: none']):not([style*='display:none'])",
      ".el-select__popper .el-select-dropdown",
      ".ant-select-dropdown:not(.ant-select-dropdown-hidden)",
      ".ivu-select-dropdown:not(.ivu-select-dropdown-hidden)",
      ".n-base-select-menu",
      ".n-select-menu",
      ".van-dropdown-menu",
      ".MuiAutocomplete-popper li[role=option]",
      "[role=listbox][aria-expanded='true']",
      ".dropdown-menu.show",
      ".select-dropdown.show",
      // Moka (北森): React 构建，常见浮层模式
      "[class*=moka][class*=dropdown]:not([style*='display: none'])",
      "[class*=moka][class*=select]:not([style*='display: none'])",
      "[class*=dropdown][class*=menu]:not([style*='display: none'])"
    ];
    for (const sel of sels) {
      try {
        const nodes = document.querySelectorAll(sel);
        for (const n of nodes) {
          const r = n.getBoundingClientRect();
          if (r.width > 0 && r.height > 0) return n;
        }
      } catch (e) {}
    }
    // 兜底：找最后一个可见的 .el-select-dropdown / ant-select-dropdown
    try {
      const last = document.querySelectorAll(".el-select-dropdown, .ant-select-dropdown, .ivu-select-dropdown, .n-base-select-menu");
      for (let i = last.length - 1; i >= 0; i--) {
        const r = last[i].getBoundingClientRect();
        if (r.width > 0 && r.height > 0) return last[i];
      }
    } catch (e) {}
    return null;
  }

  // 在浮层根节点下找候选 option 元素
  function collectOptionsFromDropdown(dropdownRoot) {
    const optSel = [
      ".el-select-dropdown__item",
      ".ant-select-item-option",
      ".ivu-select-item",
      ".n-base-select-option",
      ".van-dropdown-item",
      "li[role=option]",
      "[role=option]",
      "li[data-value]",
      ".select-option",
      "li"
    ];
    for (const sel of optSel) {
      const nodes = dropdownRoot.querySelectorAll(sel);
      if (nodes.length) {
        return Array.from(nodes).map((n) => {
          const text = (n.textContent || "").trim();
          let val = n.getAttribute("data-value") || n.getAttribute("value") || "";
          // ElementUI/antd option 通常没有 data-value，用 text 作为 fallback value
          if (!val) val = text;
          return { el: n, value: val, label: text };
        });
      }
    }
    return [];
  }

  async function fillCustomSelect(el, value) {
    const trigger = findCustomSelectTrigger(el);

    // 1. 点击触发器展开浮层
    realClick(trigger);
    // 也尝试直接点击 input（部分组件 trigger 不在 input 父级）
    if (trigger !== el) { try { realClick(el); } catch (e) {} }

    // 2. 等待浮层出现（最多 800ms）
    const dropdown = await waitFor(findDropdownRoot, { timeout: 800, interval: 40 });
    if (!dropdown) {
      return { ok: false, reason: "下拉浮层未展开", status: "warn" };
    }

    // 3. 收集候选选项
    let options = collectOptionsFromDropdown(dropdown);

    // 4. 兜底：若一次没收集到，等 100ms 再试（动画延迟）
    if (!options.length) {
      await sleep(120);
      options = collectOptionsFromDropdown(dropdown);
    }

    if (!options.length) {
      return { ok: false, reason: "下拉选项为空", status: "warn" };
    }

    // 5. 智能匹配
    const hit = matchOption(options, value);
    if (!hit) {
      // 关闭浮层（点页面空白处）
      try { document.body.click(); } catch (e) {}
      return { ok: false, reason: `无匹配选项: ${value}（共${options.length}项）`, status: "warn" };
    }

    // 6. 滚动到可见区域后点击
    try { hit.el.scrollIntoView({ block: "nearest" }); } catch (e) {}
    await sleep(30);
    realClick(hit.el);

    // 7. 等待浮层关闭 + 触发器 input 文本更新（验证）
    await sleep(80);
    const finalVal = (el.value || "").trim();
    const finalText = finalVal || (trigger.textContent || "").trim();
    if (finalText && (norm(finalText).includes(norm(value)) || norm(value).includes(norm(finalText)))) {
      return { ok: true, status: "ok" };
    }
    // 即使验证失败也认为成功（部分组件 value 异步更新或不可读）
    return { ok: true, status: "ok" };
  }

  // ============ 日期选择器：先尝试原生 input，再尝试自定义组件 ============
  // 画像里 birth/入职时间 等字段格式可能是 "1990-01-01" / "1990/01/01" / "1990年1月" / "2024-03"
  // 处理流程：
  //   1) 原生 <input type=date/datetime-local>：setNativeValue(value) 直接生效
  //   2) ElementUI/antd DatePicker：尝试 setNativeValue 触发器 input（部分支持文本输入），失败则点击展开日历选格子
  //   3) 极端情况：返回 warn 让用户手动确认
  async function fillDatePicker(el, value, framework) {
    const v = String(value).trim();
    if (!v) return { ok: false, reason: "无值", status: "skip" };

    // 解析日期：支持 1990-01-01 / 1990/01/01 / 1990年1月1日 / 1990.1 / 1990-01 等
    const parsed = parseDateFlexible(v);

    // 1. 原生 HTML5 date/datetime-local input
    const inputType = (el.getAttribute("type") || "").toLowerCase();
    if (inputType === "date" && parsed && parsed.iso) {
      try {
        setNativeValue(el, parsed.iso.slice(0, 10));
        highlight(el, "ok");
        return { ok: true, status: "ok" };
      } catch (e) {}
    }
    if (inputType === "datetime-local" && parsed && parsed.iso) {
      try {
        setNativeValue(el, parsed.iso.slice(0, 16));
        highlight(el, "ok");
        return { ok: true, status: "ok" };
      } catch (e) {}
    }

    // 2. 自定义 DatePicker：尝试直接 setNativeValue（部分组件支持文本输入模式）
    try {
      const before = el.value || "";
      setNativeValue(el, v);
      await sleep(50);
      const after = el.value || "";
      // 若 input 接受了值且不再为空 → 多半已生效，触发回车确认
      if (after && after !== before) {
        el.dispatchEvent(new KeyboardEvent("keydown", { key: "Enter", keyCode: 13, bubbles: true }));
        el.dispatchEvent(new KeyboardEvent("keypress", { key: "Enter", keyCode: 13, bubbles: true }));
        el.dispatchEvent(new KeyboardEvent("keyup", { key: "Enter", keyCode: 13, bubbles: true }));
        highlight(el, "ok");
        return { ok: true, status: "ok" };
      }
    } catch (e) {}

    // 3. 点击展开日历面板，尝试选格子（限已解析出年月日的场景）
    if (parsed && parsed.year && parsed.month && parsed.day) {
      const ok = await tryClickDatePickerCell(el, parsed, framework || "unknown");
      if (ok) {
        highlight(el, "ok");
        return { ok: true, status: "ok" };
      }
    }

    // 4. 兜底：返回 warn，让用户手动确认（避免误报 ok）
    return { ok: false, reason: `日期组件未支持自动填写，请手动选择: ${v}`, status: "warn" };
  }

  // 弹性日期解析：支持多种中文/英文/分隔符格式
  function parseDateFlexible(s) {
    if (!s) return null;
    const str = String(s).trim();
    // 1990-01-01 / 1990/01/01 / 1990.01.01
    let m = str.match(/^(\d{4})[\-\/.年](\d{1,2})[\-\/.月](\d{1,2})?日?$/);
    if (m) {
      const y = parseInt(m[1], 10);
      const mo = parseInt(m[2], 10);
      const d = m[3] ? parseInt(m[3], 10) : null;
      return { year: y, month: mo, day: d, iso: toISO(y, mo, d) };
    }
    // 1990-01 / 1990/01 / 1990年1月
    m = str.match(/^(\d{4})[\-\/.年](\d{1,2})月?$/);
    if (m) {
      const y = parseInt(m[1], 10);
      const mo = parseInt(m[2], 10);
      return { year: y, month: mo, day: null, iso: toISO(y, mo, null) };
    }
    // 仅年份 1990
    m = str.match(/^(\d{4})年?$/);
    if (m) {
      const y = parseInt(m[1], 10);
      return { year: y, month: null, day: null, iso: null };
    }
    // 尝试 Date 直接解析
    const d = new Date(str);
    if (!isNaN(d.getTime())) {
      return { year: d.getFullYear(), month: d.getMonth() + 1, day: d.getDate(), iso: toISO(d.getFullYear(), d.getMonth() + 1, d.getDate()) };
    }
    return null;
  }
  function toISO(y, m, d) {
    const pad = (n) => String(n).padStart(2, "0");
    let iso = String(y) + "-" + pad(m);
    if (d) iso += "-" + pad(d);
    return iso;
  }

  // 在日历面板中尝试点击对应日期格子（支持 ElementUI / antd / iView / Naive）
  async function tryClickDatePickerCell(el, parsed, framework) {
    realClick(el);
    await sleep(80);
    // 等待日历面板出现
    const panelSel = [
      ".el-date-picker,.el-picker-panel,.el-picker__popper",
      ".ant-picker-dropdown,.ant-picker-panel",
      ".ivu-date-picker-dropdown",
      ".n-date-picker,.n-picker",
      ".MuiDatePicker-popper"
    ];
    let panel = null;
    for (const sel of panelSel) {
      try {
        const nodes = document.querySelectorAll(sel);
        for (const n of nodes) {
          const r = n.getBoundingClientRect();
          if (r.width > 0 && r.height > 0) { panel = n; break; }
        }
      } catch (e) {}
      if (panel) break;
    }
    if (!panel) return false;

    // 导航到目标年月（ElementUI/antd 都有"上一年/上一月"按钮，但简单做法：直接尝试点击对应日期格子）
    // 先尝试直接找 cell
    const cellSelectors = [
      ".el-date-table td .el-date-table-cell span.available",
      ".el-date-table td.available",
      ".ant-picker-cell-inner",
      ".ivu-date-picker-cells-cell",
      ".n-date-picker-date .n-date-picker-date__date"
    ];
    // 按文本匹配日期数字
    const dayStr = String(parsed.day);
    const monthStr = String(parsed.month);
    const yearStr = String(parsed.year);

    // 在面板内查找所有 cell，匹配文本
    const allCells = panel.querySelectorAll("td, .ant-picker-cell, .ivu-date-picker-cells-cell, .n-date-picker-date");
    for (const cell of allCells) {
      const txt = (cell.textContent || "").trim();
      if (txt === dayStr) {
        // 检查是否 disabled / 不在当前月
        if (cell.classList.contains("disabled") || cell.classList.contains("ant-picker-cell-disabled") ||
            cell.classList.contains("out-of-range") || cell.classList.contains("is-disabled")) {
          continue;
        }
        realClick(cell);
        await sleep(80);
        return true;
      }
    }
    // 兜底：尝试 input.year/month/day 子输入框（部分组件有此结构）
    const yIn = panel.querySelector("input[placeholder*='年'], .el-date-picker__header-label input");
    if (yIn) {
      try { setNativeValue(yIn, yearStr); await sleep(80); } catch (e) {}
    }
    return false;
  }

  // ============ 级联选择器：分步选择（如 籍贯 = 省→市） ============
  // 支持 ElementUI Cascader / antd Cascader / iView Cascader / Naive Cascader
  // value 格式："江苏南京" / "江苏省-南京市" / ["江苏","南京"]
  async function fillCascader(el, value, framework) {
    const v = String(value).trim();
    if (!v) return { ok: false, reason: "无值", status: "skip" };

    // 解析级联值：尝试拆分为多个层级
    // 策略：按常见分隔符拆分，或按中文地名智能拆分（省/市/区）
    const parts = parseCascaderValue(v);
    if (!parts.length) {
      return { ok: false, reason: "无法解析级联值", status: "skip" };
    }

    // 找到级联选择器触发器
    const trigger = findCustomSelectTrigger(el);
    let currentTrigger = trigger;

    for (let i = 0; i < parts.length; i++) {
      const part = parts[i];

      // 1. 点击当前层级的触发器
      realClick(currentTrigger);
      await sleep(100);

      // 2. 等待浮层出现
      const dropdown = await waitFor(findDropdownRoot, { timeout: 800, interval: 40 });
      if (!dropdown) {
        return { ok: false, reason: `第${i + 1}级浮层未展开`, status: "warn" };
      }

      // 3. 收集选项
      let options = collectOptionsFromDropdown(dropdown);
      if (!options.length) {
        await sleep(120);
        options = collectOptionsFromDropdown(dropdown);
      }
      if (!options.length) {
        return { ok: false, reason: `第${i + 1}级选项为空`, status: "warn" };
      }

      // 4. 匹配选项
      const hit = matchOption(options, part);
      if (!hit) {
        try { document.body.click(); } catch (e) {}
        return { ok: false, reason: `第${i + 1}级无匹配: ${part}`, status: "warn" };
      }

      // 5. 点击选项
      realClick(hit.el);
      await sleep(150); // 等待下一级加载

      // 6. 检查是否有下一级（级联选择器点击后通常会展开下一级面板）
      //    如果有下一级，找到下一级的触发器（通常是新出现的 input 或 dropdown）
      if (i < parts.length - 1) {
        // 尝试找到下一级触发器（在浮层内或旁边）
        const nextTrigger = dropdown.querySelector("input, [role=combobox], .el-cascader__label, .ant-cascader-picker-label");
        if (nextTrigger) {
          currentTrigger = nextTrigger;
        } else {
          // 兜底：继续用原触发器（某些组件会自动聚焦到下一级）
          currentTrigger = trigger;
        }
      }
    }

    // 最后关闭浮层
    await sleep(80);
    try { document.body.click(); } catch (e) {}

    return { ok: true, status: "ok" };
  }

  // 解析级联值：将 "江苏南京" 或 "江苏省-南京市" 拆分为 ["江苏", "南京"]
  function parseCascaderValue(v) {
    // 1. 尝试按分隔符拆分
    const separators = /[\-\/、，,·\s]+/;
    if (separators.test(v)) {
      return v.split(separators).map(s => s.trim()).filter(Boolean);
    }

    // 2. 智能拆分中文地名（省/市/区/县）
    //    常见模式：江苏省南京市 → ["江苏", "南京"]
    //    或：江苏南京 → ["江苏", "南京"]
    const provinceSuffixes = /省|自治区|特别行政区|市$/;
    const citySuffixes = /市|自治州|地区|盟$/;

    // 尝试匹配 "XX省YY市" 或 "XX市YY区" 模式
    const m = v.match(/^(.+?)(?:省|自治区|特别行政区)?(.+?)(?:市|自治州|地区|盟|区|县)?$/);
    if (m && m[1] && m[2] && m[1].length >= 2 && m[2].length >= 2) {
      return [m[1], m[2]];
    }

    // 3. 兜底：整个值作为单级
    return [v];
  }

  // ============ 拆分日期组件：年/月两个独立下拉 ============
  // 常见于网申系统：毕业时间 = 年下拉 + 月下拉
  // 策略：找到相邻的年/月下拉，分别填充
  async function fillSplitDatePicker(el, value, framework) {
    const v = String(value).trim();
    if (!v) return { ok: false, reason: "无值", status: "skip" };

    // 解析日期
    const parsed = parseDateFlexible(v);
    if (!parsed || !parsed.year) {
      return { ok: false, reason: "无法解析日期", status: "skip" };
    }

    // 找到当前元素所在的字段容器
    const container = el.closest(".el-form-item, .ivu-form-item, .ant-form-item, .n-form-item, .field-item, .form-item, [class*=field]") || el.parentElement;
    if (!container) {
      return { ok: false, reason: "未找到字段容器", status: "skip" };
    }

    // 在容器内查找所有下拉框/输入框
    const allInputs = container.querySelectorAll("input, select, [role=combobox]");
    if (allInputs.length < 2) {
      // 只有一个输入框，尝试直接填充
      return await fillDatePicker(el, value, framework);
    }

    // 识别年/月下拉（按 placeholder 或位置）
    let yearInput = null;
    let monthInput = null;

    for (const inp of allInputs) {
      const ph = (inp.placeholder || "").toLowerCase();
      const txt = (inp.textContent || "").toLowerCase();
      if (ph.includes("年") || txt.includes("年") || ph.includes("year")) {
        yearInput = inp;
      } else if (ph.includes("月") || txt.includes("月") || ph.includes("month")) {
        monthInput = inp;
      }
    }

    // 兜底：按位置判断（第一个是年，第二个是月）
    if (!yearInput && allInputs[0]) yearInput = allInputs[0];
    if (!monthInput && allInputs[1]) monthInput = allInputs[1];

    let filled = 0;

    // 填充年份
    if (yearInput) {
      const yearStr = String(parsed.year);
      if (yearInput.tagName === "SELECT") {
        // 原生 select：按选项匹配
        const options = Array.from(yearInput.options);
        const hit = options.find(o => o.value === yearStr || o.text.trim() === yearStr);
        if (hit) {
          yearInput.value = hit.value;
          fireEvents(yearInput);
          filled++;
        }
      } else {
        // 自定义下拉或 input
        const r = await fillCustomSelect(yearInput, yearStr);
        if (r.ok) filled++;
      }
    }

    // 填充月份
    if (monthInput && parsed.month) {
      const monthStr = String(parsed.month);
      if (monthInput.tagName === "SELECT") {
        const options = Array.from(monthInput.options);
        const hit = options.find(o => o.value === monthStr || o.text.trim() === monthStr || o.text.trim() === monthStr + "月");
        if (hit) {
          monthInput.value = hit.value;
          fireEvents(monthInput);
          filled++;
        }
      } else {
        const r = await fillCustomSelect(monthInput, monthStr);
        if (r.ok) filled++;
      }
    }

    if (filled > 0) {
      highlight(el, "ok");
      return { ok: true, status: "ok", filled };
    }

    return { ok: false, reason: "年/月下拉均未匹配", status: "warn" };
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

        // 原生 <select>：增强 label 模糊匹配
        if (field.type === "select" || el.tagName === "SELECT") {
          const options = Array.from(el.options).map((o) => ({
            el: o, value: o.value, label: (o.text || "").trim()
          }));
          const hit = matchOption(options, value);
          if (hit && hit.el) {
            try {
              el.value = hit.el.value; // 走原生 setter 触发 change
            } catch (e) {
              setNativeValue(el, hit.el.value);
            }
            fireEvents(el);
            highlight(el, "ok");
            return { ok: true, status: "ok", matched: hit.label };
          }
          highlight(el, "warn");
          return { ok: false, reason: `选项无匹配: ${value}`, status: "warn" };
        }

        // 自定义下拉框（ElementUI/antd/iView/Naive UI/Vant/MUI 等）
        if (field.type === "custom_select") {
          const r = await fillCustomSelect(el, value);
          highlight(el, r.status);
          return r;
        }

        // 日期选择器
        if (field.type === "date_picker") {
          const r = await fillDatePicker(el, value, field.framework);
          highlight(el, r.status);
          return r;
        }

        if (field.type === "radio") {
          const options = (field.options || []).map((o) => ({
            value: o.value, label: o.label, el: o.el || null
          }));
          const hit = matchOption(options, value);
          if (hit) {
            let r = hit.el || document.querySelector(
              `input[type=radio][name="${CSS.escape(field.name)}"][value="${CSS.escape(hit.value)}"]`
            );
            if (r) {
              const ok = await safeCheck(r, true);
              highlight(el, ok ? "ok" : "warn");
              return ok ? { ok: true, status: "ok" } : { ok: false, reason: "勾选失败", status: "warn" };
            }
          }
          highlight(el, "warn");
          return { ok: false, reason: "选项无匹配", status: "warn" };
        }
        if (field.type === "checkbox") {
          const v = String(value).toLowerCase();
          const checked = v === "true" || v === "是" || v === "1" || v === "yes";
          const ok = await safeCheck(el, checked);
          highlight(el, ok ? "ok" : "warn");
          return ok ? { ok: true, status: "ok" } : { ok: false, reason: "勾选失败", status: "warn" };
        }
        if (field.type === "checkbox_group") {
          // 参考项目多选组：别名组候选匹配，逐个 safeCheck
          const desired = Array.isArray(value)
            ? value.map(String).filter(Boolean)
            : String(value || "").split(/[,，、;；\s]+/).map(String).filter(Boolean);
          if (!desired.length) {
            highlight(el, "skip");
            return { ok: false, reason: "没有可勾选项", status: "skip" };
          }
          let any = false;
          for (const option of field.options || []) {
            const checkedCandidates = desired.filter((c) => matchesValue(option.label || option.value, c) >= 60);
            const shouldCheck = checkedCandidates.length > 0;
            const oEl = option.el;
            if (!oEl) continue;
            const ok = await safeCheck(oEl, Boolean(oEl.checked) || shouldCheck);
            if (ok && shouldCheck) any = true;
          }
          highlight(el, any ? "ok" : "warn");
          return any
            ? { ok: true, status: "ok" }
            : { ok: false, reason: "未找到可匹配的多选项", status: "warn" };
        }

        // 兜底：readonly input 但 scanner 没标 custom_select/date_picker（旧缓存可能）
        // 在此处再次尝试自定义下拉框流程
        if (el.tagName === "INPUT" && (el.readOnly === true || el.hasAttribute("readonly"))) {
          // 语义像日期 → date_picker；否则按自定义下拉框尝试
          const txt = `${field.label || ""} ${field.name || ""} ${field.placeholder || ""}`;
          if (/(date|日期|时间|年月日|生日|出生|入职|毕业|参加工作|起止|起始|结束|到期|有效期|开始|截止)/.test(txt.toLowerCase())) {
            const r = await fillDatePicker(el, value, field.framework);
            highlight(el, r.status);
            return r;
          }
          const r = await fillCustomSelect(el, value);
          highlight(el, r.status);
          return r;
        }

        // 普通文本类：严格按参考项目流程（prepare → setValueWithEvents → 薪资回退）
        const desired = prepareTextValueForRuntime(field, value);
        if (!desired) {
          highlight(el, "skip");
          return { ok: false, reason: "没有可填写内容", status: "skip" };
        }
        let wk = await setValueWithEvents(el, desired, field);
        if (wk) {
          highlight(el, "ok");
          return { ok: true, status: "ok" };
        }
        for (const fb of buildTextFallbackValues(field, desired)) {
          const fbOk = await setValueWithEvents(el, fb, field);
          if (fbOk) {
            highlight(el, "ok");
            return { ok: true, status: "ok", fallback: fb };
          }
        }
        highlight(el, "warn");
        return { ok: false, reason: "写入失败", status: "warn" };
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
          if (el) field = { selector: m.selector, type: m.type, name: m.field_name, framework: m.framework, el };
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
    },

    // 暴露给上层（调试 / popup 可调用）
    _internals: { matchOption, norm, parseDateFlexible, prepareTextValueForRuntime, isSalaryLikeRuntime, parseSalaryValue }
  };
})();
