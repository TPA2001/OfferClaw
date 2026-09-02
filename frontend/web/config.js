/**
 * OfferCabin 前端共享配置
 *
 * 集中管理 API_BASE，避免每个 HTML 文件硬编码。
 * 部署时只需修改本文件，不用逐页改。
 *
 * 内测模式：单用户，无鉴权 token。后端忽略 Authorization 头。
 */
window.OFFERCABIN_CONFIG = {
    // API 基地址：开发环境自动指向 localhost:8000，生产环境通过 nginx 反代用相对路径
    API_BASE: window.OFFERCABIN_API_BASE !== undefined
        ? window.OFFERCABIN_API_BASE
        : (location.hostname === 'localhost' || location.hostname === '127.0.0.1'
            ? 'http://localhost:8000'
            : ''),
    // 管理后台端口（与公开应用隔离，独立端口；仅管理员入口可见）
    ADMIN_PORT: 8001,
    // 内测模式无需鉴权 token，保留占位以兼容 api.js 的 headers 构造
    TOKEN: 'internal-beta',
    // 是否开启调试日志
    DEBUG: false,
};

/**
 * 安全的 URL scheme 校验，防止 javascript: 协议注入 XSS
 * 仅允许 http/https/mailto/tel 协议
 */
window.sanitizeUrl = function(url) {
    if (!url || typeof url !== "string") return "";
    var trimmed = url.trim();
    if (!trimmed) return "";
    // 相对路径允许
    if (trimmed.startsWith("/") || trimmed.startsWith("./") || trimmed.startsWith("../")) {
        return trimmed;
    }
    // 协议白名单
    var allowedSchemes = ["http:", "https:", "mailto:", "tel:"];
    try {
        var parsed = new URL(trimmed);
        if (allowedSchemes.includes(parsed.protocol.toLowerCase())) {
            return trimmed;
        }
    } catch (e) {
        // 不是合法 URL，可能是锚点或纯文本
        if (trimmed.startsWith("#")) return trimmed;
        return "";
    }
    return "";
};

/**
 * 主题管理器
 * - 主题列表与元数据（颜色样本用于设置页预览）
 * - get/set/apply，持久化到 localStorage
 * - 暗色主题同步 is-dark 类到 body（影响纹理叠加）
 */
(function (global) {
    "use strict";

    var STORAGE_KEY = "oc_theme";
    var DENSITY_KEY = "oc_density";
    var ACCENT_KEY = "oc_accent";

    // 主题元数据：swatches 顺序 [paper, ink, primary, secondary]
    // 设计纪律（参考 GitHub Primer / Linear / Notion）：
    // 近中性微着色画布 + 每主题一个明确主色，保证任何状态色/主色调放上去都协调
    var THEMES = [
        {
            id: "paper",
            name: "纸白",
            desc: "Ivory & Blue",
            dark: false,
            swatches: ["#f7f6f3", "#27251f", "#2563eb", "#e8590c"],
        },
        {
            id: "ink",
            name: "午夜",
            desc: "Midnight Graphite",
            dark: true,
            swatches: ["#101216", "#ececee", "#60a5fa", "#e3b04b"],
        },
        {
            id: "forest",
            name: "森林",
            desc: "Deep Forest",
            dark: true,
            swatches: ["#101612", "#e5ebe2", "#4ade80", "#e3b04b"],
        },
        {
            id: "ocean",
            name: "深海",
            desc: "Deep Sea",
            dark: true,
            swatches: ["#0d1420", "#e3eaf4", "#22d3ee", "#e8a35c"],
        },
        {
            id: "sunset",
            name: "暖沙",
            desc: "Warm Sand",
            dark: false,
            swatches: ["#faf6f0", "#35281f", "#e0563f", "#b45309"],
        },
        {
            id: "mono",
            name: "极简",
            desc: "Mono Contrast",
            dark: false,
            swatches: ["#fafafa", "#111111", "#171717", "#737373"],
        },
    ];

    var THEME_MAP = {};
    THEMES.forEach(function (t) { THEME_MAP[t.id] = t; });

    // 主色调选项（按色环排序，主流 Tailwind 色阶）：
    // color = 浅色主题用（600 系，深底白字）；colorDark = 暗色主题用（400 系提亮）
    // 点击后 --olive 变成对应变体，soft/dark/glow 由 color-mix 自动派生
    var ACCENTS = [
        { id: "blue",    name: "海蓝",   color: "#2563eb", colorDark: "#60a5fa" },
        { id: "sky",     name: "天蓝",   color: "#0284c7", colorDark: "#38bdf8" },
        { id: "cyan",    name: "晴青",   color: "#0891b2", colorDark: "#22d3ee" },
        { id: "teal",    name: "青绿",   color: "#0d9488", colorDark: "#2dd4bf" },
        { id: "emerald", name: "翡翠",   color: "#059669", colorDark: "#34d399" },
        { id: "olive",   name: "橄榄",   color: "#65a30d", colorDark: "#a3e635" },
        { id: "gold",    name: "暖金",   color: "#ca8a04", colorDark: "#facc15" },
        { id: "amber",   name: "琥珀",   color: "#d97706", colorDark: "#fbbf24" },
        { id: "terra",   name: "暖橙",   color: "#ea580c", colorDark: "#fb923c" },
        { id: "crimson", name: "朱红",   color: "#dc2626", colorDark: "#f87171" },
        { id: "rose",    name: "玫红",   color: "#e11d48", colorDark: "#fb7185" },
        { id: "pink",    name: "樱粉",   color: "#db2777", colorDark: "#f472b6" },
        { id: "violet",  name: "紫罗兰", color: "#7c3aed", colorDark: "#a78bfa" },
        { id: "indigo",  name: "靛蓝",   color: "#4f46e5", colorDark: "#818cf8" },
        { id: "slate",   name: "岩灰",   color: "#475569", colorDark: "#94a3b8" },
    ];

    function current() {
        var t = "paper";
        try { t = localStorage.getItem(STORAGE_KEY) || "paper"; } catch (e) {}
        if (!THEME_MAP[t]) t = "paper";
        return t;
    }

    function apply(themeId) {
        if (!THEME_MAP[themeId]) themeId = "paper";
        var meta = THEME_MAP[themeId];
        var root = document.documentElement;
        root.setAttribute("data-theme", themeId);
        // 同步暗色标记到 body（纹理叠加需要）
        var body = document.body;
        if (body) {
            body.classList.toggle("is-dark", !!meta.dark);
        } else {
            // body 尚未解析，标记待 DOMContentLoaded 处理
            root.classList.toggle("is-dark-pending", !!meta.dark);
        }
        try { localStorage.setItem(STORAGE_KEY, themeId); } catch (e) {}
        // 主题明暗切换后，重应用当前主色调以切换到对应的明/暗变体
        var ac = currentAccent();
        if (ac) applyAccent(ac);
        // 通知其它组件（如代码高亮）主题已变
        try {
            global.dispatchEvent(new CustomEvent("oc-theme-change", { detail: { theme: themeId, dark: !!meta.dark } }));
        } catch (e) {}
    }

    // ============ 主色调（accent）============

    function currentAccent() {
        var a = "";
        try { a = localStorage.getItem(ACCENT_KEY) || ""; } catch (e) {}
        return a;
    }

    /** 按 id 查找主色调定义 */
    function findAccent(accentId) {
        for (var i = 0; i < ACCENTS.length; i++) {
            if (ACCENTS[i].id === accentId) return ACCENTS[i];
        }
        return null;
    }

    /** 当前主题下该主色调的实际显示色（浅色主题 600 系 / 暗色主题 400 系变体） */
    function accentColor(accentId) {
        var a = findAccent(accentId);
        if (!a) return "";
        var t = THEME_MAP[current()];
        return (t && t.dark && a.colorDark) ? a.colorDark : a.color;
    }

    function applyAccent(accentId) {
        var root = document.documentElement;
        if (!accentId) {
            // 清除自定义主色，回归主题预设
            root.style.removeProperty("--olive");
            try { localStorage.removeItem(ACCENT_KEY); } catch (e) {}
        } else {
            var accent = findAccent(accentId);
            if (!accent) return;
            // 用 inline style 覆盖 --olive（按主题明暗选择变体），衍生色由 color-mix 自动派生
            root.style.setProperty("--olive", accentColor(accentId));
            try { localStorage.setItem(ACCENT_KEY, accentId); } catch (e) {}
        }
        try {
            global.dispatchEvent(new CustomEvent("oc-accent-change", { detail: { accent: accentId } }));
        } catch (e) {}
    }

    function currentDensity() {
        var d = "comfortable";
        try { d = localStorage.getItem(DENSITY_KEY) || "comfortable"; } catch (e) {}
        return d === "compact" ? "compact" : "comfortable";
    }

    function applyDensity(d) {
        d = (d === "compact") ? "compact" : "comfortable";
        var body = document.body;
        if (body) body.setAttribute("data-density", d);
        try { localStorage.setItem(DENSITY_KEY, d); } catch (e) {}
    }

    // 启动时同步 is-dark-pending → body.is-dark，并应用 density 和 accent
    function bootstrap() {
        var t = current();
        var meta = THEME_MAP[t];
        var body = document.body;
        if (body) {
            body.classList.toggle("is-dark", !!(meta && meta.dark));
            document.documentElement.classList.remove("is-dark-pending");
            applyDensity(currentDensity());
            // 恢复自定义主色调（若有）
            var ac = currentAccent();
            if (ac) applyAccent(ac);
        }
    }

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", bootstrap);
    } else {
        bootstrap();
    }

    global.OfferCabinTheme = {
        THEMES: THEMES,
        THEME_MAP: THEME_MAP,
        ACCENTS: ACCENTS,
        current: current,
        apply: apply,
        getMeta: function (id) { return THEME_MAP[id] || null; },
        currentDensity: currentDensity,
        applyDensity: applyDensity,
        currentAccent: currentAccent,
        applyAccent: applyAccent,
        accentColor: accentColor,
    };
})(window);
