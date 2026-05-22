from types import SimpleNamespace

from src.capabilities.context_compression import ContextCompressionCapability
from src.capabilities.model_routing.router import ModelRouter
from src.capabilities.prompt import PromptCapability


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


def test_context_compression_depends_on_model_and_conversation_context():
    cap = ContextCompressionCapability.from_settings(
        _settings(),
        model_router=ModelRouter(),
    )

    assert cap.manifest.name == "context_compression"
    assert cap.manifest.depends_on == ("model_router", "conversation_context")
    assert "compressed_context" in cap.manifest.provides
    assert cap.manifest.install_order > 20
