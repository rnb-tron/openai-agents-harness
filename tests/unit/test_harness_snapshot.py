from types import SimpleNamespace

from src.harness.builder import HarnessBuilder


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


def test_capability_snapshot_includes_enabled_and_disabled_capabilities():
    harness = HarnessBuilder(
        _settings(auth_enabled=True, rate_limit_enabled=False)
    ).build()

    snapshot = harness.context.capability_snapshot()
    by_name = {item["name"]: item for item in snapshot["capabilities"]}

    assert by_name["model_router"]["enabled"] is True
    assert by_name["auth"]["enabled"] is True
    assert by_name["rate_limit"]["enabled"] is False
    assert by_name["auth"]["kind"] == "protocol"
    assert by_name["model_router"]["kind"] == "runtime"
    assert "principal" in snapshot["provided"]
    assert snapshot["missing_dependencies"] == {}


def test_capability_snapshot_enabled_only_filters_disabled_capabilities():
    harness = HarnessBuilder(
        _settings(auth_enabled=False, observability_enabled=True)
    ).build()

    snapshot = harness.context.capability_snapshot(enabled_only=True)
    names = [item["name"] for item in snapshot["capabilities"]]

    assert "auth" not in names
    assert "observability" in names
    assert "tracing" in snapshot["provided"]
