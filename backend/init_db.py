"""Database initialization script"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.core.database import engine, Base

# Import all models to register them
from app.models.profile import Profile
from app.models.application import Application, AgentSession

print("Creating database tables...")
Base.metadata.create_all(bind=engine)
print("✓ Database tables created successfully!")
print("  - profiles")
print("  - applications")
print("  - agent_sessions")