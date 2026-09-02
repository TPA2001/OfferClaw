"""
管理后台独立 FastAPI 应用（独立端口，默认 127.0.0.1:8001）

与主应用 app.main:app 隔离：
- 启动硬守卫：默认 SECRET_KEY 或 AUTH_MODE=open 时拒绝启动（不存在「无鉴权的管理后台」）
- 更严 CORS（admin_cors_origin_list）、安全响应头、可选 IP 白名单守卫
- 仅挂管理路由 app.api.admin + /health；静态挂管理前端到 /、复用主站样式到 /__styles/
- 公开端口 8000 上零管理端点（管理路由不挂主 app）

单进程双 app 共享同一 DB 引擎单例（app.core.database 模块级），无 SQLite 并发问题。
"""

import logging
from datetime import datetime, timezone

from fastapi import FastAPI, Request, HTTPException
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pathlib import Path

from app.core.config import settings
from app.core.database import engine, Base, SessionLocal
from app.core.response import APIError, business_code_for_http
from app.core.security_middleware import (
    SecurityHeadersMiddleware,
    AdminIpGuardMiddleware,
    warn_admin_ip_guard_disabled,
)
from app.core.paths import admin_static_dir, web_styles_dir
from app.api import admin as admin_api

logger = logging.getLogger("offercabin.admin")


def _enforce_startup_guards() -> None:
    """启动硬守卫：拒绝在不安全配置下启动管理后台"""
    if settings.auth_mode == "open":
        raise RuntimeError(
            "拒绝启动管理后台：AUTH_MODE=open 为无鉴权模式，不允许运行管理后台。"
            "请设置 AUTH_MODE=jwt 并配置强 SECRET_KEY 后再启动。"
        )
    if settings.secret_key == "dev-secret-key-12345":
        raise RuntimeError(
            "拒绝启动管理后台：SECRET_KEY 仍为默认值。"
            "请通过环境变量设置强随机密钥（SECRET_KEY）后再启动管理后台。"
        )


def create_admin_app() -> FastAPI:
    """构造管理后台 FastAPI 应用"""
    _enforce_startup_guards()

    # 确保 AdminAuditLog 等表存在（与主 app 共享 engine，create_all 幂等）
    Base.metadata.create_all(bind=engine)

    # 泛化自动迁移（补齐缺失列，与主 app 共享，幂等）
    try:
        from app.core.migrations import auto_migrate
        auto_migrate(engine, Base.metadata)
    except Exception as e:  # 迁移失败不阻断启动，仅告警
        logger.warning(f"[管理后台] 自动迁移跳过: {e}")

    app = FastAPI(
        title="OfferCabin Admin",
        description="OfferCabin 管理后台（独立端口，仅授权管理员可访问）",
        version="1.0.0",
        docs_url=None,  # 生产关闭 Swagger，减少暴露面
        redoc_url=None,
        openapi_url=None,
    )

    # 更严的 CORS：仅允许管理后台配置的来源
    origins = settings.admin_cors_origin_list
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=settings.admin_allow_credentials,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # 安全响应头（与主 app 一致）
    app.add_middleware(SecurityHeadersMiddleware)
    # IP 白名单守卫（仅管理后台）
    app.add_middleware(AdminIpGuardMiddleware)

    warn_admin_ip_guard_disabled()

    # 管理路由
    app.include_router(admin_api.router)

    # ============ 全局异常处理器（与主 app 信封一致）============
    @app.exception_handler(APIError)
    async def api_error_handler(request: Request, exc: APIError):
        return JSONResponse(
            status_code=exc.status_code,
            content={"code": exc.code, "message": exc.message, "detail": exc.detail},
            headers=getattr(exc, "headers", None),
        )

    @app.exception_handler(HTTPException)
    async def http_exception_handler(request: Request, exc: HTTPException):
        code = business_code_for_http(exc.status_code)
        if isinstance(exc.detail, dict):
            message = exc.detail.get("message") or exc.detail.get("detail") or "请求错误"
            detail = exc.detail
        else:
            message = str(exc.detail) if exc.detail else "请求错误"
            detail = None
        return JSONResponse(
            status_code=exc.status_code,
            content={"code": code, "message": message, "detail": detail},
            headers=getattr(exc, "headers", None),
        )

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(request: Request, exc: RequestValidationError):
        return JSONResponse(
            status_code=422,
            content={"code": 42200, "message": "请求参数校验失败", "detail": exc.errors()},
        )

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception):
        logger.exception(f"[管理后台] 未捕获异常 [{request.method} {request.url.path}]: {exc}")
        return JSONResponse(
            status_code=500,
            content={"code": 50000, "message": "服务器内部错误", "detail": None},
        )

    # ============ 健康检查 ============
    @app.get("/health")
    async def health():
        from sqlalchemy import text
        db_status = "connected"
        try:
            db = SessionLocal()
            try:
                db.execute(text("SELECT 1"))
            finally:
                db.close()
        except Exception as e:
            db_status = f"disconnected: {e}"
        return {
            "status": "healthy" if db_status == "connected" else "unhealthy",
            "service": "admin",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "services": {"database": db_status},
        }

    # ============ 静态文件（最后挂载，兜底）============
    # 复用主站样式，保持设计系统一致
    styles_path = web_styles_dir()
    if Path(str(styles_path)).exists():
        app.mount("/__styles", StaticFiles(directory=str(styles_path)), name="admin-styles")
    else:
        logger.warning(f"[管理后台] 主站样式目录不存在，跳过挂载：{styles_path}")

    admin_path = admin_static_dir()
    if Path(str(admin_path)).exists():
        app.mount("/", StaticFiles(directory=str(admin_path), html=True), name="admin-frontend")
        logger.info(f"[管理后台] 前端静态文件已挂载：{admin_path}")
    else:
        logger.warning(
            f"[管理后台] 管理前端目录不存在，跳过挂载：{admin_path}（仅 API 可用）"
        )

    return app


# 模块级实例：run.py 以 app.admin_main:app 引用
app = create_admin_app()
