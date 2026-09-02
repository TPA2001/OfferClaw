"""
用户账号模型

网页服务多租户模式：每个注册用户一个账号，
业务数据（投递记录/画像/日志/Agent会话）通过 user_id 关联隔离。
"""

from sqlalchemy import Column, String, DateTime, Boolean, Integer
from sqlalchemy.sql import func
import uuid

from app.core.database import Base


def _uuid_str() -> str:
    """生成 UUID 字符串（与其他表保持一致，兼容 SQLite）"""
    return str(uuid.uuid4())


class User(Base):
    """用户账号表"""
    __tablename__ = "users"

    id = Column(String(36), primary_key=True, default=_uuid_str)

    # 登录名（唯一）
    username = Column(String(64), unique=True, nullable=False, index=True)
    # 邮箱（唯一，用于找回密码）
    email = Column(String(255), unique=True, nullable=False, index=True)

    # 密码哈希（pbkdf2_sha256$iterations$salt$digest 格式）
    password_hash = Column(String(255), nullable=False)

    # Token 版本号：修改/重置密码时 +1，使所有旧 JWT 立即失效
    token_version = Column(Integer, nullable=False, default=0)

    # 找回密码：重置令牌哈希 + 过期时间（令牌原文只出现一次，不落库）
    reset_token_hash = Column(String(64), nullable=True)
    reset_token_expires_at = Column(DateTime(timezone=True), nullable=True)

    # 账号可用开关（封禁/停用时置 False）
    is_active = Column(Boolean, nullable=False, default=True)

    # 角色：user=普通用户 / admin=管理员
    # server_default 确保既有行在 auto_migrate ADD COLUMN 时回填 "user"
    role = Column(String(20), nullable=False, default="user", server_default="user")

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
