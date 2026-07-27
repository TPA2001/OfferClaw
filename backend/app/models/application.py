"""
投递记录模型
"""

from sqlalchemy import Column, String, DateTime, Text, Integer, JSON
from sqlalchemy.sql import func
import uuid

from app.core.database import Base


def _uuid_str() -> str:
    """生成 UUID 字符串"""
    return str(uuid.uuid4())


class Application(Base):
    """投递记录表"""
    __tablename__ = "applications"

    # 用 String(36) 而非 UUID 类型，兼容 SQLite + 任意字符串 user_id
    id = Column(String(36), primary_key=True, default=_uuid_str)
    user_id = Column(String(64), nullable=False, index=True)

    # 基本信息
    company = Column(String(200), nullable=False, index=True)
    position = Column(String(200), nullable=False)
    job_url = Column(Text, nullable=True)
    source = Column(String(50), nullable=True)  # 来源：boss/直聘/官网/内推/校招

    # 状态：applied/assessment/interview/offer/rejected/withdrawn
    status = Column(String(20), default="applied", nullable=False, index=True)

    # === 细化字段（校招/社招场景）===

    # 拒绝环节（仅 status=rejected 时使用）
    # resume_rejected=简历初筛挂 / assessment_failed=笔试挂 /
    # interview_1_failed=一面挂 / interview_2_failed=二面挂 /
    # interview_3_failed=三面挂 / hr_failed=HR面挂 /
    # offer_collapsed=offer谈崩 / hc_empty=HC没有 / other=其他
    rejection_stage = Column(String(30), nullable=True)

    # 当前面试轮次（仅 status=interview 时使用，1=一面 2=二面 3=三面 4=HR面）
    interview_round = Column(Integer, nullable=True)

    # 下一面试时间（用于倒计时提醒）
    next_interview_at = Column(DateTime(timezone=True), nullable=True)

    # 笔试截止时间（仅 status=assessment 时使用，很多公司笔试有 deadline）
    assessment_deadline = Column(DateTime(timezone=True), nullable=True)

    # offer 状态（仅 status=offer 时使用）
    # pending=待回复 / accepted=已接受 / declined=已拒绝offer
    offer_status = Column(String(20), nullable=True)

    # offer 详情（薪资范围/工作地点/签约 deadline/HR 联系方式）
    offer_salary = Column(String(100), nullable=True)        # 如 "25k×16" 或 "30-35k"
    offer_location = Column(String(100), nullable=True)       # 工作地点
    offer_deadline = Column(DateTime(timezone=True), nullable=True)  # 签约最后期限
    hr_contact = Column(String(200), nullable=True)           # HR 联系方式（微信/电话/邮箱）

    # 优先级：high=心仪/必拿 / medium=普通 / low=备选
    priority = Column(String(10), default="medium", nullable=False)

    # 时间节点
    applied_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # 备注
    notes = Column(Text, nullable=True)
    tags = Column(String(500), nullable=True)  # 逗号分隔的标签

    # 排序
    sort_order = Column(Integer, default=0)

    # 状态变更历史（JSON 数组，记录每次状态变更的时间/旧状态/新状态/备注）
    # 示例: [{"at":"2026-07-22T10:00:00Z","from":"applied","to":"assessment","note":"收到笔试通知"}]
    status_history = Column(JSON, nullable=True, default=list)


class AgentSession(Base):
    """Agent 会话表 - 持久化对话历史"""
    __tablename__ = "agent_sessions"

    id = Column(String(36), primary_key=True, default=_uuid_str)
    user_id = Column(String(64), nullable=False, index=True)

    title = Column(String(200), nullable=True)  # 会话标题（由首条消息生成）
    messages = Column(Text, nullable=False, default="[]")  # JSON 序列化的消息列表

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
