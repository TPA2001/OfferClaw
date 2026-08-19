// OfferClaw 扩展 - 数据结构与常量定义
// 所有 shared 脚本以经典脚本方式加载，挂到 globalThis.OC 命名空间
(function () {
  if (typeof globalThis !== "undefined" && globalThis.OC && globalThis.OC.__loaded_schema) return;
  const OC = globalThis.OC || (globalThis.OC = {});
  OC.__loaded_schema = true;

  OC.schema = {
    DB_VERSION: 2,
    DB_KEY: "offerclaw_db",

    // 敏感字段关键词（本地填写，后端 profile 不存储这些）
    SENSITIVE_KEYS: [
      "身份证", "身份号", "身份证明", "id_card", "idcard", "identity", "id_number",
      "家庭住址", "住址", "home_address", "address",
      "银行卡", "银行账号", "bank_card", "bank_account",
      "护照", "passport",
      "社保号", "社保", "social_security",
      "紧急联系人", "紧急电话", "emergency_contact", "emergency_phone"
    ],

    // 投递状态枚举（与后端 applications API 一致）
    APPLICATION_STATUSES: {
      applied: "已投递",
      assessment: "笔试中",
      interview: "面试中",
      offer: "已录用",
      rejected: "已拒绝",
      withdrawn: "已撤回"
    },

    APPLICATION_PRIORITIES: {
      high: "心仪",
      medium: "普通",
      low: "备选"
    },

    // 扩展版本（用于 storage 迁移与诊断）
    EXT_VERSION: "0.0.3",

    // 本地画像空结构（本地数据库模式，不依赖后端）
    EMPTY_LOCAL_PROFILE: function () {
      return {
        basic: {
          name: "", gender: "", age: "", birth: "",
          phone: "", email: "", location: "",
          ethnicity: "", political_status: "", marital_status: "", native_place: "",
          wechat: "", qq: "", website: "", github: "", linkedin: "",
          english_level: "", driving_license: "", job_status: "",
          job_intent: "", avatar: ""
        },
        education: [],
        experience: [],
        projects: [],
        skills: [],
        summary: { strengths: "", interests: "" },
        certificates: [],
        job_intent: {
          target_positions: [], target_cities: [],
          expected_salary: "", work_type: "", availability: ""
        },
        // 用户自定义字段（来自后端 extra_fields），用于兜底匹配任意网申表单字段
        custom_fields: {}
      };
    },

    // 投递记录空结构
    EMPTY_APPLICATION: function () {
      const now = new Date();
      return {
        id: "app_" + Date.now() + "_" + Math.random().toString(36).slice(2, 8),
        company: "", position: "",
        job_url: null, source: "extension",
        status: "applied", priority: "medium",
        notes: null,
        applied_at: now.toISOString(),
        updated_at: now.toISOString()
      };
    }
  };
})();
