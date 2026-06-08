import asyncio
import contextlib
import json
import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import AliasChoices, BaseModel, Field, model_validator

from src.api.middleware.auth.base import Principal
from src.api.middleware.auth.deps import get_current_principal
from src.application.orchestration.agent_runtime import AgentSession
from src.capabilities.session_store import SessionStore
from src.core.logging import log_event, setup_logger
from src.harness.builder import Harness
from src.harness.deps import get_harness
from src.infrastructure.redis_client import get_redis_client
from src.utils.response import create_success_response

router = APIRouter(prefix="/chat", tags=["chat"])
logger = setup_logger("api.routers.chat")
_CHAT_STREAM_EVENT_CACHE_TTL_SECONDS = 600
_CHAT_STREAM_QUEUE_DONE = object()
_active_chat_tasks: dict[tuple[str, str], asyncio.Task[None]] = {}
_active_chat_tasks_lock = asyncio.Lock()


class SessionPersistError(Exception):
    """会话持久化失败。"""


class ChatRequest(BaseModel):
    message: str = Field(..., description="user input")
    session_id: str | None = Field(default=None, description="optional session id for memory")
    user_id: str | None = Field(default=None, description="optional user id")


class ChatSessionCreateRequest(BaseModel):
    session_id: str | None = Field(default=None, description="optional session id")
    user_id: str | None = Field(default=None, description="optional user id")
    title: str | None = Field(default="新会话", description="session title")


class ChatResumeRequest(BaseModel):
    run_state: dict[str, Any] = Field(..., description="OpenAI Agents SDK 序列化运行状态")
    approval_request_id: str | None = Field(default=None, description="启用 HITL 时返回的审批请求标识")
    interruption_index: int = Field(..., ge=0, description="待批准或拒绝的中断序号")
    approved: bool = Field(..., description="人工审批决策")
    session_id: str = Field(..., description="中断响应返回的会话标识")
    message: str = Field(..., min_length=1, description="中断响应中的原始用户输入")
    model: str = Field(..., description="中断响应中的实际执行模型")
    always: bool = Field(default=False, description="是否对匹配的后续工具调用复用该决策")
    rejection_message: str | None = Field(default=None, description="拒绝工具调用时返回的说明")
    user_id: str | None = Field(default=None, description="可选用户标识")


class ChatCancelRequest(BaseModel):
    session_id: str | None = Field(
        default=None,
        validation_alias=AliasChoices("sessionId", "session_id"),
        description="要取消的会话标识",
    )
    user_id: str | None = Field(
        default=None,
        validation_alias=AliasChoices("userId", "user_id"),
        description="可选用户标识",
    )

    @model_validator(mode="after")
    def validate_session_id(self) -> "ChatCancelRequest":
        if not self.session_id:
            raise ValueError("sessionId is required")
        return self


class ChatCancelResponse(BaseModel):
    code: str
    msg: str


def _resolve_user_id(principal: Principal, requested_user_id: str | None) -> str | None:
    if principal.is_anonymous:
        return requested_user_id
    return principal.user_id


def _session_store(harness: Harness) -> SessionStore | None:
    return getattr(harness, "session_store", None)


def _chat_task_key(session_id: str, user_id: str | None) -> tuple[str, str]:
    return (session_id, user_id or "anonymous")


async def _register_chat_task(key: tuple[str, str], task: asyncio.Task[None]) -> None:
    async with _active_chat_tasks_lock:
        previous = _active_chat_tasks.get(key)
        if previous is not None and not previous.done() and previous is not task:
            previous.cancel()
        _active_chat_tasks[key] = task


async def _get_chat_task(key: tuple[str, str]) -> asyncio.Task[None] | None:
    async with _active_chat_tasks_lock:
        task = _active_chat_tasks.get(key)
        if task is not None and task.done():
            _active_chat_tasks.pop(key, None)
            return None
        return task


async def _remove_chat_task(key: tuple[str, str], task: asyncio.Task[None]) -> None:
    async with _active_chat_tasks_lock:
        if _active_chat_tasks.get(key) is task:
            _active_chat_tasks.pop(key, None)


def _chat_stream_event_cache_key(session_id: str, user_id: str | None) -> str:
    return f"chat:stream:events:{session_id}:{user_id or 'anonymous'}"


async def _append_stream_event_cache(*, session_id: str, user_id: str | None, event: dict[str, Any]) -> None:
    redis = get_redis_client(for_write=True)
    if redis is None:
        return
    key = _chat_stream_event_cache_key(session_id, user_id)
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


async def _persist_cancelled_chat_from_cache(
    *,
    store: SessionStore | None,
    session_id: str,
    user_id: str | None,
) -> None:
    if store is None:
        return
    redis = get_redis_client(for_write=False)
    if redis is None:
        return
    key = _chat_stream_event_cache_key(session_id, user_id)
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
        return

    user_input = None
    assistant_chunks: list[str] = []
    model = None
    for raw in values:
        try:
            event = json.loads(raw)
        except (TypeError, json.JSONDecodeError):
            continue
        event_type = event.get("type")
        if event_type == "start":
            user_input = event.get("input") or user_input
            model = event.get("model") or model
        elif event_type == "delta":
            delta = event.get("delta")
            if isinstance(delta, str) and delta:
                assistant_chunks.append(delta)
        elif event_type == "done":
            return

    assistant_output = "".join(assistant_chunks).strip()
    if not user_input or not assistant_output:
        return

    try:
        await store.append_turn(
            session_id=session_id,
            user_id=user_id,
            user_input=user_input,
            assistant_output=assistant_output,
            model=model,
            status="cancelled",
            metadata={"source": "chat_cancel_cache", "partial": True},
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


def _schedule_cancelled_chat_persist(
    *,
    store: SessionStore | None,
    session_id: str,
    user_id: str | None,
) -> None:
    async def _runner() -> None:
        await _persist_cancelled_chat_from_cache(
            store=store,
            session_id=session_id,
            user_id=user_id,
        )

    asyncio.create_task(_runner())


async def _persist_chat_turn(
    *,
    store: SessionStore | None,
    session_id: str,
    user_id: str | None,
    user_input: str,
    result: dict[str, Any],
    source: str,
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


async def _persist_resume_result(
    *,
    store: SessionStore | None,
    session_id: str,
    user_id: str | None,
    result: dict[str, Any],
    source: str,
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


@router.post("/stream")
async def chat_stream(
    request: ChatRequest,
    principal: Principal = Depends(get_current_principal),
    harness: Harness = Depends(get_harness),
) -> StreamingResponse:
    """以 NDJSON 事件流返回 chat 执行过程。"""
    user_id = _resolve_user_id(principal, request.user_id)
    session_id = request.session_id or str(uuid.uuid4())
    session = AgentSession(session_id=session_id, user_id=user_id)

    async def events():
        queue: asyncio.Queue[dict[str, Any] | object] = asyncio.Queue()
        task_key = _chat_task_key(session_id, user_id)
        producer_task: asyncio.Task[None] | None = None

        async def produce() -> None:
            try:
                async for event in harness.runtime.run_stream(
                    session=session,
                    user_input=request.message,
                ):
                    if event.get("type") == "start" and not event.get("input"):
                        event = {**event, "input": request.message}
                    if event.get("type") == "done":
                        await _persist_chat_turn(
                            store=_session_store(harness),
                            session_id=session_id,
                            user_id=user_id,
                            user_input=request.message,
                            result=event.get("data", {}),
                            source="chat_stream",
                        )
                    await _append_stream_event_cache(session_id=session_id, user_id=user_id, event=event)
                    await queue.put(event)
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
                    await _remove_chat_task(task_key, producer_task)
                await queue.put(_CHAT_STREAM_QUEUE_DONE)

        producer_task = asyncio.create_task(produce())
        await _register_chat_task(task_key, producer_task)
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

    return StreamingResponse(
        events(),
        media_type="application/x-ndjson",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post("/cancel", response_model=ChatCancelResponse)
async def cancel_chat(
    request: ChatCancelRequest,
    principal: Principal = Depends(get_current_principal),
    harness: Harness = Depends(get_harness),
) -> ChatCancelResponse:
    """取消当前会话正在执行的普通 chat stream。"""
    session_id = request.session_id or ""
    user_id = _resolve_user_id(principal, request.user_id)
    task = await _get_chat_task(_chat_task_key(session_id, user_id))
    if task is None:
        return ChatCancelResponse(code="1", msg="未找到运行中的会话")
    task.cancel()
    _schedule_cancelled_chat_persist(
        store=_session_store(harness),
        session_id=session_id,
        user_id=user_id,
    )
    return ChatCancelResponse(code="1", msg="取消成功")


@router.post("/resume/stream")
async def resume_chat_stream(
    request: ChatResumeRequest,
    principal: Principal = Depends(get_current_principal),
    harness: Harness = Depends(get_harness),
) -> StreamingResponse:
    """以 NDJSON 流式返回人工审批后的继续执行结果。"""
    user_id = _resolve_user_id(principal, request.user_id)
    session = AgentSession(session_id=request.session_id, user_id=user_id)

    async def events():
        try:
            async for event in harness.runtime.resume_stream_with_approval(
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
                if event.get("type") == "done":
                    await _persist_resume_result(
                        store=_session_store(harness),
                        session_id=request.session_id,
                        user_id=user_id,
                        result=event.get("data", {}),
                        source="chat_resume_stream",
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

    return StreamingResponse(
        events(),
        media_type="application/x-ndjson",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get("/sessions")
async def list_chat_sessions(
    limit: int = 20,
    user_id: str | None = None,
    principal: Principal = Depends(get_current_principal),
    harness: Harness = Depends(get_harness),
):
    """列出当前用户的持久化会话。"""
    store = _session_store(harness)
    if store is None:
        raise HTTPException(status_code=400, detail="SESSION_STORE_ENABLED is false")
    resolved_user_id = _resolve_user_id(principal, user_id)
    return create_success_response(data=await store.list_sessions(user_id=resolved_user_id, limit=limit))


@router.post("/sessions")
async def create_chat_session(
    request: ChatSessionCreateRequest,
    principal: Principal = Depends(get_current_principal),
    harness: Harness = Depends(get_harness),
):
    """创建一个空会话，便于 UI 先展示在会话列表中。"""
    store = _session_store(harness)
    if store is None:
        raise HTTPException(status_code=400, detail="SESSION_STORE_ENABLED is false")
    user_id = _resolve_user_id(principal, request.user_id)
    session_id = request.session_id or str(uuid.uuid4())
    session = await store.create_session(
        session_id=session_id,
        user_id=user_id,
        title=request.title or "新会话",
        metadata={"source": "ui"},
    )
    return create_success_response(data=session)


@router.get("/sessions/{session_id}/messages")
async def list_chat_messages(
    session_id: str,
    limit: int = 100,
    recent: bool = False,
    principal: Principal = Depends(get_current_principal),
    harness: Harness = Depends(get_harness),
):
    """列出一个会话的持久化消息流水。"""
    store = _session_store(harness)
    if store is None:
        raise HTTPException(status_code=400, detail="SESSION_STORE_ENABLED is false")
    session = await store.get_session(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="session not found")
    requester = _resolve_user_id(principal, None)
    if requester is not None and session["user_id"] != requester:
        raise HTTPException(status_code=403, detail="session forbidden")
    if recent:
        messages = await store.list_recent_messages(session_id=session_id, limit=limit)
    else:
        messages = await store.list_messages(session_id=session_id, limit=limit)
    return create_success_response(data=messages)


@router.delete("/sessions/{session_id}")
async def delete_chat_session(
    session_id: str,
    user_id: str | None = None,
    principal: Principal = Depends(get_current_principal),
    harness: Harness = Depends(get_harness),
):
    """删除一个会话及其消息流水。"""
    store = _session_store(harness)
    if store is None:
        raise HTTPException(status_code=400, detail="SESSION_STORE_ENABLED is false")
    session = await store.get_session(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="session not found")
    requester = _resolve_user_id(principal, user_id)
    if requester is not None and session["user_id"] != requester:
        raise HTTPException(status_code=403, detail="session forbidden")
    deleted = await store.delete_session(session_id)
    if deleted and harness.memory_manager is not None:
        await harness.memory_manager.clear_session(session_id)
    return create_success_response(data={"session_id": session_id, "deleted": deleted})
