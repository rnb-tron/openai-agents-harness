from types import SimpleNamespace

from src.capabilities.observability import ObservabilityCapability
from src.harness.builder import HarnessBuilder
from src.harness.config import HarnessConfig
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


def test_observability_marker_describes_tracing_outputs():
    cap = ObservabilityCapability(enabled=True)

    assert cap.manifest.kind == CapabilityKind.RESOURCE
    assert "tracing" in cap.manifest.provides
    assert "log_correlation" in cap.manifest.provides
    assert "opentelemetry" in cap.manifest.tags


def test_harness_config_disables_runtime_tracing_when_observability_is_off():
    off = HarnessConfig.from_settings(_settings(observability_enabled=False))
    on = HarnessConfig.from_settings(_settings(observability_enabled=True))

    assert off.runtime.tracing_disabled is True
    assert on.runtime.tracing_disabled is False


def test_harness_builder_registers_observability_when_enabled():
    harness = HarnessBuilder(_settings(observability_enabled=True)).build()

    enabled = {manifest.name for manifest in harness.context.capability_manifests()}
    provided = harness.context.provided_names()

    assert "observability" in enabled
    assert "tracing" in provided
    assert "log_correlation" in provided
