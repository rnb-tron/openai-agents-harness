"""RollingSummary - LLM 滚动摘要策略

把历史拆成 (老消息 + 近 K 轮原文), 用 LLM 把老消息压成 summary,
通过 Redis 缓存避免重复压同一段。

失败兜底:
- LLM 失败 -> 抛 ``SummaryError``, 由 Hybrid 接住降级到 Truncate
- Redis 不可用 -> 跳过缓存, 直连 LLM
- ``compression_cache_ttl_sec=0`` -> 不写缓存
"""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING

from openai import AsyncOpenAI

from src.capabilities.context_compression.base import (
    CompressionResult,
    CompressionStrategy,
)
from src.capabilities.context_compression.token_budget import _split_history_and_current
from src.capabilities.context_compression.token_utils import count_tokens
from src.capabilities.plugin import RunContext
from src.core.logging import setup_logger

if TYPE_CHECKING:
    from src.capabilities.prompt.manager import PromptManager

logger = setup_logger("capabilities.context_compression.rolling_summary")


_SUMMARY_HEADER = "[Summary of earlier conversation]\n"
_SYSTEM_PROMPT = (
    "You are a precise conversation summarizer. Compress the prior dialogue "
    "while preserving: user identity, goals, hard constraints, confirmed facts, "
    "open todos, tool-call results. Skip pleasantries. Output plain text only."
)


class SummaryError(RuntimeError):
    """RollingSummary 失败的统一异常 (供 Hybrid 捕获降级)"""


@dataclass
class _SummaryConfig:
    summary_model: str
    summary_max_tokens: int
    keep_recent_turns: int
    cache_ttl_sec: int
    openai_api_key: str
    openai_base_url: str | None


class RollingSummary(CompressionStrategy):
    """LLM 滚动摘要 + Redis 缓存"""

    name = "rolling_summary"

    def __init__(
        self,
        config: _SummaryConfig,
        prompt_manager: "PromptManager | None" = None,
    ) -> None:
        self._cfg = config
        self._prompt_manager = prompt_manager

    # 工厂方法, 与 Capability.from_settings 配套
    @classmethod
    def from_settings(
        cls,
        settings,
        prompt_manager: "PromptManager | None" = None,
    ) -> "RollingSummary":
        cfg = _SummaryConfig(
            summary_model=settings.compression_summary_model or settings.agent_model_default,
            summary_max_tokens=settings.compression_summary_max_tokens,
            keep_recent_turns=settings.compression_keep_recent_turns,
            cache_ttl_sec=settings.compression_cache_ttl_sec,
            openai_api_key=settings.openai_api_key,
            openai_base_url=settings.openai_base_url,
        )
        return cls(cfg, prompt_manager=prompt_manager)

    async def compress(
        self,
        text: str,
        *,
        budget_tokens: int,
        ctx: RunContext,
    ) -> CompressionResult:
        start = time.perf_counter()
        input_tokens = count_tokens(text)
        if input_tokens <= budget_tokens:
            return CompressionResult(
                text=text,
                input_tokens=input_tokens,
                output_tokens=input_tokens,
                strategy=self.name,
                duration_ms=int((time.perf_counter() - start) * 1000),
            )

        history, current = _split_history_and_current(text)
        history_lines = [line for line in history.split("\n") if line.strip()]
        # 跳过段标头 (如 "Conversation memory:")
        if history_lines and history_lines[0].endswith(":") and ":" not in history_lines[0][:-1]:
            history_lines = history_lines[1:]

        keep_lines = self._cfg.keep_recent_turns * 2
        if len(history_lines) <= keep_lines:
            # 历史不够长, 直接返回原文 (上层 Hybrid 会再用 Truncate 兜)
            return CompressionResult(
                text=text,
                input_tokens=input_tokens,
                output_tokens=input_tokens,
                strategy=self.name,
                duration_ms=int((time.perf_counter() - start) * 1000),
            )

        old_lines = history_lines[:-keep_lines]
        recent_lines = history_lines[-keep_lines:]
        old_block = "\n".join(old_lines)

        # 1) 查缓存
        cache_key = self._cache_key(ctx.session_id, old_block)
        summary, cache_hit = await self._load_cache(cache_key)

        # 2) miss -> 调 LLM
        summary_calls = 0
        if summary is None:
            try:
                summary = await self._summarize(old_block)
                summary_calls = 1
            except Exception as exc:
                logger.warning(
                    "rolling_summary_llm_failed",
                    extra={
                        "session_id": ctx.session_id,
                        "error_type": type(exc).__name__,
                        "error": str(exc),
                    },
                )
                raise SummaryError(str(exc)) from exc
            # 写缓存 (失败仅日志, 不阻塞)
            await self._save_cache(cache_key, summary)

        # 3) 拼接
        recent_block = "\n".join(recent_lines)
        rebuilt = (
            "Conversation memory:\n"
            f"{_SUMMARY_HEADER}{summary}\n\n"
            f"{recent_block}\n"
            f"{current}"
        )

        output_tokens = count_tokens(rebuilt)
        return CompressionResult(
            text=rebuilt,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            strategy=self.name,
            summary_calls=summary_calls,
            cache_hit=cache_hit,
            duration_ms=int((time.perf_counter() - start) * 1000),
        )

    # ---------------- 内部 ----------------

    @staticmethod
    def _cache_key(session_id: str, old_block: str) -> str:
        digest = hashlib.sha1(old_block.encode("utf-8")).hexdigest()[:16]
        return f"ck:compress:summary:{session_id}:{digest}"

    async def _load_cache(self, key: str) -> tuple[str | None, bool]:
        try:
            from src.infrastructure.redis_client import get_redis_client

            client = get_redis_client(for_write=False)
            if client is None:
                return None, False
            value = await client.get(key)
            if value:
                return value, True
            return None, False
        except Exception as exc:
            logger.warning("rolling_summary_cache_read_failed", extra={"error": str(exc)})
            return None, False

    async def _save_cache(self, key: str, value: str) -> None:
        if self._cfg.cache_ttl_sec <= 0:
            return
        try:
            from src.infrastructure.redis_client import get_redis_client

            client = get_redis_client(for_write=True)
            if client is None:
                return
            await client.set(key, value, ex=self._cfg.cache_ttl_sec)
        except Exception as exc:
            logger.warning("rolling_summary_cache_write_failed", extra={"error": str(exc)})

    async def _summarize(self, old_block: str) -> str:
        system_prompt = _SYSTEM_PROMPT
        if self._prompt_manager is not None:
            try:
                mgr = self._prompt_manager
                rendered = await mgr.get("capabilities.summary")
                system_prompt = rendered.text
            except Exception as exc:
                logger.warning(
                    "summary_prompt_get_failed_using_fallback",
                    extra={"error_type": type(exc).__name__, "error": str(exc)},
                )

        client_kwargs: dict = {"api_key": self._cfg.openai_api_key}
        if self._cfg.openai_base_url:
            client_kwargs["base_url"] = self._cfg.openai_base_url
        client = AsyncOpenAI(**client_kwargs)

        resp = await client.chat.completions.create(
            model=self._cfg.summary_model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": old_block},
            ],
            max_tokens=self._cfg.summary_max_tokens,
            temperature=0.2,
        )
        content = resp.choices[0].message.content or ""
        return content.strip()
