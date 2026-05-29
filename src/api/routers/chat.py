import json
import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from src.api.middleware.auth.base import Principal
from src.api.middleware.auth.deps import get_current_principal
from src.application.orchestration.agent_runtime import AgentSession
from src.capabilities.session_store import SessionStore
from src.core.logging import setup_logger
from src.harness.builder import Harness
from src.harness.deps import get_harness
from src.utils.response import create_success_response

router = APIRouter(prefix="/chat", tags=["chat"])
logger = setup_logger("api.routers.chat")


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


def _resolve_user_id(principal: Principal, requested_user_id: str | None) -> str | None:
    if principal.is_anonymous:
        return requested_user_id
    return principal.user_id


def _session_store(harness: Harness) -> SessionStore | None:
    return getattr(harness, "session_store", None)


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
                "advanced": result.get("advanced", {}),
            },
        )
    except Exception as exc:
        logger.warning(
            "session_store_append_turn_failed",
            extra={"session_id": session_id, "error_type": type(exc).__name__},
        )


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
                "advanced": result.get("advanced", {}),
            },
        )
    except Exception as exc:
        logger.warning(
            "session_store_append_resume_failed",
            extra={"session_id": session_id, "error_type": type(exc).__name__},
        )


@router.post("")
async def chat(
    request: ChatRequest,
    principal: Principal = Depends(get_current_principal),
    harness: Harness = Depends(get_harness),
):
    # 已认证身份优先；只有 AuthPlugin 关闭、当前是匿名 principal 时，
    # 才使用请求体里的 user_id 作为兜底。
    user_id = _resolve_user_id(principal, request.user_id)

    session_id = request.session_id or str(uuid.uuid4())
    session = AgentSession(session_id=session_id, user_id=user_id)
    try:
        result = await harness.runtime.run(session=session, user_input=request.message)
        await _persist_chat_turn(
            store=_session_store(harness),
            session_id=session_id,
            user_id=user_id,
            user_input=request.message,
            result=result,
            source="chat",
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:  # pragma: no cover
        raise HTTPException(status_code=500, detail=f"chat failed: {exc}") from exc
    return create_success_response(data=result)


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
        try:
            async for event in harness.runtime.run_stream(
                session=session,
                user_input=request.message,
            ):
                if event.get("type") == "done":
                    await _persist_chat_turn(
                        store=_session_store(harness),
                        session_id=session_id,
                        user_id=user_id,
                        user_input=request.message,
                        result=event.get("data", {}),
                        source="chat_stream",
                    )
                yield json.dumps(event, ensure_ascii=False) + "\n"
        except RuntimeError as exc:
            yield json.dumps({"type": "error", "detail": str(exc)}, ensure_ascii=False) + "\n"
        except Exception as exc:  # pragma: no cover
            yield json.dumps(
                {"type": "error", "detail": f"chat failed: {exc}"},
                ensure_ascii=False,
            ) + "\n"

    return StreamingResponse(
        events(),
        media_type="application/x-ndjson",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post("/resume")
async def resume_chat(
    request: ChatResumeRequest,
    principal: Principal = Depends(get_current_principal),
    harness: Harness = Depends(get_harness),
):
    """在人工批准或拒绝工具调用后恢复 Agents SDK 运行。"""
    user_id = _resolve_user_id(principal, request.user_id)
    session = AgentSession(
        session_id=request.session_id,
        user_id=user_id,
    )
    try:
        result = await harness.runtime.resume_with_approval(
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
        )
        await _persist_resume_result(
            store=_session_store(harness),
            session_id=request.session_id,
            user_id=user_id,
            result=result,
            source="chat_resume",
        )
    except (RuntimeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:  # pragma: no cover
        raise HTTPException(status_code=500, detail=f"chat resume failed: {exc}") from exc
    return create_success_response(data=result)


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
        except (RuntimeError, ValueError) as exc:
            yield json.dumps({"type": "error", "detail": str(exc)}, ensure_ascii=False) + "\n"
        except Exception as exc:  # pragma: no cover
            yield json.dumps(
                {"type": "error", "detail": f"chat resume failed: {exc}"},
                ensure_ascii=False,
            ) + "\n"

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
    return create_success_response(data=await store.list_messages(session_id=session_id, limit=limit))


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
