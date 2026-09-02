"""
长期记忆存储层：CRUD + 双层检索（关键词过滤 + 向量余弦）

多租户隔离：所有查询必须以 user_id 过滤，绝不跨用户。
检索策略：候选集（租户 + 可选记忆类型 + 可选关键词 LIKE）内，
对 query 做「关键词重叠分 + 向量余弦」加权排序，取 Top-K。
纯 Python 实现余弦，不引入 numpy，避免新增依赖。
"""

import json
import math
import re
from typing import Optional

from sqlalchemy.orm import Session

from app.models.memory import UserMemory, MEMORY_TYPES
from app.core.log_utils import get_logger

logger = get_logger("offercabin.agent.memory.store")


# ============ 文本工具 ============

def tokenize(text: str) -> list[str]:
    """轻量查询分词：拉丁词 + 中文 2/3-gram"""
    text = text or ""
    words = re.findall(r"[a-zA-Z0-9]+", text.lower())
    cjk = [c for c in text if "\u4e00" <= c <= "\u9fff"]
    bi = ["".join(cjk[i:i + 2]) for i in range(len(cjk) - 1)]
    tri = ["".join(cjk[i:i + 3]) for i in range(len(cjk) - 2)]
    return words + tri + bi


def _cosine(a: Optional[str], b: Optional[list[float]]) -> float:
    """向量余弦相似度；embedding 为 JSON 文本，此处解析"""
    if not a or not b:
        return 0.0
    try:
        av = json.loads(a)
    except (json.JSONDecodeError, TypeError):
        return 0.0
    if not av or len(av) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(av, b))
    na = math.sqrt(sum(x * x for x in av))
    nb = math.sqrt(sum(x * x for x in b))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


def _keyword_score(tokens: set[str], content: str) -> float:
    """内容中命中 query token 的比重（0~1）"""
    if not tokens or not content:
        return 0.0
    hits = sum(1 for t in tokens if t in content)
    return hits / len(tokens)


def _combined_score(row: UserMemory, tokens: set[str], query_vec: Optional[list[float]]) -> float:
    kw = _keyword_score(tokens, row.content or "")
    vec = _cosine(row.embedding, query_vec)
    if tokens and query_vec:
        return 0.5 * kw + 0.5 * vec
    if query_vec:
        return vec
    return kw


# ============ 记忆 CRUD ============

def create_memory(
    db: Session,
    user_id: str,
    memory_type: str,
    content: str,
    embedding: Optional[str] = None,
    metadata: Optional[dict] = None,
    source: Optional[str] = None,
) -> UserMemory:
    """写入一条记忆（multitenant：始终带 user_id）"""
    if memory_type not in MEMORY_TYPES:
        raise ValueError(f"非法 memory_type: {memory_type}")
    row = UserMemory(
        user_id=user_id,
        memory_type=memory_type,
        content=content,
        embedding=embedding,
        meta=metadata or {},
        source=source,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def get_memory(db: Session, user_id: str, memory_id: str) -> Optional[UserMemory]:
    return db.query(UserMemory).filter(
        UserMemory.id == memory_id,
        UserMemory.user_id == user_id,
    ).first()


def list_memories(
    db: Session,
    user_id: str,
    memory_type: Optional[str] = None,
    limit: int = 20,
) -> list[UserMemory]:
    q = db.query(UserMemory).filter(UserMemory.user_id == user_id)
    if memory_type:
        if memory_type not in MEMORY_TYPES:
            raise ValueError(f"非法 memory_type: {memory_type}")
        q = q.filter(UserMemory.memory_type == memory_type)
    return q.order_by(UserMemory.updated_at.desc().nullslast()).limit(limit).all()


def delete_memory(db: Session, user_id: str, memory_id: str) -> bool:
    row = get_memory(db, user_id, memory_id)
    if not row:
        return False
    db.delete(row)
    db.commit()
    return True


# ============ 双层检索 ============

def search_memories(
    db: Session,
    user_id: str,
    query: str,
    top_k: int = 5,
    memory_type: Optional[str] = None,
) -> list[tuple[UserMemory, float]]:
    """
    双层记忆检索：
    1. 关键词 LIKE 粗筛子集
    2. 检索结果按（关键词重叠 + 向量余弦）加权排序取 Top-K
    """
    tokens = set(tokenize(query))
    query_vec = None
    if tokens:
        from .embedding import get_embedder
        query_vec = get_embedder().embed(query)

    q = db.query(UserMemory).filter(UserMemory.user_id == user_id)
    if memory_type:
        if memory_type not in MEMORY_TYPES:
            raise ValueError(f"非法 memory_type: {memory_type}")
        q = q.filter(UserMemory.memory_type == memory_type)

    candidates = q.limit(300).all()
    # 关键词粗筛：命中任意 token 或 content 为空时兜底保留最近若干条
    if tokens:
        filtered = [r for r in candidates if _keyword_score(tokens, r.content or "") > 0]
        if len(filtered) < top_k:
            # 候选不足时，回退到全部候选按综合分排序，保证永远能返回
            filtered = candidates
    else:
        filtered = candidates

    scored = [(r, _combined_score(r, tokens, query_vec)) for r in filtered]
    scored.sort(key=lambda x: x[1], reverse=True)
    return scored[:top_k]