from types import SimpleNamespace

from src.harness.builder import HarnessBuilder


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
        memory_preference_cache_ttl_sec=900,
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


def test_catalog_lists_optional_capabilities_even_when_not_selected():
    catalog = HarnessBuilder(_settings()).build().context.capability_catalog()
    by_name = {item["name"]: item for item in catalog["capabilities"]}

    assert by_name["tool_registry"]["enabled"] is True
    assert by_name["tool_registry"]["runtime_configurable"] is False
    assert by_name["model_router"]["enabled"] is True
    assert by_name["memory_session"]["enabled"] is True
    assert by_name["session_store"]["runtime_configurable"] is False
    assert by_name["session_store"]["assembled"] is False
    assert by_name["memory_manager"]["runtime_configurable"] is False
    assert by_name["memory_manager"]["assembled"] is False
    assert by_name["prompt"]["assembled"] is False
    assert by_name["hitl"]["assembled"] is False
    assert by_name["handoff"]["assembled"] is False
    assert by_name["checkpoint"]["assembled"] is False


def test_catalog_exposes_provider_resolution_and_external_resources():
    catalog = HarnessBuilder(_settings()).build().context.capability_catalog()
    dependencies = {
        (item["capability"], item["requires"]): item
        for item in catalog["dependencies"]
    }

    handoff = dependencies[("handoff", "model_router")]
    compression = dependencies[("context_compression", "conversation_context")]
    memory_manager = dependencies[("long_term_memory", "memory_manager")]

    assert handoff["provider_capabilities"] == ["model_router"]
    assert handoff["external_resource"] is False
    assert compression["provider_capabilities"] == ["memory_session"]
    assert memory_manager["provider_capabilities"] == ["memory_manager"]
    assert memory_manager["external_resource"] is False


def test_catalog_reports_current_optional_selection():
    catalog = HarnessBuilder(
        _settings(
            hitl_enabled=True,
            hitl_require_approval_tools=["get_weather"],
            handoff_enabled=True,
            handoff_agents={"billing": {"instructions": "处理账单请求。"}},
        )
    ).build().context.capability_catalog()
    by_name = {item["name"]: item for item in catalog["capabilities"]}

    assert by_name["hitl"]["enabled"] is True
    assert by_name["handoff"]["enabled"] is True
    assert "hitl" in catalog["current_enabled"]
    assert catalog["missing_dependencies"] == {}
