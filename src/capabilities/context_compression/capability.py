"""ContextCompressionCapability - 上下文压缩能力主体

接入点: ``BEFORE_RUN`` 钩子, 在 ``MemoryCapability`` 之后。
读取 ``ctx.selected_model`` 算预算, 选定策略压缩 ``ctx.enriched_input``,
把指标写到 ``ctx.metadata["compression"]``。

失败 fail-open: 默认压缩失败不阻塞主流程, 保留上一阶段 enriched_input。
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING
from typing import Any

from src.capabilities.context_compression.base import (
    CompressionResult,
    CompressionStrategy,
)
from src.capabilities.context_compression.hybrid import HybridStrategy
from src.capabilities.context_compression.rolling_summary import RollingSummary
from src.capabilities.context_compression.token_budget import TokenBudgetTruncate
from src.capabilities.context_compression.token_utils import count_tokens
from src.capabilities.model_routing.router import ModelRouter
from src.capabilities.plugin import Capability, RunContext
from src.core.logging import setup_logger
from src.harness.manifest import CapabilityKind, CapabilityManifest

if TYPE_CHECKING:
    from src.capabilities.prompt.manager import PromptManager

logger = setup_logger("capabilities.context_compression.capability")


_STRATEGY_TOKEN_BUDGET = "token_budget"
_STRATEGY_ROLLING_SUMMARY = "rolling_summary"
_STRATEGY_HYBRID = "hybrid"


class ContextCompressionCapability(Capability):
    name = "context_compression"
    manifest = CapabilityManifest(
        name="context_compression",
        kind=CapabilityKind.RUNTIME,
        config_section="compression",
        depends_on=("model_router", "conversation_context"),
        provides=("compressed_context",),
        install_order=30,
    )

    def __init__(
        self,
        strategy: CompressionStrategy,
        model_router: ModelRouter,
        *,
        enabled: bool,
        safety_ratio: float,
        fail_open: bool,
    ) -> None:
        self._strategy = strategy
        self._model_router = model_router
        self._enabled = enabled
        self._safety_ratio = safety_ratio
        self._fail_open = fail_open

    @classmethod
    def from_settings(
        cls,
        settings,
        model_router: ModelRouter,
        prompt_manager: "PromptManager | None" = None,
    ) -> "ContextCompressionCapability":
        strategy_name = (settings.compression_strategy or _STRATEGY_TOKEN_BUDGET).lower()
        if strategy_name == _STRATEGY_HYBRID:
            strategy: CompressionStrategy = HybridStrategy.from_settings(
                settings,
                prompt_manager=prompt_manager,
            )
        elif strategy_name == _STRATEGY_ROLLING_SUMMARY:
            strategy = RollingSummary.from_settings(
                settings,
                prompt_manager=prompt_manager,
            )
        else:
            strategy = TokenBudgetTruncate()

        return cls(
            strategy=strategy,
            model_router=model_router,
            enabled=settings.compression_enabled,
            safety_ratio=settings.compression_safety_ratio,
            fail_open=settings.compression_fail_open,
        )

    def is_enabled(self) -> bool:
        return self._enabled

    async def before_run(self, ctx: RunContext) -> None:
        if not self._enabled:
            return

        start = time.perf_counter()
        try:
            model = ctx.selected_model or self._model_router.default_model
            budget = self._model_router.get_input_budget(model, self._safety_ratio)
            input_tokens = count_tokens(ctx.enriched_input)

            if budget <= 0:
                # 异常配置, 不动 enriched_input, 写 metadata 留痕
                ctx.metadata["compression"] = {
                    "strategy": self._strategy.name,
                    "skipped": "non_positive_budget",
                    "input_tokens": input_tokens,
                    "model": model,
                }
                return

            if input_tokens <= budget:
                ctx.metadata["compression"] = {
                    "strategy": self._strategy.name,
                    "skipped": "within_budget",
                    "input_tokens": input_tokens,
                    "output_tokens": input_tokens,
                    "budget_tokens": budget,
                    "compress_ratio": 1.0,
                    "fallback_used": False,
                    "summary_calls": 0,
                    "cache_hit": False,
                    "duration_ms": int((time.perf_counter() - start) * 1000),
                    "model": model,
                }
                return

            result: CompressionResult = await self._strategy.compress(
                ctx.enriched_input, budget_tokens=budget, ctx=ctx
            )
            ctx.enriched_input = result.text
            payload: dict[str, Any] = result.to_dict()
            payload["budget_tokens"] = budget
            payload["model"] = model
            ctx.metadata["compression"] = payload

            logger.info(
                "context_compressed",
                extra={
                    "session_id": ctx.session_id,
                    "strategy": result.strategy,
                    "input_tokens": result.input_tokens,
                    "output_tokens": result.output_tokens,
                    "compress_ratio": result.compress_ratio,
                    "fallback_used": result.fallback_used,
                    "cache_hit": result.cache_hit,
                    "summary_calls": result.summary_calls,
                    "duration_ms": result.duration_ms,
                },
            )
        except Exception as exc:
            logger.warning(
                "context_compression_failed",
                extra={
                    "session_id": ctx.session_id,
                    "error_type": type(exc).__name__,
                    "error": str(exc),
                },
            )
            ctx.metadata["compression"] = {
                "strategy": self._strategy.name,
                "skipped": "exception",
                "error_type": type(exc).__name__,
                "fallback_used": True,
            }
            if not self._fail_open:
                raise
