// OfferClaw 填表助手 - 后端配置管理
// 本地数据库优先；后端可选，通过 use_backend 开关启用
(function () {
  if (globalThis.OC && globalThis.OC.__loaded_config) return;
  const OC = globalThis.OC || (globalThis.OC = {});
  OC.__loaded_config = true;

  const DEFAULT_BACKEND = "http://localhost:8000";
  const API_PREFIX = "/api/v1";

  OC.config = {
    DEFAULT_BACKEND,
    API_PREFIX,

    async getBackend() {
      const cfg = (await OC.store.get("config")) || {};
      return cfg.backend || DEFAULT_BACKEND;
    },

    async isLocalMode() {
      // 本地模式 = use_backend 关闭（默认）或后端不可达
      const cfg = (await OC.store.get("config")) || {};
      return cfg.use_backend !== true;
    },

    async getUseLlm() {
      const cfg = (await OC.store.get("config")) || {};
      return !!cfg.use_llm;
    },

    // 兼容旧签名：set(backend, use_llm) 或 set(backend, use_backend)
    async set(backend, use_backend) {
      const patch = { backend };
      // 兼容老参数 use_llm；新参数语义是"启用后端"
      if (typeof use_backend === "boolean") {
        patch.use_backend = use_backend;
        // 启用后端时若旧的 use_llm 也开着，保持原 use_llm；否则 use_llm=false
        const cur = await this.get();
        patch.use_llm = use_backend ? cur.use_llm : false;
      }
      await OC.store.update("config", patch);
    },

    async get() {
      const cfg = (await OC.store.get("config")) || {};
      return {
        backend: cfg.backend || DEFAULT_BACKEND,
        use_llm: !!cfg.use_llm,
        use_backend: cfg.use_backend === true,
        local_mode: cfg.use_backend !== true
      };
    }
  };
})();
