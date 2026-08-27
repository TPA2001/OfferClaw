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
      handleScanAndFill(msg)
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

  async function handleScanAndFill(msg) {
    OC.filler.clearHighlight();
    const mode = msg && msg.mode ? msg.mode : "all";

    // 1. 扫描当前页面真实表单
    const allFields = OC.scanner.withContext(OC.scanner.scan());
    if (!allFields.length) {
      return { ok: false, error: "页面未发现可填写表单字段" };
    }
    let fields = allFields;

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

    // 4.5 站点模板覆盖：命中站点模板时，用模板字段映射优先/补充匹配
    let templateUsed = "";
    try {
      if (window.templateManager && window.siteMatcher) {
        if (!window.__ocTemplateReady) {
          await window.templateManager.init();
          window.__ocTemplateReady = true;
        }
        const tpl = window.siteMatcher.matchTemplate(location.href);
        if (tpl) templateUsed = tpl.siteId || "";
        if (tpl && Array.isArray(tpl.fields) && tpl.fields.length) {
          const overrides = {};
          for (const tf of tpl.fields) {
            const val = OC.matcher.getProfileValue(profile, tf.profile);
            if (!val) continue;
            const tokens = [...(Array.isArray(tf.match) ? tf.match : []), tf.label].filter(Boolean);
            for (const f of fields) {
              const text = `${f.label || ""} ${f.name || ""} ${f.placeholder || ""} ${(f.nearbyLabels || []).join(" ")}`.toLowerCase();
              if (tokens.some((t) => text.includes(String(t).toLowerCase()))) {
                overrides[f.id] = {
                  field_id: f.id, field_name: f.name, selector: f.selector,
                  type: f.type, inputType: f.inputType, readOnly: f.readOnly,
                  placeholder: f.placeholder, nearbyLabels: f.nearbyLabels, options: f.options,
                  value: String(val), action: "fill", source: "template",
                  reason: "站点模板命中"
                };
              }
            }
          }
          if (Object.keys(overrides).length) {
            const existing = new Set();
            mappings = mappings.map((m) => {
              const k = m.field_id || m.id;
              existing.add(k);
              return overrides[k] || m;
            });
            for (const k in overrides) {
              if (!existing.has(k)) {
                const f = fields.find((x) => x.id === k);
                if (f) mappings.push(overrides[k]);
              }
            }
          }
        }
      }
    } catch (e) {
      console.warn("[OfferClaw] 模板加载失败（忽略）:", e.message);
    }

    // 4.6 填写模式过滤：整页 / 当前区块 / 选中单字段
    if (mode === "section") {
      const active = document.activeElement;
      let sec = "";
      if (active && typeof active.closest === "function") {
        const cont = active.closest("fieldset, section, [class*=section], [class*=block], form");
        if (cont) {
          const h = cont.querySelector("h1, h2, h3, h4, h5, legend, .title, .section-title");
          if (h) sec = (h.textContent || "").trim();
        }
      }
      if (!sec) {
        return { ok: false, error: "未定位到当前区块：请先点击表单内任一字段，再点『填写本区块』" };
      }
      fields = fields.filter((f) => f.section === sec);
      const allowed = new Set(fields.map((f) => f.id).concat(fields.map((f) => f.name).filter(Boolean)));
      mappings = mappings.filter((m) => allowed.has(m.field_id || m.id));
    } else if (mode === "selection") {
      const target = fieldUnderSelection(allFields);
      if (!target) {
        return { ok: false, error: "未选中表单字段：请先在页面上拖动选中目标字段的文字或输入框，再点『填写选中字段』" };
      }
      const allowed = new Set([target.id, target.name].filter(Boolean));
      fields = [target];
      mappings = mappings.filter((m) => allowed.has(m.field_id || m.id));
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
      template: templateUsed,
      sample_skips: report.details
        .filter((d) => d.status !== "ok")
        .slice(0, 16)
        .map((d) => {
          const f = fields.find((x) => (x.id || "") === d.field_id) ||
                    fields.find((x) => (x.name || "") === d.field_id);
          const name = d.field || (f ? (f.label || f.name || f.id) : d.field_id);
          const v = d.value ? `想填「${d.value}」` : "";
          return `${name}(${d.type || "?"}) ${v} → ${d.reason}`;
        })
    };
  }

  // 选中模式：返回当前页面文本选区命中的表单字段
  function fieldUnderSelection(fieldsAll) {
    const sel = window.getSelection();
    if (!sel || sel.rangeCount === 0) return null;
    const range = sel.getRangeAt(0);
    let r = null;
    try { r = range.getBoundingClientRect(); } catch (e) { r = null; }
    if (!r || (r.width === 0 && r.height === 0)) return null;
    return (
      fieldsAll.find((f) => {
        if (!f.el) return false;
        const fr = f.el.getBoundingClientRect();
        return !(fr.right < r.left || fr.left > r.right || fr.bottom < r.top || fr.top > r.bottom);
      }) || null
    );
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
