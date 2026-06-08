from __future__ import annotations

from collections.abc import AsyncIterator
import time
from typing import Any

from agents.stream_events import AgentUpdatedStreamEvent, RawResponsesStreamEvent
from openai.types.responses.response_reasoning_summary_text_done_event import (
    ResponseReasoningSummaryTextDoneEvent,
)
from openai.types.responses.response_reasoning_summary_text_delta_event import (
    ResponseReasoningSummaryTextDeltaEvent,
)
from openai.types.responses.response_reasoning_text_delta_event import ResponseReasoningTextDeltaEvent
from openai.types.responses.response_reasoning_text_done_event import ResponseReasoningTextDoneEvent
from openai.types.responses.response_text_delta_event import ResponseTextDeltaEvent


async def iter_chat_events(run_result: Any) -> AsyncIterator[dict[str, Any]]:
    """Translate OpenAI Agents SDK stream events into unified chat events."""
    # 有些模型会先发 summary delta，最后再发 summary done；这里记录已流过的
    # summary，避免 UI 把 done 里的整段文本再追加一遍。
    streamed_reasoning_summaries: set[tuple[str | None, int | None]] = set()
    streamed_reasoning_texts: set[tuple[str | None, int | None, int | None]] = set()
    thinking_started_at: float | None = None

    async def emit_thinking_end() -> AsyncIterator[dict[str, Any]]:
        nonlocal thinking_started_at
        if thinking_started_at is None:
            return
        cost = max(0, int((time.perf_counter() - thinking_started_at) * 1000))
        thinking_started_at = None
        yield {"event": "thinkingEnd", "data": {"cost": cost}}

    async for event in run_result.stream_events():
        if isinstance(event, RawResponsesStreamEvent) and isinstance(event.data, ResponseTextDeltaEvent):
            async for thinking_end in emit_thinking_end():
                yield thinking_end
            yield {"event": "content", "data": {"text": event.data.delta}}
        elif isinstance(event, RawResponsesStreamEvent) and isinstance(
            event.data, ResponseReasoningSummaryTextDeltaEvent
        ):
            streamed_reasoning_summaries.add((event.data.item_id, event.data.summary_index))
            yield {
                "event": "thinking",
                "data": {"text": event.data.delta},
            }
            if thinking_started_at is None:
                thinking_started_at = time.perf_counter()
        elif isinstance(event, RawResponsesStreamEvent) and isinstance(
            event.data, ResponseReasoningSummaryTextDoneEvent
        ):
            summary_key = (event.data.item_id, event.data.summary_index)
            if summary_key in streamed_reasoning_summaries:
                continue
            yield {
                "event": "thinking",
                "data": {"text": event.data.text},
            }
            if thinking_started_at is None:
                thinking_started_at = time.perf_counter()
        # 兼容第三方 provider 直接返回 reasoning_text 的情况，前端仍统一展示到
        # “推理摘要”气泡里。
        elif isinstance(event, RawResponsesStreamEvent) and isinstance(event.data, ResponseReasoningTextDeltaEvent):
            streamed_reasoning_texts.add((event.data.item_id, event.data.content_index, event.data.output_index))
            yield {
                "event": "thinking",
                "data": {"text": event.data.delta},
            }
            if thinking_started_at is None:
                thinking_started_at = time.perf_counter()
        elif isinstance(event, RawResponsesStreamEvent) and isinstance(event.data, ResponseReasoningTextDoneEvent):
            reasoning_key = (event.data.item_id, event.data.content_index, event.data.output_index)
            if reasoning_key in streamed_reasoning_texts:
                continue
            yield {
                "event": "thinking",
                "data": {"text": event.data.text},
            }
            if thinking_started_at is None:
                thinking_started_at = time.perf_counter()
        elif isinstance(event, AgentUpdatedStreamEvent):
            continue
    async for thinking_end in emit_thinking_end():
        yield thinking_end
