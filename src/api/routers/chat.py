import uuid

from fastapi import APIRouter, Depends, HTTPException
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


@router.post("")
async def chat(
    request: ChatRequest,
    principal: Principal = Depends(get_current_principal),
    harness: Harness = Depends(get_harness),
):
    # Authenticated identity wins; body.user_id only used as fallback when
    # AuthPlugin is disabled (anonymous principal).
    if principal.is_anonymous:
        user_id = request.user_id
    else:
        user_id = principal.user_id

    session_id = request.session_id or str(uuid.uuid4())
    session = AgentSession(session_id=session_id, user_id=user_id)
    try:
        result = await harness.runtime.run(session=session, user_input=request.message)
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:  # pragma: no cover
        raise HTTPException(status_code=500, detail=f"chat failed: {exc}") from exc
    return create_success_response(data=result)
