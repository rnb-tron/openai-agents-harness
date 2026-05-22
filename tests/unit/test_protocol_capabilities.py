from types import SimpleNamespace

from src.api.middleware.capabilities import AuthCapability, RateLimitCapability
from src.harness.builder import HarnessBuilder
from src.harness.manifest import CapabilityKind


def _settings(**overrides):
    defaults = dict(
        agent_model_default="gpt-4o-mini",
        agent_model_reasoning="gpt-4.1-mini",
        auth_enabled=False,
        rate_limit_enabled=False,
        database_enabled=False,
        database_url="",
        memory_enabled=False,
        memory_long_term_enabled=False,
        memory_short_term_ttl=3600,
        memory_es_hosts="http://localhost:9200",
        memory_es_index="agent_memories",
        memory_vector_dimension=1536,
        memory_max_context_turns=6,
        memory_retrieval_top_k=3,
        memory_importance_threshold=0.3,
        memory_forgetting_enabled=True,
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
    assert rate_limit.manifest.depends_on == ()
    assert "uses_principal_when_available" in rate_limit.manifest.tags


def test_harness_builder_registers_enabled_protocol_capabilities():
    harness = HarnessBuilder(
        _settings(auth_enabled=True, rate_limit_enabled=True)
    ).build()

    enabled = {manifest.name for manifest in harness.context.capability_manifests()}

    assert "auth" in enabled
    assert "rate_limit" in enabled
    assert "principal" in harness.context.provided_names()
    assert harness.context.missing_dependencies() == {}


def test_harness_builder_keeps_disabled_protocol_capabilities_out_of_enabled_graph():
    harness = HarnessBuilder(_settings()).build()

    enabled = {manifest.name for manifest in harness.context.capability_manifests()}

    assert "auth" not in enabled
    assert "rate_limit" not in enabled
