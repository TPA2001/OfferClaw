// OfferClaw 扩展 - 后端 API 客户端
// 对接 OfferClaw 后端：/automation/ext/match（隐私匹配）、/profiles、/applications
// 鉴权说明：后端内测模式为 open（无 token），DEV 模式需后端 OFFERCLAW_DEV=1 绕过 license 门控
(function () {
  if (globalThis.OC && globalThis.OC.__loaded_api) return;
  const OC = globalThis.OC || (globalThis.OC = {});
  OC.__loaded_api = true;

  async function request(method, path, body, isHealth) {
    const backend = await OC.config.getBackend();
    const url = isHealth ? `${backend}${path}` : `${backend}${OC.config.API_PREFIX}${path}`;
    const opt = { method, headers: { "Content-Type": "application/json" } };
    if (body !== undefined) opt.body = JSON.stringify(body);

    let resp;
    try {
      resp = await fetch(url, opt);
    } catch (e) {
      throw new Error(`无法连接后端（${backend}）：${e.message}`);
    }
    const text = await resp.text();
    let data = {};
    try {
      data = text ? JSON.parse(text) : {};
    } catch (e) {
      throw new Error(`后端返回非 JSON：${text.slice(0, 120)}`);
    }
    if (!resp.ok) {
      const msg = (data && (data.message || data.detail)) || `HTTP ${resp.status}`;
      const code = data && data.code;
      // license 门控错误（40301/40302/40303）：提示用户开启 DEV 模式或激活授权
      if (code === 40301 || code === 40302 || code === 40303) {
        throw new Error(`后端授权未通过（${code}）：请在后端设置 OFFERCLAW_DEV=1 或激活授权。${msg}`);
      }
      throw new Error(msg);
    }
    // 后端统一响应：{code,message,data,...}
    if (data && typeof data === "object" && "data" in data) return data.data;
    return data;
  }

  OC.api = {
    // 健康检查（/health 不在 /api/v1 前缀下）
    health() {
      return request("GET", "/health", undefined, true);
    },

    // 用户画像
    getProfile() {
      return request("GET", "/profiles/");
    },
    updateProfile(profile) {
      return request("POST", "/profiles/", profile);
    },
    getProfileFlatten() {
      return request("GET", "/profiles/flatten");
    },
    getProfileCompletion() {
      return request("GET", "/profiles/completion");
    },

    // 扩展专用匹配（隐私优先）
    // useLlm=false 默认规则匹配（零隐私、免 LLM Key、免订阅）
    // useLlm=true 走后端脱敏 LLM
    extMatch(fields, useLlm, pageUrl) {
      return request("POST", "/automation/ext/match", {
        fields,
        use_llm: !!useLlm,
        page_url: pageUrl || location.href
      });
    },

    // 投递记录
    listApplications(status) {
      const q = status ? `?status=${encodeURIComponent(status)}` : "";
      return request("GET", `/applications/${q}`);
    },
    createApplication(app) {
      return request("POST", "/applications/", app);
    },
    updateApplicationStatus(id, newStatus) {
      return request("PATCH", `/applications/${encodeURIComponent(id)}/status?new_status=${encodeURIComponent(newStatus)}`);
    },
    deleteApplication(id) {
      return request("DELETE", `/applications/${encodeURIComponent(id)}`);
    },
    getStatsOverview() {
      return request("GET", "/applications/stats/overview");
    },
    getFollowups() {
      return request("GET", "/applications/stats/followups");
    }
  };
})();
