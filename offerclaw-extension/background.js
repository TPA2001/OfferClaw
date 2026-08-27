// OfferClaw 扩展 - Service Worker（后台）
// 职责：启动迁移、健康检查转发、可选的定时同步（V0.0.1 仅最小化）
importScripts(
  "shared/schema.js",
  "shared/storage.js",
  "shared/config.js",
  "shared/api-client.js"
);

// 点击扩展图标时打开侧边栏（而非弹窗）
try {
  chrome.sidePanel?.setPanelBehavior({ openPanelOnActionClick: true }).catch(() => {});
} catch (e) {
  // ignore
}

// 安装/启动时触发数据迁移，保证版本升级后数据依然可用
chrome.runtime.onInstalled.addListener(async () => {
  try {
    await OC.store.getAll();
    console.log("[OfferClaw] storage 初始化/迁移完成");
  } catch (e) {
    console.warn("[OfferClaw] storage 迁移失败:", e);
  }
});

// 消息路由：供 popup/content 复用，网络请求集中在 service worker
chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
  if (!msg || !msg.type) return;

  if (msg.type === "oc_health") {
    OC.api
      .health()
      .then((d) => sendResponse({ ok: true, data: d }))
      .catch((e) => sendResponse({ ok: false, error: e.message }));
    return true;
  }

  if (msg.type === "oc_get_stats") {
    OC.api
      .getStatsOverview()
      .then((d) => sendResponse({ ok: true, data: d }))
      .catch((e) => sendResponse({ ok: false, error: e.message }));
    return true;
  }

  // 代理 content 脚本同步后端画像：content 直接 fetch 后端会遭 CORS（Origin 为页面域名），
  // 由 service worker（Origin = chrome-extension://）代理拉取后返回原始画像（含 basic_info）
  if (msg.type === "oc_sync_profile") {
    OC.api
      .getProfile()
      .then((remote) => sendResponse({ ok: true, remote }))
      .catch((e) => sendResponse({ ok: false, error: e.message }));
    return true;
  }
});
