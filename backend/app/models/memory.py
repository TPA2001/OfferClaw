"""
长期记忆与画像演化模型

Phase 1 核心：让 Agent 跨会话记住用户偏好，并在简历/画像更新时自动刷新认知。

- user_memories       长期记忆条目（向量检索 + 关键词过滤）
- profile_snapshots   画像变更快照（记录演化历史，驱动记忆更新）

设计要点：
- 均为纯新增表，由 Base.metadata.create_all 自动创建，不改动任何既有表，
  因此旧数据库可无缝加载继续使用（兼容 auto_migrate 的建表流程）。
- 全部含 user_id 外键索引，沿用现有多租户数据隔离约定。
- embedding 以 JSON 文本列存储 float[]，检索在应用层用 numpy 余弦相似度，
  避免 sqlite-vss 等外部向量库的编译/部署成本（本地优先）。
"""

import uuid
from sqlalchemy import Column, String, Text, Integer, JSON
from sqlalchemy.sql import func
from sqlalchemy import DateTime

from app.core.database import Base


def _uuid_str() -> str:
    """生成 UUID 字符串（兼容 SQLite + 任意字符串 user_id）"""
    return str(uuid.uuid4())


# memory_type 枚举取值（字符串存储，便于与旧数据/前端兼容）
MEMORY_TYPES = ("preference", "experience", "feedback")


class UserMemory(Base):
    """长期记忆条目表

    memory_type: preference(偏好/意向) / experience(经历/变化) / feedback(反馈/结论)
    content:     记忆正文（注入 System Prompt 的文本）
    embedding:   JSON float[]，用于向量检索；无 Key 时可存确定性 hash 向量
    metadata:    JSON，如 {source, related_fields, importance}
    """
    __tablename__ = "user_memories"

    id = Column(String(36), primary_key=True, default=_uuid_str)
    user_id = Column(String(64), nullable=False, index=True)

    memory_type = Column(String(20), nullable=False, default="preference", index=True)
    content = Column(Text, nullable=False)

    embedding = Column(Text, nullable=True)          # JSON float[]
    # 注：属性名用 meta 而非 metadata（SQLAlchemy 声明式保留字），DB 列名仍为 metadata
    meta = Column("metadata", JSON, nullable=True, default=dict)
    source = Column(String(30), nullable=True)       # profile_update / agent / manual

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    @property
    def embedding_vector(self) -> list | None:
        """解析 embedding 文本为 float 列表"""
        if not self.embedding:
            return None
        try:
            import json
            return json.loads(self.embedding)
        except (json.JSONDecodeError, TypeError):
            return None


class ProfileSnapshot(Base):
    """画像变更快照表

    每次检测到画像关键字段变化时写入一行，记录当时画像全量 + 变更字段，
    是触发记忆演化（evolution）的历史依据。
    """
    __tablename__ = "profile_snapshots"

    id = Column(String(36), primary_key=True, default=_uuid_str)
    user_id = Column(String(64), nullable=False, index=True)

    # 规范化画像的稳定 hash：用于判定是否发生实际变化、防止重复提炼
    profile_hash = Column(String(64), nullable=False, index=True)

    snapshot = Column(JSON, nullable=False, default=dict)      # 当时的全量画像
    changed_fields = Column(JSON, nullable=True, default=list) # 本次变更的区块
    trigger_source = Column(String(20), nullable=False, default="api")  # api / agent

    created_at = Column(DateTime(timezone=True), server_default=func.now())


# 供 create_all 感知两张新表的占位（避免 IDE 提示未使用）
__all__ = ["UserMemory", "ProfileSnapshot", "MEMORY_TYPES"]