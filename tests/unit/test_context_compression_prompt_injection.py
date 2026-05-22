from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.capabilities.context_compression.rolling_summary import RollingSummary
from src.capabilities.plugin import RunContext


def _settings():
    return SimpleNamespace(
        compression_summary_model="gpt-4o-mini",
        compression_summary_max_tokens=128,
        compression_keep_recent_turns=2,
        compression_cache_ttl_sec=0,
        agent_model_default="gpt-4o-mini",
        openai_api_key="sk-test",
        openai_base_url=None,
    )


def _long_text() -> str:
    lines = ["Conversation memory:"]
    for i in range(20):
        role = "user" if i % 2 == 0 else "assistant"
        lines.append(f"{role}: line-{i} " + ("payload " * 8))
    lines.append("")
    lines.append("User:")
    lines.append("continue")
    return "\n".join(lines)


@pytest.mark.asyncio
async def test_rolling_summary_uses_injected_prompt_manager():
    prompt_manager = MagicMock()
    prompt_manager.get = AsyncMock(
        return_value=SimpleNamespace(text="CUSTOM SUMMARY SYSTEM PROMPT")
    )
    strategy = RollingSummary.from_settings(_settings(), prompt_manager=prompt_manager)

    fake_resp = MagicMock()
    fake_resp.choices = [MagicMock(message=MagicMock(content="SUMMARY"))]
    fake_client = MagicMock()
    fake_client.chat = MagicMock()
    fake_client.chat.completions = MagicMock()
    fake_client.chat.completions.create = AsyncMock(return_value=fake_resp)

    with patch(
        "src.capabilities.context_compression.rolling_summary.AsyncOpenAI",
        return_value=fake_client,
    ), patch(
        "src.infrastructure.redis_client.get_redis_client",
        return_value=None,
    ):
        await strategy.compress(
            _long_text(),
            budget_tokens=120,
            ctx=RunContext(session_id="s1", user_input="continue"),
        )

    prompt_manager.get.assert_awaited_once_with("capabilities.summary")
    messages = fake_client.chat.completions.create.await_args.kwargs["messages"]
    assert messages[0]["content"] == "CUSTOM SUMMARY SYSTEM PROMPT"
