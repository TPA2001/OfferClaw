"""
长期记忆检索装配：把检索结果注入 Agent System Prompt
"""

from typing import Optional

from sqlalchemy.orm import Session

from app.core.log_utils import get_logger

from . import store
from .schema import MemoryRecord

logger = get_logger("offercabin.agent.memory.retrieval")

# System Prompt 中的占位符标记（job_agent 运行时替换为真实记忆段）
MEMORY_PLACEHOLDER = "<user_long_term_memory>"

_EMPTY_BLOCK = "（暂无长期记忆；如需记住偏好可告诉我）"


def _to_record(row, score: float) -> MemoryRecord:
    return MemoryRecord(
        id=str(row.id),
        memory_type=row.memory_type,
        content=row.content,
        metadata=row.meta or {},
        source=row.source,
        created_at=row.created_at.isoformat() if row.created_at else None,
        updated_at=row.updated_at.isoformat() if row.updated_at else None,
        score=round(score, 4) if score else None,
    )


def retrieve(
    db: Session,
    user_id: str,
    query: Optional[str] = None,
    top_k: int = 5,
    memory_type: Optional[str] = None,
) -> list[MemoryRecord]:
    """基于当前 query 做双层检索，返回 Top-K 记忆"""
    query = (query or "").strip()
    hits = store.search_memories(
        db, user_id=user_id, query=query, top_k=top_k, memory_type=memory_type
    )
    return [_to_record(r, score) for r, score in hits]


def assemble_long_term_memory(
    db: Session,
    user_id: str,
    query: Optional[str] = None,
    top_k: int = 5,
) -> str:
    """
    生成 <user_long_term_memory> 段落文本（不含占位符标记本身）。

    有命中 → Markdown 列表：每条标注类型（偏好/经历/反馈），附相关度。
    无命中 → 一句占位提示，保证 System Prompt 结构完整。
    """
    records = retrieve(db, user_id, query, top_k)
    if not records:
        return _EMPTY_BLOCK

    type_label = {"preference": "偏好", "experience": "经历", "feedback": "反馈"}
    lines = [
        "以下是该用户的长期记忆（跨会话有效，请优先参考并保持一致性）：",
    ]
    for r in records:
        label = type_label.get(r.memory_type, r.memory_type)
        lines.append(f"- **{label}**：{r.content}")
    return "\n".join(lines)


def inject_into_system_prompt(system_prompt: str, memory_block: str) -> str:
    """
    把记忆段写入 system_prompt：优先替换占位符，否则追加到末尾。
    """
    if MEMORY_PLACEHOLDER in system_prompt:
        return system_prompt.replace(
            MEMORY_PLACEHOLDER, f"\n# 用户长期记忆\n```\n{memory_block}\n```"
        )
    return system_prompt + f"\n# 用户长期记忆\n```\n{memory_block}\n```"