from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

from agents.stream_events import AgentUpdatedStreamEvent, RawResponsesStreamEvent
from openai.types.responses.response_reasoning_summary_text_delta_event import (
    ResponseReasoningSummaryTextDeltaEvent,
)
from openai.types.responses.response_text_delta_event import ResponseTextDeltaEvent


async def iter_stream_events(
    run_result: Any,
    *,
    agent_path: list[str],
) -> AsyncIterator[dict[str, Any]]:
    """Translate OpenAI Agents SDK stream events into API stream events."""
    async for event in run_result.stream_events():
        if isinstance(event, RawResponsesStreamEvent) and isinstance(
            event.data, ResponseTextDeltaEvent
        ):
            yield {"type": "delta", "delta": event.data.delta}
        elif isinstance(event, RawResponsesStreamEvent) and isinstance(
            event.data, ResponseReasoningSummaryTextDeltaEvent
        ):
            yield {
                "type": "reasoning_summary_delta",
                "delta": event.data.delta,
            }
        elif isinstance(event, AgentUpdatedStreamEvent):
            executing_agent = getattr(event.new_agent, "name", None)
            if isinstance(executing_agent, str) and agent_path[-1] != executing_agent:
                agent_path.append(executing_agent)
            yield {
                "type": "agent_updated",
                "agent": executing_agent or agent_path[-1],
                "agent_path": list(agent_path),
            }
