import asyncio
import json
from typing import Any

from src.capabilities.session_store import SessionStore
from src.core.logging import log_event
from src.infrastructure.redis_client import get_redis_client

_CHAT_STREAM_EVENT_CACHE_TTL_SECONDS = 600
_CHAT_STREAM_EVENT_CACHE_KEY_PREFIX = "chat:stream:events"
_CHAT_CANCEL_CACHE_SOURCE = "chat_cancel_cache"
_CHAT_PARTIAL_METADATA_KEY = "partial"
_CHAT_STREAM_EVENT_START = "start"
_CHAT_STREAM_EVENT_DELTA = "delta"
_CHAT_STREAM_EVENT_DONE = "done"


def chat_stream_event_cache_key(session_id: str, user_id: str | None) -> str:
    return f"{_CHAT_STREAM_EVENT_CACHE_KEY_PREFIX}:{session_id}:{user_id or 'anonymous'}"


def normalize_stream_event(event: dict[str, Any], user_input: str) -> dict[str, Any]:
    if event.get("type") != _CHAT_STREAM_EVENT_START or event.get("input"):
        return event
    return {**event, "input": user_input}


async def cache_stream_event(
    *,
    session_id: str,
    user_id: str | None,
    event: dict[str, Any],
    logger,
) -> None:
    redis = get_redis_client(for_write=True)
    if redis is None:
        return
    key = chat_stream_event_cache_key(session_id, user_id)
    try:
        await redis.rpush(key, json.dumps(event, ensure_ascii=False))
        await redis.expire(key, _CHAT_STREAM_EVENT_CACHE_TTL_SECONDS)
    except Exception as exc:
        log_event(
            logger,
            "chat_stream_event_cache_failed",
            level=30,
            session_id=session_id,
            error_type=type(exc).__name__,
            error=str(exc),
        )


async def load_cached_stream_events(
    session_id: str,
    user_id: str | None,
    logger,
) -> list[dict[str, Any]]:
    redis = get_redis_client(for_write=False)
    if redis is None:
        return []
    key = chat_stream_event_cache_key(session_id, user_id)
    try:
        values = await redis.lrange(key, 0, -1)
    except Exception as exc:
        log_event(
            logger,
            "chat_stream_event_cache_read_failed",
            level=30,
            session_id=session_id,
            error_type=type(exc).__name__,
            error=str(exc),
        )
        return []

    events: list[dict[str, Any]] = []
    for raw in values:
        try:
            event = json.loads(raw)
        except (TypeError, json.JSONDecodeError):
            continue
        if isinstance(event, dict):
            events.append(event)
    return events


def build_cancelled_turn_from_events(events: list[dict[str, Any]]) -> tuple[str | None, str | None, str | None] | None:
    user_input = None
    assistant_chunks: list[str] = []
    model = None
    for event in events:
        event_type = event.get("type")
        if event_type == _CHAT_STREAM_EVENT_START:
            user_input = event.get("input") or user_input
            model = event.get("model") or model
        elif event_type == _CHAT_STREAM_EVENT_DELTA:
            delta = event.get("delta")
            if isinstance(delta, str) and delta:
                assistant_chunks.append(delta)
        elif event_type == _CHAT_STREAM_EVENT_DONE:
            return None

    assistant_output = "".join(assistant_chunks).strip()
    if not user_input or not assistant_output:
        return None
    return user_input, assistant_output, model


async def persist_cancelled_chat_from_cache(
    *,
    store: SessionStore | None,
    session_id: str,
    user_id: str | None,
    logger,
) -> None:
    if store is None:
        return
    events = await load_cached_stream_events(session_id, user_id, logger)
    cancelled_turn = build_cancelled_turn_from_events(events)
    if cancelled_turn is None:
        return

    user_input, assistant_output, model = cancelled_turn
    try:
        await store.append_turn(
            session_id=session_id,
            user_id=user_id,
            user_input=user_input,
            assistant_output=assistant_output,
            model=model,
            status="cancelled",
            metadata={"source": _CHAT_CANCEL_CACHE_SOURCE, _CHAT_PARTIAL_METADATA_KEY: True},
        )
    except Exception as exc:
        log_event(
            logger,
            "session_store_append_cancelled_failed",
            level=30,
            session_id=session_id,
            error_type=type(exc).__name__,
            error=str(exc),
        )


def schedule_cancelled_chat_persist(
    *,
    store: SessionStore | None,
    session_id: str,
    user_id: str | None,
    logger,
) -> None:
    async def _runner() -> None:
        await persist_cancelled_chat_from_cache(
            store=store,
            session_id=session_id,
            user_id=user_id,
            logger=logger,
        )

    asyncio.create_task(_runner())
