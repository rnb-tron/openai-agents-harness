import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import AliasChoices, BaseModel, ConfigDict, Field, model_validator

from src.api.middleware.auth.base import Principal
from src.api.middleware.auth.deps import get_current_principal
from src.application.orchestration.agent_runtime import AgentSession
from src.core.logging import setup_logger
from src.harness.builder import Harness
from src.harness.deps import get_harness
from src.services.chat_service import (
    chat_task_key,
    get_chat_task,
    resolve_user_id,
    schedule_cancel_persist,
    session_store_from_harness,
    stream_chat_events,
    stream_resume_events,
)
from src.utils.response import create_success_response

router = APIRouter(prefix="/chat", tags=["chat"])
logger = setup_logger("api.routers.chat")


class ChatRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    session_id: str | None = Field(
        default=None,
        validation_alias=AliasChoices("sessionId", "session_id"),
        description="会话 ID；新请求可不传，续传必传",
    )
    query: str | None = Field(default=None, description="用户本轮输入")
    model: str | None = Field(default=None, description="可选模型")
    msg_id: str | None = Field(
        default=None,
        validation_alias=AliasChoices("msgId", "msg_id"),
        description="整轮续传的消息 ID",
    )
    last_event_id: str | None = Field(
        default=None,
        validation_alias=AliasChoices("lastEventId", "last_event_id"),
        description="分片续传游标",
    )
    user_id: str | None = Field(
        default=None,
        validation_alias=AliasChoices("userId", "user_id"),
        description="用户唯一 ID",
    )
    messages: Any | None = Field(default=None, description="保留字段")
    options: dict[str, Any] | None = Field(default=None, description="保留字段")

    @model_validator(mode="after")
    def validate_request(self) -> "ChatRequest":
        if not self.user_id:
            raise ValueError("userId is required")
        if self.last_event_id or self.msg_id:
            if not self.session_id:
                raise ValueError("sessionId is required for replay requests")
            return self
        if not self.query:
            raise ValueError("query is required")
        return self


class ChatSessionCreateRequest(BaseModel):
    session_id: str | None = Field(default=None, description="optional session id")
    user_id: str | None = Field(default=None, description="optional user id")
    title: str | None = Field(default="新会话", description="session title")


class ChatResumeRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    run_state: dict[str, Any] = Field(..., description="OpenAI Agents SDK 序列化运行状态")
    approval_request_id: str | None = Field(default=None, description="启用 HITL 时返回的审批请求标识")
    interruption_index: int = Field(..., ge=0, description="待批准或拒绝的中断序号")
    approved: bool = Field(..., description="人工审批决策")
    session_id: str = Field(..., description="中断响应返回的会话标识")
    msg_id: str = Field(
        ...,
        validation_alias=AliasChoices("msgId", "msg_id"),
        description="本轮消息标识",
    )
    message: str = Field(..., min_length=1, description="中断响应中的原始用户输入")
    model: str = Field(..., description="中断响应中的实际执行模型")
    always: bool = Field(default=False, description="是否对匹配的后续工具调用复用该决策")
    rejection_message: str | None = Field(default=None, description="拒绝工具调用时返回的说明")
    user_id: str | None = Field(default=None, description="可选用户标识")


class ChatCancelRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    session_id: str | None = Field(
        default=None,
        validation_alias=AliasChoices("sessionId", "session_id"),
        description="要取消的会话标识",
    )
    msg_id: str | None = Field(
        default=None,
        validation_alias=AliasChoices("msgId", "msg_id"),
        description="要取消的消息标识",
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
        if not self.msg_id:
            raise ValueError("msgId is required")
        if not self.user_id:
            raise ValueError("userId is required")
        return self


class ChatCancelResponse(BaseModel):
    code: str
    msg: str


@router.post("")
async def chat(
    request: ChatRequest,
    principal: Principal = Depends(get_current_principal),
    harness: Harness = Depends(get_harness),
) -> StreamingResponse:
    """以 SSE 事件流返回 chat 执行过程。"""
    user_id = resolve_user_id(principal, request.user_id)
    session_id = request.session_id or str(uuid.uuid4())
    session = AgentSession(session_id=session_id, user_id=user_id)
    store = session_store_from_harness(harness)

    async def events():
        async for chunk in stream_chat_events(
            runtime=harness.runtime,
            session=session,
            session_id=session_id,
            user_id=user_id,
            user_input=request.query or "",
            model=request.model,
            msg_id=request.msg_id,
            last_event_id=request.last_event_id,
            store=store,
            logger=logger,
        ):
            yield chunk

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"},
    )


@router.post("/cancel", response_model=ChatCancelResponse)
async def cancel_chat(
    request: ChatCancelRequest,
    principal: Principal = Depends(get_current_principal),
    harness: Harness = Depends(get_harness),
) -> ChatCancelResponse:
    """取消当前会话正在执行的普通 chat stream。"""
    session_id = request.session_id or ""
    msg_id = request.msg_id or ""
    user_id = resolve_user_id(principal, request.user_id)
    task = await get_chat_task(chat_task_key(session_id, user_id, msg_id))
    if task is None:
        return ChatCancelResponse(code="1", msg="未找到运行中的会话")
    task.cancel()
    schedule_cancel_persist(
        store=session_store_from_harness(harness),
        session_id=session_id,
        msg_id=msg_id,
        user_id=user_id,
        logger=logger,
    )
    return ChatCancelResponse(code="1", msg="取消成功")


@router.post("/resume/stream")
async def resume_chat_stream(
    request: ChatResumeRequest,
    principal: Principal = Depends(get_current_principal),
    harness: Harness = Depends(get_harness),
) -> StreamingResponse:
    """以 SSE 流式返回人工审批后的继续执行结果。"""
    user_id = resolve_user_id(principal, request.user_id)
    session = AgentSession(session_id=request.session_id, user_id=user_id)
    store = session_store_from_harness(harness)

    async def events():
        async for chunk in stream_resume_events(
            runtime=harness.runtime,
            session=session,
            request=request,
            user_id=user_id,
            store=store,
            logger=logger,
        ):
            yield chunk

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"},
    )


@router.get("/sessions")
async def list_chat_sessions(
    limit: int = 20,
    user_id: str | None = None,
    principal: Principal = Depends(get_current_principal),
    harness: Harness = Depends(get_harness),
):
    """列出当前用户的持久化会话。"""
    store = session_store_from_harness(harness)
    if store is None:
        raise HTTPException(status_code=400, detail="SESSION_STORE_ENABLED is false")
    resolved_user_id = resolve_user_id(principal, user_id)
    return create_success_response(data=await store.list_sessions(user_id=resolved_user_id, limit=limit))


@router.post("/sessions")
async def create_chat_session(
    request: ChatSessionCreateRequest,
    principal: Principal = Depends(get_current_principal),
    harness: Harness = Depends(get_harness),
):
    """创建一个空会话，便于 UI 先展示在会话列表中。"""
    store = session_store_from_harness(harness)
    if store is None:
        raise HTTPException(status_code=400, detail="SESSION_STORE_ENABLED is false")
    user_id = resolve_user_id(principal, request.user_id)
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
    store = session_store_from_harness(harness)
    if store is None:
        raise HTTPException(status_code=400, detail="SESSION_STORE_ENABLED is false")
    session = await store.get_session(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="session not found")
    requester = resolve_user_id(principal, None)
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
    store = session_store_from_harness(harness)
    if store is None:
        raise HTTPException(status_code=400, detail="SESSION_STORE_ENABLED is false")
    session = await store.get_session(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="session not found")
    requester = resolve_user_id(principal, user_id)
    if requester is not None and session["user_id"] != requester:
        raise HTTPException(status_code=403, detail="session forbidden")
    deleted = await store.delete_session(session_id)
    if deleted and harness.memory_manager is not None:
        await harness.memory_manager.clear_session(session_id)
    return create_success_response(data={"session_id": session_id, "deleted": deleted})
