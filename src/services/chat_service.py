import asyncio
import contextlib
import json
from typing import Any

from src.application.orchestration.agent_runtime import AgentSession
from src.capabilities.session_store import SessionStore
from src.core.logging import log_event
from src.services.chat_stream_cache import (
    cache_stream_event,
    normalize_stream_event,
    schedule_cancelled_chat_persist,
)

_CHAT_STREAM_SOURCE = "chat_stream"
_CHAT_RESUME_SOURCE = "chat_resume_stream"
_CHAT_STREAM_EVENT_DONE = "done"
_CHAT_STREAM_QUEUE_DONE = object()
_active_chat_tasks: dict[tuple[str, str], asyncio.Task[None]] = {}
_active_chat_tasks_lock = asyncio.Lock()


class SessionPersistError(Exception):
    """会话持久化失败。"""


def resolve_user_id(principal, requested_user_id: str | None) -> str | None:
    if principal.is_anonymous:
        return requested_user_id
    return principal.user_id


def session_store_from_harness(harness) -> SessionStore | None:
    return getattr(harness, "session_store", None)


def chat_task_key(session_id: str, user_id: str | None) -> tuple[str, str]:
    return (session_id, user_id or "anonymous")


async def register_chat_task(key: tuple[str, str], task: asyncio.Task[None]) -> None:
    async with _active_chat_tasks_lock:
        previous = _active_chat_tasks.get(key)
        if previous is not None and not previous.done() and previous is not task:
            previous.cancel()
        _active_chat_tasks[key] = task


async def get_chat_task(key: tuple[str, str]) -> asyncio.Task[None] | None:
    async with _active_chat_tasks_lock:
        task = _active_chat_tasks.get(key)
        if task is not None and task.done():
            _active_chat_tasks.pop(key, None)
            return None
        return task


async def remove_chat_task(key: tuple[str, str], task: asyncio.Task[None]) -> None:
    async with _active_chat_tasks_lock:
        if _active_chat_tasks.get(key) is task:
            _active_chat_tasks.pop(key, None)


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


async def process_chat_stream_event(
    *,
    store: SessionStore | None,
    session_id: str,
    user_id: str | None,
    user_input: str,
    event: dict[str, Any],
    logger,
) -> dict[str, Any]:
    normalized_event = normalize_stream_event(event, user_input)
    if normalized_event.get("type") == _CHAT_STREAM_EVENT_DONE:
        await persist_chat_turn(
            store=store,
            session_id=session_id,
            user_id=user_id,
            user_input=user_input,
            result=normalized_event.get("data", {}),
            source=_CHAT_STREAM_SOURCE,
            logger=logger,
        )
    await cache_stream_event(session_id=session_id, user_id=user_id, event=normalized_event, logger=logger)
    return normalized_event


async def stream_chat_events(
    *,
    runtime,
    session: AgentSession,
    session_id: str,
    user_id: str | None,
    user_input: str,
    store: SessionStore | None,
    logger,
):
    queue: asyncio.Queue[dict[str, Any] | object] = asyncio.Queue()
    task_key = chat_task_key(session_id, user_id)
    producer_task: asyncio.Task[None] | None = None

    async def produce() -> None:
        try:
            async for event in runtime.run_stream(
                session=session,
                user_input=user_input,
            ):
                processed_event = await process_chat_stream_event(
                    store=store,
                    session_id=session_id,
                    user_id=user_id,
                    user_input=user_input,
                    event=event,
                    logger=logger,
                )
                await queue.put(processed_event)
        except asyncio.CancelledError:
            log_event(
                logger,
                "chat_stream_cancelled",
                session_id=session_id,
                user_id=user_id,
            )
            raise
        except SessionPersistError as exc:
            await queue.put({"type": "error", "detail": f"session persist failed: {exc}"})
        except RuntimeError as exc:
            await queue.put({"type": "error", "detail": str(exc)})
        except Exception as exc:  # pragma: no cover
            await queue.put({"type": "error", "detail": f"chat failed: {exc}"})
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
            yield json.dumps(item, ensure_ascii=False) + "\n"
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
            if event.get("type") == _CHAT_STREAM_EVENT_DONE:
                await persist_resume_result(
                    store=store,
                    session_id=request.session_id,
                    user_id=user_id,
                    result=event.get("data", {}),
                    source=_CHAT_RESUME_SOURCE,
                    logger=logger,
                )
            yield json.dumps(event, ensure_ascii=False) + "\n"
    except SessionPersistError as exc:
        yield (
            json.dumps(
                {"type": "error", "detail": f"session persist failed: {exc}"},
                ensure_ascii=False,
            )
            + "\n"
        )
    except (RuntimeError, ValueError) as exc:
        yield json.dumps({"type": "error", "detail": str(exc)}, ensure_ascii=False) + "\n"
    except Exception as exc:  # pragma: no cover
        yield (
            json.dumps(
                {"type": "error", "detail": f"chat resume failed: {exc}"},
                ensure_ascii=False,
            )
            + "\n"
        )


def schedule_cancel_persist(*, store: SessionStore | None, session_id: str, user_id: str | None, logger) -> None:
    schedule_cancelled_chat_persist(
        store=store,
        session_id=session_id,
        user_id=user_id,
        logger=logger,
    )
