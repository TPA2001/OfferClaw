"""
长期记忆 Pydantic 模型（类型安全）
"""

from typing import Any, Optional, Literal

from pydantic import BaseModel, Field

MemoryType = Literal["preference", "experience", "feedback"]


class MemoryCreate(BaseModel):
    """创建/写入记忆的输入"""
    memory_type: MemoryType = "preference"
    content: str = Field(..., min_length=1)
    metadata: dict[str, Any] = Field(default_factory=dict)
    source: Optional[str] = None


class MemoryRecord(BaseModel):
    """记忆条目（检索/列表输出）"""
    id: str
    memory_type: str
    content: str
    metadata: dict[str, Any] = Field(default_factory=dict)
    source: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    score: Optional[float] = None  # 检索相关度（关键词+向量加权）


class EvolutionResult(BaseModel):
    """一次画像演化产出的记忆条目"""
    memory_type: MemoryType
    content: str
    related_fields: list[str] = Field(default_factory=list)