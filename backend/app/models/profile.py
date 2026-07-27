"""
用户画像模型
存储用户的个人信息，用于智能填写
"""

from sqlalchemy import Column, String, DateTime
from sqlalchemy.dialects.sqlite import JSON
from sqlalchemy.sql import func
import uuid

from app.core.database import Base


def _uuid_str() -> str:
    """生成 UUID 字符串（与 Application 表保持一致，兼容 SQLite）"""
    return str(uuid.uuid4())


class Profile(Base):
    """用户画像表"""
    __tablename__ = "profiles"

    # 用 String(36) 而非 UUID 类型，兼容 SQLite + 任意字符串 user_id
    id = Column(String(36), primary_key=True, default=_uuid_str)
    user_id = Column(String(64), unique=True, nullable=False, index=True)

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

    # 项目经历
    projects = Column(JSON, default=[])
    # [
    #   {
    #     "name": "OfferClaw 求职管理系统",
    #     "role": "全栈开发",
    #     "start_date": "2024-01",
    #     "end_date": "2024-06",
    #     "description": "基于 FastAPI + Playwright 实现的求职管理工具...",
    #     "tech_stack": ["Python", "FastAPI", "Vue"]
    #   }
    # ]

    # 自我评价 / 个人简介
    summary = Column(JSON, default={})
    # {
    #   "self_eval": "5 年后端开发经验，熟悉分布式系统设计...",
    #   "advantage": "主导过百万级 QPS 系统的架构设计",
    #   "career_goal": "希望成长为技术专家..."
    # }

    # 证书 / 荣誉
    certifications = Column(JSON, default=[])
    # [
    #   {
    #     "name": "PMP 项目管理认证",
    #     "issuer": "PMI",
    #     "date": "2023-06",
    #     "score": ""
    #   }
    # ]

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