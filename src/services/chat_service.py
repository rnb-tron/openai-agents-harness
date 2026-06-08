import asyncio
import contextlib
import json
import uuid
from dataclasses import dataclass
from typing import Any

from src.application.orchestration.agent_runtime import AgentSession
from src.capabilities.session_store import SessionStore
from src.core.logging import log_event
from src.services.chat_stream_cache import (
    cache_stream_frame,
    is_chat_cancelled,
    load_cached_stream_frames,
    load_last_frame_sequence,
    schedule_cancelled_chat_persist,
)

_CHAT_STREAM_SOURCE = "chat_stream"
_CHAT_RESUME_SOURCE = "chat_resume_stream"
_CHAT_STREAM_QUEUE_DONE = object()
_active_chat_tasks: dict[tuple[str, str, str], asyncio.Task[None]] = {}
_active_chat_tasks_lock = asyncio.Lock()


class SessionPersistError(Exception):
    """会话持久化失败。"""


@dataclass
class ChatStreamState:
    session_id: str
    msg_id: str
    user_id: str | None
    user_input: str
    requested_model: str | None = None
    selected_model: str | None = None
    sequence: int = 0

    def next_id(self) -> str:
        self.sequence += 1
        return f"{self.msg_id}_{self.sequence}"

    def protocol(self, **extra: Any) -> dict[str, Any]:
        payload = {"sessionId": self.session_id, "msgId": self.msg_id}
        payload.update(extra)
        return payload


def resolve_user_id(principal, requested_user_id: str | None) -> str | None:
    if principal.is_anonymous:
        return requested_user_id
    return principal.user_id


def session_store_from_harness(harness) -> SessionStore | None:
    return getattr(harness, "session_store", None)


def chat_task_key(session_id: str, user_id: str | None, msg_id: str) -> tuple[str, str, str]:
    return (session_id, user_id or "anonymous", msg_id)


async def register_chat_task(key: tuple[str, str, str], task: asyncio.Task[None]) -> None:
    async with _active_chat_tasks_lock:
        previous = _active_chat_tasks.get(key)
        if previous is not None and not previous.done() and previous is not task:
            previous.cancel()
        _active_chat_tasks[key] = task


async def get_chat_task(key: tuple[str, str, str]) -> asyncio.Task[None] | None:
    async with _active_chat_tasks_lock:
        task = _active_chat_tasks.get(key)
        if task is not None and task.done():
            _active_chat_tasks.pop(key, None)
            return None
        return task


async def remove_chat_task(key: tuple[str, str, str], task: asyncio.Task[None]) -> None:
    async with _active_chat_tasks_lock:
        if _active_chat_tasks.get(key) is task:
            _active_chat_tasks.pop(key, None)


def generate_msg_id() -> str:
    return f"msg_{uuid.uuid4().hex}"


def parse_msg_id_from_event_id(event_id: str | None) -> str | None:
    if not event_id or "_" not in event_id:
        return None
    prefix, _, _ = event_id.rpartition("_")
    return prefix or None


def serialize_sse_frame(frame: dict[str, Any]) -> str:
    lines = [f"event:{frame['event']}"]
    frame_id = frame.get("id")
    if isinstance(frame_id, str) and frame_id:
        lines.append(f"id:{frame_id}")
    lines.append(f"data:{json.dumps(frame['data'], ensure_ascii=False)}")
    return "\n".join(lines) + "\n\n"


def build_sse_frame(
    state: ChatStreamState,
    event_name: str,
    *,
    body: dict[str, Any] | None = None,
    protocol_extra: dict[str, Any] | None = None,
    include_id: bool = True,
) -> dict[str, Any]:
    data = {"protocol": state.protocol(**(protocol_extra or {}))}
    if body:
        data.update(body)
    frame: dict[str, Any] = {"event": event_name, "data": data}
    if include_id:
        frame["id"] = state.next_id()
    return frame


def build_error_frame(
    *,
    session_id: str,
    msg_id: str | None,
    detail: str,
    code: str = "chatError",
) -> dict[str, Any]:
    protocol: dict[str, Any] = {"sessionId": session_id}
    if msg_id:
        protocol["msgId"] = msg_id
    return {
        "event": "error",
        "data": {
            "protocol": protocol,
            "code": code,
            "msg": detail,
        },
    }


async def cache_frame(
    *,
    session_id: str,
    msg_id: str,
    frame: dict[str, Any],
    logger,
    meta: dict[str, Any] | None = None,
) -> None:
    await cache_stream_frame(
        session_id=session_id,
        msg_id=msg_id,
        frame=frame,
        logger=logger,
        meta=meta,
    )


async def persist_chat_turn(
    *,
    store: SessionStore | None,
    session_id: str,
    user_id: str | None,
    user_input: str,
    result: dict[str, Any],
    source: str,
    logger,
) -> None:
    if store is None:
        return
    try:
        status = "interrupted" if result.get("interrupted") else "completed"
        await store.append_turn(
            session_id=session_id,
            user_id=user_id,
            user_input=user_input,
            assistant_output=result.get("output"),
            model=result.get("model"),
            status=status,
            metadata={
                "source": source,
                "tool_calls": result.get("tool_calls", []),
                "msg_id": result.get("msgId"),
            },
        )
    except Exception as exc:
        log_event(
            logger,
            "session_store_append_turn_failed",
            level=30,
            session_id=session_id,
            error_type=type(exc).__name__,
            error=str(exc),
        )
        raise SessionPersistError(f"session store append turn failed: {exc}") from exc


async def persist_resume_result(
    *,
    store: SessionStore | None,
    session_id: str,
    user_id: str | None,
    result: dict[str, Any],
    source: str,
    logger,
) -> None:
    if store is None:
        return
    try:
        await store.ensure_session(session_id=session_id, user_id=user_id)
        await store.append_message(
            session_id=session_id,
            user_id=user_id,
            role="assistant",
            content=result.get("output") or "",
            model=result.get("model"),
            status="interrupted" if result.get("interrupted") else "completed",
            metadata={
                "source": source,
                "tool_calls": result.get("tool_calls", []),
            },
        )
    except Exception as exc:
        log_event(
            logger,
            "session_store_append_resume_failed",
            level=30,
            session_id=session_id,
            error_type=type(exc).__name__,
            error=str(exc),
        )
        raise SessionPersistError(f"session store append resume failed: {exc}") from exc


def _persist_result_from_end_data(data: dict[str, Any], msg_id: str) -> dict[str, Any]:
    return {
        "output": data.get("output"),
        "model": data.get("model"),
        "interrupted": bool(data.get("interrupted")),
        "tool_calls": data.get("tool_calls", []),
        "metadata": data.get("metadata", {}),
        "msgId": msg_id,
    }


def _prepare_frame_from_event(state: ChatStreamState, event: dict[str, Any]) -> dict[str, Any]:
    event_name = event.get("event")
    if not isinstance(event_name, str) or not event_name:
        raise ValueError("chat event missing event name")
    raw_data = event.get("data")
    data = dict(raw_data) if isinstance(raw_data, dict) else {}
    if event_name == "init":
        if state.selected_model is None:
            state.selected_model = data.get("model") or state.requested_model
        if state.selected_model and "model" not in data:
            data["model"] = state.selected_model
        if state.user_id and "userId" not in data:
            data["userId"] = state.user_id
    protocol_extra: dict[str, Any] | None = None
    if event_name == "thinkingEnd" and "cost" in data:
        protocol_extra = {"cost": data.pop("cost")}
    body = {key: value for key, value in data.items() if value is not None}
    return build_sse_frame(
        state,
        event_name,
        body=body or None,
        protocol_extra=protocol_extra,
        include_id=event_name != "error",
    )


async def process_chat_event(
    *,
    state: ChatStreamState,
    store: SessionStore | None,
    event: dict[str, Any],
    source: str,
    logger,
) -> list[dict[str, Any]]:
    event_name = event.get("event")
    if event_name == "error":
        data = event.get("data") if isinstance(event.get("data"), dict) else {}
        return [
            build_error_frame(
                session_id=state.session_id,
                msg_id=state.msg_id,
                detail=str(data.get("msg") or "chat failed"),
                code=str(data.get("code") or "chatError"),
            )
        ]

    frame = _prepare_frame_from_event(state, event)
    meta = {"userInput": state.user_input} if event_name == "init" else None
    await cache_frame(
        session_id=state.session_id,
        msg_id=state.msg_id,
        frame=frame,
        logger=logger,
        meta=meta,
    )
    if event_name == "end":
        result = _persist_result_from_end_data(frame["data"], state.msg_id)
        if source == _CHAT_STREAM_SOURCE:
            await persist_chat_turn(
                store=store,
                session_id=state.session_id,
                user_id=state.user_id,
                user_input=state.user_input,
                result=result,
                source=source,
                logger=logger,
            )
        elif source == _CHAT_RESUME_SOURCE:
            await persist_resume_result(
                store=store,
                session_id=state.session_id,
                user_id=state.user_id,
                result=result,
                source=source,
                logger=logger,
            )
    return [frame]


async def replay_chat_events(
    *,
    session_id: str,
    msg_id: str,
    last_event_id: str | None,
    logger,
):
    if await is_chat_cancelled(session_id, msg_id, logger):
        yield serialize_sse_frame(
            build_error_frame(
                session_id=session_id,
                msg_id=msg_id,
                detail="当前轮次已取消，拒绝续传",
                code="chatCancelled",
            )
        )
        return
    frames = await load_cached_stream_frames(session_id, msg_id, logger)
    if not frames:
        yield serialize_sse_frame(
            build_error_frame(
                session_id=session_id,
                msg_id=msg_id,
                detail="未找到可续传的消息缓存",
                code="chatReplayNotFound",
            )
        )
        return
    start_index = 0
    if last_event_id:
        for index, frame in enumerate(frames):
            if frame.get("id") == last_event_id:
                start_index = index + 1
                break
        else:
            yield serialize_sse_frame(
                build_error_frame(
                    session_id=session_id,
                    msg_id=msg_id,
                    detail="lastEventId 不存在",
                    code="chatReplayInvalidCursor",
                )
            )
            return
    for frame in frames[start_index:]:
        yield serialize_sse_frame(frame)


async def stream_chat_events(
    *,
    runtime,
    session: AgentSession,
    session_id: str,
    user_id: str | None,
    user_input: str,
    model: str | None,
    msg_id: str | None,
    last_event_id: str | None,
    store: SessionStore | None,
    logger,
):
    replay_msg_id = msg_id or parse_msg_id_from_event_id(last_event_id)
    if replay_msg_id is not None:
        async for chunk in replay_chat_events(
            session_id=session_id,
            msg_id=replay_msg_id,
            last_event_id=last_event_id,
            logger=logger,
        ):
            yield chunk
        return

    resolved_msg_id = generate_msg_id()
    state = ChatStreamState(
        session_id=session_id,
        msg_id=resolved_msg_id,
        user_id=user_id,
        user_input=user_input,
        requested_model=model,
    )
    queue: asyncio.Queue[dict[str, Any] | object] = asyncio.Queue()
    task_key = chat_task_key(session_id, user_id, resolved_msg_id)
    producer_task: asyncio.Task[None] | None = None

    async def produce() -> None:
        try:
            async for event in runtime.run_stream(
                session=session,
                user_input=user_input,
            ):
                processed_frames = await process_chat_event(
                    state=state,
                    store=store,
                    event=event,
                    source=_CHAT_STREAM_SOURCE,
                    logger=logger,
                )
                for frame in processed_frames:
                    await queue.put(frame)
        except asyncio.CancelledError:
            log_event(
                logger,
                "chat_stream_cancelled",
                session_id=session_id,
                user_id=user_id,
                msg_id=resolved_msg_id,
            )
            raise
        except SessionPersistError as exc:
            await queue.put(
                build_error_frame(
                    session_id=session_id,
                    msg_id=resolved_msg_id,
                    detail=f"session persist failed: {exc}",
                    code="sessionPersistFailed",
                )
            )
        except RuntimeError as exc:
            await queue.put(
                build_error_frame(
                    session_id=session_id,
                    msg_id=resolved_msg_id,
                    detail=str(exc),
                )
            )
        except Exception as exc:  # pragma: no cover
            await queue.put(
                build_error_frame(
                    session_id=session_id,
                    msg_id=resolved_msg_id,
                    detail=f"chat failed: {exc}",
                )
            )
        finally:
            if producer_task is not None:
                await remove_chat_task(task_key, producer_task)
            await queue.put(_CHAT_STREAM_QUEUE_DONE)

    producer_task = asyncio.create_task(produce())
    await register_chat_task(task_key, producer_task)
    try:
        while True:
            item = await queue.get()
            if item is _CHAT_STREAM_QUEUE_DONE:
                break
            yield serialize_sse_frame(item)
    finally:
        if producer_task is not None and not producer_task.done():
            producer_task.cancel()
        if producer_task is not None:
            with contextlib.suppress(asyncio.CancelledError):
                await producer_task


async def stream_resume_events(
    *,
    runtime,
    session: AgentSession,
    request,
    user_id: str | None,
    store: SessionStore | None,
    logger,
):
    state = ChatStreamState(
        session_id=request.session_id,
        msg_id=request.msg_id,
        user_id=user_id,
        user_input=request.message,
        requested_model=request.model,
        selected_model=request.model,
        sequence=await load_last_frame_sequence(request.session_id, request.msg_id, logger),
    )
    try:
        async for event in runtime.resume_stream_with_approval(
            session=session,
            run_state=request.run_state,
            interruption_index=request.interruption_index,
            approved=request.approved,
            approval_request_id=request.approval_request_id,
            reviewer=user_id or "anonymous",
            model=request.model,
            user_input=request.message,
            always=request.always,
            rejection_message=request.rejection_message,
        ):
            frames = await process_chat_event(
                state=state,
                store=store,
                event=event,
                source=_CHAT_RESUME_SOURCE,
                logger=logger,
            )
            for frame in frames:
                yield serialize_sse_frame(frame)
    except SessionPersistError as exc:
        yield serialize_sse_frame(
            build_error_frame(
                session_id=request.session_id,
                msg_id=request.msg_id,
                detail=f"session persist failed: {exc}",
                code="sessionPersistFailed",
            )
        )
    except (RuntimeError, ValueError) as exc:
        yield serialize_sse_frame(
            build_error_frame(
                session_id=request.session_id,
                msg_id=request.msg_id,
                detail=str(exc),
            )
        )
    except Exception as exc:  # pragma: no cover
        yield serialize_sse_frame(
            build_error_frame(
                session_id=request.session_id,
                msg_id=request.msg_id,
                detail=f"chat resume failed: {exc}",
            )
        )


def schedule_cancel_persist(
    *,
    store: SessionStore | None,
    session_id: str,
    msg_id: str,
    user_id: str | None,
    logger,
) -> None:
    schedule_cancelled_chat_persist(
        store=store,
        session_id=session_id,
        msg_id=msg_id,
        user_id=user_id,
        logger=logger,
    )
