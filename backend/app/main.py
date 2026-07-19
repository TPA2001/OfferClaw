"""
OfferClaw Backend Application
Job Application Management System with Smart Form Filling
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import logging

from app.core.database import engine, Base
from app.api import profile, autofill, resume, jobs, applications, subscription, agent, automation

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger("offerclaw")

# Create database tables
Base.metadata.create_all(bind=engine)
logger.info("Database tables created")

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
app.include_router(profile.router)
app.include_router(autofill.router)
app.include_router(resume.router)
app.include_router(jobs.router)
app.include_router(applications.router)
app.include_router(subscription.router)
app.include_router(agent.router)
app.include_router(automation.router)  # Smart form filling


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
            "automation": "available"
        }
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)