from contextlib import nullcontext
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from agents.stream_events import AgentUpdatedStreamEvent, RawResponsesStreamEvent
from openai.types.responses.response_text_delta_event import ResponseTextDeltaEvent

from src.application.orchestration.agent_runtime import AgentOrchestrator, AgentSession
from src.capabilities.advanced_agents import CheckpointConfig, HandoffConfig, HITLConfig
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
async def test_rejected_resume_returns_controlled_result_without_model_continuation():
    sdk_state = MagicMock()
    sdk_state.get_interruptions.return_value = [SimpleNamespace(name="get_weather")]
    orchestrator = AgentOrchestrator(
        tool_registry=ToolRegistry(),
        memory_store=MemoryStore(),
        model_router=ModelRouter(),
        settings=_settings(),
        hitl_config=HITLConfig(enabled=True, require_approval_tools=["get_weather"]),
    )
    request = await orchestrator.hitl_mgr.request_sdk_approval(
        interruption=SimpleNamespace(name="get_weather", arguments={"city": "上海"}),
        interruption_index=0,
        run_state={"snapshot": True},
        session_id="s1",
        user_id="u1",
    )

    with patch(
        "src.application.orchestration.agent_runtime.RunState.from_json",
        new=AsyncMock(return_value=sdk_state),
    ), patch(
        "src.application.orchestration.agent_runtime.Runner.run",
        new=AsyncMock(),
    ) as runner_run, patch(
        "src.application.orchestration.agent_runtime.AsyncOpenAI",
    ), patch(
        "src.application.orchestration.agent_runtime.OpenAIChatCompletionsModel",
    ), patch(
        "src.application.orchestration.agent_runtime.Agent",
        return_value=MagicMock(),
    ), patch(
        "src.application.orchestration.agent_runtime.get_tracer_manager",
        return_value=None,
    ):
        result = await orchestrator.resume_with_approval(
            AgentSession(session_id="s1", user_id="u1"),
            run_state={"snapshot": True},
            interruption_index=0,
            approved=False,
            approval_request_id=request.id,
            reviewer="u1",
            user_input="查询上海天气",
        )

    runner_run.assert_not_awaited()
    assert result["tool_executed"] is False
    assert result["decision"] == "rejected"
    assert "未执行工具 get_weather" in result["output"]
    assert "上海天气" not in result["output"]
    assert result["advanced"]["approvals"][0]["status"] == "rejected"


@pytest.mark.asyncio
async def test_rejected_resume_stream_yields_controlled_deltas():
    sdk_state = MagicMock()
    sdk_state.get_interruptions.return_value = [SimpleNamespace(name="get_weather")]
    orchestrator = AgentOrchestrator(
        tool_registry=ToolRegistry(),
        memory_store=MemoryStore(),
        model_router=ModelRouter(),
        settings=_settings(),
        hitl_config=HITLConfig(enabled=True, require_approval_tools=["get_weather"]),
    )
    request = await orchestrator.hitl_mgr.request_sdk_approval(
        interruption=SimpleNamespace(name="get_weather", arguments={"city": "上海"}),
        interruption_index=0,
        run_state={"snapshot": True},
        session_id="s1",
        user_id="u1",
    )

    with patch(
        "src.application.orchestration.agent_runtime.RunState.from_json",
        new=AsyncMock(return_value=sdk_state),
    ), patch(
        "src.application.orchestration.agent_runtime.Runner.run",
        new=AsyncMock(),
    ) as runner_run, patch(
        "src.application.orchestration.agent_runtime.AsyncOpenAI",
    ), patch(
        "src.application.orchestration.agent_runtime.OpenAIChatCompletionsModel",
    ), patch(
        "src.application.orchestration.agent_runtime.Agent",
        return_value=MagicMock(),
    ), patch(
        "src.application.orchestration.agent_runtime.get_tracer_manager",
        return_value=None,
    ):
        events = [
            event
            async for event in orchestrator.resume_stream_with_approval(
                AgentSession(session_id="s1", user_id="u1"),
                run_state={"snapshot": True},
                interruption_index=0,
                approved=False,
                approval_request_id=request.id,
                reviewer="u1",
                user_input="查询上海天气",
            )
        ]

    runner_run.assert_not_awaited()
    deltas = [event["delta"] for event in events if event["type"] == "delta"]
    assert deltas == [
        "操作已被拒绝，",
        "未执行工具 get_weather。",
        "因此无法基于该工具的查询结果提供信息或建议。",
    ]
    assert events[-1]["data"]["tool_executed"] is False


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
    fake_run_result.current_agent = SimpleNamespace(name="billing")

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
        yield AgentUpdatedStreamEvent(new_agent=SimpleNamespace(name="billing"))
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
        checkpoint_config=CheckpointConfig(enabled=True, auto_save=True),
        handoff_config=HandoffConfig(enabled=True, agents={}),
    )
    observation = MagicMock()
    langfuse = MagicMock()
    langfuse.start_as_current_observation.return_value = nullcontext(observation)
    tracer_manager = SimpleNamespace(langfuse=langfuse, is_initialized=True)

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
    ), patch(
        "src.application.orchestration.agent_runtime.get_tracer_manager",
        return_value=tracer_manager,
    ), patch(
        "src.application.orchestration.agent_runtime.propagate_attributes",
        return_value=nullcontext(),
    ):
        events = [
            event
            async for event in orchestrator.run_stream(AgentSession(session_id="s1"), "answer")
        ]

    assert events[0]["type"] == "start"
    assert events[0]["advanced"]["executing_agent"] == "MinimalChatAgent"
    assert [event["delta"] for event in events if event["type"] == "delta"] == ["完", "成"]
    assert [event for event in events if event["type"] == "agent_updated"][0]["agent"] == "billing"
    assert events[-1]["type"] == "done"
    assert events[-1]["data"]["output"] == "完成"
    advanced = events[-1]["data"]["advanced"]
    assert advanced["agent_path"] == ["MinimalChatAgent", "billing"]
    assert advanced["enabled"]["checkpoint"] is True
    assert [item["description"] for item in advanced["checkpoints"]] == [
        "Agent 调用前",
        "Agent 调用完成",
    ]
    assert orchestrator.advanced_state("s1")["agent_path"] == [
        "MinimalChatAgent",
        "billing",
    ]
    langfuse.start_as_current_observation.assert_called_once_with(
        name="agent.chat.stream",
        as_type="agent",
        input="answer",
    )
    langfuse.set_current_trace_io.assert_any_call(input="answer")
    langfuse.set_current_trace_io.assert_any_call(output="完成")
    observation.update.assert_called_once_with(
        output="完成",
        metadata={"model": "stream-model", "interrupted": False},
    )


@pytest.mark.asyncio
async def test_approved_resume_stream_yields_model_deltas():
    sdk_state = MagicMock()
    sdk_state.get_interruptions.return_value = [object()]
    fake_result = MagicMock()
    fake_result.interruptions = []
    fake_result.final_output = "天气晴朗"
    fake_result.new_items = []
    fake_result.current_agent = SimpleNamespace(name="MinimalChatAgent")

    async def stream_events():
        yield RawResponsesStreamEvent(
            data=ResponseTextDeltaEvent(
                content_index=0,
                delta="天气",
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
                delta="晴朗",
                item_id="message-1",
                logprobs=[],
                output_index=0,
                sequence_number=2,
                type="response.output_text.delta",
            )
        )

    fake_result.stream_events = stream_events
    orchestrator = AgentOrchestrator(
        tool_registry=ToolRegistry(),
        memory_store=MemoryStore(),
        model_router=ModelRouter(default_model="stream-model"),
        settings=_settings(),
    )

    with patch(
        "src.application.orchestration.agent_runtime.RunState.from_json",
        new=AsyncMock(return_value=sdk_state),
    ), patch(
        "src.application.orchestration.agent_runtime.Runner.run_streamed",
        return_value=fake_result,
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
    ), patch(
        "src.application.orchestration.agent_runtime.get_tracer_manager",
        return_value=None,
    ):
        events = [
            event
            async for event in orchestrator.resume_stream_with_approval(
                AgentSession(session_id="s1"),
                run_state={"snapshot": True},
                interruption_index=0,
                approved=True,
                user_input="查询天气",
            )
        ]

    assert [event["delta"] for event in events if event["type"] == "delta"] == ["天气", "晴朗"]
    assert events[-1]["data"]["output"] == "天气晴朗"
