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


def test_harness_builder_enables_hitl_and_configures_sdk_tool_approval():
    harness = HarnessBuilder(
        _settings(
            hitl_enabled=True,
            hitl_approval_timeout=30.0,
            hitl_require_approval_tools=["get_weather"],
            hitl_auto_approve_tools=[],
        )
    ).build()

    enabled = {
        item["name"]
        for item in harness.context.capability_snapshot(enabled_only=True)["capabilities"]
    }
    weather_tool = next(
        tool
        for tool in harness.context.tool_registry.list_agent_tools()
        if tool.name == "get_weather"
    )

    assert harness.runtime.hitl_mgr is not None
    assert "hitl" in enabled
    assert harness.context.tool_registry.list_approval_required() == ["get_weather"]
    assert weather_tool.needs_approval is True


def test_harness_builder_enables_in_process_checkpoint_snapshots():
    harness = HarnessBuilder(
        _settings(
            checkpoint_enabled=True,
            checkpoint_max_checkpoints=3,
            checkpoint_auto_save=True,
        )
    ).build()

    snapshot = harness.context.capability_snapshot(enabled_only=True)
    names = {item["name"] for item in snapshot["capabilities"]}

    assert harness.runtime.checkpoint_mgr is not None
    assert harness.runtime.checkpoint_mgr.config.storage_backend == "memory"
    assert harness.runtime.checkpoint_mgr.config.max_checkpoints == 3
    assert harness.runtime.checkpoint_mgr.config.auto_save is True
    assert "checkpoint" in names
    assert "run_checkpoints" in snapshot["provided"]


def test_harness_builder_enables_native_handoff_targets():
    harness = HarnessBuilder(
        _settings(
            handoff_enabled=True,
            handoff_agents={
                "billing": {
                    "description": "处理账单问题",
                    "instructions": "只处理账单相关请求。",
                }
            },
        )
    ).build()

    snapshot = harness.context.capability_snapshot(enabled_only=True)
    names = {item["name"] for item in snapshot["capabilities"]}

    assert harness.runtime.handoff_mgr is not None
    assert "handoff" in names
    assert "agent_handoffs" in snapshot["provided"]
