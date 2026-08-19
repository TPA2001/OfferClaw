// OfferClaw 扩展 - 持久化层（chrome.storage.local + 版本迁移）
// 设计目标：版本升级后数据依然可用，通过 version 字段 + migrate() 兼容旧结构
// 本地数据库模式：所有画像、投递记录、敏感数据均存 chrome.storage.local
(function () {
  if (globalThis.OC && globalThis.OC.__loaded_storage) return;
  const OC = globalThis.OC || (globalThis.OC = {});
  OC.__loaded_storage = true;

  const DB_KEY = OC.schema.DB_KEY;
  const DB_VERSION = OC.schema.DB_VERSION;

  // 默认数据结构（V2：本地数据库模式）
  const DEFAULTS = {
    version: DB_VERSION,
    config: { backend: "http://localhost:8000", use_llm: false, local_mode: true },
    profile_local: OC.schema.EMPTY_LOCAL_PROFILE(),     // 本地画像（本地数据库主存储）
    sensitive_local: {                                 // 敏感数据本地存储（后端永不接触）
      id_card: "",
      home_address: "",
      bank_card: "",
      passport: "",
      emergency_contact: "",
      emergency_phone: ""
    },
    applications_local: {                              // 投递记录本地表（本地数据库主存储）
      list: [],
      seq: 0
    },
    mapping_cache: {},                                 // {page_signature: {mappings, ts}}
    stats: { scan_count: 0, fill_count: 0 },
    installed_at: null
  };

  // 迁移函数：根据 version 逐级升级到最新
  function migrate(data) {
    let d = data || {};
    const fromV = typeof d.version === "number" ? d.version : 0;

    if (fromV < 1) {
      // v1 → 旧结构初始化（保留兼容）
      d = Object.assign({}, {
        config: { backend: "http://localhost:8000", use_llm: false },
        sensitive_local: { id_card: "", home_address: "", bank_card: "", passport: "" },
        applications_cache: { list: [], fetched_at: 0 },
        mapping_cache: {},
        stats: { scan_count: 0, fill_count: 0 }
      }, d);
      d.installed_at = d.installed_at || Date.now();
    }

    if (fromV < 2) {
      // v2 → 本地数据库模式：
      // 1) config.local_mode 默认 true（本地优先）
      // 2) profile_local 若空则初始化为 EMPTY_LOCAL_PROFILE
      // 3) applications_cache 迁移为 applications_local（保留旧数据）
      if (!d.config) d.config = {};
      d.config.local_mode = true;
      if (!d.profile_local || typeof d.profile_local !== "object") {
        d.profile_local = OC.schema.EMPTY_LOCAL_PROFILE();
      }
      // 把旧的 applications_cache.list 迁移到 applications_local.list
      const oldList = d.applications_cache && Array.isArray(d.applications_cache.list)
        ? d.applications_cache.list : [];
      delete d.applications_cache;
      d.applications_local = { list: oldList, seq: oldList.length };
    }

    // 默认结构兜底
    d.config = Object.assign({}, DEFAULTS.config, d.config || {});
    d.sensitive_local = Object.assign({}, DEFAULTS.sensitive_local, d.sensitive_local || {});
    d.profile_local = Object.assign({}, OC.schema.EMPTY_LOCAL_PROFILE(), d.profile_local || {});
    d.applications_local = Object.assign({}, DEFAULTS.applications_local, d.applications_local || {});
    d.mapping_cache = d.mapping_cache || {};
    d.stats = Object.assign({}, DEFAULTS.stats, d.stats || {});
    d.installed_at = d.installed_at || Date.now();

    d.version = DB_VERSION;
    return d;
  }

  // 注意：不缓存到内存，每次 load 都从 chrome.storage.local 读取。
  // 原因：popup / content / background 是彼此隔离的执行上下文，各自若持有
  // 一份内存缓存，popup 同步后端画像写盘后，content.js 仍会读到旧的空画像，
  // 导致"填表用的是旧空画像、全部跳过"。改为始终读盘，保证跨上下文即时可见。

  async function load() {
    const got = await chrome.storage.local.get(DB_KEY);
    const data = migrate(got[DB_KEY]);
    // 回写迁移后的结构（保证升级后落盘）
    await chrome.storage.local.set({ [DB_KEY]: data });
    return data;
  }

  async function save(data) {
    await chrome.storage.local.set({ [DB_KEY]: data });
  }

  OC.store = {
    DB_KEY,

    async getAll() {
      return await load();
    },

    async get(section, key) {
      const d = await load();
      const sec = d[section];
      if (sec == null) return undefined;
      if (key == null) return sec;
      return sec[key];
    },

    async set(section, key, value) {
      const d = await load();
      if (key == null) {
        d[section] = value;
      } else {
        if (!d[section] || typeof d[section] !== "object") d[section] = {};
        d[section][key] = value;
      }
      await save(d);
    },

    async update(section, patch) {
      const d = await load();
      if (!d[section] || typeof d[section] !== "object") d[section] = {};
      d[section] = Object.assign({}, d[section], patch);
      await save(d);
    },

    async bumpStat(key) {
      const d = await load();
      if (!d.stats) d.stats = { scan_count: 0, fill_count: 0 };
      if (typeof d.stats[key] === "number") d.stats[key] += 1;
      await save(d);
    },

    async reset() {
      await chrome.storage.local.set({ [DB_KEY]: migrate({}) });
      return await load();
    },

    async exportData() {
      // 导出全部本地数据（用户备份）
      const d = await load();
      return JSON.parse(JSON.stringify(d));
    },

    // ============ 画像（本地数据库） ============
    async getProfile() {
      const d = await load();
      // 返回深拷贝避免外部误改
      return JSON.parse(JSON.stringify(d.profile_local));
    },

    async saveProfile(profile) {
      const d = await load();
      d.profile_local = JSON.parse(JSON.stringify(profile || {}));
      await save(d);
    },

    async patchBasicInfo(patch) {
      const d = await load();
      if (!d.profile_local.basic) d.profile_local.basic = {};
      Object.assign(d.profile_local.basic, patch || {});
      await save(d);
    },

    // ============ 投递记录（本地数据库） ============
    async listApplications(status) {
      const d = await load();
      let list = (d.applications_local && d.applications_local.list) || [];
      // 复制避免外部误改
      list = list.slice().reverse(); // 最新的在前
      if (status) list = list.filter((a) => a.status === status);
      return list;
    },

    async createApplication(app) {
      const d = await load();
      const seq = (d.applications_local.seq || 0) + 1;
      const now = new Date().toISOString();
      const row = Object.assign(OC.schema.EMPTY_APPLICATION(), app || {}, {
        id: "app_" + seq + "_" + Date.now().toString(36),
        seq,
        applied_at: now,
        updated_at: now
      });
      d.applications_local.list.push(row);
      d.applications_local.seq = seq;
      await save(d);
      return row;
    },

    async updateApplicationStatus(id, newStatus) {
      const d = await load();
      const row = (d.applications_local.list || []).find((a) => a.id === id);
      if (!row) throw new Error("投递记录不存在");
      row.status = newStatus;
      row.updated_at = new Date().toISOString();
      await save(d);
      return row;
    },

    async deleteApplication(id) {
      const d = await load();
      d.applications_local.list = (d.applications_local.list || []).filter((a) => a.id !== id);
      await save(d);
    }
  };

  // 启动时自动迁移
  if (typeof chrome !== "undefined" && chrome.runtime && chrome.runtime.id) {
    load().catch((e) => console.warn("[OfferClaw] storage 迁移失败:", e));
  }
})();
