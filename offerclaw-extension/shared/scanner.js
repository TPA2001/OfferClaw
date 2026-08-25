// OfferClaw 扩展 - 表单字段扫描器
// 在真实页面 DOM 上扫描 input/select/textarea/contenteditable，生成后端可匹配的字段结构
(function () {
  if (globalThis.OC && globalThis.OC.__loaded_scanner) return;
  const OC = globalThis.OC || (globalThis.OC = {});
  OC.__loaded_scanner = true;

  const FIELD_SELECTOR =
    "input:not([type=hidden]):not([type=submit]):not([type=button]):not([type=reset]):not([type=image]), select, textarea, [contenteditable=true], [role=combobox], [role=listbox], [class*=select]:not(select):not([class*=row]):not([class*=col]), [class=custom-select]";

  // 判断一个"字段容器"（含 role=combobox / 自定义下拉的 div）是否含真实可见的下拉交互层
  // 用于在扫描阶段把 div 模拟的 select/date 也纳入，交给 filler 的下拉流程处理。

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

  // ============ 字段 label 判分模型（借鉴 AI-Resume-Form-Filling-Assistant 的候选判分法） ============
  // 核心思想：不"找到第一个候选就返回"，而是收集所有候选文本，
  // 用一套启发式评分选"最像字段名"的那个，并过滤掉 +86/请选择/本科/日期等非字段名文本。
  function normLabel(t) {
    return String(t || "")
      .replace(/[\s\r\n]+/g, "")
      .replace(/^[*＊※·\s]+/, "")
      .replace(/[*＊※]$/, "")
      .replace(/[：:?？。.!！;；]+$/, "")
      .trim();
  }

  // 该文本是否"有意义"（是候选字段名，而非空/纯符号/纯数字/过短）
  function meaningfulLabel(t) {
    const s = normLabel(t);
    if (!s) return false;
    if (s.length <= 1) return false;                     // 单个字符（如"男"）过于模糊
    if (/^[+()\-.\s\d/\uFF0C\uFF0F]+$/.test(s)) return false; // 纯数字/符号（+86、手机号、日期）
    return true;
  }

  // 评估一个文本有多"像字段名"，分数越高越可信
  function scoreLabelCandidate(t) {
    const s = normLabel(t);
    if (!meaningfulLabel(s)) return Number.NEGATIVE_INFINITY;
    let score = 0;
    const len = s.length;

    // 长度加分：字段名多为 2-10 字
    if (len >= 2 && len <= 8) score += 15;
    else if (len <= 16) score += 9;
    else if (len <= 30) score += 2;
    else score -= 6;

    // 简历常见字段关键词（强烈提示这是字段名）
    if (/(姓名|名字|邮箱|邮件|手机|电话|联系方式|证件|身份证|性别|民族|生日|出生|年龄|户籍|籍贯|婚姻|政治面貌|学历|学位|学校|院校|学院|专业|毕业|入学|在校|培养|学制|导师|实习|工作|职位|岗位|部门|公司|项目|经历|描述|职责|城市|地区|地点|爱好|特长|期望|薪资|到岗|证书|语言|四级|六级|托福|雅思|推荐|来源)/.test(s)) {
      score += 12;
    }

    // 尾部带冒号/问号 → 像字段名
    if (/[：:?？]$/.test(s)) score += 4;

    // 两个以上冒号 → 可能是一整行说明，降低
    if ((s.match(/[：:]/g) || []).length >= 2) score -= 8;

    // 纯占位性提示词 → 明确不是字段名
    if (/^(请选择|请填写|请输入|请在下拉列表中选择|输入|选择|下拉|推荐码|手机号|手机|^\+\d)/.test(s)) score -= 12;
    if (s === "请选择") return Number.NEGATIVE_INFINITY;   // 读取当前选中值的占位
    if (s === "推荐码" || s === "+86" || /^\+86$/.test(s)) return Number.NEGATIVE_INFINITY;

    // 像选项值（男/女/本科/硕士...）而非字段名
    if (/^(男|女|是|否|本科|硕士|博士|大专|高中|初中|统招|全日制|应届|毕业生|未婚|已婚)$/.test(s)) score -= 20;

    return score;
  }

  // 从候选列表选出得分最高的字段名（无有效候选则返回空字符串）
  function selectBestLabel(candidates) {
    let best = "";
    let bestScore = Number.NEGATIVE_INFINITY;
    for (const c of candidates) {
      const t = normLabel(c || "");
      if (!t) continue;
      const s = scoreLabelCandidate(t);
      if (s > bestScore) {
        bestScore = s;
        best = t;
      }
    }
    return Number.isFinite(bestScore) ? best : "";
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
    // ============ 候选收集 + 判分（借鉴参考项目的候选判分法） ============
    // 不"找到第一个候选就返回"，而是收集所有候选文本，用 scoreLabelCandidate
    // 选"最像字段名"的那个。彻底避免：+86 / 请选择 / 本科 / 大学名称 / 选项值 被误当 label。
    const candidates = [];
    const push = (t) => {
      const s = normLabel(t);
      if (s && meaningfulLabel(s) && !candidates.includes(s)) candidates.push(s);
    };

    // A. 直接语义来源
    push(el.getAttribute && el.getAttribute("aria-label"));
    const labelledBy = el.getAttribute && el.getAttribute("aria-labelledby");
    if (labelledBy) {
      labelledBy.split(/\s+/).forEach((id) => {
        const tgt = document.getElementById(id);
        if (tgt) push(tgt.textContent);
      });
    }
    if (el.id) {
      const lbl = document.querySelector(`label[for="${CSS.escape(el.id)}"]`);
      if (lbl) push(lbl.textContent);
    }
    const wrap = el.closest("label");
    if (wrap) push(wrap.textContent);

    const pushContainerLabels = (container) => {
      if (!container) return;
      // 直接子元素中的 label 语义元素（不搜孙辈，避免跨字段）
      const children = Array.from(container.children || []);
      for (const child of children) {
        if (child === el || (child.contains && child.contains(el))) continue;
        // 只取"像 label"的元素：短文本 + 不含表单控件
        if (child.querySelector("input, select, textarea, [role=combobox]")) continue;
        push(child.textContent);
        const nested = child.querySelector(
          "label, .label, [class*=label]:not(input):not(textarea), [class*=title], [class*=name], legend"
        );
        if (nested && nested !== el) push(nested.textContent);
      }
    };

    // B. 就近字段容器（Moka/ElementUI/antd 等）
    const FIELD_CONTAINER =
      ".el-form-item, .ivu-form-item, .ant-form-item, .n-form-item, " +
      ".field-item, .form-item, .form-field, .field, .form-group, .control-group, " +
      "[class*=field-item], [class*=form-item]:not(form), [class*=question], " +
      "[class*=row],[class*=cell],fieldset,section,li,dt,td,th";
    const container = el.closest(FIELD_CONTAINER);
    if (container && container !== el && container.contains(el)) {
      pushContainerLabels(container);
    } else {
      // 未找到合适的字段容器：从 el 的祖先逐层收集候选
      let cur = el.parentElement;
      for (let i = 0; i < 4 && cur; i++) {
        pushContainerLabels(cur);
        cur = cur.parentElement;
      }
    }

    // C. 表格布局：同行前一个 td/th
    const tr = el.closest("tr");
    if (tr) {
      const td = el.closest("td, th");
      if (td) {
        let prev = td.previousElementSibling;
        while (prev) {
          push(prev.textContent);
          prev = prev.previousElementSibling;
        }
      }
    }

    // D. 紧邻兄弟 / 文本节点（上方 div/span 或前一个文本）
    let block = el.previousElementSibling;
    if (block && !block.querySelector("input, select, textarea, [role=combobox]")) {
      push(block.textContent);
    }
    let sib = el.previousSibling;
    while (sib) {
      if (sib.nodeType === 3 && sib.textContent.trim()) {
        push(sib.textContent);
        break;
      }
      sib = sib.previousSibling;
    }

    // E. placeholder / name 作为低优先级候选（可能正是真实字段名，如"请输入邮箱"）
    push(el.placeholder);
    push(el.getAttribute && el.getAttribute("name"));

    // 判分选最佳
    return selectBestLabel(candidates);
  }

  // 检测元素所属前端框架（用于识别 ElementUI / antd / iView / Naive UI / Vant 自定义组件）
  // 返回：{ framework: "el"|"antd"|"ivu"|"naive"|"vant"|"muimd"|"unknown", role: ""|"select"|"date"|"cascader"|"autocomplete" }
  function detectFramework(el) {
    const tag = el.tagName.toLowerCase();
    let node = el;
    // 向上 10 层找已知 class 容器（部分网申系统 DOM 嵌套较深）
    for (let i = 0; i < 10 && node; i++) {
      const cls = node.className || "";
      if (typeof cls !== "string") { node = node.parentElement; continue; }
      const has = (kw) => cls.indexOf(kw) !== -1;

      // ElementUI / Element Plus
      if (has("el-select")) return { framework: "el", role: "select", root: node };
      if (has("el-date-editor")) return { framework: "el", role: "date", root: node };
      if (has("el-cascader")) return { framework: "el", role: "cascader", root: node };
      if (has("el-autocomplete")) return { framework: "el", role: "autocomplete", root: node };
      if (has("el-time-picker") || has("el-time-select")) return { framework: "el", role: "date", root: node };
      // antd
      if (has("ant-select")) return { framework: "antd", role: "select", root: node };
      if (has("ant-picker")) return { framework: "antd", role: "date", root: node };
      if (has("ant-cascader")) return { framework: "antd", role: "cascader", root: node };
      // iView / View UI
      if (has("ivu-select")) return { framework: "ivu", role: "select", root: node };
      if (has("ivu-date-picker") || has("ivu-time-picker")) return { framework: "ivu", role: "date", root: node };
      if (has("ivu-cascader")) return { framework: "ivu", role: "cascader", root: node };
      // Naive UI
      if (has("n-base-selection") || has("n-select")) return { framework: "naive", role: "select", root: node };
      if (has("n-date-picker")) return { framework: "naive", role: "date", root: node };
      if (has("n-cascader")) return { framework: "naive", role: "cascader", root: node };
      // Vant (移动端)
      if (has("van-picker") || has("van-dropdown")) return { framework: "vant", role: "select", root: node };
      if (has("van-date-picker")) return { framework: "vant", role: "date", root: node };
      // MUI (x-date-pickers / autocomplete)
      if (has("MuiAutocomplete")) return { framework: "mui", role: "autocomplete", root: node };
      if (has("MuiDatePicker") || has("MuiPickers")) return { framework: "mui", role: "date", root: node };
      // Moka (北森网申系统)：React 构建，自定义组件
      if (has("moka-select") || has("mokaSelect")) return { framework: "moka", role: "select", root: node };
      if (has("moka-date") || has("mokaDate")) return { framework: "moka", role: "date", root: node };
      if (has("moka-cascader") || has("mokaCascader")) return { framework: "moka", role: "cascader", root: node };
      // 通用语义：combobox / listbox（WAI-ARIA 1.2）
      const role = node.getAttribute && node.getAttribute("role");
      if (role === "combobox" || role === "listbox") return { framework: "unknown", role: "select", root: node };

      node = node.parentElement;
    }
    return { framework: "unknown", role: "", root: null };
  }

  // 判断字段语义是否为日期/时间（用于把 readonly input 标为 date_picker）
  function looksLikeDate(text) {
    const t = (text || "").toLowerCase();
    if (!t) return false;
    return /(date|日期|时间|年月日|生日|出生|入职|毕业|参加工作|起止|起始|结束|到期|有效期|开始|截止|签发|失效|颁证|发证)/.test(t);
  }

  // 判断 input 是否位于自定义组件容器内（select/date picker/cascader 等）
  // 用于跳过 inner input，让外层容器被扫描
  function isInsideCustomSelectContainer(el) {
    let node = el.parentElement;
    for (let i = 0; i < 12 && node; i++) {
      const cls = (typeof node.className === "string") ? node.className : "";
      // Select 类
      if (
        cls.indexOf("el-select") !== -1 ||
        cls.indexOf("ant-select") !== -1 ||
        cls.indexOf("ivu-select") !== -1 ||
        cls.indexOf("n-base-selection") !== -1 ||
        cls.indexOf("n-select") !== -1 ||
        cls.indexOf("van-dropdown") !== -1 ||
        cls.indexOf("MuiAutocomplete") !== -1 ||
        cls.indexOf("moka-select") !== -1 ||
        cls.indexOf("mokaSelect") !== -1 ||
        cls.indexOf("custom-select") !== -1
      ) {
        return true;
      }
      // Date picker 类
      if (
        cls.indexOf("el-date") !== -1 ||
        cls.indexOf("ant-picker") !== -1 ||
        cls.indexOf("ivu-date") !== -1 ||
        cls.indexOf("n-date") !== -1 ||
        cls.indexOf("van-date") !== -1 ||
        cls.indexOf("MuiPickers") !== -1 ||
        cls.indexOf("MuiDatePicker") !== -1 ||
        cls.indexOf("moka-date") !== -1 ||
        cls.indexOf("mokaDate") !== -1 ||
        cls.indexOf("date-picker") !== -1 ||
        cls.indexOf("datepicker") !== -1
      ) {
        return true;
      }
      // Cascader 类
      if (
        cls.indexOf("el-cascader") !== -1 ||
        cls.indexOf("ant-cascader") !== -1 ||
        cls.indexOf("ivu-cascader") !== -1 ||
        cls.indexOf("n-cascader") !== -1 ||
        cls.indexOf("moka-cascader") !== -1 ||
        cls.indexOf("mokaCascader") !== -1 ||
        cls.indexOf("cascader") !== -1
      ) {
        return true;
      }
      // 通用语义
      const role = node.getAttribute && node.getAttribute("role");
      if (role === "combobox" || role === "listbox") return true;
      
      // 兜底：结构特征检测
      // 如果父容器只有当前这一个表单控件，且有其他子元素（箭头/图标等），则视为自定义组件容器
      // 注意：要排除简单的 label+input 组合（label 通常不在 input 的父容器内）
      const formControls = node.querySelectorAll("input, select, textarea, [role=combobox]");
      if (formControls.length === 1 && formControls[0] === el && node.children.length > 1) {
        // 进一步确认：有其他非 label 子元素（如箭头、图标、前缀等）
        const nonLabelChildren = Array.from(node.children).filter((child) => {
          return child.tagName.toLowerCase() !== "label" && 
                 !child.classList.contains("label") &&
                 !child.classList.contains("form-label");
        });
        if (nonLabelChildren.length > 0) {
          return true;
        }
      }
      
      node = node.parentElement;
    }
    return false;
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

    // 识别自定义下拉框 / 日期选择器：
    // ElementUI/antd/iView/Naive UI 的 Select/DatePicker 本质是 <input readonly> + 浮层，
    // 直接 setNativeValue 无效，必须走"点击展开→点击选项"的真实交互流程。
    // 这里在扫描期就标 type 为 custom_select / date_picker，让 filler 走对应分支。
    let framework = "unknown";
    
    // 关键修复：如果 input 位于自定义 select/date 容器内（如 el-select、ant-select），
    // 则跳过该 inner input，让外层容器被扫描（FIELD_SELECTOR 会匹配 div.el-select 等）。
    // 原因：filler 需要点击外层容器触发下拉，而不是直接写 inner readonly input。
    // 即使这个 input 本身有 readonly + 框架 class，也跳过 —— 因为点击它不如点击外层可靠。
    if (tag === "input" && type === "text" && isInsideCustomSelectContainer(el)) {
      return null; // 跳过 inner input，外层容器会被扫描为 custom_select
    }
    
    if (tag === "input" && type === "text") {
      const fw = detectFramework(el);
      framework = fw.framework;
      if (fw.role === "select" || fw.role === "cascader" || fw.role === "autocomplete") {
        type = "custom_select";
      } else if (fw.role === "date") {
        type = "date_picker";
      } else if (el.hasAttribute("readonly") || el.readOnly === true) {
        // 兜底：readonly input 且语义为日期 → date_picker；否则按自定义下拉框尝试
        if (looksLikeDate(label + " " + name + " " + placeholder)) {
          type = "date_picker";
        } else {
          // 仍可能是自定义组件（不在已知框架列表），保留为 text 但加 readonly 标记
          // filler 会在 fillOne 中再次尝试 custom_select 流程
          type = "custom_select";
        }
      }
    }

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
      // 同 name 多选组合并为一个 checkbox_group（参考项目多选组）
      const group = name ? document.querySelectorAll(`input[type=checkbox][name="${CSS.escape(name)}"]`) : [];
      if (group.length > 1) {
        type = "checkbox_group";
        options = Array.from(group).map((r) => ({
          value: r.value,
          label: getLabel(r) || r.value,
          checked: r.checked,
          el: r
        }));
        current_value = Array.from(group).filter((r) => r.checked).map((r) => r.value).join(",");
      } else {
        current_value = el.checked ? "true" : "false";
        options = [
          { value: "true", label: "是", el },
          { value: "false", label: "否", el }
        ];
      }
    } else if (type === "contenteditable") {
      current_value = (el.textContent || "").trim();
    } else if (tag === "div" || tag === "span" || tag === "li") {
      // div 模拟的自定义下拉（role=combobox / .custom-select / .el-select 等）：
      // 没有原生 value，取当前选中文本作为 current_value，并标为 custom_select
      // 让 filler 走"点击展开→点击选项"的下拉流程（fillCustomSelect / fillCascader / fillDatePicker）
      if (!looksLikeDate(label + " " + name + " " + placeholder)) {
        type = "custom_select";
      } else {
        type = "date_picker";
      }
      // 当前显示文本：优先取 value/选中 span，其次 textContent
      const valEl = el.querySelector("[class*=value], [class*=-value], [class*=selected], [class*=selection], [class*=single], .custom-select-value");
      current_value = valEl ? valEl.textContent.trim() : (el.textContent || "").trim();
      // 排除容器文本（如"请选择"占位、箭头、嵌套 span）里过于复杂的：只保留较短一段
      if (current_value.length > 20) current_value = "";
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
      framework,
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
      // 已作为 checkbox_group 合并的同名 checkbox：后续同 name 成员跳过，避免重复字段
      const mergedCheckboxGroups = new Set();
      all.forEach((el) => {
        if (!isVisible(el)) return;
        const elTag = el.tagName.toLowerCase();
        const elType = (el.getAttribute("type") || "").toLowerCase();
        if (elTag === "input" && elType === "checkbox" && el.name) {
          const g = document.querySelectorAll(`input[type=checkbox][name="${CSS.escape(el.name)}"]`);
          if (g.length > 1) {
            if (mergedCheckboxGroups.has(el.name)) return; // 该组已合并过，跳过成员
            mergedCheckboxGroups.add(el.name);
          }
        }
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
