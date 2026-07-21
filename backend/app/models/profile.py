"""
用户画像模型
存储用户的个人信息，用于智能填写
"""

from sqlalchemy import Column, String, DateTime
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.dialects.sqlite import JSON
from sqlalchemy.sql import func
import uuid

from app.core.database import Base


class Profile(Base):
    """用户画像表"""
    __tablename__ = "profiles"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), unique=True, nullable=False, index=True)

    # 基本信息
    basic_info = Column(JSON, default={})
    # {
    #   "name": "张三",
    #   "phone": "13800138000",
    #   "email": "zhangsan@example.com",
    #   "gender": "男",
    #   "birth": "1995-01-01",
    #   "id_number": "310...",  # 敏感信息，仅本地存储
    #   "home_address": "上海市..."  # 敏感信息，仅本地存储
    # }

    # 教育经历
    education = Column(JSON, default=[])
    # [
    #   {
    #     "school": "清华大学",
    #     "major": "计算机科学与技术",
    #     "degree": "本科",
    #     "start_date": "2013-09",
    #     "end_date": "2017-07"
    #   }
    # ]

    # 工作经历
    experience = Column(JSON, default=[])
    # [
    #   {
    #     "company": "阿里巴巴",
    #     "title": "高级工程师",
    #     "start_date": "2017-08",
    #     "end_date": "2020-06",
    #     "description": "负责..."
    #   }
    # ]

    # 技能列表
    skills = Column(JSON, default=[])
    # ["Python", "Java", "MySQL", "Docker"]

    # 求职意向
    job_intent = Column(JSON, default={})
    # {
    #   "role": "高级软件工程师",
    #   "cities": ["上海", "北京", "深圳"],
    #   "salary_min": 30000,
    #   "salary_max": 50000,
    #   "job_type": "全职"
    # }

    # 自定义字段（用于存储额外信息）
    extra_fields = Column(JSON, default={})

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())