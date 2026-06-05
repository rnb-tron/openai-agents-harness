from types import SimpleNamespace

import pytest

from src.api.middleware.assembler import build_protocol_chain
from src.api.middleware.capabilities import AuthCapability, RateLimitCapability
from src.harness.builder import HarnessBuilder
from src.harness.manifest import CapabilityKind


def _settings(**overrides):
    defaults = dict(
        agent_model_default="gpt-4o-mini",
        agent_model_reasoning="gpt-4.1-mini",
        auth_enabled=False,
        rate_limit_enabled=False,
        database_url="",
        session_store_enabled=False,
        session_store_auto_create=True,
        redis_enabled=False,
        memory_short_term_enabled=False,
        memory_session_summary_enabled=False,
        memory_long_term_enabled=False,
        memory_long_term_provider="mem0",
        memory_short_term_ttl=3600,
        memory_long_term_mem0_mode="local",
        memory_long_term_mem0_api_key="",
        memory_long_term_mem0_config_json="",
        memory_long_term_vector_store="pgvector",
        memory_pgvector_table="agent_memories",
        memory_es_hosts="http://localhost:9200",
        memory_es_index="agent_memories",
        memory_vector_dimension=1536,
        memory_short_term_context_max_turns=6,
        memory_long_term_context_max_memories=3,
        compression_enabled=False,
        prompt_enabled=False,
        observability_enabled=False,
        openai_api_key="",
        openai_base_url=None,
        prompt_fail_open=True,
    )
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def test_protocol_capability_markers_use_protocol_kind():
    auth = AuthCapability(enabled=True)
    rate_limit = RateLimitCapability(enabled=True)

    assert auth.manifest.kind == CapabilityKind.PROTOCOL
    assert rate_limit.manifest.kind == CapabilityKind.PROTOCOL
    assert "principal" in auth.manifest.provides
    assert rate_limit.manifest.depends_on == ("principal",)
    assert "user_dimension" in rate_limit.manifest.tags


def test_harness_builder_registers_enabled_protocol_capabilities():
    harness = HarnessBuilder(_settings(auth_enabled=True, rate_limit_enabled=True)).build()

    enabled = {manifest.name for manifest in harness.context.capability_manifests()}

    assert "auth" in enabled
    assert "rate_limit" in enabled
    assert "principal" in harness.context.provided_names()
    assert harness.context.missing_dependencies() == {}


def test_harness_builder_requires_auth_for_user_dimension_rate_limit():
    with pytest.raises(ValueError, match="rate_limit"):
        HarnessBuilder(_settings(rate_limit_enabled=True)).build()


@pytest.mark.parametrize("key_strategy", ["ip", "principal_or_ip"])
def test_harness_builder_allows_explicit_compatible_rate_limit_strategy(key_strategy):
    harness = HarnessBuilder(_settings(rate_limit_enabled=True, rate_limit_key_strategy=key_strategy)).build()

    rate_limit = next(manifest for manifest in harness.context.capability_manifests() if manifest.name == "rate_limit")
    assert rate_limit.depends_on == ()
    assert "compatibility_key_strategy" in rate_limit.tags


def test_protocol_chain_declares_auth_before_user_dimension_rate_limit():
    settings = _settings(
        observability_enabled=True,
        auth_enabled=True,
        auth_jwt_secret="test-secret-value-with-sufficient-length",
        rate_limit_enabled=True,
        rate_limit_backend="memory",
    )

    chain = build_protocol_chain(settings)

    assert [plugin.name for plugin in chain.request_order] == [
        "request_context",
        "auth",
        "rate_limit",
    ]


def test_harness_builder_keeps_disabled_protocol_capabilities_out_of_enabled_graph():
    harness = HarnessBuilder(_settings()).build()

    enabled = {manifest.name for manifest in harness.context.capability_manifests()}

    assert "auth" not in enabled
    assert "rate_limit" not in enabled
