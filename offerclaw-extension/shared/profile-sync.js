// OfferClaw 扩展 - 后端画像同步
// 目的：把后端 OfferClaw（Web 端 /profile 页填的）画像拉进本地 chrome.storage，
//       让智能填表在没有手动录入的情况下也能工作。
// 设计：
//   - 后端 → 本地字段映射（basic_info/education/... → local profile 结构）
//   - 合并策略：远端非空字段覆盖本地空字段；本地非空且远端空的保留本地（不丢用户已录入的）
//   - 敏感字段（身份证/住址/银行卡/护照）远端永远不会有，仅从本地敏感存储读取
//   - 记录最后一次同步时间，便于 UI 展示
(function () {
  if (globalThis.OC && globalThis.OC.__loaded_profile_sync) return;
  const OC = globalThis.OC || (globalThis.OC = {});
  OC.__loaded_profile_sync = true;

  // 安全取字符串（远端可能返回 null / 数字 / 对象）
  function s(v) {
    if (v == null) return "";
    return String(v);
  }

  // 后端 skills 可能是字符串数组，也可能是 [{name, level, category}]
  function normalizeSkills(arr) {
    if (!Array.isArray(arr)) return [];
    return arr
      .map((it) => {
        if (typeof it === "string") return it;
        if (it && typeof it === "object") return it.name || it.skill || "";
        return "";
      })
      .filter(Boolean);
  }

  // 后端 basic_info → 本地 basic
  function mapBasic(b) {
    const src = b || {};
    return {
      name: s(src.name),
      gender: s(src.gender),
      age: s(src.age),
      birth: s(src.birth),
      phone: s(src.phone),
      email: s(src.email),
      location: s(src.location || src.city || src.hometown),
      ethnicity: s(src.ethnicity),
      political_status: s(src.political_status),
      marital_status: s(src.marital_status),
      native_place: s(src.native_place),
      wechat: s(src.wechat),
      qq: s(src.qq),
      website: s(src.website),
      github: s(src.github),
      linkedin: s(src.linkedin),
      english_level: s(src.english_level),
      driving_license: s(src.driving_license),
      job_status: s(src.job_status),
      job_intent: s(src.job_intent || src.intent_role),
      avatar: s(src.avatar)
    };
  }

  // 后端 education → 本地 education（保持原结构，matcher 用 school/major/degree）
  function mapEducation(arr) {
    if (!Array.isArray(arr)) return [];
    return arr
      .filter((e) => e && (e.school || e.major || e.degree))
      .map((e) => ({
        school: s(e.school),
        major: s(e.major),
        degree: s(e.degree),
        start_date: s(e.start_date),
        end_date: s(e.end_date),
        gpa: s(e.gpa),
        description: s(e.description)
      }));
  }

  // 后端 experience → 本地 experience
  // matcher 读 .position（最新一份公司职位），所以同时输出 position
  function mapExperience(arr) {
    if (!Array.isArray(arr)) return [];
    return arr
      .filter((e) => e && (e.company || e.title))
      .map((e) => ({
        company: s(e.company),
        title: s(e.title),
        position: s(e.title || e.position),  // 兼容 matcher 字段名
        start_date: s(e.start_date),
        end_date: s(e.end_date),
        description: s(e.description)
      }));
  }

  // 后端 projects → 本地 projects
  function mapProjects(arr) {
    if (!Array.isArray(arr)) return [];
    return arr
      .filter((p) => p && p.name)
      .map((p) => ({
        name: s(p.name),
        role: s(p.role),
        description: s(p.description),
        tech_stack: p.tech_stack || "",
        start_date: s(p.start_date),
        end_date: s(p.end_date)
      }));
  }

  // 后端 summary {self_eval, advantage, career_goal} → 本地 summary {strengths, interests}
  function mapSummary(sum) {
    const src = sum || {};
    return {
      strengths: s(src.advantage || src.self_eval || src.strengths),
      interests: s(src.career_goal || src.interests)
    };
  }

  // 后端 certifications → 本地 certificates
  function mapCertificates(arr) {
    if (!Array.isArray(arr)) return [];
    return arr
      .filter((c) => c && c.name)
      .map((c) => ({
        name: s(c.name),
        issuer: s(c.issuer),
        date: s(c.date),
        score: s(c.score)
      }));
  }

  // 后端 job_intent → 本地 job_intent
  function mapJobIntent(j) {
    const src = j || {};
    let salary = "";
    if (src.salary_min || src.salary_max) {
      const min = src.salary_min != null ? `${src.salary_min}` : "";
      const max = src.salary_max != null ? `${src.salary_max}` : "";
      salary = min && max ? `${min}-${max}k` : (min || max) + "k";
    }
    let role = [];
    if (typeof src.role === "string" && src.role.trim()) role = [src.role.trim()];
    if (Array.isArray(src.roles) && src.roles.length) role = role.concat(src.roles);
    const cities = Array.isArray(src.cities) ? src.cities.filter(Boolean) : [];
    return {
      target_positions: role,
      target_cities: cities,
      expected_salary: salary,
      work_type: s(src.job_type || src.work_type),
      availability: s(src.availability)
    };
  }

  // 完整映射：后端 profile → 本地 EMPTY_LOCAL_PROFILE 结构
  function mapBackendProfile(remote) {
    const empty = OC.schema.EMPTY_LOCAL_PROFILE();
    if (!remote || typeof remote !== "object") return empty;
    return {
      basic: Object.assign({}, empty.basic, mapBasic(remote.basic_info)),
      education: mapEducation(remote.education).length ? mapEducation(remote.education) : empty.education,
      experience: mapExperience(remote.experience).length ? mapExperience(remote.experience) : empty.experience,
      projects: mapProjects(remote.projects).length ? mapProjects(remote.projects) : empty.projects,
      skills: (() => {
        const ns = normalizeSkills(remote.skills);
        return ns.length ? ns : empty.skills;
      })(),
      summary: Object.assign({}, empty.summary, mapSummary(remote.summary)),
      certificates: mapCertificates(remote.certifications).length
        ? mapCertificates(remote.certifications) : empty.certificates,
      job_intent: Object.assign({}, empty.job_intent, mapJobIntent(remote.job_intent)),
      // 用户自定义字段：后端 extra_fields → 本地 custom_fields
      custom_fields: (remote.extra_fields && typeof remote.extra_fields === "object") ? remote.extra_fields : {}
    };
  }

  // 合并：远端非空值覆盖本地空值；本地已有值保留
  // 远端 == "空" 视为未设置；远端有值才覆盖
  function isEmpty(v) {
    if (v == null) return true;
    if (typeof v === "string") return v.trim() === "";
    if (Array.isArray(v)) return v.length === 0;
    if (typeof v === "object") {
      return Object.values(v).every((x) => isEmpty(x));
    }
    return false;
  }

  function mergeBasic(local, remote) {
    const out = Object.assign({}, local || {}, remote || {});
    // 双向择优
    Object.keys(out).forEach((k) => {
      if (!isEmpty(remote && remote[k])) {
        out[k] = remote[k];  // 远端有值
      } else if (!isEmpty(local && local[k])) {
        out[k] = local[k];   // 远端空，留本地
      } else {
        out[k] = local ? local[k] : (remote ? remote[k] : out[k]);
      }
    });
    return out;
  }

  function mergeArrayByNonEmpty(local, remote) {
    // 只要任一侧有数据，优先取远端（因为远端是用户在 Web 端填的"主"画像）
    if (!isEmpty(remote)) return remote;
    if (!isEmpty(local)) return local;
    return local || remote || [];
  }

  // 主合并：local + remote(local-shape) → 合并后 profile
  function mergeBackendIntoLocal(localProfile, remoteProfile) {
    const empty = OC.schema.EMPTY_LOCAL_PROFILE();
    const local = localProfile || empty;
    const remoteRaw = mapBackendProfile(remoteProfile);

    return {
      basic: mergeBasic(local.basic, remoteRaw.basic),
      education: mergeArrayByNonEmpty(local.education, remoteRaw.education),
      experience: mergeArrayByNonEmpty(local.experience, remoteRaw.experience),
      projects: mergeArrayByNonEmpty(local.projects, remoteRaw.projects),
      skills: mergeArrayByNonEmpty(local.skills, remoteRaw.skills),
      summary: mergeBasic(local.summary, remoteRaw.summary),
      certificates: mergeArrayByNonEmpty(local.certificates, remoteRaw.certificates),
      job_intent: mergeBasic(local.job_intent, remoteRaw.job_intent),
      // 自定义字段：远端（后端）非空则覆盖，否则保留本地
      custom_fields: !isEmpty(remoteRaw.custom_fields) ? remoteRaw.custom_fields
        : (!isEmpty(local.custom_fields) ? local.custom_fields : {})
    };
  }

  // 从后端拉一次并写回本地
  async function pullFromBackend(opts) {
    const silent = !!(opts && opts.silent);
    const cfg = await OC.config.get();
    // 内测 / 默认：只要后端可达就同步，不再强制要求"启用后端"开关
    // 健康检查（失败直接抛错，让调用方知道后端不可用，降级为本地画像）
    await OC.api.health();
    // 拉画像
    const remote = await OC.api.getProfile();
    const local = await OC.store.getProfile();
    const merged = mergeBackendIntoLocal(local, remote);
    await OC.store.saveProfile(merged);
    // 记同步时间
    await OC.store.set("stats", "last_profile_sync_at", Date.now());
    return {
      merged: merged,
      remote_had: !!remote && Object.keys(remote).length > 0,
      backend: cfg.backend || OC.config.DEFAULT_BACKEND
    };
  }

  // 格式化"上次同步时间"
  function formatLastSync(ts) {
    if (!ts) return "尚未同步";
    const d = new Date(ts);
    const now = Date.now();
    const diff = Math.floor((now - ts) / 1000);
    if (diff < 60) return `${diff} 秒前同步过`;
    if (diff < 3600) return `${Math.floor(diff / 60)} 分钟前同步过`;
    if (diff < 86400) return `${Math.floor(diff / 3600)} 小时前同步过`;
    return `${d.toLocaleDateString()} 同步过`;
  }

  // 统计合并后画像覆盖了多少字段（用于 UI 反馈）
  function countFilled(profile) {
    if (!profile) return 0;
    const b = profile.basic || {};
    const basicFilled = [
      "name", "gender", "age", "birth", "phone", "email", "location",
      "ethnicity", "political_status", "marital_status", "native_place",
      "wechat", "qq", "website", "github", "linkedin",
      "english_level", "driving_license", "job_status", "job_intent"
    ].filter((k) => !isEmpty(b[k])).length;
    const arr = ["education", "experience", "projects", "skills", "certificates"]
      .reduce((acc, k) => acc + (Array.isArray(profile[k]) && profile[k].length ? 1 : 0), 0);
    const customFilled = (profile.custom_fields && typeof profile.custom_fields === "object")
      ? Object.values(profile.custom_fields).filter((v) => v !== "" && v != null).length : 0;
    return basicFilled + arr + (customFilled > 0 ? 1 : 0);
  }

  OC.sync = {
    mapBackendProfile,
    mergeBackendIntoLocal,
    pullFromBackend,
    formatLastSync,
    countFilled
  };
})();
