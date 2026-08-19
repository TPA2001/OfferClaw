"""
OfferClaw Backend Application
Job Application Management System with Smart Form Filling
"""

import os
import sys
import asyncio
import json
import logging
from datetime import datetime, timezone
from pathlib import Path

# ============================================================================
# Windows 事件循环策略修正（必须在 uvicorn/FastAPI import 之前）
# ============================================================================
# 问题：uvicorn 在 --reload 模式下会设置 WindowsSelectorEventLoopPolicy，
#       而 SelectorEventLoop 不支持 asyncio.create_subprocess_exec，
#       导致 Playwright 启动 node 子进程时报 NotImplementedError。
# 修正：强制使用 ProactorEventLoop（支持子进程），并 monkeypatch
#       uvicorn 的 asyncio_setup，防止它覆盖回 SelectorEventLoop。
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
    try:
        import uvicorn.loops.asyncio as _oc_uvicorn_loop
        _oc_uvicorn_loop.asyncio_setup = lambda use_subprocess=False: None
    except ImportError:
        pass

# 加载 .env 文件中的环境变量（本地开发用；生产环境由进程环境注入）
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from fastapi import FastAPI, Request, HTTPException
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.core.database import engine, Base, SessionLocal
from app.core.response import (
    APIError, business_code_for_http, ok as ok_response,
)
from app.api import automation, profile, agent, applications, journal, settings, license as license_api

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger("offerclaw")

# === 启动时校验配置（内测模式：单用户，无鉴权）===
from app.core.auth import validate_auth_config, AUTH_MODE
_auth_warnings = validate_auth_config()
for w in _auth_warnings:
    logger.warning(f"[安全警告] {w}")

# Create database tables
from app.models.profile import Profile           # noqa: F401
from app.models.application import Application, AgentSession  # noqa: F401
Base.metadata.create_all(bind=engine)
logger.info("Database tables created")

# === 泛化自动迁移：比对 models 与 DB schema，自动补齐缺失列 ===
# 用户更新版本后直接重启即可，旧数据库自动升级（迁移前自动 JSON 备份，绝不丢数据）
from app.core.migrations import auto_migrate
auto_migrate(engine, Base.metadata)

# === 授权激活：启动时加载本机激活态 ===
from app.core import license as license_mod
license_mod.init_license()


# Create FastAPI app
app = FastAPI(
    title="OfferClaw",
    description="Job Application Management System with Smart Form Filling",
    version="1.1.0"
)

# CORS middleware
# 通过环境变量 CORS_ORIGINS 配置允许的来源（逗号分隔），默认放开常见本地开发端口
_default_origins = "http://localhost:3000,http://127.0.0.1:3000,http://localhost:5173,http://127.0.0.1:5173,http://localhost:8000,http://127.0.0.1:8000"
_cors_env = os.getenv("CORS_ORIGINS", _default_origins)
allow_origins = [o.strip() for o in _cors_env.split(",") if o.strip()]
# 允许在开发环境用通配符，此时必须关闭 credentials
allow_credentials = "*" not in allow_origins

# 生产环境安全检查：内测模式 + 通配 CORS = 完全公开
if "*" in allow_origins:
    logger.warning(
        "[安全警告] 内测模式 + CORS=* 意味着 API 完全无鉴权且允许任意来源访问，"
        "仅适用于本地/内测环境。正式发布请配置具体的 CORS_ORIGINS。"
    )

app.add_middleware(
    CORSMiddleware,
    allow_origins=allow_origins,
    # 允许 OfferClaw 官方浏览器扩展跨域调用（Origin = chrome-extension://<id>）
    # CORS spec 不支持 chrome-extension://* 通配，必须用正则
    allow_origin_regex=r"chrome-extension://.*",
    allow_credentials=allow_credentials,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register routers
app.include_router(license_api.router)      # 授权激活（无需鉴权，始终可达）
app.include_router(automation.router)
app.include_router(profile.router)
app.include_router(agent.router)
app.include_router(applications.router)
app.include_router(journal.router)
app.include_router(settings.router)


# === 授权门控中间件：未激活/过期/功能未授权 → 403 ===
@app.middleware("http")
async def license_gate_middleware(request: Request, call_next):
    """产品授权门控

    - 始终放行：根/健康检查/授权接口/文档
    - 未激活或已过期：拒绝其余请求，引导到激活页
    - 已激活但该路径所需功能未授权：拒绝并提示升级
    - 开发模式(OFFERCLAW_DEV=1)：全部放行
    """
    # 始终放行的路径前缀（健康检查、文档、授权接口）
    _PUBLIC_PREFIXES = (
        "/health", "/docs", "/openapi.json", "/redoc",
        "/api/v1/license",
    )
    path = request.url.path
    if any(path == p or path.startswith(p + "/") for p in _PUBLIC_PREFIXES):
        return await call_next(request)
    # 非 API 路径放行：前端静态资源/SPA 路由由 StaticFiles 处理，激活页必须可访问
    if not path.startswith("/api/"):
        return await call_next(request)

    if license_mod.is_dev_mode():
        return await call_next(request)

    if not license_mod.is_activated():
        info = license_mod.get_license()
        code = 40302 if (info and info.is_expired()) else 40301
        msg = "授权已过期，请重新激活" if code == 40302 else "产品未激活，请提交授权密钥"
        return JSONResponse(
            status_code=403,
            content={"code": code, "message": msg, "detail": {"need_activation": True}},
        )

    # 已激活：校验路径所需功能
    required_feature = license_mod.require_feature_for_path(path)
    if required_feature and not license_mod.is_feature_enabled(required_feature):
        return JSONResponse(
            status_code=403,
            content={
                "code": 40303,
                "message": f"当前授权未包含「{required_feature}」功能，请联系开发者升级",
                "detail": {"required_feature": required_feature, "need_upgrade": True},
            },
        )

    return await call_next(request)


# === 全局异常处理器：统一错误响应信封 ===
# 所有错误响应都遵循 {"code": <非0>, "message": "...", "detail": ...} 格式
# 业务码与 HTTP 状态码对齐（业务码 = HTTP × 100）

@app.exception_handler(APIError)
async def api_error_handler(request: Request, exc: APIError):
    """业务 APIError → 统一信封"""
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "code": exc.code,
            "message": exc.message,
            "detail": exc.detail,
        },
        headers=getattr(exc, "headers", None),
    )


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    """普通 HTTPException（含未走 APIError 的旧代码）→ 统一信封

    将 detail 字符串映射为 message，业务码由 HTTP 状态码反推。
    """
    code = business_code_for_http(exc.status_code)
    # exc.detail 可能是字符串，也可能是 dict（FastAPI 内部用法）
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
    """请求参数校验失败 → 42200 + 字段错误列表"""
    return JSONResponse(
        status_code=422,
        content={
            "code": 42200,
            "message": "请求参数校验失败",
            "detail": exc.errors(),
        },
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    """未捕获异常 → 50000，避免向前端暴露内部堆栈"""
    logger.exception(f"未捕获异常 [{request.method} {request.url.path}]: {exc}")
    return JSONResponse(
        status_code=500,
        content={
            "code": 50000,
            "message": "服务器内部错误，请稍后重试或联系管理员",
            "detail": None,  # 不向客户端暴露异常详情
        },
    )


# 根路由 / 由文件末尾 StaticFiles 挂载接管（返回前端 index.html），不再返回 API 欢迎页


@app.get("/health")
async def health():
    """真实健康检查：探测数据库连接可用性"""
    from sqlalchemy import text
    db_status = "connected"
    db_error = None
    try:
        db = SessionLocal()
        try:
            db.execute(text("SELECT 1"))
        finally:
            db.close()
    except Exception as e:
        db_status = "disconnected"
        db_error = str(e)

    # LLM provider 可用性（不实际调用，只检查配置）
    llm_status = "unknown"
    llm_configured = False
    mock_mode = False
    model_info = {}
    try:
        from app.core.llm import get_default_provider
        from app.core.config_store import get_masked_config
        provider = get_default_provider()
        llm_status = provider.name
        cfg = get_masked_config()
        agent = cfg.get("agent", {}) or {}
        llm_configured = bool(agent.get("configured"))
        mock_mode = llm_status == "mock" or cfg.get("mock_fallback", False)
        model_info = {
            "provider": agent.get("provider", ""),
            "model": agent.get("model", ""),
            "type": agent.get("provider", ""),
        }
    except Exception as e:
        llm_status = f"error: {type(e).__name__}"

    healthy = db_status == "connected"
    return {
        "status": "healthy" if healthy else "unhealthy",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "llm_configured": llm_configured,
        "llm_ready": llm_configured,
        "mock_mode": mock_mode,
        "model_info": model_info,
        "services": {
            "database": db_status,
            "database_error": db_error,
            "llm_provider": llm_status,
            "auth_mode": AUTH_MODE,
            "license_activated": license_mod.is_activated(),
            "license_dev_mode": license_mod.is_dev_mode(),
        },
    }


# === 前端静态文件挂载（必须在所有 API 路由之后注册，最后匹配）===
# 开发模式：服务项目根 frontend/web/；打包模式：服务 _MEIPASS/frontend/web/
from pathlib import Path as _Path
from fastapi.staticfiles import StaticFiles as _StaticFiles
from app.core.paths import static_dir as _static_dir

_static_path = str(_static_dir())
if _Path(_static_path).exists():
    app.mount("/", _StaticFiles(directory=_static_path, html=True), name="frontend")
    logger.info(f"前端静态文件已挂载：{_static_path}")
else:
    logger.warning(f"前端静态目录不存在，跳过挂载：{_static_path}")