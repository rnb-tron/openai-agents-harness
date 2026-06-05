"""Context Compression Capability tests.

Run:
    venv/bin/python -m tests.test_context_compression
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.capabilities.context_compression import (
    ContextCompressionCapability,
    HybridStrategy,
    RollingSummary,
    TokenBudgetTruncate,
)
from src.capabilities.model_routing.router import ModelRouter
from src.capabilities.plugin import RunContext

# ----------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------


def _make_settings(**overrides):
    defaults = dict(
        compression_enabled=True,
        compression_strategy="token_budget",
        compression_safety_ratio=0.9,
        compression_keep_recent_turns=2,
        compression_summary_model="",
        compression_summary_max_tokens=128,
        compression_cache_ttl_sec=3600,
        compression_fail_open=True,
        agent_model_default="gpt-4o-mini",
        openai_api_key="sk-test",
        openai_base_url=None,
    )
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def _make_long_enriched_input(lines: int = 200) -> str:
    """Build an enriched_input that mimics MemoryCapability output."""
    history = ["Conversation memory:"]
    for i in range(lines):
        role = "user" if i % 2 == 0 else "assistant"
        history.append(f"{role}: line-{i} " + ("filler " * 8))
    history.append("")
    history.append("User:")
    history.append("what is the latest summary?")
    return "\n".join(history)


def _make_ctx(text: str, model: str = "gpt-4o-mini") -> RunContext:
    return RunContext(
        session_id="sess-test",
        user_id="user-test",
        user_input="what is the latest summary?",
        enriched_input=text,
        selected_model=model,
    )


# ----------------------------------------------------------------------
# Tests
# ----------------------------------------------------------------------


def test_disabled_no_op() -> None:
    settings = _make_settings(compression_enabled=False)
    cap = ContextCompressionCapability.from_settings(settings, model_router=ModelRouter())
    assert cap.is_enabled() is False

    text = _make_long_enriched_input(50)
    ctx = _make_ctx(text)
    asyncio.run(cap.before_run(ctx))
    # Disabled -> enriched_input unchanged, no metadata
    assert ctx.enriched_input == text
    assert "compression" not in ctx.metadata


def test_within_budget_no_op() -> None:
    settings = _make_settings(compression_enabled=True)
    cap = ContextCompressionCapability.from_settings(settings, model_router=ModelRouter())
    text = "Conversation memory:\nuser: hi\nassistant: hello\n\nUser:\nfollow-up"
    ctx = _make_ctx(text)
    asyncio.run(cap.before_run(ctx))
    assert ctx.enriched_input == text
    meta = ctx.metadata["compression"]
    assert meta["skipped"] == "within_budget"
    assert meta["compress_ratio"] == 1.0


def test_token_budget_truncates_to_budget() -> None:
    """Force tiny budget (use unknown model + tiny ratio) and verify cap."""
    strategy = TokenBudgetTruncate()
    text = _make_long_enriched_input(200)
    ctx = _make_ctx(text)

    async def run():
        return await strategy.compress(text, budget_tokens=200, ctx=ctx)

    result = asyncio.run(run())
    assert result.output_tokens <= 200, f"output={result.output_tokens} > budget=200"
    assert result.input_tokens > result.output_tokens
    assert 0 < result.compress_ratio < 1.0
    assert result.strategy == "token_budget"


def test_token_budget_preserves_current_user_input() -> None:
    strategy = TokenBudgetTruncate()
    text = _make_long_enriched_input(200)
    ctx = _make_ctx(text)
    result = asyncio.run(strategy.compress(text, budget_tokens=200, ctx=ctx))
    # The current user_input must survive in any case
    assert "what is the latest summary?" in result.text


def test_rolling_summary_calls_llm_and_caches() -> None:
    settings = _make_settings(compression_strategy="rolling_summary")
    rs = RollingSummary.from_settings(settings)

    text = _make_long_enriched_input(100)
    ctx = _make_ctx(text)

    fake_resp = MagicMock()
    fake_resp.choices = [MagicMock(message=MagicMock(content="SUMMARY-CONTENT"))]

    fake_client = MagicMock()
    fake_client.chat = MagicMock()
    fake_client.chat.completions = MagicMock()
    fake_client.chat.completions.create = AsyncMock(return_value=fake_resp)

    cache_storage: dict[str, str] = {}
    fake_redis = MagicMock()
    fake_redis.get = AsyncMock(side_effect=lambda key: cache_storage.get(key))
    fake_redis.set = AsyncMock(side_effect=lambda key, value, ex=None: cache_storage.__setitem__(key, value))

    with (
        patch(
            "src.capabilities.context_compression.rolling_summary.AsyncOpenAI",
            return_value=fake_client,
        ),
        patch(
            "src.infrastructure.redis_client.get_redis_client",
            return_value=fake_redis,
        ),
    ):
        # First call: cache miss -> LLM called
        first = asyncio.run(rs.compress(text, budget_tokens=200, ctx=ctx))
        # Second call (same content): cache hit -> LLM NOT called again
        second = asyncio.run(rs.compress(text, budget_tokens=200, ctx=ctx))

    assert first.summary_calls == 1
    assert first.cache_hit is False
    assert "SUMMARY-CONTENT" in first.text
    assert second.summary_calls == 0
    assert second.cache_hit is True
    # OpenAI should have been called exactly once
    assert fake_client.chat.completions.create.await_count == 1


def test_rolling_summary_falls_back_to_truncate_on_llm_error() -> None:
    """Hybrid: when summary raises, fall back to truncate and stay under budget."""
    settings = _make_settings(compression_strategy="hybrid")
    strategy = HybridStrategy.from_settings(settings)

    text = _make_long_enriched_input(200)
    ctx = _make_ctx(text)

    fake_client = MagicMock()
    fake_client.chat = MagicMock()
    fake_client.chat.completions = MagicMock()
    fake_client.chat.completions.create = AsyncMock(side_effect=RuntimeError("LLM down"))

    with (
        patch(
            "src.capabilities.context_compression.rolling_summary.AsyncOpenAI",
            return_value=fake_client,
        ),
        patch(
            "src.infrastructure.redis_client.get_redis_client",
            return_value=None,  # no redis -> always miss
        ),
    ):
        result = asyncio.run(strategy.compress(text, budget_tokens=300, ctx=ctx))

    assert result.fallback_used is True, "Hybrid should mark fallback when summary fails"
    assert result.output_tokens <= 300
    assert "what is the latest summary?" in result.text


def test_redis_unavailable_still_works() -> None:
    """Redis errors must not break summary; LLM is still called, no caching."""
    settings = _make_settings(compression_strategy="rolling_summary")
    rs = RollingSummary.from_settings(settings)

    text = _make_long_enriched_input(100)
    ctx = _make_ctx(text)

    fake_resp = MagicMock()
    fake_resp.choices = [MagicMock(message=MagicMock(content="OK"))]
    fake_client = MagicMock()
    fake_client.chat = MagicMock()
    fake_client.chat.completions = MagicMock()
    fake_client.chat.completions.create = AsyncMock(return_value=fake_resp)

    def boom(*_a, **_kw):
        raise ConnectionError("redis down")

    with (
        patch(
            "src.capabilities.context_compression.rolling_summary.AsyncOpenAI",
            return_value=fake_client,
        ),
        patch(
            "src.infrastructure.redis_client.get_redis_client",
            side_effect=boom,
        ),
    ):
        result = asyncio.run(rs.compress(text, budget_tokens=200, ctx=ctx))

    assert result.summary_calls == 1
    assert result.cache_hit is False
    assert "OK" in result.text


def test_metadata_compression_injected() -> None:
    settings = _make_settings(compression_strategy="token_budget")
    cap = ContextCompressionCapability.from_settings(settings, model_router=ModelRouter())
    text = _make_long_enriched_input(400)
    ctx = _make_ctx(text, model="gpt-3.5-turbo")  # smaller window

    asyncio.run(cap.before_run(ctx))
    meta = ctx.metadata["compression"]
    # Either compressed or skipped within_budget; in both cases payload schema valid
    assert "strategy" in meta
    assert "input_tokens" in meta or "skipped" in meta
    assert meta.get("model") == "gpt-3.5-turbo"


# ----------------------------------------------------------------------
# Runner
# ----------------------------------------------------------------------

ALL_TESTS = [
    test_disabled_no_op,
    test_within_budget_no_op,
    test_token_budget_truncates_to_budget,
    test_token_budget_preserves_current_user_input,
    test_rolling_summary_calls_llm_and_caches,
    test_rolling_summary_falls_back_to_truncate_on_llm_error,
    test_redis_unavailable_still_works,
    test_metadata_compression_injected,
]


def main() -> int:
    failed = 0
    for fn in ALL_TESTS:
        try:
            fn()
            print(f"[OK]   {fn.__name__}")
        except AssertionError as e:
            failed += 1
            print(f"[FAIL] {fn.__name__}: {e}")
        except Exception as e:  # pragma: no cover
            failed += 1
            print(f"[ERR ] {fn.__name__}: {type(e).__name__}: {e}")
    print(f"\n{len(ALL_TESTS) - failed}/{len(ALL_TESTS)} passed")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
