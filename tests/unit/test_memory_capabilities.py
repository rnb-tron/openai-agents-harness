from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from src.application.orchestration.agent_runtime import AgentOrchestrator, AgentSession
from src.capabilities.memory.capability import (
    LongTermMemoryCapability,
    MemoryCapability,
    VectorSearchCapability,
)
from src.capabilities.memory.store import MemoryStore
from src.capabilities.model_routing.router import ModelRouter
from src.capabilities.plugin import RunContext
from src.capabilities.tools import ToolRegistry


def _settings(**overrides):
    defaults = dict(
        memory_short_term_enabled=False,
        memory_session_summary_enabled=False,
        memory_long_term_enabled=False,
        compression_enabled=False,
        prompt_enabled=False,
        observability_enabled=False,
        openai_api_key="",
        openai_base_url=None,
        prompt_fail_open=True,
    )
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def test_memory_session_manifest_is_separate_from_long_term_memory():
    cap = MemoryCapability(memory_store=MemoryStore())

    assert cap.name == "memory_session"
    assert cap.manifest.name == "memory_session"
    assert "conversation_context" in cap.manifest.provides
    assert cap.manifest.depends_on == ()
    assert "required" in cap.manifest.tags


def test_memory_marker_capabilities_express_dependencies():
    long_term = LongTermMemoryCapability(enabled=True)
    vector = VectorSearchCapability(enabled=True)

    assert long_term.manifest.depends_on == ("memory_manager",)
    assert "mem0" in long_term.manifest.tags
    assert vector.manifest.depends_on == ("long_term_memory",)
    assert "mem0" in vector.manifest.tags


def test_orchestrator_registers_only_memory_session_when_manager_absent():
    orchestrator = AgentOrchestrator(
        tool_registry=ToolRegistry(),
        memory_store=MemoryStore(),
        model_router=ModelRouter(),
        settings=_settings(memory_short_term_enabled=True, memory_long_term_enabled=True),
    )

    enabled_names = [manifest.name for manifest in orchestrator.registry.enabled]

    assert enabled_names == ["memory_session", "user_prompt"]


def test_orchestrator_registers_mem0_memory_without_embedding_provider():
    manager = SimpleNamespace(
        supports_vector_search=True,
        vector_store=None,
        embedding_provider=None,
    )
    orchestrator = AgentOrchestrator(
        tool_registry=ToolRegistry(),
        memory_store=MemoryStore(),
        model_router=ModelRouter(),
        memory_manager=manager,
        settings=_settings(memory_short_term_enabled=True, memory_long_term_enabled=True),
    )

    manifests = {capability.manifest.name: capability.manifest for capability in orchestrator.registry.enabled}

    assert manifests["long_term_memory"].depends_on == ("memory_manager",)
    assert manifests["vector_search"].depends_on == ("long_term_memory",)


@pytest.mark.asyncio
async def test_memory_capability_writes_memory_context_metadata_without_touching_enriched_input():
    manager = SimpleNamespace(get_context=AsyncMock(return_value="user: hi\nassistant: hello"))
    cap = MemoryCapability(
        memory_store=MemoryStore(),
        memory_manager=manager,
        long_term_enabled=True,
    )
    ctx = RunContext(
        session_id="session-1",
        user_id="user-1",
        user_input="follow-up",
        enriched_input="follow-up",
    )

    await cap.before_run(ctx)

    assert ctx.metadata["memory_context"] == "user: hi\nassistant: hello"
    assert ctx.enriched_input == "follow-up"


@pytest.mark.asyncio
async def test_prepare_agent_run_injects_request_context_metadata(monkeypatch):
    orchestrator = AgentOrchestrator(
        tool_registry=ToolRegistry(),
        memory_store=MemoryStore(),
        model_router=ModelRouter(),
        settings=_settings(memory_short_term_enabled=True, prompt_enabled=False, openai_api_key="sk-test"),
    )
    monkeypatch.setattr(orchestrator, "_create_openai_client", lambda: object())
    monkeypatch.setattr(orchestrator, "_build_agent", lambda **kwargs: object())

    async def _resolve_instructions(task_type, ctx):
        assert ctx.metadata["request_context"] == {"scene": "ticket_dispatch", "tenant_id": "tenant-1"}
        return "ok"

    monkeypatch.setattr(orchestrator, "_resolve_instructions", _resolve_instructions)
    session = AgentSession(
        session_id="session-1",
        user_id="user-1",
        context={"request_context": {"scene": "ticket_dispatch", "tenant_id": "tenant-1"}},
    )

    run = await orchestrator._prepare_agent_run(session, "follow-up")

    assert run.ctx.metadata["request_context"] == {"scene": "ticket_dispatch", "tenant_id": "tenant-1"}
