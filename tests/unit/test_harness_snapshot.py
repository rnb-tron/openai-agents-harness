from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.capabilities.memory.store import MemoryStore
from src.harness.builder import Harness, HarnessBuilder


def _settings(**overrides):
    defaults = dict(
        agent_model_default="gpt-4o-mini",
        agent_model_reasoning="gpt-4.1-mini",
        auth_enabled=False,
        rate_limit_enabled=False,
        mysql_enabled=False,
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


def test_capability_snapshot_includes_enabled_and_disabled_capabilities():
    harness = HarnessBuilder(_settings(auth_enabled=True, rate_limit_enabled=False)).build()

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
    harness = HarnessBuilder(_settings(auth_enabled=False, observability_enabled=True)).build()

    snapshot = harness.context.capability_snapshot(enabled_only=True)
    names = [item["name"] for item in snapshot["capabilities"]]

    assert "auth" not in names
    assert "observability" in names
    assert "langfuse" in snapshot["provided"]


def test_harness_builder_enables_hitl_without_registering_demo_tools():
    harness = HarnessBuilder(
        _settings(
            hitl_enabled=True,
            hitl_approval_timeout=30.0,
            hitl_require_approval_tools=["get_weather"],
            hitl_auto_approve_tools=[],
        )
    ).build()

    enabled = {item["name"] for item in harness.context.capability_snapshot(enabled_only=True)["capabilities"]}

    assert harness.runtime.hitl_mgr is not None
    assert "hitl" in enabled
    assert harness.context.tool_registry.list_tools() == []
    assert harness.context.tool_registry.list_approval_required() == []


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


async def test_harness_owns_redis_lifecycle():
    harness = HarnessBuilder(
        _settings(
            redis_enabled=True,
            redis_url="redis://localhost:6379/0",
            redis_slave_url=None,
        )
    ).build()
    fake_redis = MagicMock()

    with (
        patch("src.harness.builder.init_redis", new=AsyncMock()) as init_redis,
        patch("src.harness.builder.get_redis_client", return_value=fake_redis),
        patch("src.harness.builder.close_redis", new=AsyncMock()) as close_redis,
    ):
        await harness.setup()
        await harness.teardown()

    init_redis.assert_awaited_once_with("redis://localhost:6379/0", None)
    close_redis.assert_awaited_once()
    assert harness.context.get_resource("redis") is fake_redis


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


def test_harness_context_and_runtime_share_same_memory_store_reference():
    harness = HarnessBuilder(_settings()).build()

    assert harness.context.get_resource("memory_store") is harness.memory_store
    assert harness.runtime.memory_store is harness.memory_store


def test_harness_builder_assembles_mem0_memory_without_database_resource():
    harness = HarnessBuilder(_settings(memory_long_term_enabled=True)).build()

    snapshot = harness.context.capability_snapshot(enabled_only=True)
    names = {item["name"] for item in snapshot["capabilities"]}

    assert harness.database_resource is None
    assert harness.memory_manager is not None
    assert harness.memory_manager.provider_name == "mem0"
    assert "long_term_memory" in names
    assert "vector_search" in names
    assert snapshot["missing_dependencies"] == {}


def test_harness_builder_assembles_session_store_from_database_resource():
    harness = HarnessBuilder(
        _settings(
            session_store_enabled=True,
            database_url="mysql+aiomysql://agent:secret@localhost/agent",
        )
    ).build()

    assert harness.database_resource is not None
    assert harness.session_store is not None
    assert harness.context.get_resource("session_store") is harness.session_store


def test_harness_builder_can_enable_mysql_without_session_store():
    harness = HarnessBuilder(
        _settings(
            mysql_enabled=True,
            session_store_enabled=False,
            database_url="mysql+aiomysql://agent:secret@localhost/agent",
        )
    ).build()

    assert harness.database_resource is not None
    assert harness.session_store is None
    assert harness.context.get_resource("database") is harness.database_resource
    assert harness.context.get_resource("session_store") is None
    assert "database" in harness.context.capability_catalog()["current_enabled"]


@pytest.mark.asyncio
async def test_harness_teardown_releases_resources_after_partial_startup():
    memory_manager = AsyncMock()
    database_resource = AsyncMock()
    session = AsyncMock()
    runtime = AsyncMock()
    context = SimpleNamespace(get_resource=lambda name: None)
    harness = Harness(
        context=context,
        runtime=runtime,
        memory_store=MemoryStore(),
        memory_manager=memory_manager,
        database_resource=database_resource,
        _memory_session=session,
        _setup_done=False,
    )

    await harness.teardown()

    runtime.teardown.assert_not_awaited()
    memory_manager.close.assert_awaited_once()
    session.close.assert_awaited_once()
    database_resource.close.assert_awaited_once()
