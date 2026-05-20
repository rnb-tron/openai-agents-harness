"""HybridStrategy - 先 RollingSummary, 失败或仍超 budget 时 Truncate 兜底"""

from __future__ import annotations

import time

from src.capabilities.context_compression.base import (
    CompressionResult,
    CompressionStrategy,
)
from src.capabilities.context_compression.rolling_summary import (
    RollingSummary,
    SummaryError,
)
from src.capabilities.context_compression.token_budget import TokenBudgetTruncate
from src.capabilities.context_compression.token_utils import count_tokens
from src.capabilities.plugin import RunContext
from src.core.logging import setup_logger

logger = setup_logger("capabilities.context_compression.hybrid")


class HybridStrategy(CompressionStrategy):
    """组合策略 - 先摘要再 Truncate 兜底"""

    name = "hybrid"

    def __init__(
        self,
        summary: RollingSummary,
        truncate: TokenBudgetTruncate,
    ) -> None:
        self._summary = summary
        self._truncate = truncate

    @classmethod
    def from_settings(cls, settings) -> "HybridStrategy":
        return cls(
            summary=RollingSummary.from_settings(settings),
            truncate=TokenBudgetTruncate(),
        )

    async def compress(
        self,
        text: str,
        *,
        budget_tokens: int,
        ctx: RunContext,
    ) -> CompressionResult:
        start = time.perf_counter()
        fallback_used = False
        summary_calls = 0
        cache_hit = False

        # 第一步: 试 summary
        try:
            primary = await self._summary.compress(
                text, budget_tokens=budget_tokens, ctx=ctx
            )
            summary_calls = primary.summary_calls
            cache_hit = primary.cache_hit
            current = primary.text
        except SummaryError as exc:
            logger.warning(
                "hybrid_summary_failed_fallback_truncate",
                extra={"session_id": ctx.session_id, "error": str(exc)},
            )
            fallback_used = True
            current = text

        # 第二步: 仍超 budget -> Truncate 兜底
        if count_tokens(current) > budget_tokens:
            fallback_used = True
            tail = await self._truncate.compress(
                current, budget_tokens=budget_tokens, ctx=ctx
            )
            current = tail.text

        input_tokens = count_tokens(text)
        output_tokens = count_tokens(current)
        return CompressionResult(
            text=current,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            strategy=self.name,
            fallback_used=fallback_used,
            summary_calls=summary_calls,
            cache_hit=cache_hit,
            duration_ms=int((time.perf_counter() - start) * 1000),
        )
