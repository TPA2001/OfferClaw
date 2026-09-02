"""
管理员审计日志模型

记录所有管理后台的写操作（用户管理 / 内容审核），
actor / action / target 全链路留痕，便于事后追溯与合规。
create_all 自动建表，不影响既有表。
"""

from sqlalchemy import Column, String, Text, DateTime
from sqlalchemy.sql import func
import uuid

from app.core.database import Base


def _uuid_str() -> str:
    return str(uuid.uuid4())


class AdminAuditLog(Base):
    """管理员操作审计日志"""

    __tablename__ = "admin_audit_logs"

    id = Column(String(36), primary_key=True, default=_uuid_str)

    # 操作者
    actor_id = Column(String(64), nullable=False, index=True)
    actor_username = Column(String(64), nullable=False)

    # 操作语义，如 user.disable / post.hide / report.handle
    action = Column(String(64), nullable=False, index=True)

    # 操作目标：user / post / jobshare / comment / report
    target_type = Column(String(20), nullable=False)
    target_id = Column(String(64), nullable=True)

    # 诊断信息快照（JSON 字符串或简述）
    detail = Column(Text, nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)
