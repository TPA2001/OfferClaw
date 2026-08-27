// OfferClaw 扩展 - 确定性填写运行时
// 在真实页面 DOM 上执行填写，兼容 React/Vue 受控组件（nativeInputValueSetter）
// 增强：自定义下拉(custom_select)/日期选择器(date_picker)/单选组点击 等复杂控件交互
(function () {
  if (globalThis.OC && globalThis.OC.__loaded_filler) return;
  const OC = globalThis.OC || (globalThis.OC = {});
  OC.__loaded_filler = true;

  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

  // 以“用户真实点击”方式触发，兼顾 Vue/React 合成的 click
  // 关键：传入真实坐标 clientX/clientY（弹层组件会用 elementFromPoint 反算命中项），
  // 并同时派发 pointer/mouse 事件序列，覆盖不同框架的监听方式。
  function clickLikeUser(el) {
    if (!el) return;
    try {
      el.scrollIntoView({ block: "center", behavior: "instant" });
      const rect = el.getBoundingClientRect();
      const x = rect.left + rect.width / 2;
      const y = rect.top + rect.height / 2;
      const base = {
        bubbles: true, cancelable: true, composed: true,
        view: window, clientX: x, clientY: y, screenX: x, screenY: y,
        button: 0, buttons: 1, detail: 1
      };
      try { el.focus?.(); } catch (e) {}
      const seq = [
        ["pointerdown", "PointerEvent"],
        ["mousedown", "MouseEvent"],
        ["pointerup", "PointerEvent"],
        ["mouseup", "MouseEvent"],
        ["click", "MouseEvent"]
      ];
      for (const [type, name] of seq) {
        try {
          const Ctor = globalThis[name] || MouseEvent;
          el.dispatchEvent(new Ctor(type, base));
        } catch (e) {}
      }
    } catch (e) {}
  }

  // 兼容 React/Vue 受控组件写入值
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
  }

  function fireEvents(el) {
    el.dispatchEvent(new Event("input", { bubbles: true }));
    el.dispatchEvent(new Event("change", { bubbles: true }));
    el.dispatchEvent(new Event("blur", { bubbles: true }));
  }

  function highlight(el, status) {
    el.classList.remove("oc-fill-ok", "oc-fill-warn", "oc-fill-skip");
    if (status === "ok") el.classList.add("oc-fill-ok");
    else if (status === "warn") el.classList.add("oc-fill-warn");
    else if (status === "skip") el.classList.add("oc-fill-skip");
  }

  // 已知的可见下拉选项选择器（框架通用，含基础/原生子级）
  const OPTION_SELECTOR = [
    "[role=option]", "[role=listbox] [role=option]",
    ".el-select-dropdown__item", ".el-cascader-node",
    ".ant-select-item-option", ".ant-cascader-menu-item",
    ".ivu-select-item", ".n-base-option", ".n-base-select-option",
    ".van-dropdown-item__option", ".select2-results__option",
    // 通用大小写不敏感模式（覆盖自研组件 sd-/iks/xxx-Select-option 等）
    "[class*=select-option i]", "[class*=option-item i]", "[class*=menu-item i]",
    "[class*=dropdown-item i]", "[class*=dropdown-list i]", "[class*=option i]",
    // sd-Select-common-item（无 role=option 的自研选项项）
    "[class*=common-item i]", "[class*=select-item i]"
  ].join(", ");

  // 打开下拉：优先点输入框（Moka/sd 点输入框本身即弹菜单），外壳/箭头作为兜底
  function focusAndOpen(el) {
    clickLikeUser(el);
  }

  function caretToggleOf(el) {
    let node = el;
    for (let i = 0; i < 3 && node; i++) {
      const sib = node.querySelector
        ? node.querySelector("[class*=caret], [class*=iconcaret], [class*=addon] [class*=icon], [class*=suffix], [class*=arrow]")
        : null;
      if (sib) return sib;
      node = node.parentElement;
    }
    return null;
  }

  // 关闭下拉，避免遮挡后续填写
  function closeDropdown() {
    try {
      document.body.dispatchEvent(new MouseEvent("mousedown", { bubbles: true }));
      document.body.dispatchEvent(new MouseEvent("keydown", { key: "Escape", code: "Escape", bubbles: true }));
    } catch (e) {}
  }

  // 回车按键（combobox 搜索后确认）
  function pressEnter(el) {
    try {
      ["keydown", "keypress", "keyup"].forEach((type) => {
        el.dispatchEvent(new KeyboardEvent(type, { key: "Enter", code: "Enter", keyCode: 13, bubbles: true }));
      });
    } catch (e) {}
  }

  // 读取控件当前展示文本（部分框架选中值显示在壳内而非 input.value）
  function visibleTextOfShell(el) {
    const node = el.closest(
      ".el-select, .el-select__tags, .ant-select, .ant-select-selection-wrap, .ivu-select, " +
      ".n-base-select, .n-base-selection, .MuiOutlinedInput-root, .vue-select, .multiselect, " +
      ".van-dropdown-item, [class*=cascader]"
    ) || el.parentElement;
    if (!node) return el.value || "";
    const hit = node.querySelector(
      ".el-select__selected-item, .el-select__tags-text, .el-select__placeholder, .el-select__input span, " +
      ".ant-select-selection-item, .ant-select-selection-placeholder, " +
      ".ivu-select-selected-value, .ivu-select-placeholder, " +
      ".n-base-selection__label, .n-base-selection-placeholder, " +
      ".van-dropdown-item__title, " +
      ".sd-Input-display-value, [class*=display-value i], [class*=selected-value i], [class*=input-display-value i]"
    );
    if (hit && hit.textContent) return hit.textContent.trim();
    return el.value || "";
  }

  // 收集当前可见选项（优先限定在已打开的面板/弹层内，避免误中别处同名项）
  function queryVisibleOptions() {
    let roots = Array.from(document.querySelectorAll(
      ".el-select__popper, .el-select-dropdown, .ant-select-dropdown, .select2-dropdown, " +
      ".ivu-select-dropdown, .van-dropdown-menu__item, .moka-dropdown, .moka-dropdown-menu, " +
      "[class*=cascader-menu], [class*=el-cascader__dropdown], [class*=popper-container], " +
      ".n-base-selection, .n-base-select-menu, " +
      // 自研组件通用：弹出层(popper/tooltip/dropdown/menu)等可见面板
      "[class*=dropdown-panel i], [class*=tooltip-panel i], [class*=popup-container i], [class*=popper-panel i], " +
      "[class*=select-menu i], [class*=select-scrollable i], [class*=dropdown-dropdown i]"
    )).filter(isPanelVisible);
    if (!roots.length) roots = [document];
    const seen = new Set();
    const out = [];
    for (const root of roots) {
      for (const o of root.querySelectorAll(OPTION_SELECTOR)) {
        if (seen.has(o)) continue;
        seen.add(o);
        const disabled =
          (o.getAttribute && o.getAttribute("aria-disabled") === "true") || /disabled/.test(o.className || "");
        if (disabled) continue;
        if (!isPanelVisible(o)) continue;
        out.push(o);
      }
    }
    return out;
  }

  // 挑选最佳匹配：精确 > 前缀 > 包含；Element cascader 优先按 data-offset 前缀
  function pickOption(options, desired) {
    const d = norm(desired);
    let prefix = null;
    let incl = null;
    for (const o of options) {
      const t = norm(o.textContent);
      if (!t) continue;
      if (t === d) return o;
      if (!prefix && t.startsWith(d)) prefix = o;
      else if (!incl && t.includes(d)) incl = o;
    }
    for (const o of options) {
      const off = o.getAttribute && o.getAttribute("data-offset");
      if (off && norm(off).startsWith(d)) return o;
    }
    return prefix || incl || null;
  }

  // 尝试通过点击下拉框选择文本匹配的选项
  async function fillCustomSelect(runtime, value) {
    const el = runtime.el;
    if (!el) return { ok: false, reason: "无元素" };
    const desired = String(value || "").trim();
    if (!desired) return { ok: false, reason: "无值" };

    // 原生 select（扫描器偶尔漏分类）：按值/标签选
    if (el.tagName === "SELECT") {
      const t = Array.from(el.options).find(
        (o) => norm(o.value) === norm(desired) || norm(o.textContent) === norm(desired)
      );
      if (!t) return { ok: false, reason: "原生select无匹配项", status: "warn" };
      setNativeValue(el, t.value);
      fireEvents(el);
      highlight(el, "ok");
      return { ok: true, status: "ok" };
    }

    const editable = !el.readOnly && el.tagName !== "BUTTON";

    // 1) 打开下拉并轮询收集选项（输入框 → 箭头 → 外壳，逐次重查）
    let options = [];
    focusAndOpen(el);
    await sleep(240);
    options = queryVisibleOptions();
    if (!options.length) {
      const caret = caretToggleOf(el);
      if (caret && caret !== el) {
        clickLikeUser(caret);
        await sleep(200);
        options = queryVisibleOptions();
      }
    }
    if (!options.length && editable) {
      setNativeValue(el, desired);
      fireEvents(el);
      await sleep(260);
      options = queryVisibleOptions();
    }
    if (!options.length) {
      const shell = el.closest(
        ".el-select, .ant-select, .ivu-select, .n-base-select, .MuiAutocomplete-root, " +
        ".vue-select, .multiselect, .van-dropdown-item, .cascader, [class*=cascader], .select, " +
        "[class*=dropdown-container i], [class*=select-container i]"
      );
      if (shell && shell !== el) {
        clickLikeUser(shell);
        await sleep(220);
        options = queryVisibleOptions();
      }
    }

    // 2) 匹配并点击选项
    const matched = pickOption(options, desired);
    if (matched) {
      clickLikeUser(matched);
      await sleep(180);
      const finalVal = String(el.value || "").trim();
      const shown = norm(visibleTextOfShell(el));
      const okEq =
        norm(finalVal) === norm(desired) ||
        (shown && (shown === norm(desired) || shown.startsWith(norm(desired))));
      // 已点选成功即为成功；个别框架 input.value 不更新属正常
      return { ok: true, status: okEq ? "ok" : "warn", reason: okEq ? undefined : "已点选选项，值未直接校验请确认" };
    }

    // 2.5 级联选择（省/市/区 如籍贯"山东济宁"）：先选前缀再选剩余部分
    const casc = await tryCascading(runtime, el, desired, editable);
    if (casc) return casc;

    // 4) combobox 允许自由输入的兜底：输入后回车
    if (editable) {
      setNativeValue(el, desired);
      fireEvents(el);
      await sleep(120);
      pressEnter(el);
      await sleep(160);
      const finalVal = String(el.value || "").trim();
      if (norm(finalVal) === norm(desired) || (finalVal && finalVal.length >= 2)) {
        closeDropdown();
        highlight(el, "ok");
        return { ok: true, status: "ok" };
      }
    }

    closeDropdown();
    highlight(el, "warn");
    return { ok: false, reason: "下拉未找到匹配选项", status: "warn" };
  }

  // 级联选择（省/市/区，如籍贯"山东济宁"）：先选"是 desired 最长前缀"的顶层项，再在次级面板选剩余部分
  async function tryCascading(runtime, el, desired, editable) {
    let options = queryVisibleOptions();
    const d = norm(desired);
    let seg = null, segLen = 0;
    for (const o of options) {
      const t = norm(o.textContent);
      // 顶层选项必须是 desired 的前缀（如 "山东" 之于 "山东济宁"）
      if (t && t.length > 1 && d.startsWith(t) && t.length > segLen) { seg = o; segLen = t.length; }
    }
    if (!seg) return null;
    clickLikeUser(seg);
    await sleep(200);
    const rest = d.slice(segLen);
    if (!rest) {
      closeDropdown();
      highlight(el, "ok");
      return { ok: true, status: "ok" };
    }
    // 次级面板：选剩余部分（市/区）
    let opts2 = queryVisibleOptions();
    let hit = null;
    for (const o of opts2) {
      const t = norm(o.textContent);
      if (t === rest || (t.startsWith(rest) && rest.length > 1) || rest.startsWith(t)) { hit = o; break; }
    }
    if (hit) {
      clickLikeUser(hit);
      await sleep(160);
      closeDropdown();
      highlight(el, "ok");
      return { ok: true, status: "ok" };
    }
    return null; // 次级别难度大，交回上层兜底
  }

  function norm(t) {
    return String(t || "").trim().toLowerCase().replace(/\s+/g, "");
  }

  // 普通文本框写入（readonly 时临时解除再恢复）
  function tryWriteText(el, value, runtime) {
    const wasReadonly = Boolean(el.readOnly) || el.hasAttribute("readonly");
    try {
      if (wasReadonly) {
        el.readOnly = false;
        el.removeAttribute("readonly");
      }
      setNativeValue(el, value);
      el.setAttribute("value", String(value));
      fireEvents(el);
      return true;
    } catch (e) {
      return false;
    } finally {
      if (wasReadonly) {
        el.readOnly = true;
        el.setAttribute("readonly", "");
      }
    }
  }

  // Moka/sd 年月列表式日期选择器：面板内以 "年月列表项" 呈现（sd-picker-date-year-item / sd-picker-date-month-item）
  // 先选年份，再选月份（dee选年月/日期）。返回 null 表示未命中此类型，交由通用面板逻辑处理。
  async function handleYearMonthList(el, desired, original) {
    const YM_SEL = "[class*=date-year-item i], [class*=picker-date-year i], [class*=year-item i], [class*=year-panel i]";
    const MO_SEL = "[class*=date-month-item i], [class*=picker-date-month i], [class*=month-item i], [class*=month-panel i]";

    // 目标年份：优先取 desired 里的 4 位年份，否则"年/年-月"形式
    const ym = String(desired || "").match(/(20\d{2}|19\d{2})(?:[^\d]{0,4}(\d{1,2}))?/);
    if (!ym) return null;
    let yearWanted = Number(ym[1]);
    const monthWanted = ym[2] != null ? Number(ym[2]) : null;
    // 若 desired 本身是完整年月（04 → year=2004，不能当月份），修正：1999-04 的 month=4
    if (/^\d{4}$/.test(desired)) yearWanted = Number(desired);

    // 确认面板已出现年月列表项
    let years = Array.from(document.querySelectorAll(YM_SEL)).filter(isPanelVisible);
    if (!years.length) return null; // 非 Moka 年月列表，交回通用逻辑

    // 选定年份（若当前列表不含目标年，点"上/下一年"翻页，防死循环）
    let guard = 0;
    while (guard++ < 20) {
      let items = Array.from(document.querySelectorAll(YM_SEL)).filter(isPanelVisible);
      const hit = items.find((it) => norm(it.textContent) === String(yearWanted));
      if (hit) { clickLikeUser(hit); await sleep(160); break; }
      // 找相邻翻页：标题/上"一年"按钮
      const nav = findYearNav(items, yearWanted);
      if (!nav) return null;
      clickLikeUser(nav);
      await sleep(120);
    }
    if (guard > 20) return null;

    // 若只要年（年龄场景），到此即可视为完成
    if (monthWanted == null && /^\d{4}$/.test(desired)) return { ok: true };

    // 选择月份
    await sleep(160);
    let months = Array.from(document.querySelectorAll(MO_SEL)).filter(isPanelVisible);
    if (!months.length) return { ok: true }; // 已选年份，后续月份由用户补
    const mo = monthWanted != null ? String(monthWanted) : "01";
    let mHit = months.find((it) => norm(it.textContent) === mo);
    if (!mHit) mHit = months.sort((a, b) => (isNaN(+a.textContent) ? 1 : 0) - (isNaN(+b.textContent) ? 1 : 0))[0];
    if (mHit) { clickLikeUser(mHit); await sleep(160); }
    return { ok: true };
  }

  // 在相邻年月翻页中定位可点的上一个/下一个年份项
  function findYearNav(yearItems, yearWanted) {
    const texts = yearItems.map((it) => parseInt(norm(it.textContent), 10)).filter((n) => !isNaN(n));
    if (!texts.length) return yearItems[0] || null;
    const lo = Math.min(...texts);
    const hi = Math.max(...texts);
    const wantPrev = yearWanted < lo;
    // 优先点面板内可见的翻页按钮；否则点当前列表最小/最大年份项本身
    const btnSel = wantPrev
      ? "[class*=prev], [class*=left] button, [class*=previous] [class*=year], [class*=year] [class*=prev], [aria-label*=前]"
      : "[class*=next], [class*=right] button, [aria-label*=后]";
    const btn = Array.from(document.querySelectorAll(btnSel)).filter(isPanelVisible)[0];
    if (btn) return btn;
    return yearItems.find((it) => norm(it.textContent) === String(wantPrev ? lo : hi)) || null;
  }

  // 尝试通过日期面板选择
  async function fillDatePicker(runtime, value) {
    const el = runtime.el;
    if (!el) return { ok: false, reason: "无元素" };
    const original = String(value || "").trim();
    if (!original) return { ok: false, reason: "无值" };

    const now = new Date();
    // desired = 用于匹配面板的日期值；纯数字按年龄换算出生年份（如 26 → 1999）
    const isAgeValue = /^\d{1,3}$/.test(original);
    let desired = original;
    if (isAgeValue) {
      const age = parseInt(original, 10);
      if (age >= 1 && age <= 120) desired = String(now.getFullYear() - age);
    }

    // 1. 直接写入（readonly 临时解除）。仅对"完整日期串"且非年龄换算时判成功，
    //    年龄换算出的"纯年份"必须走面板选择，避免收到虚假成功。
    const direct = tryWriteText(el, desired, runtime);
    if (!isAgeValue && direct && desired && /^\d{4}[-/]/.test(desired) && el.value && norm(el.value) === norm(desired)) {
      return { ok: true, status: "ok" };
    }

    clickLikeUser(el);
    await sleep(180);

    // Moka/sd 年月列表式选择器（先选年再选月），命中即处理
    const moka = await handleYearMonthList(el, desired, original);
    if (moka) {
      closeDropdown();
      highlight(el, "ok");
      return { ok: true, status: "ok" };
    }

    // 绑定控件打开的面板容器
    const panel = document.querySelector(".el-picker-panel, .ant-picker-dropdown, .ivu-picker-panel, .n-date-picker, [class*=picker-panel]");
    if (!panel || !isPanelVisible(panel)) {
      document.body.dispatchEvent(new MouseEvent("mousedown", { bubbles: true }));
      return { ok: false, reason: "未打开日期面板", status: "warn" };
    }

    // 面板内含 Y/M/D 输入框 → 分别写
    const ymdInputs = panel.querySelectorAll("input:not([type=hidden])");
    if (ymdInputs.length >= 3) {
      const m = desired.match(/^(\d{4})-(\d{1,2})-(\d{1,2})$/);
      if (m) {
        const [ , y, mo, d ] = m;
        const order = [y, mo, d];
        let ok = true;
        ymdInputs.forEach((inp, i) => {
          tryWriteText(inp, String(order[i] ?? ""), {});
        });
        // 触发确认
        clickLikeUser(panel.querySelector("button, .el-picker-panel__footer button, .confirmation, .btn-primary") || panel);
        await sleep(100);
        try {
          if (panel.classList) { /* keep */ }
        } catch (e) {}
        ok = Boolean(el.value && norm(el.value) === norm(desired));
        return ok ? { ok: true, status: "ok" } : { ok: false, reason: "年月日输入后未确认成功", status: "warn" };
      }
    }

    // 否则按日历格子点击
    const p = desired.match(/^(\d{4})-(\d{1,2})-(\d{1,2})$/);
    if (!p) return { ok: false, reason: "日期格式无法识别", status: "warn" };
    const [, yearWanted, monthWanted, dayWanted] = p.map((x, i) => (i === 0 ? x : Number(x)));

    // 定位面板标题和前后翻页按钮
    const header = panel.querySelector("[class*=header], [class*=title], .el-date-table th");
    const prevBtn = panel.querySelector("[class*=prev], [class*=left] button, .arrow-left, [aria-label*=前]");
    const nextBtn = panel.querySelector("[class*=next], [class*=right] button, .arrow-right, [aria-label*=后]");

    // 循环翻页直到面板标题匹配目标年月（防御死循环）
    let guard = 0;
    while (guard++ < 24) {
      const cur = (header && header.textContent) || "";
      const inMonitor = /(202\d|201\d)[^\d]*\d{1,2}/.test(cur) && monthOf(cur) !== null;
      if (inMonitor && headerMatches(panel, yearWanted, monthWanted)) break;
      // 若无法解析标题，直接尝试找目标格子
      const dayCell = findDayCell(panel, dayWanted, monthWanted, yearWanted);
      if (dayCell) {
        clickLikeUser(dayCell);
        await sleep(120);
        if (el.value && norm(el.value) === norm(desired)) return { ok: true, status: "ok" };
        break;
      }
      const btn = (monthWanted > monthOf(cur)) ? nextBtn : prevBtn;
      if (!btn) break;
      clickLikeUser(btn);
      await sleep(90);
    }

    // 点击目标日期格子
    const cell = findDayCell(panel, dayWanted, monthWanted, yearWanted);
    if (cell) {
      clickLikeUser(cell);
      await sleep(150);
      const ok = el.value && norm(el.value) === norm(desired);
      return ok ? { ok: true, status: "ok" } : { ok: false, reason: "日期已点选，但值未校验通过", status: "warn" };
    }

    document.body.dispatchEvent(new MouseEvent("mousedown", { bubbles: true }));
    return { ok: false, reason: "未在日历中找到目标日期", status: "warn" };
  }

  function isPanelVisible(panel) {
    const rect = panel.getBoundingClientRect();
    const style = window.getComputedStyle(panel);
    return rect.width > 0 && rect.height > 0 && style.visibility !== "hidden" && style.display !== "none";
  }

  function monthOf(headerText) {
    const m = String(headerText || "").match(/(\d{1,2})\s*月|month/i);
    return m ? Number(m[1]) : null;
  }
  function yearOf(headerText) {
    const m = String(headerText || "").match(/(20\d{2}|19\d{2})/);
    return m ? Number(m[0]) : null;
  }
  function headerMatches(panel, y, m) {
    const header = (panel.querySelector("[class*=header], [class*=title], .el-date-table th") || {}).textContent || "";
    const hy = yearOf(header);
    const hm = monthOf(header);
    if (hy === null || hm === null) return false;
    return hy === y && hm === m;
  }
  function findDayCell(panel, day, month, year) {
    const cells = panel.querySelectorAll("td, [class*=day-cell], [class*=available]");
    for (const cell of cells) {
      const t = norm(cell.textContent);
      // 跳过前后月溢出格
      if (/前|后|next|prev|disabled/.test(cell.className || "")) continue;
      if (t === String(day)) {
        const cls = cell.className || "";
        if (/prev-month|next-month|other-month/.test(cls)) continue;
        return cell;
      }
    }
    // 兜底：标题不匹配时暂按当前可视月份点日
    for (const cell of cells) {
      if (norm(cell.textContent) === String(day) && !/prev-month|next-month|other-month/.test(cell.className || "")) {
        return cell;
      }
    }
    return null;
  }

  // 单选组点击（兼容自定义样式 radio）
  async function fillRadioGroup(runtime, value) {
    const options = runtime.options || [];
    const desired = String(value || "").trim();
    const target = options.find((o) => norm(o.value) === norm(desired) || norm(o.label) === norm(desired));
    if (!target) {
      highlight(runtime.el, "warn");
      return { ok: false, reason: "选项无匹配", status: "warn" };
    }
    const radio = target.el || runtime.el;
    if (radio) {
      radio.checked = true;
      clickLikeUser(radio);
      fireEvents(radio);
      highlight(runtime.el, "ok");
      return { ok: true, status: "ok" };
    }
    highlight(runtime.el, "warn");
    return { ok: false, reason: "单选元素缺失", status: "warn" };
  }

  // 勾选组（checkbox 组 / 多选）——本版仅处理含 options 的多选
  async function fillCheckboxGroup(runtime, values) {
    const options = runtime.options || [];
    const desiredList = (Array.isArray(values) ? values : [values]).map((v) => norm(v));
    let any = false;
    for (const opt of options) {
      const should = desiredList.includes(norm(opt.value)) || desiredList.includes(norm(opt.label));
      if (opt.el) {
        if (opt.el.checked !== should) {
          opt.el.checked = should;
          clickLikeUser(opt.el);
          fireEvents(opt.el);
        }
        if (should) any = true;
      }
    }
    highlight(runtime.el, any ? "ok" : "warn");
    return { ok: any, status: any ? "ok" : "warn", reason: any ? undefined : "未找到可勾选项" };
  }

  OC.filler = {
    async fillOne(field, mapping) {
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

      // 组装运行时上下文（供复杂控件使用）
      const runtime = {
        el,
        type: field.type,
        label: field.label || "",
        placeholder: field.placeholder || "",
        readOnly: field.readOnly,
        inputType: field.inputType,
        options: field.options,
        nearbyLabels: field.nearbyLabels,
        section: field.section,
        value: String(value)
      };

      try {
        if (field.type === "contenteditable") {
          el.textContent = value;
          fireEvents(el);
          highlight(el, "ok");
          return { ok: true, status: "ok" };
        }
        if (field.type === "select") {
          const opts = field.options || [];
          const t = opts.find((o) => norm(o.value) === norm(value) || norm(o.label) === norm(value));
          if (t) {
            setNativeValue(el, t.value);
            fireEvents(el);
          } else {
            setNativeValue(el, value);
            fireEvents(el);
          }
          highlight(el, "ok");
          return { ok: true, status: "ok" };
        }
        if (field.type === "radio") {
          return await fillRadioGroup(runtime, value);
        }
        if (field.type === "checkbox") {
          const v = String(value).toLowerCase();
          el.checked = v === "true" || v === "是" || v === "1" || v === "yes";
          fireEvents(el);
          highlight(el, "ok");
          return { ok: true, status: "ok" };
        }
        if (field.type === "custom_select") {
          const r = await fillCustomSelect(runtime, value);
          highlight(el, r.ok ? "ok" : "warn");
          return r;
        }
        if (field.type === "date_picker") {
          const r = await fillDatePicker(runtime, value);
          highlight(el, r.ok ? "ok" : "warn");
          return r;
        }
        // 普通文本类
        if (tryWriteText(el, String(value), runtime)) {
          highlight(el, "ok");
          return { ok: true, status: "ok" };
        }
        highlight(el, "warn");
        return { ok: false, reason: "写入失败", status: "warn" };
      } catch (e) {
        highlight(el, "warn");
        return { ok: false, reason: String(e), status: "warn" };
      }
    },

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
        report.details.push({
          field_id: fid,
          field: m.field_name || (field && field.label) || fid,
          value: m.value != null ? String(m.value) : "",
          type: m.type || (field && field.type) || "",
          ok: r.ok, reason: r.reason, status: r.status
        });
      }
      return report;
    },

    clearHighlight() {
      document.querySelectorAll(".oc-fill-ok,.oc-fill-warn,.oc-fill-skip").forEach((el) => {
        el.classList.remove("oc-fill-ok", "oc-fill-warn", "oc-fill-skip");
      });
    }
  };
})();