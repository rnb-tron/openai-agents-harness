from types import SimpleNamespace

import pytest

from src.api.routers.health import (
    CapabilitySelectionRequest,
    capabilities,
    capability_catalog,
    health,
    validate_capability_selection,
)
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


@pytest.mark.asyncio
async def test_health_ok_payload():
    assert await health() == {"code": "1", "msg": "ok"}


@pytest.mark.asyncio
async def test_capabilities_endpoint_returns_snapshot_payload():
    harness = HarnessBuilder(_settings(auth_enabled=True)).build()

    payload = await capabilities(harness)

    assert "capabilities" in payload
    assert "provided" in payload
    assert "missing_dependencies" in payload
    assert any(item["name"] == "auth" for item in payload["capabilities"])


@pytest.mark.asyncio
async def test_capability_catalog_endpoint_returns_scaffold_metadata():
    harness = HarnessBuilder(_settings()).build()

    payload = await capability_catalog(harness)
    by_name = {item["name"]: item for item in payload["capabilities"]}

    assert payload["version"] == 1
    assert "dependencies" in payload
    assert by_name["tool_registry"]["enabled"] is True
    assert by_name["handoff"]["enabled"] is False


@pytest.mark.asyncio
async def test_capability_selection_validation_endpoint_returns_resolved_graph():
    harness = HarnessBuilder(_settings()).build()

    payload = await validate_capability_selection(
        CapabilitySelectionRequest(selected=["handoff"]),
        harness,
    )

    assert payload["valid"] is True
    assert payload["requested_selection"] == ["handoff"]
    assert "model_router" in payload["resolved_selection"]
    assert payload["external_requirements"] == []
