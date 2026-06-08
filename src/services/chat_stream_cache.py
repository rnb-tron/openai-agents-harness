import asyncio
import json
from typing import Any

from src.capabilities.session_store import SessionStore
from src.core.logging import log_event
from src.infrastructure.redis_client import get_redis_client

_CHAT_STREAM_EVENT_CACHE_TTL_SECONDS = 600
_CHAT_STREAM_EVENT_CACHE_KEY_PREFIX = "chat:sse:events"
_CHAT_STREAM_CANCELLED_KEY_PREFIX = "chat:sse:cancelled"
_CHAT_CANCEL_CACHE_SOURCE = "chat_cancel_cache"
_CHAT_PARTIAL_METADATA_KEY = "partial"


def chat_stream_event_cache_key(session_id: str, msg_id: str) -> str:
    return f"{_CHAT_STREAM_EVENT_CACHE_KEY_PREFIX}:{session_id}:{msg_id}"


def chat_stream_cancelled_key(session_id: str, msg_id: str) -> str:
    return f"{_CHAT_STREAM_CANCELLED_KEY_PREFIX}:{session_id}:{msg_id}"


def _extract_frame(record: dict[str, Any]) -> dict[str, Any] | None:
    frame = record.get("frame", record)
    if isinstance(frame, dict):
        return frame
    return None


def frame_sequence(frame: dict[str, Any]) -> int:
    frame_id = frame.get("id")
    if not isinstance(frame_id, str) or "_" not in frame_id:
        return 0
    _, _, suffix = frame_id.rpartition("_")
    try:
        return int(suffix)
    except ValueError:
        return 0


async def cache_stream_frame(
    *,
    session_id: str,
    msg_id: str,
    frame: dict[str, Any],
    logger,
    meta: dict[str, Any] | None = None,
) -> None:
    redis = get_redis_client(for_write=True)
    if redis is None:
        return
    key = chat_stream_event_cache_key(session_id, msg_id)
    record = {"frame": frame, "meta": meta or {}}
    try:
        await redis.rpush(key, json.dumps(record, ensure_ascii=False))
        await redis.expire(key, _CHAT_STREAM_EVENT_CACHE_TTL_SECONDS)
    except Exception as exc:
        log_event(
            logger,
            "chat_stream_event_cache_failed",
            level=30,
            session_id=session_id,
            msg_id=msg_id,
            error_type=type(exc).__name__,
            error=str(exc),
        )


async def load_cached_stream_records(
    session_id: str,
    msg_id: str,
    logger,
) -> list[dict[str, Any]]:
    redis = get_redis_client(for_write=False)
    if redis is None:
        return []
    key = chat_stream_event_cache_key(session_id, msg_id)
    try:
        values = await redis.lrange(key, 0, -1)
    except Exception as exc:
        log_event(
            logger,
            "chat_stream_event_cache_read_failed",
            level=30,
            session_id=session_id,
            msg_id=msg_id,
            error_type=type(exc).__name__,
            error=str(exc),
        )
        return []

    records: list[dict[str, Any]] = []
    for raw in values:
        try:
            record = json.loads(raw)
        except (TypeError, json.JSONDecodeError):
            continue
        if isinstance(record, dict):
            records.append(record)
    return records


async def load_cached_stream_frames(
    session_id: str,
    msg_id: str,
    logger,
) -> list[dict[str, Any]]:
    frames: list[dict[str, Any]] = []
    for record in await load_cached_stream_records(session_id, msg_id, logger):
        frame = _extract_frame(record)
        if frame is not None:
            frames.append(frame)
    return frames


async def load_last_frame_sequence(session_id: str, msg_id: str, logger) -> int:
    frames = await load_cached_stream_frames(session_id, msg_id, logger)
    return max((frame_sequence(frame) for frame in frames), default=0)


def build_cancelled_turn_from_records(records: list[dict[str, Any]]) -> tuple[str | None, str | None, str | None] | None:
    user_input = None
    assistant_chunks: list[str] = []
    model = None
    for record in records:
        frame = _extract_frame(record)
        if frame is None:
            continue
        payload = frame.get("data") if isinstance(frame.get("data"), dict) else {}
        event_name = frame.get("event")
        if event_name == "init":
            meta = record.get("meta") if isinstance(record.get("meta"), dict) else {}
            if isinstance(meta.get("userInput"), str):
                user_input = meta["userInput"]
            if isinstance(payload.get("model"), str):
                model = payload["model"]
        elif event_name == "content":
            text = payload.get("text")
            if isinstance(text, str) and text:
                assistant_chunks.append(text)
        elif event_name == "end":
            return None

    assistant_output = "".join(assistant_chunks).strip()
    if not user_input or not assistant_output:
        return None
    return user_input, assistant_output, model


async def mark_chat_cancelled(
    *,
    session_id: str,
    msg_id: str,
    logger,
) -> None:
    redis = get_redis_client(for_write=True)
    if redis is None:
        return
    key = chat_stream_cancelled_key(session_id, msg_id)
    try:
        await redis.set(key, "1", ex=_CHAT_STREAM_EVENT_CACHE_TTL_SECONDS)
    except Exception as exc:
        log_event(
            logger,
            "chat_stream_cancel_mark_failed",
            level=30,
            session_id=session_id,
            msg_id=msg_id,
            error_type=type(exc).__name__,
            error=str(exc),
        )


async def is_chat_cancelled(session_id: str, msg_id: str, logger) -> bool:
    redis = get_redis_client(for_write=False)
    if redis is None:
        return False
    key = chat_stream_cancelled_key(session_id, msg_id)
    try:
        return bool(await redis.get(key))
    except Exception as exc:
        log_event(
            logger,
            "chat_stream_cancel_mark_read_failed",
            level=30,
            session_id=session_id,
            msg_id=msg_id,
            error_type=type(exc).__name__,
            error=str(exc),
        )
        return False


async def persist_cancelled_chat_from_cache(
    *,
    store: SessionStore | None,
    session_id: str,
    msg_id: str,
    user_id: str | None,
    logger,
) -> None:
    if store is None:
        return
    records = await load_cached_stream_records(session_id, msg_id, logger)
    cancelled_turn = build_cancelled_turn_from_records(records)
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
            metadata={"source": _CHAT_CANCEL_CACHE_SOURCE, _CHAT_PARTIAL_METADATA_KEY: True, "msg_id": msg_id},
        )
    except Exception as exc:
        log_event(
            logger,
            "session_store_append_cancelled_failed",
            level=30,
            session_id=session_id,
            msg_id=msg_id,
            error_type=type(exc).__name__,
            error=str(exc),
        )


def schedule_cancelled_chat_persist(
    *,
    store: SessionStore | None,
    session_id: str,
    msg_id: str,
    user_id: str | None,
    logger,
) -> None:
    async def _runner() -> None:
        await mark_chat_cancelled(session_id=session_id, msg_id=msg_id, logger=logger)
        await persist_cancelled_chat_from_cache(
            store=store,
            session_id=session_id,
            msg_id=msg_id,
            user_id=user_id,
            logger=logger,
        )

    asyncio.create_task(_runner())
