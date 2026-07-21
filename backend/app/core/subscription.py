"""Subscription manager"""
from sqlalchemy.orm import Session


class SubscriptionManager:
    """Subscription management"""
    
    def __init__(self, db: Session):
        self.db = db
    
    def check_permission(self, user_id: str, feature: str) -> bool:
        """Check if user has permission for a feature"""
        # Mock implementation - always return True for demo
        return True
    
    def increment_usage(self, user_id: str, feature: str):
        """Increment usage count for a feature"""
        pass