import json
import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from src.api.middleware.auth.base import Principal
from src.api.middleware.auth.deps import get_current_principal
from src.application.orchestration.agent_runtime import AgentSession
from src.harness.builder import Harness
from src.harness.deps import get_harness
from src.utils.response import create_success_response

router = APIRouter(prefix="/chat", tags=["chat"])


class ChatRequest(BaseModel):
    message: str = Field(..., description="user input")
    session_id: str | None = Field(default=None, description="optional session id for memory")
    user_id: str | None = Field(default=None, description="optional user id")


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


@router.post("")
async def chat(
    request: ChatRequest,
    principal: Principal = Depends(get_current_principal),
    harness: Harness = Depends(get_harness),
):
    # Authenticated identity wins; body.user_id only used as fallback when
    # AuthPlugin is disabled (anonymous principal).
    user_id = _resolve_user_id(principal, request.user_id)

    session_id = request.session_id or str(uuid.uuid4())
    session = AgentSession(session_id=session_id, user_id=user_id)
    try:
        result = await harness.runtime.run(session=session, user_input=request.message)
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
    """Stream chat execution as newline-delimited JSON events."""
    user_id = _resolve_user_id(principal, request.user_id)
    session_id = request.session_id or str(uuid.uuid4())
    session = AgentSession(session_id=session_id, user_id=user_id)

    async def events():
        try:
            async for event in harness.runtime.run_stream(
                session=session,
                user_input=request.message,
            ):
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
    except (RuntimeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:  # pragma: no cover
        raise HTTPException(status_code=500, detail=f"chat resume failed: {exc}") from exc
    return create_success_response(data=result)
