/**
 * OfferClaw 前端共享配置
 *
 * 集中管理 API_BASE 和 TOKEN，避免每个 HTML 文件硬编码。
 * 部署时只需修改本文件，不用逐页改。
 *
 * 安全说明：
 * - TOKEN 在 demo 模式下是占位符，真实鉴权由后端 AUTH_MODE 控制
 * - 生产环境应通过 httpOnly cookie 或后端模板注入真实 token
 */
window.OFFERCLAW_CONFIG = {
    // API 基地址，部署时改为实际后端地址
    API_BASE: window.OFFERCLAW_API_BASE || "http://localhost:8000",
    // 鉴权 token（demo 模式占位符，生产环境由登录系统提供）
    TOKEN: window.OFFERCLAW_TOKEN || "demo-token",
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
 * 构建 API 请求的 headers（带鉴权）
 */
window.apiHeaders = function(extra) {
    var headers = {
        "Authorization": "Bearer " + window.OFFERCLAW_CONFIG.TOKEN,
    };
    if (extra) {
        for (var k in extra) {
            if (Object.prototype.hasOwnProperty.call(extra, k)) {
                headers[k] = extra[k];
            }
        }
    }
    return headers;
};
