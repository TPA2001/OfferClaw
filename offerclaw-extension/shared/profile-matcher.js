// OfferClaw 扩展 - 本地字段匹配器
// 设计目标：不依赖后端 API，直接基于本地画像 + 扫描字段做规则匹配
// 隐私：所有匹配在浏览器本地完成，画像不出本地存储
(function () {
  if (globalThis.OC && globalThis.OC.__loaded_matcher) return;
  const OC = globalThis.OC || (globalThis.OC = {});
  OC.__loaded_matcher = true;

  // 字段 → 画像 key 映射规则
  // 每条规则：{ keywords:[...], source:"basic|edu|exp|proj|sensitive", field:"xxx", priority }
  const RULES = [
    // 基本信息
    { keywords: ["姓名", "名字", "name", "fullname"], source: "basic", field: "name", priority: 10 },
    { keywords: ["手机", "电话", "phone", "tel", "mobile", "联系"], source: "basic", field: "phone", priority: 10 },
    { keywords: ["邮箱", "email", "mail", "e-mail"], source: "basic", field: "email", priority: 10 },
    { keywords: ["性别", "gender", "sex"], source: "basic", field: "gender", priority: 8 },
    { keywords: ["年龄", "age"], source: "basic", field: "age", priority: 8 },
    { keywords: ["出生", "生日", "birth", "birthday", "birthdate"], source: "basic", field: "birth", priority: 8 },
    { keywords: ["籍贯", "户口", "籍貫", "出生地", "native", "祖籍"], source: "basic", field: "native_place", priority: 6 },
    { keywords: ["民族", "ethnicity", "nation", "少数民族"], source: "basic", field: "ethnicity", priority: 6 },
    { keywords: ["政治面貌", "political", "political_status", "党派", "团员", "党员"], source: "basic", field: "political_status", priority: 6 },
    { keywords: ["婚姻", "婚育", "marital", "已婚", "未婚"], source: "basic", field: "marital_status", priority: 6 },
    { keywords: ["微信", "wechat", "weixin"], source: "basic", field: "wechat", priority: 5 },
    { keywords: ["qq", "腾讯qq"], source: "basic", field: "qq", priority: 5 },
    { keywords: ["个人网站", "作品集", "个人主页", "website", "portfolio"], source: "basic", field: "website", priority: 5 },
    { keywords: ["github", "开源主页"], source: "basic", field: "github", priority: 5 },
    { keywords: ["领英", "linkedin"], source: "basic", field: "linkedin", priority: 5 },
    { keywords: ["英语水平", "英语等级", "四六级", "cet", "雅思", "托福", "english_level"], source: "basic", field: "english_level", priority: 5 },
    { keywords: ["驾照", "驾驶证", "driving", "驾驶"], source: "basic", field: "driving_license", priority: 5 },
    { keywords: ["求职状态", "到岗状态", "在职状态", "job_status", "目前状态", "当前状态"], source: "basic", field: "job_status", priority: 5 },
    { keywords: ["地址", "住址", "家庭住址", "address", "home"], source: "sensitive", field: "home_address", priority: 6 },
    { keywords: ["身份证", "身份号", "id_card", "idcard", "identity", "id_number"], source: "sensitive", field: "id_card", priority: 9 },
    { keywords: ["银行卡", "银行账号", "bank_card", "bank_account", "bank"], source: "sensitive", field: "bank_card", priority: 7 },
    { keywords: ["护照", "passport"], source: "sensitive", field: "passport", priority: 7 },
    { keywords: ["紧急联系人电话", "紧急联系电话", "emergency_phone"], source: "sensitive", field: "emergency_phone", priority: 7 },
    { keywords: ["紧急联系人", "emergency_contact"], source: "sensitive", field: "emergency_contact", priority: 7 },

    // 教育经历（取最高学历 / 第一条）
    { keywords: ["学校", "院校", "大学", "university", "school", "毕业院校"], source: "edu", field: "school", priority: 6 },
    { keywords: ["专业", "major", "specialty", "specialization"], source: "edu", field: "major", priority: 6 },
    { keywords: ["学历", "学位", "degree", "qualification"], source: "edu", field: "degree", priority: 6 },

    // 工作经历（取最近一份）
    { keywords: ["公司", "单位", "employer", "company", "雇主"], source: "exp", field: "company", priority: 5 },
    { keywords: ["职位", "岗位", "title", "position", "job_title"], source: "exp", field: "position", priority: 5 },

    // 求职意向
    { keywords: ["期望薪资", "期望薪水", "salary", "expected_salary"], source: "intent", field: "expected_salary", priority: 4 },
    { keywords: ["工作性质", "工作类型", "job_type", "工作形式"], source: "intent", field: "work_type", priority: 4 },
    { keywords: ["到岗时间", "可入职时间", "availability"], source: "intent", field: "availability", priority: 4 },

    // 自我评价 / 个人简介
    { keywords: ["自我评价", "个人简介", "自我介绍", "summary", "profile", "自我描述"], source: "summary", field: "strengths", priority: 3 },

    // 论文发表（论文/期刊/著作/专利）
    { keywords: ["论文", "发表论文", "期刊", "著作", "paper", "publication", "journal", "论文专利", "学术成果"], source: "paper", field: "papers", priority: 3 },
    // 专利（单独的专利字段）
    { keywords: ["专利", "patent", "专利号", "专利授权"], source: "paper", field: "papers", priority: 3 },

    // 获奖 / 荣誉 / 奖学金 / 竞赛
    { keywords: ["获奖", "奖项", "荣誉", "荣誉证书", "award", "honor", "奖学金", "竞赛", "比赛获奖", "获奖情况"], source: "award", field: "awards", priority: 3 }
  ];

  // 把数组型画像段（papers / awards）格式化成多行文本，用于填写"论文/获奖情况"等文本域或下拉
  function formatSection(arr, kind) {
    if (!Array.isArray(arr) || !arr.length) return "";
    return arr
      .map((it) => {
        if (typeof it === "string") return it;
        if (!it || typeof it !== "object") return "";
        if (kind === "paper") {
          const parts = [it.title, it.papers, it.name].filter(Boolean);
          const meta = [it.journal, it.conference, it.venue, it.year && it.year + "年", it.role, it.doi].filter(Boolean);
          const head = parts.join(" ");
          return (head ? head : "") + (meta.length ? "（" + meta.join("；") + "）" : "");
        }
        if (kind === "award") {
          const parts = [it.name, it.award, it.title].filter(Boolean);
          const meta = [it.level, it.organizer, it.year && it.year + "年"].filter(Boolean);
          const head = parts.join(" ");
          return (head ? head : "") + (meta.length ? "（" + meta.join("；") + "）" : "");
        }
        return "";
      })
      .filter(Boolean)
      .join("\n");
  }

  // 自定义字段兜底匹配：当规则都没命中时，尝试用用户自定义字段去匹配表单字段
  // 匹配策略：表单字段文本包含自定义字段的 key（或 key 的任一 token），则视为命中
  function matchCustomField(text, customFields) {
    if (!customFields || typeof customFields !== "object") return null;
    const t = (text || "").toLowerCase();
    const entries = Object.entries(customFields).filter(([, v]) => v !== "" && v != null);
    for (const [k, v] of entries) {
      const key = String(k).toLowerCase();
      if (!key) continue;
      // 整体包含
      if (t.includes(key)) return { key, value: String(v) };
      // 拆词匹配（至少 2 字/词的 token，避免误命中单字）
      const tokens = key.split(/[\s_\-·/、，,]+/).filter((tk) => tk.length >= 2);
      if (tokens.some((tk) => t.includes(tk))) return { key, value: String(v) };
    }
    return null;
  }

  // 字段描述文本（label + name + id + section + placeholder + aria-label）
  // 注意：scanner 把 placeholder 直接放在 f.placeholder（不带 attrs 包裹），这里直接读 f.placeholder
  function fieldText(f) {
    return [
      f.label || "", f.name || "", f.id || "", f.section || "",
      f.placeholder || "", f["aria-label"] || ""
    ].join(" ").toLowerCase();
  }

  function pickValueFromProfile(profile, rule) {
    if (!profile) return "";
    if (rule.source === "basic") {
      return (profile.basic && profile.basic[rule.field]) || "";
    }
    if (rule.source === "sensitive") {
      // 敏感字段不直接取值，由调用方调 OC.privacy.getLocalValue 填充
      return "__LOCAL_SENSITIVE__";
    }
    if (rule.source === "edu") {
      const arr = Array.isArray(profile.education) ? profile.education : [];
      if (!arr.length) return "";
      // 取最后一条（通常是最高学历）或第一条
      const edu = arr[arr.length - 1] || arr[0];
      return edu[rule.field] || "";
    }
    if (rule.source === "exp") {
      const arr = Array.isArray(profile.experience) ? profile.experience : [];
      if (!arr.length) return "";
      const exp = arr[0]; // 最新的
      return exp[rule.field] || "";
    }
    if (rule.source === "intent") {
      return (profile.job_intent && profile.job_intent[rule.field]) || "";
    }
    if (rule.source === "summary") {
      return (profile.summary && profile.summary[rule.field]) || "";
    }
    if (rule.source === "paper") {
      return formatSection(profile.papers, "paper");
    }
    if (rule.source === "award") {
      return formatSection(profile.awards, "award");
    }
    return "";
  }

  // 按 "source.field"（如 basic.name / edu.school / exp.company / intent.x / skills）取画像值，供站点模板使用
  function getProfileValue(profile, key) {
    if (!profile || !key) return "";
    const idx = key.indexOf(".");
    const source = idx > -1 ? key.slice(0, idx) : key;
    const field = idx > -1 ? key.slice(idx + 1) : "";
    const rule = { source };
    const v = pickValueFromProfile(profile, { ...rule, field });
    if (v === "__LOCAL_SENSITIVE__") return "";
    if (source === "skills" && Array.isArray(profile.skills)) {
      return profile.skills.map((s) => (typeof s === "string" ? s : s && s.name)).filter(Boolean).join(", ");
    }
    if (source === "papers" || source === "paper") {
      return formatSection(profile.papers, "paper");
    }
    if (source === "awards" || source === "award") {
      return formatSection(profile.awards, "award");
    }
    return v;
  }

  OC.matcher = {
    // 主匹配入口
    // 输入：fields (扫描的字段) + profile (本地画像) + sensitiveMap (敏感数据本地)
    // 输出：mappings [{field_id, value, action, source, reason}]
    match(fields, profile, sensitiveMap) {
      const out = [];
      const sensMap = sensitiveMap || {};
      const custom = (profile && profile.custom_fields) || {};

      fields.forEach((f) => {
        const text = fieldText(f);
        if (!text) return;

        // 找到第一个匹配的规则（按优先级降序）
        const matched = RULES
          .filter((r) => r.keywords.some((kw) => text.includes(kw.toLowerCase())))
          .sort((a, b) => b.priority - a.priority)[0];

        if (!matched) {
          // 规则未命中 → 回退到用户自定义字段（按字段名匹配）
          const cust = matchCustomField(text, custom);
          if (cust) {
            out.push({
              field_id: f.id,
              field_name: f.name,
              selector: f.selector,
              type: f.type,
              value: cust.value,
              action: "fill",
              source: "custom",
              reason: `命中自定义字段: ${cust.key}`
            });
            return;
          }
          // 真正未命中 → 标记 skip
          out.push({
            field_id: f.id,
            field_name: f.name,
            selector: f.selector,
            type: f.type,
            value: null,
            action: "skip",
            source: "no_rule",
            reason: "未匹配到任何画像字段"
          });
          return;
        }

        let value = pickValueFromProfile(profile, matched);

        // 敏感字段：从本地敏感数据 map 取值
        if (value === "__LOCAL_SENSITIVE__") {
          value = sensMap[matched.field] || "";
          if (!value) {
            out.push({
              field_id: f.id,
              field_name: f.name,
              selector: f.selector,
              type: f.type,
              value: null,
              action: "manual",
              source: "local_sensitive",
              reason: "敏感数据本地未配置，请到扩展设置面板填写"
            });
            return;
          }
          out.push({
            field_id: f.id,
            field_name: f.name,
            selector: f.selector,
            type: f.type,
            value: value,
            action: "fill",
            source: "local_sensitive",
            reason: "本地敏感字段"
          });
          return;
        }

        if (!value) {
          out.push({
            field_id: f.id,
            field_name: f.name,
            selector: f.selector,
            type: f.type,
            value: null,
            action: "skip",
            source: matched.source,
            reason: `画像字段 ${matched.field} 为空`
          });
          return;
        }

        out.push({
          field_id: f.id,
          field_name: f.name,
          selector: f.selector,
          type: f.type,
          value: String(value),
          action: "fill",
          source: matched.source,
          reason: `命中规则: ${matched.keywords[0]} → ${matched.source}.${matched.field}`
        });
      });

      return out;
    },

    getProfileValue,

    // 计算本地画像完成度（0-100）
    computeCompletion(profile) {
      if (!profile) return 0;
      const basic = profile.basic || {};
      const basicKeys = [
        "name", "gender", "birth", "phone", "email", "location",
        "ethnicity", "political_status", "marital_status", "native_place",
        "wechat", "qq", "website", "github", "linkedin",
        "english_level", "driving_license", "job_status", "job_intent"
      ];
      const basicFilled = basicKeys.filter((k) => {
        const v = basic[k];
        return v !== "" && v != null && (Array.isArray(v) ? v.length > 0 : true);
      }).length;

      const eduFilled = (Array.isArray(profile.education) ? profile.education : []).length;
      const expFilled = (Array.isArray(profile.experience) ? profile.experience : []).length;
      const skillsFilled = (Array.isArray(profile.skills) ? profile.skills : []).length;
      const papersFilled = (Array.isArray(profile.papers) ? profile.papers : []).length;
      const awardsFilled = (Array.isArray(profile.awards) ? profile.awards : []).length;
      const sensFilled = profile.__sens_filled || 0;
      const sensTotal = 4;

      // 加权：basic 48% + edu 12% + exp 12% + skills 10% + papers 6% + awards 6% + sensitive 6%
      const score =
        (basicFilled / basicKeys.length) * 48 +
        Math.min(eduFilled, 1) * 12 +
        Math.min(expFilled, 1) * 12 +
        Math.min(skillsFilled / 3, 1) * 10 +
        Math.min(papersFilled, 1) * 6 +
        Math.min(awardsFilled, 1) * 6 +
        Math.min(sensFilled / sensTotal, 1) * 6;

      return Math.round(score);
    }
  };
})();
