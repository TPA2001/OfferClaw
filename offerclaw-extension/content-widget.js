// OfferClaw 扩展 - 页面悬浮窗
// 在页面右下角提供一个可拖拽、可收起的悬浮按钮/面板：
//   - 一键「扫描并智能填写」
//   - 查看填写结果统计
//   - 补充画像中缺失的字段（填写后保存为自定义字段，再次填写自动命中）
// 复用 content.js 暴露的 OC.__fill（同一套扫描填写逻辑），无后端依赖。
(function () {
  if (window.__offerclaw_widget_loaded) return;
  window.__offerclaw_widget_loaded = true;

  const OC = globalThis.OC;
  if (!OC) return; // 基础命名空间都未就绪（schema.js 未加载）才不渲染

  const NS = "ocw"; // 命名空间前缀，避免与页面样式冲突

  // ---------- 创建 DOM ----------
  const fab = document.createElement("button");
  fab.className = NS + "-fab";
  fab.setAttribute("title", "OfferClaw填表助手");
  fab.innerHTML =
    '<svg viewBox="0 0 24 24" width="22" height="22" fill="none" stroke="currentColor" ' +
    'stroke-width="2" stroke-linecap="round" stroke-linejoin="round">' +
    '<path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/></svg>';

  const panel = document.createElement("div");
  panel.className = NS + "-panel";
  panel.style.display = "none";
  panel.innerHTML =
    '<div class="' + NS + '-head">' +
    '  <span class="' + NS + '-title">OfferClaw</span>' +
    '  <button class="' + NS + '-min" title="收起">—</button>' +
    '</div>' +
    '<div class="' + NS + '-body">' +
    '  <button class="' + NS + '-btn primary" id="ocw-fill">扫描并智能填写</button>' +
    '  <button class="' + NS + '-btn ghost" id="ocw-clear">清除高亮</button>' +
    '  <div class="' + NS + '-result" id="ocw-result"></div>' +
    '</div>' +
    '<div class="' + NS + '-extra" id="ocw-extra" style="display:none">' +
    '  <div class="' + NS + '-extra-title">补充画像字段</div>' +
    '  <div class="' + NS + '-extra-hint">画像中缺失的字段，填值后保存，再次填写自动填入。</div>' +
    '  <div class="' + NS + '-extra-list" id="ocw-extra-list"></div>' +
    '</div>';

  document.documentElement.appendChild(fab);
  document.documentElement.appendChild(panel);

  const $ = (id) => panel.querySelector("#" + id);
  const resultEl = $("ocw-result");
  const extraEl = $("ocw-extra");
  const extraList = $("ocw-extra-list");

  // ---------- 拖拽（FAB） ----------
  let drag = null;
  fab.addEventListener("mousedown", (e) => {
    if (e.button !== 0) return;
    const rect = fab.getBoundingClientRect();
    drag = { dx: e.clientX - rect.left, dy: e.clientY - rect.top, moved: false };
  });
  window.addEventListener("mousemove", (e) => {
    if (!drag) return;
    drag.moved = true;
    const x = Math.min(window.innerWidth - 60, Math.max(8, e.clientX - drag.dx));
    const y = Math.min(window.innerHeight - 70, Math.max(8, e.clientY - drag.dy));
    fab.style.left = x + "px";
    fab.style.top = y + "px";
    fab.style.right = "auto";
    fab.style.bottom = "auto";
  });
  window.addEventListener("mouseup", () => { drag = null; });

  // 点击 FAB 开关面板（若拖拽过则不触发开关）
  fab.addEventListener("click", () => {
    if (drag && drag.moved) { drag = null; return; }
    togglePanel();
  });
  panel.querySelector("." + NS + "-min").addEventListener("click", () => hidePanel());

  function togglePanel() {
    if (panel.style.display === "none") showPanel(); else hidePanel();
  }
  function showPanel() {
    panel.style.display = "block";
    panel.classList.add("open");
    loadStatsIntoResult();
  }
  function hidePanel() {
    panel.style.display = "none";
    panel.classList.remove("open");
  }

  // ---------- 打开时载入基础统计 ----------
  async function loadStatsIntoResult() {
    try {
      const stats = (await OC.store.get("stats")) || {};
      resultEl.textContent =
        "上次：扫描 " + ((stats && stats.scan_count) || 0) + " 次 · 填写 " +
        ((stats && stats.fill_count) || 0) + " 次";
      resultEl.classList.remove("done", "err");
    } catch (e) {}
  }

  // ---------- 填写 ----------
  // 依赖 content.js 暴露的 OC.__fill.scanAndFill。
  // 若其缺失（多为扩展重载后未刷新页面导致旧 content 脚本残留），明确提示刷新一次页面，
  // 新版 content.js 注入后即可用。
  function runFill() {
    if (OC.__fill && OC.__fill.scanAndFill) {
      return OC.__fill.scanAndFill();
    }
    return Promise.resolve({
      ok: false,
      error: "内容脚本未就绪，请先刷新一次当前页面"
    });
  }

  $("ocw-fill").addEventListener("click", async () => {
    const btn = $("ocw-fill");
    resultEl.textContent = "扫描中…";
    resultEl.classList.remove("done", "err");
    btn.disabled = true;
    try {
      const resp = await runFill();
      if (!resp.ok) {
        resultEl.textContent = "失败：" + (resp.error || "未知");
        resultEl.classList.add("err");
        return;
      }
      const rep = resp.report || {};
      let t =
        "字段 " + resp.fields + " · 映射 " + resp.mappings +
        (resp.cached ? "（缓存）" : "") + "\n" +
        "成功 " + rep.filled + " · 跳过 " + rep.skipped + " · 待确认 " + rep.warn;
      if (resp.profile_filled === 0) {
        t += "\n⚠ 画像为空，请先在扩展设置/Web端填写";
      }
      resultEl.textContent = t;
      resultEl.classList.add("done");
      renderUnmatched(resp.unmatched || []);
      OC.store.bumpStat("widget_fill");
    } catch (e) {
      resultEl.textContent = "错误：" + e.message;
      resultEl.classList.add("err");
    } finally {
      btn.disabled = false;
    }
  });

  $("ocw-clear").addEventListener("click", () => {
    try { OC.__fill.clearHighlight(); } catch (e) {}
    resultEl.textContent = "已清除高亮";
    resultEl.classList.add("done");
  });

  // ---------- 补充画像缺失字段 ----------
  function renderUnmatched(unmatched) {
    if (!unmatched || !unmatched.length) {
      extraEl.style.display = "none";
      extraList.innerHTML = "";
      return;
    }
    extraEl.style.display = "";
    extraList.innerHTML = "";
    const seen = new Set();
    unmatched.forEach((u) => {
      const key = (u.key || "").trim();
      if (!key || seen.has(key)) return;
      seen.add(key);
      const item = document.createElement("div");
      item.className = NS + "-mrow";
      const typeHint =
        u.type === "custom_select" ? " [下拉框]" :
        u.type === "date_picker" ? " [日期]" :
        u.type === "radio" ? " [单选]" : "";
      const labelText = (u.label || u.name || u.placeholder || u.key);

      const lab = document.createElement("div");
      lab.className = NS + "-mlabel";
      lab.textContent = labelText + typeHint;

      const input = document.createElement("input");
      input.className = NS + "-minput";
      input.value = u.existing || "";
      input.placeholder = "填写该字段的值并保存";

      const save = document.createElement("button");
      save.className = NS + "-msave";
      save.textContent = "保存";
      save.addEventListener("click", async () => {
        const val = input.value.trim();
        if (!val) return;
        try {
          const profile = await OC.store.getProfile();
          if (!profile.custom_fields || typeof profile.custom_fields !== "object") {
            profile.custom_fields = {};
          }
          profile.custom_fields[key] = val;
          await OC.store.saveProfile(profile);
          // 使缓存失效，下次填写命中自定义字段
          await OC.store.set("stats", "last_profile_sync_at", Date.now());
          const ok = document.createElement("span");
          ok.className = NS + "-mok";
          ok.textContent = "已保存";
          lab.appendChild(ok);
          input.disabled = true;
          save.disabled = true;
          save.textContent = "✓";
        } catch (e2) {
          lab.textContent = "保存失败：" + e2.message;
        }
      });

      item.appendChild(lab);
      item.appendChild(input);
      item.appendChild(save);
      extraList.appendChild(item);
    });
  }

  // ---------- 样式（动态注入，避免改 manifest CSS 列表） ----------
  const style = document.createElement("style");
  style.textContent =
    "." + NS + "-fab{" +
    "position:fixed;right:22px;bottom:22px;z-index:2147483000;width:52px;height:52px;" +
    "border-radius:50%;border:none;cursor:pointer;display:flex;align-items:center;justify-content:center;" +
    "background:linear-gradient(135deg,#4f46e5,#7c3aed);color:#fff;box-shadow:0 6px 20px rgba(79,70,229,.45);" +
    "transition:transform .15s ease;} " +
    "." + NS + "-fab:hover{transform:scale(1.08)} " +
    "." + NS + "-panel{" +
    "position:fixed;right:22px;bottom:84px;z-index:2147482999;width:320px;max-height:70vh;" +
    "background:#fff;border-radius:12px;box-shadow:0 12px 40px rgba(0,0,0,.25);" +
    "font-family:-apple-system,'Segoe UI','Microsoft YaHei',sans-serif;font-size:13px;color:#1f2937;" +
    "overflow:hidden;display:flex;flex-direction:column;} " +
    "." + NS + "-head{display:flex;align-items:center;justify-content:space-between;padding:10px 12px;" +
    "background:linear-gradient(135deg,#4f46e5,#7c3aed);color:#fff;}" +
    "." + NS + "-title{font-weight:700}" +
    "." + NS + "-min{background:transparent;border:none;color:#fff;font-size:14px;cursor:pointer;}" +
    "." + NS + "-body{padding:10px 12px;display:flex;flex-direction:column;gap:8px;}" +
    "." + NS + "-btn{padding:8px 10px;border:none;border-radius:6px;cursor:pointer;font-size:13px;font-weight:600;}" +
    "." + NS + "-btn.primary{background:#4f46e5;color:#fff;}" +
    "." + NS + "-btn.ghost{background:#f3f4f6;color:#374151;}" +
    "." + NS + "-btn.primary:disabled{opacity:.5;cursor:not-allowed;}" +
    "." + NS + "-result{font-size:12px;white-space:pre-wrap;color:#6b7280;}" +
    "." + NS + "-result.done{color:#16a34a;}" +
    "." + NS + "-result.err{color:#dc2626;}" +
    "." + NS + "-extra{border-top:1px solid #e5e7eb;padding:10px 12px;overflow-y:auto;}" +
    "." + NS + "-extra-title{font-weight:600;margin-bottom:4px;}" +
    "." + NS + "-extra-hint{font-size:11px;color:#9ca3af;margin-bottom:8px;}" +
    "." + NS + "-extra-list{display:flex;flex-direction:column;gap:6px;max-height:200px;overflow-y:auto;}" +
    "." + NS + "-mrow{display:flex;align-items:center;gap:6px;border:1px solid #e5e7eb;border-radius:6px;padding:6px;}" +
    "." + NS + "-mlabel{flex:0 0 auto;max-width:110px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;font-size:12px;}" +
    "." + NS + "-minput{flex:1;min-width:0;border:1px solid #d1d5db;border-radius:4px;padding:5px 6px;font-size:12px;}" +
    "." + NS + "-msave{flex:0 0 auto;border:none;background:#4f46e5;color:#fff;border-radius:4px;padding:5px 8px;cursor:pointer;font-size:12px;}" +
    "." + NS + "-mok{color:#16a34a;font-size:11px;margin-left:6px;}" +
    "." + NS + "-mrow input:disabled{background:#f3f4f6;}" +
    "." + NS + "-mrow button:disabled{opacity:.6;cursor:default;}";
  document.documentElement.appendChild(style);
})();