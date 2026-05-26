from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from agents.stream_events import RawResponsesStreamEvent
from openai.types.responses.response_text_delta_event import ResponseTextDeltaEvent

from src.application.orchestration.agent_runtime import AgentOrchestrator, AgentSession
from src.capabilities.memory.store import MemoryStore
from src.capabilities.model_routing.router import ModelRouter
from src.capabilities.tools.registry import ToolRegistry


def _settings():
    return SimpleNamespace(
        openai_api_key="sk-test",
        openai_base_url=None,
        prompt_enabled=False,
        prompt_fail_open=True,
        compression_enabled=False,
        memory_enabled=False,
    )


@pytest.mark.asyncio
async def test_resume_with_approval_applies_decision_and_runs_state():
    interruption = object()
    sdk_state = MagicMock()
    sdk_state.get_interruptions.return_value = [interruption]

    fake_run_result = MagicMock()
    fake_run_result.final_output = "done"
    fake_run_result.interruptions = []
    fake_run_result.new_items = []

    orchestrator = AgentOrchestrator(
        tool_registry=ToolRegistry(),
        memory_store=MemoryStore(),
        model_router=ModelRouter(),
        settings=_settings(),
    )

    with patch(
        "src.application.orchestration.agent_runtime.RunState.from_json",
        new=AsyncMock(return_value=sdk_state),
    ) as from_json, patch(
        "src.application.orchestration.agent_runtime.Runner.run",
        new=AsyncMock(return_value=fake_run_result),
    ) as runner_run, patch(
        "src.application.orchestration.agent_runtime.AsyncOpenAI",
    ), patch(
        "src.application.orchestration.agent_runtime.OpenAIChatCompletionsModel",
    ), patch(
        "src.application.orchestration.agent_runtime.Agent",
        return_value=MagicMock(),
    ), patch(
        "src.application.orchestration.agent_runtime.parse_tool_calls_from_result",
        return_value=[],
    ):
        result = await orchestrator.resume_with_approval(
            AgentSession(session_id="s1"),
            run_state={"snapshot": True},
            interruption_index=0,
            approved=True,
            always=True,
        )

    from_json.assert_awaited_once()
    sdk_state.approve.assert_called_once_with(interruption, always_approve=True)
    runner_run.assert_awaited_once()
    assert result["interrupted"] is False
    assert result["output"] == "done"


@pytest.mark.asyncio
async def test_interrupted_run_returns_model_that_created_the_interruption():
    fake_run_result = MagicMock()
    fake_run_result.interruptions = [
        SimpleNamespace(name="delete_data", arguments={}, call_id="call-1")
    ]
    fake_run_result.to_state.return_value.to_json.return_value = {"snapshot": True}

    model_router = MagicMock()
    model_router.infer_task_type.return_value = "reasoning"
    model_router.select.return_value = "primary-model"
    model_router.run_with_resilience = AsyncMock(return_value=fake_run_result)
    model_router.last_metrics = SimpleNamespace(success_model="fallback-model")

    orchestrator = AgentOrchestrator(
        tool_registry=ToolRegistry(),
        memory_store=MemoryStore(),
        model_router=model_router,
        settings=_settings(),
    )

    with patch("src.application.orchestration.agent_runtime.AsyncOpenAI"):
        result = await orchestrator.run(AgentSession(session_id="s1"), "delete data")

    assert result["interrupted"] is True
    assert result["model"] == "fallback-model"


@pytest.mark.asyncio
async def test_streamed_run_yields_text_delta_and_completed_result():
    fake_run_result = MagicMock()
    fake_run_result.interruptions = []
    fake_run_result.final_output = "完成"
    fake_run_result.new_items = []

    async def stream_events():
        yield RawResponsesStreamEvent(
            data=ResponseTextDeltaEvent(
                content_index=0,
                delta="完",
                item_id="message-1",
                logprobs=[],
                output_index=0,
                sequence_number=1,
                type="response.output_text.delta",
            )
        )
        yield RawResponsesStreamEvent(
            data=ResponseTextDeltaEvent(
                content_index=0,
                delta="成",
                item_id="message-1",
                logprobs=[],
                output_index=0,
                sequence_number=2,
                type="response.output_text.delta",
            )
        )

    fake_run_result.stream_events = stream_events
    orchestrator = AgentOrchestrator(
        tool_registry=ToolRegistry(),
        memory_store=MemoryStore(),
        model_router=ModelRouter(default_model="stream-model"),
        settings=_settings(),
    )

    with patch(
        "src.application.orchestration.agent_runtime.Runner.run_streamed",
        return_value=fake_run_result,
    ), patch(
        "src.application.orchestration.agent_runtime.AsyncOpenAI",
    ), patch(
        "src.application.orchestration.agent_runtime.OpenAIChatCompletionsModel",
    ), patch(
        "src.application.orchestration.agent_runtime.Agent",
        return_value=MagicMock(),
    ), patch(
        "src.application.orchestration.agent_runtime.parse_tool_calls_from_result",
        return_value=[],
    ):
        events = [
            event
            async for event in orchestrator.run_stream(AgentSession(session_id="s1"), "answer")
        ]

    assert events[0] == {"type": "start", "session_id": "s1", "model": "stream-model"}
    assert [event["delta"] for event in events if event["type"] == "delta"] == ["完", "成"]
    assert events[-1]["type"] == "done"
    assert events[-1]["data"]["output"] == "完成"
