"""
OfferClaw Backend Application
Job Application Management System with Smart Form Filling
"""

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
    ]
    with engine.begin() as conn:
        for col_name, col_type in new_cols:
            if col_name not in existing_cols:
                conn.execute(text(f"ALTER TABLE applications ADD COLUMN {col_name} {col_type}"))
                logger.info(f"Migrated: added column applications.{col_name}")

_migrate_applications_table()

# Create FastAPI app
app = FastAPI(
    title="OfferClaw",
    description="Job Application Management System with Smart Form Filling",
    version="1.0.0"
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allow all origins for development
    allow_credentials=True,
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