// OfferClaw 填表助手 - popup 交互逻辑（本地数据库优先模式）
// 所有数据存 chrome.storage.local，无需后端即可工作
// 后端可选（设置面板"启用后端"开关），仅用于健康检查显示
(function () {
  const OC = globalThis.OC;
  const $ = (id) => document.getElementById(id);

  // ============ Tab 切换 ============
  document.querySelectorAll(".oc-tab").forEach((btn) => {
    btn.addEventListener("click", () => {
      document.querySelectorAll(".oc-tab").forEach((b) => b.classList.remove("active"));
      document.querySelectorAll(".oc-panel").forEach((p) => p.classList.remove("active"));
      btn.classList.add("active");
      $("panel-" + btn.dataset.tab).classList.add("active");
      if (btn.dataset.tab === "apps") loadApplications();
      if (btn.dataset.tab === "profile") loadProfile();
      if (btn.dataset.tab === "fill") loadExtStats();
    });
  });

  // ============ 状态枚举 ============
  function fillStatusOptions(sel, withAll) {
    sel.innerHTML = "";
    if (withAll) {
      const o = document.createElement("option");
      o.value = ""; o.textContent = "全部状态";
      sel.appendChild(o);
    }
    Object.entries(OC.schema.APPLICATION_STATUSES).forEach(([k, v]) => {
      const o = document.createElement("option");
      o.value = k; o.textContent = v;
      sel.appendChild(o);
    });
  }
  function fillPriorityOptions(sel) {
    sel.innerHTML = "";
    Object.entries(OC.schema.APPLICATION_PRIORITIES).forEach(([k, v]) => {
      const o = document.createElement("option");
      o.value = k; o.textContent = v;
      sel.appendChild(o);
    });
  }
  fillStatusOptions($("appStatusFilter"), true);
  fillStatusOptions($("newStatus"), false);
  fillPriorityOptions($("newPriority"));

  // ============ 后端连接状态 ============
  // forceCheck=true 时无视 use_backend 开关，强制 ping 后端
  async function checkBackend(forceCheck) {
    const st = $("backendStatus");
    const cfg = await OC.config.get();
    // 内测阶段后端即本地，始终检测真实连接状态（不再因 use_backend=false 跳过）
    st.textContent = "检测中…";
    st.className = "oc-status";
    try {
      const data = await OC.api.health();
      st.textContent = "后端已连接";
      st.className = "oc-status ok";
      return data;
    } catch (e) {
      st.textContent = "后端未连接（请启动：python run.py）";
      st.className = "oc-status warn";
      throw e;
    }
  }

  // ============ 填写面板 ============
  async function loadExtStats() {
    const s = await OC.store.get("stats");
    $("extStats").innerHTML =
      `扫描次数：<b>${(s && s.scan_count) || 0}</b>　填写次数：<b>${(s && s.fill_count) || 0}</b>`;
  }

  async function currentTab() {
    const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
    return tab;
  }

  $("btnFill").addEventListener("click", async () => {
    const r = $("fillResult");
    r.textContent = "同步画像中…";
    try {
      const tab = await currentTab();
      if (!tab || !tab.id) {
        r.textContent = "未找到当前标签页";
        return;
      }
      // 填写前先确保本地画像已从后端同步（内测：后端即本地，保证字段有值可填）
      const sync = await ensureProfileSynced();
      if (!sync.ok) {
        r.textContent =
          "⚠️ 后端画像同步失败：\n" + sync.error +
          "\n\n请确认后端已在运行：浏览器打开 http://localhost:8000 能访问。\n" +
          "（启动命令：cd backend && python run.py）\n\n本地画像为空，无法填写。";
        return;
      }
      if (sync.filled === 0) {
        // 后端在跑但画像空：仍尝试填写（部分字段可填），但明确提示
        r.textContent =
          "⚠️ 后端已连接，但你的画像为空（Web 端 /profile 还没填写？）。\n" +
          "请先到 http://localhost:8000/profile 填写基本信息，再回来点填写。";
      } else {
        r.textContent = "扫描中…（已同步画像 " + sync.filled + " 字段）";
      }
      chrome.tabs.sendMessage(
        tab.id,
        { type: "oc_scan_and_fill" },
        (resp) => {
          if (chrome.runtime.lastError) {
            r.textContent = "无法与页面通信（可能是 chrome:// 或刷新页面后未注入）\n" + chrome.runtime.lastError.message;
            return;
          }
          if (!resp || !resp.ok) {
            r.textContent = "失败：" + (resp ? resp.error : "未知");
            return;
          }
          const rep = resp.report || {};
          let txt =
            `✅ 完成（弹窗同步 ${sync.filled} 字段 / 页面读到 ${resp.profile_filled || 0} 字段）\n` +
            `字段总数：${resp.fields}\n映射数：${resp.mappings}${resp.cached ? "（命中缓存）" : ""}\n` +
            `成功填写：${rep.filled}　跳过：${rep.skipped}　待确认：${rep.warn}`;
          if (resp.content_synced) txt += "\n（内容脚本已自动从后端同步画像）";
          if (resp.sample_skips && resp.sample_skips.length) {
            txt += "\n\n跳过样本：\n" + resp.sample_skips.join("\n");
          }
          r.textContent = txt;
          loadExtStats();
        }
      );
    } catch (e) {
      r.textContent = "错误：" + e.message;
    }
  });

  $("btnClear").addEventListener("click", async () => {
    const tab = await currentTab();
    if (tab && tab.id) chrome.tabs.sendMessage(tab.id, { type: "oc_clear_highlight" }, () => {});
  });

  // ============ 投递记录面板（本地数据库） ============
  $("appStatusFilter").addEventListener("change", loadApplications);
  $("btnRefreshApps").addEventListener("click", loadApplications);

  async function loadApplications() {
    const box = $("appsList");
    box.innerHTML = "加载中…";
    try {
      const status = $("appStatusFilter").value;
      const list = await OC.store.listApplications(status);
      if (!list.length) {
        box.innerHTML = '<div class="oc-app-item">暂无投递记录</div>';
        return;
      }
      box.innerHTML = "";
      list.slice(0, 50).forEach((a) => {
        const div = document.createElement("div");
        div.className = "oc-app-item";
        const dateStr = a.applied_at ? a.applied_at.slice(0, 10) : "";
        const statusLabel = OC.schema.APPLICATION_STATUSES[a.status] || a.status;
        const priLabel = OC.schema.APPLICATION_PRIORITIES[a.priority] || a.priority;
        div.innerHTML =
          `<div class="app-title">${escapeHtml(a.company)} · ${escapeHtml(a.position)}</div>` +
          `<div class="app-meta">${escapeHtml(statusLabel)} · ${escapeHtml(priLabel)} · ${dateStr}</div>` +
          (a.notes ? `<div class="app-meta">备注：${escapeHtml(a.notes)}</div>` : "");

        const ctrl = document.createElement("div");
        ctrl.className = "oc-row";
        ctrl.style.marginTop = "6px";

        const sel = document.createElement("select");
        sel.className = "oc-input";
        Object.entries(OC.schema.APPLICATION_STATUSES).forEach(([k, v]) => {
          const o = document.createElement("option");
          o.value = k; o.textContent = v;
          if (a.status === k) o.selected = true;
          sel.appendChild(o);
        });
        sel.addEventListener("change", async () => {
          try {
            await OC.store.updateApplicationStatus(a.id, sel.value);
            loadApplications();
          } catch (e) {
            alert("更新失败：" + e.message);
          }
        });
        ctrl.appendChild(sel);

        const delBtn = document.createElement("button");
        delBtn.className = "oc-btn danger";
        delBtn.textContent = "删除";
        delBtn.style.flex = "0 0 auto";
        delBtn.addEventListener("click", async () => {
          if (!confirm(`确定删除「${a.company} · ${a.position}」？`)) return;
          await OC.store.deleteApplication(a.id);
          loadApplications();
        });
        ctrl.appendChild(delBtn);

        div.appendChild(ctrl);
        box.appendChild(div);
      });
    } catch (e) {
      box.innerHTML = '<div class="oc-app-item">加载失败：' + escapeHtml(e.message) + "</div>";
    }
  }

  $("btnCreateApp").addEventListener("click", async () => {
    const company = $("newCompany").value.trim();
    const position = $("newPosition").value.trim();
    if (!company || !position) {
      alert("公司和职位必填");
      return;
    }
    try {
      let jobUrl = $("newJobUrl").value.trim();
      if (!jobUrl) {
        try {
          const tab = await currentTab();
          if (tab && tab.url) jobUrl = tab.url;
        } catch (e) {}
      }
      await OC.store.createApplication({
        company,
        position,
        job_url: jobUrl || null,
        source: "extension",
        status: $("newStatus").value,
        priority: $("newPriority").value,
        notes: $("newNotes").value.trim() || null
      });
      $("newCompany").value = "";
      $("newPosition").value = "";
      $("newJobUrl").value = "";
      $("newNotes").value = "";
      loadApplications();
      alert("创建成功（已存本地数据库）");
    } catch (e) {
      alert("创建失败：" + e.message);
    }
  });

  // ============ 画像面板（本地数据库） ============
  $("btnRefreshProfile").addEventListener("click", loadProfile);
  $("btnSaveBasic").addEventListener("click", saveBasicInfo);
  $("btnSaveJson").addEventListener("click", saveJsonExtra);
  $("btnExportProfile").addEventListener("click", exportProfile);
  $("btnSyncFromBackend").addEventListener("click", syncFromBackendManual);

  async function loadProfile() {
    const comp = $("profileCompletion");
    const profile = await OC.store.getProfile();
    const sens = await OC.privacy.getSensitive();

    // 计算敏感数据已填项数（用于完成度）
    let sensFilled = 0;
    Object.values(sens).forEach((v) => { if (v) sensFilled++; });
    const profileWithSens = Object.assign({}, profile, { __sens_filled: sensFilled });
    const pct = OC.matcher.computeCompletion(profileWithSens);
    comp.innerHTML = `总完成度：<b>${pct}%</b>
      <div class="oc-pb"><span style="width:${pct}%"></span></div>`;

    // 显示数据来源 / 最近同步时间
    const stats = await OC.store.get("stats") || {};
    const lastSync = stats.last_profile_sync_at || 0;
    const cfg = await OC.config.get();
    const src = $("profileSource");
    if (lastSync) {
      src.innerHTML = `数据来源：<b>本地 + 后端</b>　${OC.sync.formatLastSync(lastSync)}`;
    } else if (cfg.use_backend) {
      src.innerHTML = `数据来源：<b>本地</b>　后端已开启，<a href="#" id="lnkSyncNow">立即同步</a>`;
      const lnk = $("lnkSyncNow");
      if (lnk) lnk.addEventListener("click", (e) => { e.preventDefault(); syncFromBackendManual(); });
    } else {
      src.innerHTML = `数据来源：<b>本地</b>　后端未开启（设置 → 启用后端 → 一键同步）`;
    }

    // 填充基本信息表单
    const b = (profile && profile.basic) || {};
    $("pf-name").value = b.name || "";
    $("pf-gender").value = b.gender || "";
    $("pf-age").value = b.age || "";
    $("pf-birth").value = b.birth || "";
    $("pf-phone").value = b.phone || "";
    $("pf-email").value = b.email || "";
    $("pf-location").value = b.location || "";
    $("pf-job_intent").value = b.job_intent || "";
    $("pf-ethnicity").value = b.ethnicity || "";
    $("pf-political_status").value = b.political_status || "";
    $("pf-marital_status").value = b.marital_status || "";
    $("pf-native_place").value = b.native_place || "";
    $("pf-wechat").value = b.wechat || "";
    $("pf-qq").value = b.qq || "";
    $("pf-website").value = b.website || "";
    $("pf-github").value = b.github || "";
    $("pf-linkedin").value = b.linkedin || "";
    $("pf-english_level").value = b.english_level || "";
    $("pf-driving_license").value = b.driving_license || "";
    $("pf-job_status").value = b.job_status || "";

    // 填充 JSON 高级编辑
    const extra = {
      education: profile.education || [],
      experience: profile.experience || [],
      projects: profile.projects || [],
      skills: profile.skills || [],
      summary: profile.summary || {},
      certificates: profile.certificates || [],
      job_intent: profile.job_intent || {}
    };
    $("pfJsonExtra").value = JSON.stringify(extra, null, 2);
  }

  async function saveBasicInfo() {
    const patch = {
      name: $("pf-name").value.trim(),
      gender: $("pf-gender").value,
      age: $("pf-age").value.trim(),
      birth: $("pf-birth").value.trim(),
      phone: $("pf-phone").value.trim(),
      email: $("pf-email").value.trim(),
      location: $("pf-location").value.trim(),
      ethnicity: $("pf-ethnicity").value.trim(),
      political_status: $("pf-political_status").value.trim(),
      marital_status: $("pf-marital_status").value.trim(),
      native_place: $("pf-native_place").value.trim(),
      wechat: $("pf-wechat").value.trim(),
      qq: $("pf-qq").value.trim(),
      website: $("pf-website").value.trim(),
      github: $("pf-github").value.trim(),
      linkedin: $("pf-linkedin").value.trim(),
      english_level: $("pf-english_level").value.trim(),
      driving_license: $("pf-driving_license").value.trim(),
      job_status: $("pf-job_status").value.trim(),
      job_intent: $("pf-job_intent").value.trim()
    };
    try {
      await OC.store.patchBasicInfo(patch);
      alert("基本信息已保存到本地数据库");
      loadProfile();
    } catch (e) {
      alert("保存失败：" + e.message);
    }
  }

  async function saveJsonExtra() {
    const txt = $("pfJsonExtra").value.trim();
    if (!txt) {
      alert("JSON 不能为空");
      return;
    }
    let parsed;
    try {
      parsed = JSON.parse(txt);
    } catch (e) {
      alert("JSON 解析失败：" + e.message);
      return;
    }
    try {
      const profile = await OC.store.getProfile();
      // 只允许这些字段被覆盖，保留 basic 不被改坏
      ["education", "experience", "projects", "skills", "summary", "certificates", "job_intent"].forEach((k) => {
        if (parsed[k] !== undefined) profile[k] = parsed[k];
      });
      await OC.store.saveProfile(profile);
      alert("JSON 已保存到本地数据库");
      loadProfile();
    } catch (e) {
      alert("保存失败：" + e.message);
    }
  }

  async function exportProfile() {
    const profile = await OC.store.getProfile();
    const blob = new Blob([JSON.stringify(profile, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `offerclaw_profile_${Date.now()}.json`;
    a.click();
    URL.revokeObjectURL(url);
  }

  // ============ 后端画像同步 ============
  async function syncFromBackendManual() {
    const cfg = await OC.config.get();
    const r = $("profileSource");
    if (r) r.innerHTML = "正在从后端同步画像…";
    try {
      const res = await OC.sync.pullFromBackend({ silent: false });
      const filled = OC.sync.countFilled(res.merged);
      alert(`同步成功（${cfg.backend || OC.config.DEFAULT_BACKEND}）\n合并后画像已填字段：${filled}`);
      loadProfile();
    } catch (e) {
      const r2 = $("profileSource");
      if (r2) r2.innerHTML = `数据来源：<b>本地</b>　同步失败：${e.message}`;
      alert("同步失败：" + e.message);
    }
  }

  // 启动时自动同步：后端可达 + 画像为空（或超过 10 分钟没同步）时触发
  // 不再依赖"启用后端"开关——内测阶段后端即本地，应默认可用
  async function autoSyncProfile() {
    try {
      const cfg = await OC.config.get();
      const stats = await OC.store.get("stats") || {};
      const lastSync = stats.last_profile_sync_at || 0;
      const profile = await OC.store.getProfile();
      const filled = OC.sync.countFilled(profile);
      const stale = !lastSync || (Date.now() - lastSync > 10 * 60 * 1000);
      // 条件：从来没同步过 / 同步过期 / 画像空（首次使用）→ 自动拉一次
      if (!lastSync || stale || filled === 0) {
        const res = await OC.sync.pullFromBackend({ silent: true });
        console.log("[OfferClaw] 自动同步后端画像成功，已填字段:", OC.sync.countFilled(res.merged));
      }
    } catch (e) {
      console.warn("[OfferClaw] 自动同步后端画像失败（已忽略，本地仍可用）:", e.message);
    }
  }

  // 填写前确保本地画像已同步后端。返回 {ok, filled, error, synced}
  // 不再静默吞错：失败 / 画像为空都必须让 btnFill 明确告知用户
  async function ensureProfileSynced() {
    const stats = await OC.store.get("stats") || {};
    const lastSync = stats.last_profile_sync_at || 0;
    const profile = await OC.store.getProfile();
    const filled = OC.sync.countFilled(profile);
    const stale = !lastSync || (Date.now() - lastSync > 10 * 60 * 1000);
    if (filled > 0 && !stale) {
      // 画像已就绪，无需再拉
      return { ok: true, filled, synced: false };
    }
    // 画像空 / 从未同步 / 已过期 → 拉取
    try {
      await OC.sync.pullFromBackend({ silent: true });
      const p2 = await OC.store.getProfile();
      return { ok: true, filled: OC.sync.countFilled(p2), synced: true };
    } catch (e) {
      return { ok: false, filled, error: e.message };
    }
  }

  // ============ 设置面板 ============
  async function loadConfig() {
    const cfg = await OC.config.get();
    $("cfgBackend").value = cfg.backend || OC.config.DEFAULT_BACKEND;
    $("cfgUseBackend").checked = !!cfg.use_backend;
    const sens = await OC.privacy.getSensitive();
    $("sensIdCard").value = sens.id_card || "";
    $("sensHomeAddress").value = sens.home_address || "";
    $("sensBankCard").value = sens.bank_card || "";
    $("sensPassport").value = sens.passport || "";
    $("sensEmergencyContact").value = sens.emergency_contact || "";
    $("sensEmergencyPhone").value = sens.emergency_phone || "";
  }

  $("btnSaveConfig").addEventListener("click", async () => {
    const backend = $("cfgBackend").value.trim() || OC.config.DEFAULT_BACKEND;
    const use_backend = $("cfgUseBackend").checked;
    await OC.config.set(backend, use_backend);
    alert("配置已保存");
    checkBackend();
  });

  $("btnTestConn").addEventListener("click", async () => {
    const backend = $("cfgBackend").value.trim() || OC.config.DEFAULT_BACKEND;
    await OC.config.set(backend, $("cfgUseBackend").checked);
    await checkBackend();
  });

  $("btnSaveSensitive").addEventListener("click", async () => {
    await OC.privacy.setSensitive({
      id_card: $("sensIdCard").value.trim(),
      home_address: $("sensHomeAddress").value.trim(),
      bank_card: $("sensBankCard").value.trim(),
      passport: $("sensPassport").value.trim(),
      emergency_contact: $("sensEmergencyContact").value.trim(),
      emergency_phone: $("sensEmergencyPhone").value.trim()
    });
    alert("敏感数据已保存到本地（后端永不接触）");
  });

  $("btnExport").addEventListener("click", async () => {
    const data = await OC.store.exportData();
    const blob = new Blob([JSON.stringify(data, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `offerclaw_backup_${Date.now()}.json`;
    a.click();
    URL.revokeObjectURL(url);
  });

  $("btnReset").addEventListener("click", async () => {
    if (!confirm("确定重置所有本地数据？此操作不可恢复。")) return;
    await OC.store.reset();
    alert("已重置");
    loadConfig();
    loadProfile();
  });

  // ============ 工具 ============
  function escapeHtml(s) {
    return String(s == null ? "" : s)
      .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
  }

  // ============ 启动 ============
  loadConfig();
  loadExtStats();
  checkBackend();
  // 启动后异步尝试从后端同步画像（本地仍可用，后端可达即同步）
  autoSyncProfile();
})();
