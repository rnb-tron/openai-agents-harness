from types import SimpleNamespace
from unittest.mock import AsyncMock

from src.capabilities.context_compression import ContextCompressionCapability
from src.capabilities.model_routing.router import ModelRouter
from src.capabilities.plugin import RunContext
from src.capabilities.prompt import PromptCapability, UserPromptCapability


def _settings(**overrides):
    defaults = dict(
        compression_enabled=True,
        compression_strategy="token_budget",
        compression_safety_ratio=0.9,
        compression_keep_recent_turns=4,
        compression_summary_model="",
        compression_summary_max_tokens=512,
        compression_cache_ttl_sec=3600,
        compression_fail_open=True,
        agent_model_default="gpt-4o-mini",
        openai_api_key="",
        openai_base_url=None,
        prompt_warmup_names="",
    )
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def test_prompt_capability_manifest_provides_prompt_rendering():
    cap = PromptCapability(manager=None, warmup_names=[], enabled=True)

    assert cap.manifest.name == "prompt"
    assert "prompt_manager" in cap.manifest.provides
    assert "prompt_rendering" in cap.manifest.provides
    assert cap.manifest.install_order < 20


def test_user_prompt_capability_manifest_sits_between_memory_and_compression():
    cap = UserPromptCapability(manager=None)

    assert cap.manifest.name == "user_prompt"
    assert cap.manifest.depends_on == ("conversation_context",)
    assert "user_prompt_rendering" in cap.manifest.provides
    assert 20 < cap.manifest.install_order < 30


def test_user_prompt_capability_falls_back_to_legacy_format():
    cap = UserPromptCapability(manager=None)
    ctx = RunContext(
        session_id="s1",
        user_id="u1",
        user_input="follow-up",
        metadata={"memory_context": "user: hi\nassistant: hello"},
    )

    import asyncio

    asyncio.run(cap.before_run(ctx))

    assert ctx.enriched_input == "Conversation memory:\nuser: hi\nassistant: hello\n\nUser:\nfollow-up"


def test_user_prompt_capability_includes_city_id_in_fallback():
    cap = UserPromptCapability(manager=None)
    ctx = RunContext(
        session_id="s1",
        user_id="u1",
        user_input="follow-up",
        metadata={
            "memory_context": "summary",
            "business": {"city_id": "310100"},
        },
    )

    import asyncio

    asyncio.run(cap.before_run(ctx))

    assert ctx.enriched_input == (
        "Conversation memory:\nsummary\n\n"
        "City ID: 310100\n"
        "User:\nfollow-up"
    )


def test_user_prompt_capability_uses_prompt_manager_when_available():
    rendered = SimpleNamespace(
        text="Conversation memory:\nsummary\n\nUser:\nfollow-up",
        to_metadata=lambda: {"name": "agents.main_user_chat", "source": "yaml"},
    )
    manager = SimpleNamespace(get=AsyncMock(return_value=rendered))
    cap = UserPromptCapability(manager=manager)
    ctx = RunContext(
        session_id="s1",
        user_id="u1",
        user_input="follow-up",
        metadata={
            "memory_context": "summary",
            "business": {"city_id": "310100"},
        },
    )

    import asyncio

    asyncio.run(cap.before_run(ctx))

    assert ctx.enriched_input == "Conversation memory:\nsummary\n\nUser:\nfollow-up"
    assert ctx.metadata["user_prompt"]["name"] == "agents.main_user_chat"
    manager.get.assert_awaited_once_with(
        "agents.main_user_chat",
        memory_block="Conversation memory:\nsummary\n\n",
        city_id="310100",
        user_input="follow-up",
    )


def test_context_compression_depends_on_model_and_conversation_context():
    cap = ContextCompressionCapability.from_settings(
        _settings(),
        model_router=ModelRouter(),
    )

    assert cap.manifest.name == "context_compression"
    assert cap.manifest.depends_on == ("model_router", "conversation_context")
    assert "compressed_context" in cap.manifest.provides
    assert cap.manifest.install_order > 20
