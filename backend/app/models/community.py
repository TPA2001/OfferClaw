"""
社区 + 岗位分享模型

新增表（create_all 自动创建，不影响既有表，升级零数据丢失）：
- community_posts            社区帖子
- community_post_comments    帖子评论（支持楼中楼）
- community_job_shares       岗位分享（网申广场）
- community_user_reactions   点赞/收藏统一表（幂等：唯一约束）
- community_content_reports  用户举报表

⚠️ 重要：社区内容为【全站共享】，与业务数据（投递/画像/日志按 user_id 隔离）
不同，查询时不要加 user_id 过滤；user_id 仅用于内容归属与作者权限校验。
"""

from sqlalchemy import Column, String, DateTime, Text, Integer, UniqueConstraint
from sqlalchemy.sql import func
import uuid

from app.core.database import Base


def _uuid_str() -> str:
    """生成 UUID 字符串"""
    return str(uuid.uuid4())


class CommunityPost(Base):
    """社区帖子表"""

    __tablename__ = "community_posts"

    id = Column(String(36), primary_key=True, default=_uuid_str)
    user_id = Column(String(64), nullable=False, index=True)  # 作者（仅归属/权限校验，非数据隔离）

    title = Column(String(200), nullable=False)
    content = Column(Text, nullable=False)

    # 板块：resume=简历优化 / interview=面试经验 / offer=Offer抉择 / help=求职求助 / chat=闲聊
    category = Column(String(30), nullable=False, default="chat", index=True)

    # 状态：normal=正常 / pinned=置顶 / hidden=违规或审核中（作者可见，他人不可见）/ deleted=已删除
    status = Column(String(20), nullable=False, default="normal", index=True)

    # 计数（冗余，随 reaction 同步更新，避免每次 COUNT）
    view_count = Column(Integer, nullable=False, default=0)
    like_count = Column(Integer, nullable=False, default=0)
    comment_count = Column(Integer, nullable=False, default=0)
    collect_count = Column(Integer, nullable=False, default=0)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())


class PostComment(Base):
    """帖子评论表（parent_id 非空时为楼中楼回复）"""

    __tablename__ = "community_post_comments"

    id = Column(String(36), primary_key=True, default=_uuid_str)
    post_id = Column(String(36), nullable=False, index=True)
    user_id = Column(String(64), nullable=False, index=True)

    content = Column(Text, nullable=False)

    # 楼中楼：一级评论为 NULL，回复指向一级评论 id
    parent_id = Column(String(36), nullable=True, index=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())


class CommunityJobShare(Base):
    """岗位分享表（网申广场）"""

    __tablename__ = "community_job_shares"

    id = Column(String(36), primary_key=True, default=_uuid_str)
    user_id = Column(String(64), nullable=False, index=True)  # 分享者

    company = Column(String(200), nullable=False, index=True)
    position = Column(String(200), nullable=False)
    apply_url = Column(Text, nullable=False)  # 网申官网链接（创建时校验 http/https + 域名）
    city = Column(String(50), nullable=True)
    salary = Column(String(100), nullable=True)
    deadline = Column(DateTime(timezone=True), nullable=True, index=True)
    description = Column(Text, nullable=True)

    # 状态：normal / hidden=违规或审核中 / deleted / expired=已过期
    status = Column(String(20), nullable=False, default="normal", index=True)

    view_count = Column(Integer, nullable=False, default=0)
    click_count = Column(Integer, nullable=False, default=0)  # 跳转官网次数
    like_count = Column(Integer, nullable=False, default=0)
    collect_count = Column(Integer, nullable=False, default=0)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())


class UserReaction(Base):
    """点赞/收藏统一表

    target_type: post / jobshare
    action: like / collect
    唯一约束 (user_id, target_type, target_id, action) 保证幂等。
    """

    __tablename__ = "community_user_reactions"
    __table_args__ = (
        UniqueConstraint(
            "user_id", "target_type", "target_id", "action",
            name="uq_reaction_user_target_action",
        ),
    )

    id = Column(String(36), primary_key=True, default=_uuid_str)
    user_id = Column(String(64), nullable=False, index=True)
    target_type = Column(String(20), nullable=False)
    target_id = Column(String(36), nullable=False, index=True)
    action = Column(String(20), nullable=False)  # like / collect
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class ContentReport(Base):
    """内容举报表（达阈值自动隐藏目标内容）"""

    __tablename__ = "community_content_reports"

    id = Column(String(36), primary_key=True, default=_uuid_str)
    user_id = Column(String(64), nullable=False)
    target_type = Column(String(20), nullable=False)  # post / jobshare
    target_id = Column(String(36), nullable=False, index=True)
    reason = Column(String(200), nullable=True)

    # pending=待处理 / handled=已处理 / dismissed=不予处理
    status = Column(String(20), nullable=False, default="pending", index=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
