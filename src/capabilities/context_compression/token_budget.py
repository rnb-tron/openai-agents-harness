"""TokenBudgetTruncate - 零开销裁剪策略

策略:
1. 识别 enriched_input 中的 "User:\\n<current>" 锚点, 把当前用户输入与历史隔离
2. 历史部分按 "\\n" 切行, 从最老开始整行丢弃, 直到总 tokens <= budget
3. 当前用户输入必保留
4. budget 极小(< 当前 input)时, 只保留当前 input 并 warning 一次

不调用 LLM, 不需要 Redis, 适合做兜底。
"""

from __future__ import annotations

import time

from src.capabilities.context_compression.base import (
    CompressionResult,
    CompressionStrategy,
)
from src.capabilities.context_compression.token_utils import count_tokens
from src.capabilities.plugin import RunContext
from src.core.logging import setup_logger

logger = setup_logger("capabilities.context_compression.token_budget")


# 与 MemoryCapability.before_run 中拼接的格式保持一致
_USER_ANCHOR = "\nUser:\n"


def _split_history_and_current(text: str) -> tuple[str, str]:
    """把 enriched_input 拆成 (history_block, current_block)

    优先用 ``"\\nUser:\\n"`` 锚点 (MemoryCapability 拼接的格式);
    若不存在则视全文为当前输入, 历史为空。
    """
    idx = text.rfind(_USER_ANCHOR)
    if idx == -1:
        return "", text
    history = text[:idx]
    current = text[idx + 1:]  # 保留 "User:\n..." 部分本身
    return history, current


class TokenBudgetTruncate(CompressionStrategy):
    """按 token 预算丢弃历史行的简单策略"""

    name = "token_budget"

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
        current_tokens = count_tokens(current)

        # 边界 1: 当前输入自己就超 budget, 只保留当前
        if current_tokens >= budget_tokens:
            logger.warning(
                "current_input_exceeds_budget",
                extra={
                    "session_id": ctx.session_id,
                    "current_tokens": current_tokens,
                    "budget_tokens": budget_tokens,
                },
            )
            return CompressionResult(
                text=current,
                input_tokens=input_tokens,
                output_tokens=current_tokens,
                strategy=self.name,
                fallback_used=True,
                duration_ms=int((time.perf_counter() - start) * 1000),
            )

        # 整行从老到新丢弃直到达标
        history_lines = history.split("\n") if history else []
        # 跳过第一行 "Conversation memory:" 这种段标头? - 不区分, 一并丢, 不影响语义
        # 维护一个滑动起点 idx, 反复测算
        drop_idx = 0
        while drop_idx < len(history_lines):
            kept_history = "\n".join(history_lines[drop_idx:])
            candidate = (kept_history + "\n" + current) if kept_history else current
            if count_tokens(candidate) <= budget_tokens:
                output_text = candidate
                break
            drop_idx += 1
        else:
            # 全部历史都丢光仍然超? 此时只剩 current, 上面边界 1 已覆盖,
            # 但浮点估算偶有偏差, 兜底取 current
            output_text = current

        output_tokens = count_tokens(output_text)
        return CompressionResult(
            text=output_text,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            strategy=self.name,
            duration_ms=int((time.perf_counter() - start) * 1000),
        )
