from unittest.mock import MagicMock

from agents import Agent

from src.application.orchestration.agent_runtime import AgentOrchestrator
from src.capabilities.advanced_agents import HandoffConfig, HandoffManager
from src.capabilities.memory.store import MemoryStore
from src.capabilities.model_routing.router import ModelRouter
from src.capabilities.tools.registry import ToolRegistry


def _settings():
    return MagicMock(
        memory_enabled=False,
        compression_enabled=False,
        prompt_enabled=False,
    )


def test_handoff_manager_builds_sdk_agents_and_filters_disabled_targets():
    manager = HandoffManager(
        HandoffConfig(
            enabled=True,
            agents={
                "billing": {
                    "description": "处理账单问题",
                    "instructions": "只处理账单相关请求。",
                },
                "disabled": {"enabled": False, "instructions": "不会装配"},
            },
        )
    )
    model = "gpt-test"

    targets = manager.build_configured_handoffs(model)

    assert len(targets) == 1
    assert isinstance(targets[0], Agent)
    assert targets[0].name == "billing"
    assert targets[0].handoff_description == "处理账单问题"
    assert targets[0].model == model


def test_runtime_attaches_native_handoffs_to_primary_agent():
    orchestrator = AgentOrchestrator(
        tool_registry=ToolRegistry(),
        memory_store=MemoryStore(),
        model_router=ModelRouter(),
        settings=_settings(),
        handoff_config=HandoffConfig(
            enabled=True,
            agents={
                "billing": {
                    "description": "处理账单问题",
                    "instructions": "只处理账单相关请求。",
                }
            },
        ),
    )

    agent = orchestrator._build_agent(
        model="gpt-4o-mini",
        client=MagicMock(),
        instructions="处理用户请求。",
    )

    assert [target.name for target in agent.handoffs] == ["billing"]
    assert "Handoffs" in agent.instructions
