// OfferClaw 填表助手 - 内容脚本（注入真实页面，扫描+填写）
// 本地数据库优先：扫描字段 → 本地画像本地匹配 → 在真实 DOM 上填写
// 不依赖后端，所有匹配在浏览器本地完成，画像/敏感数据不出本地存储
(function () {
  if (window.__offerclaw_content_loaded) return;
  window.__offerclaw_content_loaded = true;

  const OC = globalThis.OC;

  // 监听来自 popup 的指令
  chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
    if (!msg || !msg.type) return;

    if (msg.type === "oc_scan_only") {
      try {
        const fields = OC.scanner.withContext(OC.scanner.scan());
        OC.store.bumpStat("scan_count");
        sendResponse({ ok: true, fields, count: fields.length });
      } catch (e) {
        sendResponse({ ok: false, error: e.message });
      }
      return true;
    }

    if (msg.type === "oc_scan_and_fill") {
      handleScanAndFill()
        .then((r) => sendResponse(r))
        .catch((e) => sendResponse({ ok: false, error: e.message }));
      return true;
    }

    if (msg.type === "oc_clear_highlight") {
      OC.filler.clearHighlight();
      sendResponse({ ok: true });
      return true;
    }
  });

  async function handleScanAndFill() {
    OC.filler.clearHighlight();

    // 1. 扫描当前页面真实表单
    const fields = OC.scanner.withContext(OC.scanner.scan());
    if (!fields.length) {
      return { ok: false, error: "页面未发现可填写表单字段" };
    }

    // 1.5 确保本地画像已就绪（双保险：popup 可能尚未同步，此处经 background 代理兜底从后端拉）
    //     注意：content 脚本直接 fetch 后端会遭 CORS（Origin 是页面域名），必须由
    //     service worker 代理——background 的 Origin 是 chrome-extension://，命中后端 CORS 正则。
    let profile = await OC.store.getProfile();
    let contentSynced = false;
    if (OC.sync) {
      const pf = OC.sync.countFilled(profile);
      if (pf === 0) {
        try {
          const resp = await new Promise((resolve) =>
            chrome.runtime.sendMessage({ type: "oc_sync_profile" }, resolve)
          );
          if (resp && resp.ok && resp.remote) {
            const local = await OC.store.getProfile();
            profile = OC.sync.mergeBackendIntoLocal(local, resp.remote);
            await OC.store.saveProfile(profile);
            contentSynced = true;
          }
        } catch (e) {
          console.warn("[OfferClaw] content 兜底同步失败（用本地画像）:", e.message);
        }
      }
    }
    const profileFilled = OC.sync ? OC.sync.countFilled(profile) : (profile && profile.basic ? Object.values(profile.basic).filter(Boolean).length : 0);

    // 2. 查映射缓存
    //    签名 = 页面结构 + 画像指纹 + 同步时间：
    //    - 页面结构：字段 type/label/name（不含动态 idx，避免同结构页面误命中）
    //    - 画像指纹：画像关键字段变化即失效重匹配
    //    - 同步时间：同画像下避免无限复用
    const pf = profileFingerprint(profile);
    const stats = (await OC.store.get("stats")) || {};
    const syncAt = stats.last_profile_sync_at || 0;
    const sig = OC.scanner.pageSignature(fields) + "#" + pf + "#" + syncAt;
    const cache = (await OC.store.get("mapping_cache")) || {};
    const cached = cache[sig];
    const CACHE_TTL = 24 * 3600 * 1000;

    let mappings;
    let usedCache = false;
    if (cached && Date.now() - cached.ts < CACHE_TTL) {
      // 防御：若本地画像已同步（非空）但缓存全是 skip，说明是旧缓存 → 失效重匹配
      const cachedAllSkip = cached.mappings.every((m) => m.action !== "fill");
      if (!cachedAllSkip) {
        mappings = cached.mappings;
        usedCache = true;
      }
    }
    if (!mappings) {
      // 3. 本地匹配（不调后端）
      const sens = await OC.privacy.getSensitive();
      mappings = OC.matcher.match(fields, profile, sens);
      cache[sig] = { mappings, ts: Date.now() };
      await OC.store.set("mapping_cache", sig, cache[sig]);
    }

    // 4. 敏感字段：从本地 storage 读值填入（后端不接触这些值）
    for (const m of mappings) {
      if (m.source === "local_sensitive" && (m.action === "manual" || !m.value)) {
        const fid = m.field_id || m.id;
        const field = fields.find((f) => f.id === fid) || fields.find((f) => f.name === fid);
        if (field) {
          const localVal = await OC.privacy.getLocalValue(
            `${field.label} ${field.name} ${field.id}`
          );
          if (localVal) {
            m.value = localVal;
            m.action = "fill";
          }
        }
      }
    }

    // 5. 执行填写（不自动提交，由用户确认）
    const report = await OC.filler.fillAll(fields, mappings);
    await OC.store.bumpStat("fill_count");

    // 防御：命中旧缓存却一个都没填上（多为 SPA DOM 变化导致 selector 失效）
    // → 丢弃该缓存，下次重新匹配，避免用户反复看到 "0 填写"
    if (usedCache && report.filled === 0 && cached) {
      try {
        delete cache[sig];
        await OC.store.set("mapping_cache", cache);
        console.warn("[OfferClaw] 命中缓存但 0 填写，已丢弃该缓存，下次将重新匹配");
      } catch (e) {
        console.warn("[OfferClaw] 缓存清理失败（可忽略）:", e.message);
      }
    }

    return {
      ok: true,
      report,
      fields: fields.length,
      mappings: mappings.length,
      cached: usedCache,
      profile_filled: profileFilled,
      content_synced: contentSynced,
      sample_skips: report.details
        .filter((d) => d.status !== "ok")
        .slice(0, 12)
        .map((d) => {
          const f = fields.find((x) => (x.id || "") === d.field_id) ||
                    fields.find((x) => (x.name || "") === d.field_id);
          return `${f ? (f.label || f.name || f.id) : d.field_id} → ${d.reason}`;
        })
    };
  }

  // 画像指纹：仅基于关键字段，画像变化即变化 → 驱动缓存失效
  function profileFingerprint(p) {
    const basic = (p && p.basic) || {};
    const edu = (p && Array.isArray(p.education) && p.education[0]) || {};
    const exp = (p && Array.isArray(p.experience) && p.experience[0]) || {};
    const s = JSON.stringify({
      name: basic.name || "",
      phone: basic.phone || "",
      email: basic.email || "",
      school: edu.school || "",
      company: exp.company || "",
      lenEdu: (p && p.education || []).length,
      lenExp: (p && p.experience || []).length
    });
    let h = 0;
    for (let i = 0; i < s.length; i++) h = ((h << 5) - h + s.charCodeAt(i)) | 0;
    return "pf" + (Math.abs(h) % 100000).toString(36);
  }
})();
