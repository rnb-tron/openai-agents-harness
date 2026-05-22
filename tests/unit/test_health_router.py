from types import SimpleNamespace

import pytest

from src.api.routers.health import capabilities, health
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
