/**
 * OfferClaw 前端共享配置
 *
 * 集中管理 API_BASE，避免每个 HTML 文件硬编码。
 * 部署时只需修改本文件，不用逐页改。
 *
 * 内测模式：单用户，无鉴权 token。后端忽略 Authorization 头。
 */
window.OFFERCLAW_CONFIG = {
    // API 基地址：开发环境自动指向 localhost:8000，生产环境通过 nginx 反代用相对路径
    API_BASE: window.OFFERCLAW_API_BASE !== undefined
        ? window.OFFERCLAW_API_BASE
        : (location.hostname === 'localhost' || location.hostname === '127.0.0.1'
            ? 'http://localhost:8000'
            : ''),
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

    // 主题元数据：swatches 顺序 [paper, ink, primary, accent]
    var THEMES = [
        {
            id: "paper",
            name: "纸质档案",
            desc: "Editorial Paper",
            dark: false,
            swatches: ["#f5f1e8", "#2d2a26", "#6b7d0a", "#c4664a"],
        },
        {
            id: "ink",
            name: "午夜墨色",
            desc: "Midnight Ink",
            dark: true,
            swatches: ["#14171c", "#e8e6e0", "#7da3d1", "#d4a574"],
        },
        {
            id: "forest",
            name: "深林",
            desc: "Deep Forest",
            dark: true,
            swatches: ["#1a2820", "#e8e3d0", "#8fb049", "#d4a554"],
        },
        {
            id: "ocean",
            name: "潮汐深蓝",
            desc: "Tidal Deep",
            dark: true,
            swatches: ["#0f1a24", "#dde8f0", "#4db8a8", "#7dc4e8"],
        },
        {
            id: "sunset",
            name: "沙漠日落",
            desc: "Desert Sunset",
            dark: false,
            swatches: ["#faf3ec", "#3a2820", "#d4664a", "#c8854a"],
        },
        {
            id: "mono",
            name: "极简赤墨",
            desc: "Brutalist Mono",
            dark: false,
            swatches: ["#fafafa", "#0a0a0a", "#d63030", "#888888"],
        },
    ];

    var THEME_MAP = {};
    THEMES.forEach(function (t) { THEME_MAP[t.id] = t; });

    // 主色调选项：点击后 --olive 变成该颜色，衍生色由 color-mix 自动派生
    var ACCENTS = [
        { id: "olive",   name: "橄榄",   color: "#6b7d0a" },
        { id: "ocean",   name: "海蓝",   color: "#2d6a9f" },
        { id: "terra",   name: "砖红",   color: "#c4664a" },
        { id: "amber",   name: "琥珀",   color: "#b8860b" },
        { id: "emerald", name: "翡翠",   color: "#5a7a3a" },
        { id: "violet",  name: "紫罗兰", color: "#7a4d8f" },
        { id: "teal",    name: "青绿",   color: "#4db8a8" },
        { id: "rose",    name: "玫红",   color: "#c04d6f" },
        { id: "indigo",  name: "靛蓝",   color: "#4d5d9f" },
        { id: "gold",    name: "金橙",   color: "#d4a554" },
        { id: "crimson", name: "朱红",   color: "#d63030" },
        { id: "slate",   name: "岩灰",   color: "#5a6878" },
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

    function applyAccent(accentId) {
        var root = document.documentElement;
        if (!accentId) {
            // 清除自定义主色，回归主题预设
            root.style.removeProperty("--olive");
            try { localStorage.removeItem(ACCENT_KEY); } catch (e) {}
        } else {
            var accent = null;
            for (var i = 0; i < ACCENTS.length; i++) {
                if (ACCENTS[i].id === accentId) { accent = ACCENTS[i]; break; }
            }
            if (!accent) return;
            // 用 inline style 覆盖 --olive，衍生色由 color-mix 自动派生
            root.style.setProperty("--olive", accent.color);
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

    global.OfferClawTheme = {
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
    };
})(window);
