"""
长期记忆与画像演化模块（Phase 1）

对外能力：
- store.search_memories         双层记忆检索
- evolution.trigger_evolution   画像变更 → 记忆演化（后台）
- retrieval.assemble_...        记忆注入 System Prompt
- embedding.get_embedder        嵌入 provider
"""

from .schema import MemoryCreate, MemoryRecord, EvolutionResult
from . import store, evolution, retrieval, embedding

__all__ = [
    "MemoryCreate",
    "MemoryRecord",
    "EvolutionResult",
    "store",
    "evolution",
    "retrieval",
    "embedding",
]