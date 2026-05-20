"""上下文压缩 Capability 的抽象层

设计目标:
- 定义统一的 ``CompressionStrategy`` 协议, 让 TokenBudgetTruncate /
  RollingSummary / Hybrid 等不同策略可互换
- ``CompressionResult`` 携带完整的可观测指标 (input/output tokens, ratio,
  fallback 标记, 缓存命中, 耗时), 便于注入 ``ctx.metadata`` 与日志
- 与 Capability 抽象解耦: Strategy 只负责"压一段文本", 不感知 ``RunContext``
  以外的应用细节, 便于单测
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Protocol, runtime_checkable

from src.capabilities.plugin import RunContext


@dataclass
class CompressionResult:
    """一次压缩操作的结果与指标"""

    text: str
    input_tokens: int
    output_tokens: int
    strategy: str
    compress_ratio: float = 0.0
    fallback_used: bool = False
    summary_calls: int = 0
    cache_hit: bool = False
    duration_ms: int = 0
    extra: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.compress_ratio == 0.0 and self.input_tokens > 0:
            self.compress_ratio = round(self.output_tokens / self.input_tokens, 4)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        # text 可能很大, metadata 中不重复带回, 已写入 ctx.enriched_input
        d.pop("text", None)
        return d


@runtime_checkable
class CompressionStrategy(Protocol):
    """压缩策略协议"""

    name: str

    async def compress(
        self,
        text: str,
        *,
        budget_tokens: int,
        ctx: RunContext,
    ) -> CompressionResult:
        ...
