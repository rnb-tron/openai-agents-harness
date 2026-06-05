from contextlib import nullcontext
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from agents.stream_events import AgentUpdatedStreamEvent, RawResponsesStreamEvent
from openai.types.responses.response_reasoning_summary_text_delta_event import (
    ResponseReasoningSummaryTextDeltaEvent,
)
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
        memory_short_term_enabled=False,
        memory_session_summary_enabled=False,
        memory_long_term_enabled=False,
    )


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

    with (
        patch(
            "src.application.orchestration.agent_resume.RunState.from_json",
            new=AsyncMock(return_value=sdk_state),
        ),
        patch(
            "src.application.orchestration.agent_resume.Runner.run_streamed",
        ) as runner_run_streamed,
        patch(
            "src.application.orchestration.agent_factory.AsyncOpenAI",
        ),
        patch(
            "src.application.orchestration.agent_factory.OpenAIChatCompletionsModel",
        ),
        patch(
            "src.application.orchestration.agent_factory.Agent",
            return_value=MagicMock(),
        ),
        patch(
            "src.application.orchestration.agent_observation.get_tracer_manager",
            return_value=None,
        ),
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

    runner_run_streamed.assert_not_called()
    deltas = [event["delta"] for event in events if event["type"] == "delta"]
    assert deltas == [
        "操作已被拒绝，",
        "未执行工具 get_weather。",
        "因此无法基于该工具的查询结果提供信息或建议。",
    ]
    assert events[-1]["data"]["tool_executed"] is False


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
            data=ResponseReasoningSummaryTextDeltaEvent(
                delta="正在整理",
                item_id="reasoning-1",
                output_index=0,
                sequence_number=2,
                summary_index=0,
                type="response.reasoning_summary_text.delta",
            )
        )
        yield RawResponsesStreamEvent(
            data=ResponseTextDeltaEvent(
                content_index=0,
                delta="成",
                item_id="message-1",
                logprobs=[],
                output_index=0,
                sequence_number=3,
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

    with (
        patch(
            "src.application.orchestration.agent_runtime.Runner.run_streamed",
            return_value=fake_run_result,
        ),
        patch(
            "src.application.orchestration.agent_factory.AsyncOpenAI",
        ),
        patch(
            "src.application.orchestration.agent_factory.OpenAIChatCompletionsModel",
        ),
        patch(
            "src.application.orchestration.agent_factory.Agent",
            return_value=MagicMock(),
        ),
        patch(
            "src.application.orchestration.agent_runtime.parse_tool_calls_from_result",
            return_value=[],
        ),
        patch(
            "src.application.orchestration.agent_observation.get_tracer_manager",
            return_value=tracer_manager,
        ),
        patch(
            "src.application.orchestration.agent_observation.propagate_attributes",
            return_value=nullcontext(),
        ),
    ):
        events = [event async for event in orchestrator.run_stream(AgentSession(session_id="s1"), "answer")]

    assert events[0]["type"] == "start"
    assert [event["delta"] for event in events if event["type"] == "delta"] == ["完", "成"]
    assert [event["delta"] for event in events if event["type"] == "reasoning_summary_delta"] == ["正在整理"]
    assert [event for event in events if event["type"] == "agent_updated"][0]["agent"] == "billing"
    assert events[-1]["type"] == "done"
    assert events[-1]["data"]["output"] == "完成"
    langfuse.start_as_current_observation.assert_called_once_with(
        name="agent.chat.stream",
        as_type="agent",
        input="answer",
    )
    langfuse.set_current_trace_io.assert_any_call(input="answer")
    langfuse.set_current_trace_io.assert_any_call(output="完成")
    update_kwargs = observation.update.call_args.kwargs
    assert update_kwargs["output"] == "完成"
    assert update_kwargs["metadata"]["model"] == "stream-model"
    assert update_kwargs["metadata"]["interrupted"] is False
    assert "tools" in update_kwargs["metadata"]


def test_runtime_adds_reasoning_summary_model_settings_when_enabled():
    settings = _settings()
    settings.reasoning_summary_enabled = True
    settings.reasoning_summary_mode = "concise"
    orchestrator = AgentOrchestrator(
        tool_registry=ToolRegistry(),
        memory_store=MemoryStore(),
        model_router=ModelRouter(),
        settings=settings,
    )

    with (
        patch(
            "src.application.orchestration.agent_factory.OpenAIChatCompletionsModel",
        ),
        patch(
            "src.application.orchestration.agent_factory.Agent",
            return_value=MagicMock(),
        ) as agent_cls,
    ):
        orchestrator._build_agent(
            model="gpt-5-mini",
            client=MagicMock(),
            instructions="answer",
        )

    model_settings = agent_cls.call_args.kwargs["model_settings"]
    assert model_settings.reasoning.summary == "concise"


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

    with (
        patch(
            "src.application.orchestration.agent_resume.RunState.from_json",
            new=AsyncMock(return_value=sdk_state),
        ),
        patch(
            "src.application.orchestration.agent_resume.Runner.run_streamed",
            return_value=fake_result,
        ),
        patch(
            "src.application.orchestration.agent_factory.AsyncOpenAI",
        ),
        patch(
            "src.application.orchestration.agent_factory.OpenAIChatCompletionsModel",
        ),
        patch(
            "src.application.orchestration.agent_factory.Agent",
            return_value=MagicMock(),
        ),
        patch(
            "src.application.orchestration.agent_runtime.parse_tool_calls_from_result",
            return_value=[],
        ),
        patch(
            "src.application.orchestration.agent_observation.get_tracer_manager",
            return_value=None,
        ),
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
