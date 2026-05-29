from types import SimpleNamespace

from src.application.orchestration.agent_runtime import AgentOrchestrator
from src.capabilities.memory.capability import (
    LongTermMemoryCapability,
    MemoryCapability,
    VectorSearchCapability,
)
from src.capabilities.memory.store import MemoryStore
from src.capabilities.model_routing.router import ModelRouter
from src.capabilities.tools import ToolRegistry


def _settings(**overrides):
    defaults = dict(
        memory_enabled=False,
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
        settings=_settings(memory_enabled=True),
    )

    enabled_names = [manifest.name for manifest in orchestrator.registry.enabled]

    assert enabled_names == ["memory_session"]


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
        settings=_settings(memory_enabled=True),
    )

    manifests = {
        capability.manifest.name: capability.manifest
        for capability in orchestrator.registry.enabled
    }

    assert manifests["long_term_memory"].depends_on == ("memory_manager",)
    assert manifests["vector_search"].depends_on == ("long_term_memory",)
