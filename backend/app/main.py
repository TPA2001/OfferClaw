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
from app.api import automation, profile, agent, applications

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger("offerclaw")

# === 启动时校验鉴权配置（不安全配置直接拒绝启动）===
from app.core.auth import validate_auth_config, AUTH_MODE
_auth_warnings = validate_auth_config()
for w in _auth_warnings:
    logger.warning(f"[安全警告] {w}")

# Create database tables
from app.models.profile import Profile           # noqa: F401
from app.models.application import Application, AgentSession  # noqa: F401
Base.metadata.create_all(bind=engine)
logger.info("Database tables created")

# === 自动迁移：为已存在的 applications 表追加新列（SQLite 安全的 ALTER TABLE）===
# 这样旧数据库无需手动迁移即可获得新字段
def _migrate_applications_table():
    """对 SQLite 友好的列追加迁移：缺失的列用 ALTER TABLE ADD COLUMN 补齐"""
    from sqlalchemy import text, inspect
    insp = inspect(engine)
    if "applications" not in insp.get_table_names():
        return
    existing_cols = {c["name"] for c in insp.get_columns("applications")}
    new_cols = [
        ("rejection_stage", "VARCHAR(30)"),
        ("interview_round", "INTEGER"),
        ("next_interview_at", "DATETIME"),
        ("offer_status", "VARCHAR(20)"),
        ("priority", "VARCHAR(10) DEFAULT 'medium'"),
        ("assessment_deadline", "DATETIME"),
        ("offer_salary", "VARCHAR(100)"),
        ("offer_location", "VARCHAR(100)"),
        ("offer_deadline", "DATETIME"),
        ("hr_contact", "VARCHAR(200)"),
        ("status_history", "JSON"),
    ]
    with engine.begin() as conn:
        for col_name, col_type in new_cols:
            if col_name not in existing_cols:
                conn.execute(text(f"ALTER TABLE applications ADD COLUMN {col_name} {col_type}"))
                logger.info(f"Migrated: added column applications.{col_name}")

_migrate_applications_table()


# === 自动迁移：为已存在的 profiles 表追加新列 ===
# 安全策略：移除 DROP TABLE 重建逻辑，改为数据导出备份 + 增量 ALTER ADD COLUMN。
# 旧 UUID 类型 user_id 列在不兼容时，仅记录警告并保留原表，由管理员手动处理。
def _migrate_profiles_table():
    """对 SQLite 友好的列追加迁移：缺失的列用 ALTER TABLE ADD COLUMN 补齐。

    安全策略：绝不 DROP TABLE，避免数据丢失。若检测到旧 schema（UUID 类型 user_id），
    仅记录警告并尝试备份，由管理员手动迁移。
    """
    from sqlalchemy import text, inspect
    insp = inspect(engine)
    if "profiles" not in insp.get_table_names():
        return
    cols = insp.get_columns("profiles")
    existing_cols = {c["name"] for c in cols}

    # 检测旧 schema：user_id 列类型若为 UUID/BLOB，记录警告并备份数据
    uid_decl_type = ""
    with engine.begin() as conn:
        pragma_rows = conn.execute(text("PRAGMA table_info(profiles)")).fetchall()
        for r in pragma_rows:
            if r[1] == "user_id":
                uid_decl_type = (r[2] or "").upper()
                break

    if uid_decl_type in ("UUID", "BLOB") or uid_decl_type.startswith("UUID"):
        # 旧 schema 检测到，先做 JSON 备份到磁盘（绝不丢数据）
        _backup_table_to_json("profiles")
        logger.warning(
            f"检测到 profiles 表使用旧 UUID 类型 user_id（decl_type={uid_decl_type}）。"
            "已备份数据到 data/backups/。由于 SQLite 不支持 ALTER COLUMN 类型，"
            "如需迁移请手动导出 → 删表 → 重建 → 导入。本次启动跳过该表的列追加。"
        )
        return

    # 正常追加新列
    new_cols = [
        ("projects", "JSON"),
        ("summary", "JSON"),
        ("certifications", "JSON"),
    ]
    with engine.begin() as conn:
        for col_name, col_type in new_cols:
            if col_name not in existing_cols:
                conn.execute(text(f"ALTER TABLE profiles ADD COLUMN {col_name} {col_type}"))
                logger.info(f"Migrated: added column profiles.{col_name}")


def _backup_table_to_json(table_name: str) -> Path | None:
    """把整张表导出为 JSON 文件作为迁移前备份，绝不丢数据。"""
    from sqlalchemy import text
    try:
        backup_dir = Path("data/backups")
        backup_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        backup_path = backup_dir / f"{table_name}_{timestamp}.json"

        with engine.begin() as conn:
            result = conn.execute(text(f"SELECT * FROM {table_name}"))
            rows = [dict(row._mapping) for row in result]

        # 序列化（datetime 等转字符串）
        def _default(o):
            if isinstance(o, datetime):
                return o.isoformat()
            return str(o)

        backup_path.write_text(
            json.dumps(rows, ensure_ascii=False, indent=2, default=_default),
            encoding="utf-8",
        )
        logger.info(f"已备份 {table_name} 表（{len(rows)} 行）到 {backup_path}")
        return backup_path
    except Exception as e:
        logger.error(f"备份 {table_name} 表失败: {e}")
        return None


_migrate_profiles_table()


# Create FastAPI app
app = FastAPI(
    title="OfferClaw",
    description="Job Application Management System with Smart Form Filling",
    version="1.1.0"
)

# CORS middleware
# 通过环境变量 CORS_ORIGINS 配置允许的来源（逗号分隔），默认放开常见本地开发端口
_default_origins = "http://localhost:3000,http://127.0.0.1:3000,http://localhost:5173,http://127.0.0.1:5173,http://localhost:8000"
_cors_env = os.getenv("CORS_ORIGINS", _default_origins)
allow_origins = [o.strip() for o in _cors_env.split(",") if o.strip()]
# 允许在开发环境用通配符，此时必须关闭 credentials
allow_credentials = "*" not in allow_origins

# 生产环境安全检查：demo 模式 + 通配 CORS = 完全公开
if AUTH_MODE == "demo" and "*" in allow_origins:
    logger.warning(
        "[安全警告] AUTH_MODE=demo + CORS=* 意味着 API 完全无鉴权且允许任意来源访问，"
        "仅适用于本地开发。生产环境请配置 AUTH_MODE=jwt 和具体的 CORS_ORIGINS。"
    )

app.add_middleware(
    CORSMiddleware,
    allow_origins=allow_origins,
    allow_credentials=allow_credentials,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register routers
app.include_router(automation.router)
app.include_router(profile.router)
app.include_router(agent.router)
app.include_router(applications.router)


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


@app.get("/")
async def root():
    """Root endpoint"""
    return ok_response(
        data={
            "version": "1.1.0",
            "docs": "/docs",
            "health": "/health",
        },
        message="Welcome to OfferClaw API",
    )


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
    try:
        from app.core.llm import get_default_provider
        provider = get_default_provider()
        llm_status = provider.name
    except Exception as e:
        llm_status = f"error: {type(e).__name__}"

    healthy = db_status == "connected"
    return {
        "status": "healthy" if healthy else "unhealthy",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "services": {
            "database": db_status,
            "database_error": db_error,
            "llm_provider": llm_status,
            "auth_mode": AUTH_MODE,
        },
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)