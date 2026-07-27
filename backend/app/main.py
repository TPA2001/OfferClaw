"""
OfferClaw Backend Application
Job Application Management System with Smart Form Filling
"""

import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import logging

from app.core.database import engine, Base
from app.api import automation, profile, agent, applications

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger("offerclaw")

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


# === 自动迁移：为已存在的 profiles 表追加新列（SQLite 安全的 ALTER TABLE）===
def _migrate_profiles_table():
    """对 SQLite 友好的列追加迁移：缺失的列用 ALTER TABLE ADD COLUMN 补齐。
    若旧表使用了 UUID/BLOB 类型列（与 String 不兼容），则重建表。"""
    from sqlalchemy import text, inspect
    insp = inspect(engine)
    if "profiles" not in insp.get_table_names():
        return
    cols = insp.get_columns("profiles")
    existing_cols = {c["name"] for c in cols}

    # 检测旧 schema：user_id 列类型若为 UUID/BLOB/null，说明是 UUID(as_uuid=True) 创建的旧表
    # 需 DROP 重建为 String(64)，与 Application 表保持一致
    # 注意：SQLAlchemy inspect 在 SQLite 下把 UUID 归类为 NUMERIC，所以用 PRAGMA 取原始声明类型
    uid_decl_type = ""
    with engine.begin() as conn:
        pragma_rows = conn.execute(text("PRAGMA table_info(profiles)")).fetchall()
        for r in pragma_rows:
            # (cid, name, type, notnull, dflt_value, pk)
            if r[1] == "user_id":
                uid_decl_type = (r[2] or "").upper()
                break
    needs_rebuild = uid_decl_type in ("UUID", "BLOB") or uid_decl_type.startswith("UUID")

    if needs_rebuild:
        # 备份现有数据（虽然通常是空的）
        backup_rows = []
        with engine.begin() as conn:
            try:
                result = conn.execute(text("SELECT * FROM profiles"))
                backup_rows = [dict(row._mapping) for row in result]
            except Exception:
                backup_rows = []
        logger.info(f"Rebuilding profiles table (old uid decl type={uid_decl_type}, backup_rows={len(backup_rows)})")
        with engine.begin() as conn:
            conn.execute(text("DROP TABLE IF EXISTS profiles"))
        # 重新创建（用新 schema）
        Base.metadata.create_all(bind=engine, tables=[Profile.__table__])
        logger.info("Profiles table rebuilt with String(64) user_id")
        # 恢复数据（把 user_id 当作字符串写入）
        if backup_rows:
            with engine.begin() as conn:
                for row in backup_rows:
                    # 只保留与新 schema 匹配的列
                    safe = {k: v for k, v in row.items() if k in {"user_id", "basic_info", "education",
                            "experience", "skills", "projects", "summary", "certifications",
                            "job_intent", "extra_fields"}}
                    safe.setdefault("id", _uuid_str_safe())
                    cols_str = ", ".join(safe.keys())
                    vals_str = ", ".join(f":{k}" for k in safe.keys())
                    conn.execute(text(f"INSERT INTO profiles ({cols_str}) VALUES ({vals_str})"), safe)
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


def _uuid_str_safe() -> str:
    import uuid as _u
    return str(_u.uuid4())


_migrate_profiles_table()


# Create FastAPI app
app = FastAPI(
    title="OfferClaw",
    description="Job Application Management System with Smart Form Filling",
    version="1.0.0"
)

# CORS middleware
# 注意：allow_origins=["*"] 与 allow_credentials=True 不能同时使用（浏览器会拒绝）
# 通过环境变量 CORS_ORIGINS 配置允许的来源（逗号分隔），默认放开常见本地开发端口
_default_origins = "http://localhost:3000,http://127.0.0.1:3000,http://localhost:5173,http://127.0.0.1:5173,http://localhost:8000"
_cors_env = os.getenv("CORS_ORIGINS", _default_origins)
allow_origins = [o.strip() for o in _cors_env.split(",") if o.strip()]
# 允许在开发环境用通配符，此时必须关闭 credentials
allow_credentials = "*" not in allow_origins

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


@app.get("/")
async def root():
    """Root endpoint"""
    return {
        "message": "Welcome to OfferClaw API",
        "version": "1.0.0",
        "docs": "/docs",
        "health": "/health"
    }


@app.get("/health")
async def health():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "services": {
            "database": "connected",
            "automation": "available",
            "profile": "available",
            "agent": "available",
            "applications": "available"
        }
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)