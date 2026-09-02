"""
安全中间件

- security_headers：通用安全响应头，主应用与管理后台共用
- admin_ip_guard：管理端口 IP 白名单守卫（仅管理后台挂载）

设计原则：纵深防御，最小暴露面。这些头本身不替代鉴权/限流，
但能显著提升常见 Web 攻击（点击劫持、MIME 嗅探、协议跳转）的门槛。
"""

import logging

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response

from app.core.config import settings

logger = logging.getLogger("offercabin.security")


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """注入安全响应头。

    - X-Content-Type-Options: nosniff —— 阻止浏览器嗅探 MIME 类型
    - X-Frame-Options: DENY —— 阻止点击劫持（页面禁止被 iframe 嵌入）
    - Referrer-Policy: no-referrer —— 不向外站泄漏完整 Referrer
    - Strict-Transport-Security —— 仅在 HTTPS 下下发，强制后续连接走 TLS
    """

    async def dispatch(self, request: Request, call_next):
        response: Response = await call_next(request)
        try:
            response.headers["X-Content-Type-Options"] = "nosniff"
            response.headers["X-Frame-Options"] = "DENY"
            response.headers["Referrer-Policy"] = "no-referrer"
            # 仅在 HTTPS（直连或反代 X-Forwarded-Proto）下下发 HSTS，避免把 HTTP 流量锁死
            scheme = request.url.scheme.lower()
            forwarded_proto = request.headers.get("x-forwarded-proto", "").split(",")[0].strip().lower()
            if scheme == "https" or forwarded_proto == "https":
                response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        except Exception:
            pass
        return response


class AdminIpGuardMiddleware(BaseHTTPMiddleware):
    """管理端口 IP 白名单守卫。

    若 ADMIN_ALLOW_IPS 已配置，仅允许白名单内 IP 访问管理后台；
    未配置时放行（启动时记录告警，建议生产显式配置）。
    """

    async def dispatch(self, request: Request, call_next):
        allow = settings.admin_allow_ip_list
        if allow:
            client_ip = request.client.host if request.client else "unknown"
            # 兼容反代：优先取 X-Forwarded-For 首段
            forwarded = request.headers.get("x-forwarded-for", "")
            if forwarded:
                client_ip = forwarded.split(",")[0].strip()
            if client_ip not in allow:
                logger.warning(f"[管理后台] IP 被拒绝访问: {client_ip} path={request.url.path}")
                return Response("Forbidden: IP not allowed", status_code=403)
        return await call_next(request)


def warn_admin_ip_guard_disabled():
    """启动时提醒：未配置 IP 白名单（仅用于日志提示，不阻断启动）"""
    if not settings.admin_allow_ip_list:
        logger.warning(
            "[安全警告] ADMIN_ALLOW_IPS 未配置：管理后台未启用 IP 白名单，"
            "建议生产环境显式配置以收窄管理端口可达范围"
        )
