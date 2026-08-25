// OfferClaw 扩展 - 本地字段匹配器
// 设计目标：不依赖后端 API，直接基于本地画像 + 扫描字段做规则匹配
// 隐私：所有匹配在浏览器本地完成，画像不出本地存储
(function () {
  if (globalThis.OC && globalThis.OC.__loaded_matcher) return;
  const OC = globalThis.OC || (globalThis.OC = {});
  OC.__loaded_matcher = true;

  // 字段 → 画像 key 映射规则
  // 每条规则：{ keywords:[...], source:"basic|edu|exp|proj|sensitive", field:"xxx", priority, valueType? }
  // valueType: "number" | "date" | "text" | "select" — 用于值类型校验，防止误填
  const RULES = [
    // ── 基本信息（高优先级） ──────────────────────────────────
    { keywords: ["姓名", "名字", "name", "fullname", "real_name", "真实姓名"], source: "basic", field: "name", priority: 10, valueType: "text" },
    { keywords: ["手机", "电话", "phone", "tel", "mobile", "联系", "手机号", "联系电话", "手机号码"], source: "basic", field: "phone", priority: 10, valueType: "text" },
    { keywords: ["邮箱", "email", "mail", "e-mail", "电子邮箱", "电子邮件"], source: "basic", field: "email", priority: 10, valueType: "text" },
    { keywords: ["性别", "gender", "sex"], source: "basic", field: "gender", priority: 8, valueType: "select" },
    { keywords: ["年龄", "age", "岁数"], source: "basic", field: "age", priority: 8, valueType: "number" },
    { keywords: ["出生", "生日", "birth", "birthday", "birthdate", "出生日期", "出生年月", "出生时间"], source: "basic", field: "birth", priority: 8, valueType: "date" },
    { keywords: ["身高", "height", "身高(cm)", "身高(厘米)"], source: "basic", field: "height", priority: 7, valueType: "number" },
    { keywords: ["体重", "weight", "体重(kg)", "体重(公斤)"], source: "basic", field: "weight", priority: 7, valueType: "number" },
    { keywords: ["籍贯", "籍貫", "出生地", "native", "祖籍"], source: "basic", field: "native_place", priority: 6, valueType: "text" },
    { keywords: ["户口", "户口所在地", "户籍", "hukou", "户口所在"], source: "basic", field: "hukou", priority: 6, valueType: "text" },
    { keywords: ["民族", "ethnicity", "nation", "少数民族"], source: "basic", field: "ethnicity", priority: 6, valueType: "select" },
    { keywords: ["国籍", "nationality", "country", "nationality区域", "所在国家"], source: "basic", field: "nationality", priority: 6, valueType: "text" },
    { keywords: ["政治面貌", "political", "political_status", "党派", "团员", "党员", "群众"], source: "basic", field: "political_status", priority: 6, valueType: "select" },
    { keywords: ["婚姻", "婚育", "marital", "已婚", "未婚", "婚姻状况"], source: "basic", field: "marital_status", priority: 6, valueType: "select" },
    { keywords: ["现居", "现居住地", "current_address", "居住城市", "所在城市", "常住地", "常驻城市", "现居城市"], source: "basic", field: "current_city", priority: 6, valueType: "text" },
    { keywords: ["目前公司", "当前公司", "现在公司", "现公司", "现就职公司", "current_company", "所在公司", "任职公司", "工作单位"], source: "basic", field: "current_company", priority: 6, valueType: "text" },
    { keywords: ["目前职位", "当前职位", "现职位", "现任职务", "现在职位", "current_title", "现职", "目前职务"], source: "basic", field: "current_title", priority: 6, valueType: "text" },
    { keywords: ["工作年限", "工作年数", "经验年限", "工作经历年限", "years_experience", "从业年限", "几年经验", "工作多少年"], source: "basic", field: "years_experience", priority: 6, valueType: "number" },
    { keywords: ["微信", "wechat", "weixin"], source: "basic", field: "wechat", priority: 5, valueType: "text" },
    { keywords: ["qq", "腾讯qq"], source: "basic", field: "qq", priority: 5, valueType: "text" },
    { keywords: ["个人网站", "作品集", "个人主页", "website", "portfolio", "博客", "blog"], source: "basic", field: "website", priority: 5, valueType: "text" },
    { keywords: ["github", "开源主页", "gitee"], source: "basic", field: "github", priority: 5, valueType: "text" },
    { keywords: ["领英", "linkedin"], source: "basic", field: "linkedin", priority: 5, valueType: "text" },
    { keywords: ["英语水平", "英语等级", "四六级", "cet", "雅思", "托福", "english_level", "外语水平", "语言能力", "英语能力", "英语六级", "英语四级"], source: "basic", field: "english_level", priority: 5, valueType: "text" },
    { keywords: ["驾照", "驾驶证", "driving", "驾驶"], source: "basic", field: "driving_license", priority: 5, valueType: "select" },
    { keywords: ["求职状态", "到岗状态", "在职状态", "job_status", "目前状态", "当前状态", "工作状态"], source: "basic", field: "job_status", priority: 5, valueType: "select" },

    // ── 敏感字段（高优先级，需本地填写） ──────────────────────
    { keywords: ["身份证", "身份号", "身份证明", "id_card", "idcard", "identity", "id_number", "证件号码", "证件号"], source: "sensitive", field: "id_card", priority: 9, valueType: "text" },
    { keywords: ["证件照", "照片", "头像", "avatar", "photo", "证件照片", "个人照片", "免冠照片"], source: "basic", field: "avatar", priority: 7, valueType: "file" },
    { keywords: ["地址", "住址", "家庭住址", "address", "home", "通讯地址", "邮寄地址"], source: "sensitive", field: "home_address", priority: 6, valueType: "text" },
    { keywords: ["银行卡", "银行账号", "bank_card", "bank_account", "银行"], source: "sensitive", field: "bank_card", priority: 7, valueType: "text" },
    { keywords: ["护照", "passport"], source: "sensitive", field: "passport", priority: 7, valueType: "text" },
    { keywords: ["紧急联系人电话", "紧急联系电话", "emergency_phone"], source: "sensitive", field: "emergency_phone", priority: 7, valueType: "text" },
    { keywords: ["紧急联系人", "emergency_contact"], source: "sensitive", field: "emergency_contact", priority: 7, valueType: "text" },

    // ── 教育经历 ─────────────────────────────────────────────
    { keywords: ["学校", "院校", "大学", "university", "school", "毕业院校", "母校", "毕业学校"], source: "edu", field: "school", priority: 7, valueType: "text" },
    { keywords: ["专业", "major", "specialty", "specialization", "所学专业"], source: "edu", field: "major", priority: 6, valueType: "text" },
    { keywords: ["学历", "学位", "degree", "qualification", "最高学历", "学位层次"], source: "edu", field: "degree", priority: 6, valueType: "select" },
    { keywords: ["学历类型", "学历性质", "统招全日制", "非统招", "全日制", "教育类型", "学历类别"], source: "edu", field: "study_mode", priority: 6, valueType: "select" },
    { keywords: ["培养方式", "学习形式", "学习方式", "培养形式"], source: "edu", field: "study_mode", priority: 5, valueType: "select" },
    { keywords: ["导师", "tutor", "mentor", "指导老师"], source: "edu", field: "advisor", priority: 4, valueType: "text" },
    { keywords: ["排名", "成绩排名", "ranking", "班级排名", "年级排名", "专业排名"], source: "edu", field: "ranking", priority: 4, valueType: "text" },
    { keywords: ["学校城市", "就读城市", "学校所在城市"], source: "edu", field: "city", priority: 4, valueType: "text" },
    { keywords: ["入学", "入学时间", "enroll", "enrollment", "开始时间"], source: "edu", field: "start_date", priority: 5, valueType: "date" },
    { keywords: ["毕业", "毕业时间", "graduation", "grad_date", "结束时间", "毕业年份"], source: "edu", field: "end_date", priority: 5, valueType: "date" },
    { keywords: ["gpa", "成绩", "绩点", "平均分", "score", "grade"], source: "edu", field: "gpa", priority: 4, valueType: "text" },

    // ── 实习经历（参考项目单独区分实习，映射到最近工作经历） ──
    { keywords: ["实习公司", "实习单位", "实习机构"], source: "exp", field: "company", priority: 5, valueType: "text" },
    { keywords: ["实习职位", "实习岗位", "实习职务"], source: "exp", field: "position", priority: 5, valueType: "text" },
    { keywords: ["实习开始", "实习起始", "实习时间"], source: "exp", field: "start_date", priority: 4, valueType: "date" },
    { keywords: ["实习结束"], source: "exp", field: "end_date", priority: 4, valueType: "date" },

    // ── 工作经历 ─────────────────────────────────────────────
    { keywords: ["公司", "单位", "employer", "company", "雇主"], source: "exp", field: "company", priority: 6, valueType: "text" },
    { keywords: ["职位", "岗位", "title", "position", "job_title", "职务", "职位名称", "岗位名称"], source: "exp", field: "position", priority: 5, valueType: "text" },
    { keywords: ["入职", "入职时间", "start_date", "参加工作", "工作开始", "任职起止"], source: "exp", field: "start_date", priority: 4, valueType: "date" },
    { keywords: ["离职", "离职时间", "end_date", "工作结束", "至今"], source: "exp", field: "end_date", priority: 4, valueType: "date" },
    { keywords: ["工作描述", "工作内容", "职责", "responsibilities", "job_description", "工作业绩", "岗位职责"], source: "exp", field: "description", priority: 4, valueType: "text" },

    // ── 项目经历 ─────────────────────────────────────────────
    { keywords: ["项目名称", "project_name", "project", "项目"], source: "proj", field: "name", priority: 5, valueType: "text" },
    { keywords: ["项目角色", "project_role", "项目职责", "项目职务"], source: "proj", field: "role", priority: 4, valueType: "text" },
    { keywords: ["项目描述", "project_desc", "project_description", "项目介绍", "项目内容"], source: "proj", field: "description", priority: 4, valueType: "text" },
    { keywords: ["项目时间", "项目周期", "项目起止"], source: "proj", field: "period", priority: 3, valueType: "date" },

    // ── 技能 ─────────────────────────────────────────────────
    { keywords: ["技能", "skills", "技能标签", "技术栈", "tech_stack", "技术能力", "专长", "skill_tags", "掌握技能", "专业技能"], source: "skill", field: "skills", priority: 5, valueType: "text" },

    // ── 证书与荣誉 ───────────────────────────────────────────
    { keywords: ["证书", "cert", "资格证书", "qualification", "certifications", "certificate"], source: "cert", field: "name", priority: 4, valueType: "text" },
    { keywords: ["获奖", "荣誉", "奖项", "奖励", "荣誉奖项", "所获荣誉", "获奖情况", "获奖经历"], source: "cert", field: "name", priority: 4, valueType: "text" },

    // ── 求职意向 ─────────────────────────────────────────────
    { keywords: ["期望薪资", "期望薪水", "salary", "expected_salary", "薪资要求", "薪酬", "期望月薪", "期望年薪"], source: "intent", field: "expected_salary", priority: 4, valueType: "text" },
    { keywords: ["工作性质", "工作类型", "job_type", "工作形式", "全职", "兼职", "实习"], source: "intent", field: "work_type", priority: 4, valueType: "select" },
    { keywords: ["到岗时间", "可入职时间", "availability", "最快到岗", "何时到岗", "到岗日期"], source: "intent", field: "availability", priority: 4, valueType: "text" },
    { keywords: ["意向城市", "期望城市", "工作城市", "target_city", "preferred_city", "工作地点", "期望工作地点"], source: "intent", field: "target_cities", priority: 4, valueType: "text" },
    { keywords: ["意向岗位", "期望岗位", "目标岗位", "应聘岗位", "target_position", "applied_position", "期望职位"], source: "intent", field: "target_positions", priority: 4, valueType: "text" },

    // ── 自我评价 / 个人简介 ──────────────────────────────────
    { keywords: ["自我评价", "个人简介", "自我介绍", "summary", "profile", "自我描述", "个人评价"], source: "summary", field: "strengths", priority: 3, valueType: "text" },
    { keywords: ["兴趣爱好", "hobby", "interest", "特长", "爱好", "才艺", "个人特长"], source: "summary", field: "interests", priority: 3, valueType: "text" },
    { keywords: ["职业规划", "career", "发展目标", "职业目标"], source: "summary", field: "career_goal", priority: 3, valueType: "text" }
  ];

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

  // 字段描述文本（label + name + id + placeholder + aria-label）
  // 注意：故意不包含 section，因为 section 通常是区块标题（如"工作经历"），
  //       包含 section 会导致跨字段误匹配（如体重字段匹配到工作经历区块的公司名）
  function fieldText(f) {
    return [
      f.label || "", f.name || "", f.id || "",
      f.placeholder || "", f["aria-label"] || ""
    ].join(" ").toLowerCase();
  }

  // 值类型校验：防止画像值类型与字段期望类型不匹配导致误填
  // 例如：公司名（文本）不应填入体重字段（数字）
  function validateValueType(value, valueType, fieldLabel) {
    if (!value || !valueType) return true; // 无类型约束则放行
    const v = String(value).trim();
    if (!v) return true;
    switch (valueType) {
      case "number":
        // 数字字段：值必须是纯数字（允许小数、单位如 cm/kg）
        return /^\d+(\.\d+)?\s*(cm|kg|mm|m)?$/i.test(v);
      case "date":
        // 日期字段：值必须看起来像日期
        return /\d{4}[\-\/.年]\d{1,2}/.test(v) || /^\d{4}$/.test(v) || /\d{1,2}月\d{1,2}日?/.test(v);
      case "select":
        // 下拉字段：值应该是短文本（通常 1-4 个字），不是长句子
        return v.length <= 10;
      case "file":
        // 文件字段：跳过值校验，由调用方处理
        return true;
      default:
        return true;
    }
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
    if (rule.source === "proj") {
      const arr = Array.isArray(profile.projects) ? profile.projects : [];
      if (!arr.length) return "";
      const proj = arr[arr.length - 1] || arr[0];
      return proj[rule.field] || "";
    }
    if (rule.source === "skill") {
      // 技能/技术栈：取 skills 数组，用顿号/逗号拼接
      const arr = Array.isArray(profile.skills) ? profile.skills : [];
      if (!arr.length) return "";
      return arr
        .map((it) => {
          if (typeof it === "string") return it;
          if (it && typeof it === "object") return it.name || it.skill || "";
          return "";
        })
        .filter((it) => it && String(it).trim())
        .join("、");
    }
    if (rule.source === "cert") {
      // 证书/荣誉：取 certificates 数组的证书名称拼接
      const arr = Array.isArray(profile.certificates) ? profile.certificates : [];
      if (!arr.length) return "";
      return arr
        .map((it) => (it && typeof it === "object" ? it.name : String(it)))
        .filter((it) => it && String(it).trim())
        .join("、");
    }
    if (rule.source === "intent") {
      const ji = profile.job_intent || {};
      const v = ji[rule.field];
      // target_cities / target_positions 是数组，取第一个或拼接
      if (Array.isArray(v)) return v.length ? v.join("、") : "";
      return v || "";
    }
    if (rule.source === "summary") {
      return (profile.summary && profile.summary[rule.field]) || "";
    }
    return "";
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

        // 找到所有匹配的规则（按优先级降序），取第一个值类型校验通过的
        const candidates = RULES
          .filter((r) => r.keywords.some((kw) => text.includes(kw.toLowerCase())))
          .sort((a, b) => b.priority - a.priority);

        // 值类型校验：防止画像值类型与字段期望类型不匹配导致误填
        // 例如：公司名（文本）不应填入体重字段（数字）
        let matched = null;
        for (const rule of candidates) {
          const value = pickValueFromProfile(profile, rule);
          if (!value && rule.source !== "sensitive") continue;
          // 值类型校验（仅对有值的非敏感字段）
          if (value && rule.valueType && !validateValueType(value, rule.valueType, f.label)) {
            continue; // 值类型不匹配，尝试下一个候选规则
          }
          matched = rule;
          break;
        }

        if (!matched) {
          // 规则未命中 → 回退到用户自定义字段（按字段名匹配）
          const cust = matchCustomField(text, custom);
          if (cust) {
            out.push({
              field_id: f.id,
              field_name: f.name,
              selector: f.selector,
              type: f.type,
              framework: f.framework || "unknown",
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
            framework: f.framework || "unknown",
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
              framework: f.framework || "unknown",
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
            framework: f.framework || "unknown",
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
            framework: f.framework || "unknown",
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
          framework: f.framework || "unknown",
          value: String(value),
          action: "fill",
          source: matched.source,
          reason: `命中规则: ${matched.keywords[0]} → ${matched.source}.${matched.field}`
        });
      });

      return out;
    },

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
      const sensFilled = profile.__sens_filled || 0;
      const sensTotal = 4;

      // 加权：basic 50% + edu 15% + exp 15% + skills 10% + sensitive 10%
      const score =
        (basicFilled / basicKeys.length) * 50 +
        Math.min(eduFilled, 1) * 15 +
        Math.min(expFilled, 1) * 15 +
        Math.min(skillsFilled / 3, 1) * 10 +
        (sensFilled / sensTotal) * 10;

      return Math.round(score);
    }
  };
})();
