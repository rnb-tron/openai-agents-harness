"""上下文压缩 Capability

策略可插拔:
- ``TokenBudgetTruncate``: 零开销, 从老到新丢弃
- ``RollingSummary``: LLM 滚动摘要 + Redis 缓存
- ``HybridStrategy``: 先摘要再 Truncate 兜底

入口: ``ContextCompressionCapability``, 通过 ``from_settings`` 构造。
"""

from src.capabilities.context_compression.base import (
    CompressionResult,
    CompressionStrategy,
)
from src.capabilities.context_compression.capability import ContextCompressionCapability
from src.capabilities.context_compression.hybrid import HybridStrategy
from src.capabilities.context_compression.rolling_summary import RollingSummary
from src.capabilities.context_compression.token_budget import TokenBudgetTruncate

__all__ = [
    "CompressionResult",
    "CompressionStrategy",
    "ContextCompressionCapability",
    "HybridStrategy",
    "RollingSummary",
    "TokenBudgetTruncate",
]
