"""
文本嵌入抽象（本地优先，零外部依赖）

Phase 1 采用确定性 HashEmbedder：
- 无需任何 API Key，无网也能用（满足 Mock 降级）
- 输出稳定，测试可复现
- 基于字符 bag + MD5 高维投影，配合关键词过滤，检索质量对当前记忆量级足够

后续可无侵入替换为远程 embedding（如复用 agent provider 的 /embeddings 端点），
只需换掉 get_embedder() 的返回实现即可，调用方不感知。
"""

import hashlib
import math
from abc import ABC, abstractmethod
from typing import Optional

from app.core.log_utils import get_logger

logger = get_logger("offercabin.agent.memory.embedding")

EMBEDDING_DIM = 64


class EmbeddingProvider(ABC):
    """嵌入抽象"""
    name: str = "base"

    @abstractmethod
    def embed(self, text: str) -> list[float]:
        """将文本映射为归一化 float 向量"""
        ...


class HashEmbedder(EmbeddingProvider):
    """确定性 hash 嵌入（Mock 降级）"""

    name = "hash"
    dim = EMBEDDING_DIM

    def embed(self, text: str) -> list[float]:
        text = text or ""
        vec = [0.0] * self.dim
        # 字符加权累加：字符越靠前权重越大，并做位置区分
        for i, ch in enumerate(text):
            h = int(hashlib.md5(f"{i}:{ch}".encode("utf-8")).hexdigest(), 16)
            vec[h % self.dim] += 1.0 / (1 + i)
        norm = math.sqrt(sum(x * x for x in vec)) or 1.0
        return [round(v / norm, 6) for v in vec]


_embedder: Optional[EmbeddingProvider] = None


def get_embedder() -> EmbeddingProvider:
    """获取全局嵌入 provider（单例）"""
    global _embedder
    if _embedder is None:
        _embedder = HashEmbedder()
    return _embedder