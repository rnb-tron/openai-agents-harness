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


def test_catalog_lists_optional_capabilities_even_when_not_selected():
    catalog = HarnessBuilder(_settings()).build().context.capability_catalog()
    by_name = {item["name"]: item for item in catalog["capabilities"]}

    assert by_name["tool_registry"]["enabled"] is True
    assert by_name["tool_registry"]["selectable"] is False
    assert by_name["model_router"]["enabled"] is True
    assert by_name["memory_session"]["enabled"] is True
    assert by_name["memory_manager"]["selectable"] is False
    assert by_name["memory_manager"]["assembled"] is False
    assert by_name["prompt"]["assembled"] is False
    assert by_name["hitl"]["assembled"] is False
    assert by_name["handoff"]["assembled"] is False
    assert by_name["checkpoint"]["assembled"] is False


def test_catalog_exposes_provider_resolution_and_external_requirements():
    catalog = HarnessBuilder(_settings()).build().context.capability_catalog()
    dependencies = {
        (item["capability"], item["requires"]): item
        for item in catalog["dependencies"]
    }

    handoff = dependencies[("handoff", "model_router")]
    compression = dependencies[("context_compression", "conversation_context")]
    database = dependencies[("long_term_memory", "database")]
    memory_manager = dependencies[("long_term_memory", "memory_manager")]
    embedding_provider = dependencies[("vector_search", "embedding_provider")]

    assert handoff["provider_capabilities"] == ["model_router"]
    assert handoff["external_resource"] is False
    assert compression["provider_capabilities"] == ["memory_session"]
    assert database["provider_capabilities"] == []
    assert database["external_resource"] is True
    assert memory_manager["provider_capabilities"] == ["memory_manager"]
    assert memory_manager["external_resource"] is False
    assert embedding_provider["provider_capabilities"] == ["embedding_provider"]
    assert embedding_provider["external_resource"] is False


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
    assert "hitl" in catalog["current_selection"]
    assert catalog["missing_dependencies"] == {}


def test_selection_validator_resolves_internal_resources_and_external_config():
    validation = HarnessBuilder(_settings()).build().context.validate_capability_selection(
        ["vector_search"]
    )

    assert validation["valid"] is True
    assert validation["requested_selection"] == ["vector_search"]
    assert set(validation["resolved_selection"]) >= {
        "tool_registry",
        "model_router",
        "memory_session",
        "memory_manager",
        "embedding_provider",
        "long_term_memory",
        "vector_search",
    }
    assert "long_term_memory" in validation["auto_included"]
    assert "memory_manager" in validation["auto_included"]
    assert "embedding_provider" in validation["auto_included"]
    assert validation["external_requirements"] == [
        {
            "resource": "database",
            "required_by": ["long_term_memory", "memory_manager"],
        },
        {
            "resource": "embedding_api",
            "required_by": ["embedding_provider"],
        },
    ]


def test_selection_validator_rejects_unknown_capabilities():
    validation = HarnessBuilder(_settings()).build().context.validate_capability_selection(
        ["nonexistent_capability"]
    )

    assert validation["valid"] is False
    assert validation["unknown_capabilities"] == ["nonexistent_capability"]
