from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

from agents.stream_events import AgentUpdatedStreamEvent, RawResponsesStreamEvent
from openai.types.responses.response_reasoning_summary_text_done_event import (
    ResponseReasoningSummaryTextDoneEvent,
)
from openai.types.responses.response_reasoning_summary_text_delta_event import (
    ResponseReasoningSummaryTextDeltaEvent,
)
from openai.types.responses.response_reasoning_text_delta_event import ResponseReasoningTextDeltaEvent
from openai.types.responses.response_text_delta_event import ResponseTextDeltaEvent


async def iter_stream_events(
    run_result: Any,
    *,
    agent_path: list[str],
) -> AsyncIterator[dict[str, Any]]:
    """Translate OpenAI Agents SDK stream events into API stream events."""
    # 有些模型会先发 summary delta，最后再发 summary done；这里记录已流过的
    # summary，避免 UI 把 done 里的整段文本再追加一遍。
    streamed_reasoning_summaries: set[tuple[str | None, int | None]] = set()
    async for event in run_result.stream_events():
        if isinstance(event, RawResponsesStreamEvent) and isinstance(event.data, ResponseTextDeltaEvent):
            yield {"type": "delta", "delta": event.data.delta}
        elif isinstance(event, RawResponsesStreamEvent) and isinstance(
            event.data, ResponseReasoningSummaryTextDeltaEvent
        ):
            streamed_reasoning_summaries.add((event.data.item_id, event.data.summary_index))
            yield {
                "type": "reasoning_summary_delta",
                "delta": event.data.delta,
            }
        elif isinstance(event, RawResponsesStreamEvent) and isinstance(
            event.data, ResponseReasoningSummaryTextDoneEvent
        ):
            summary_key = (event.data.item_id, event.data.summary_index)
            if summary_key in streamed_reasoning_summaries:
                continue
            yield {
                "type": "reasoning_summary_delta",
                "delta": event.data.text,
            }
        # 兼容第三方 provider 直接返回 reasoning_text 的情况，前端仍统一展示到
        # “推理摘要”气泡里。
        elif isinstance(event, RawResponsesStreamEvent) and isinstance(event.data, ResponseReasoningTextDeltaEvent):
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
