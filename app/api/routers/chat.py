import uuid

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.application.orchestration.agent_runtime import AgentOrchestrator, AgentSession
from app.capabilities.memory.store import MemoryStore
from app.capabilities.model_routing.router import ModelRouter
from app.capabilities.tools.registry import ToolRegistry
from app.shared.utils.response import create_success_response

router = APIRouter(prefix="/chat", tags=["chat"])

_memory_store = MemoryStore()
_tool_registry = ToolRegistry()
_tool_registry.register_defaults()
_model_router = ModelRouter()
_orchestrator = AgentOrchestrator(
    tool_registry=_tool_registry,
    memory_store=_memory_store,
    model_router=_model_router,
)


class ChatRequest(BaseModel):
    message: str = Field(..., description="user input")
    session_id: str | None = Field(default=None, description="optional session id for memory")
    user_id: str | None = Field(default=None, description="optional user id")


@router.post("")
async def chat(request: ChatRequest):
    session_id = request.session_id or str(uuid.uuid4())
    session = AgentSession(session_id=session_id, user_id=request.user_id)
    try:
        result = await _orchestrator.run(session=session, user_input=request.message)
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:  # pragma: no cover
        raise HTTPException(status_code=500, detail=f"chat failed: {exc}") from exc
    return create_success_response(data=result)
