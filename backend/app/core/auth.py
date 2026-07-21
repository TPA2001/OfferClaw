"""Authentication module"""
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

security = HTTPBearer()


def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)) -> str:
    """
    Get current user ID from token
    
    Returns:
        str: User ID
    """
    # Mock implementation for demo
    # In production, validate JWT token here
    token = credentials.credentials
    
    # For demo, return a mock user ID
    return "demo-user-123"