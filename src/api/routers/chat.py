import uuid

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from src.application.orchestration.agent_runtime import AgentOrchestrator, AgentSession
from src.capabilities.memory.store import MemoryStore
from src.capabilities.model_routing.router import ModelRouter
from src.capabilities.tools.registry import ToolRegistry
from src.utils.response import create_success_response

# ============================================================
# 可插拔能力配置
# ============================================================

# 基础能力 (必需)
_memory_store = MemoryStore()
_tool_registry = ToolRegistry()
_tool_registry.register_defaults()
_model_router = ModelRouter()

# 可选能力 1: 高级 Agent 能力 (HITL, Checkpoint, Handoff)
# 默认不启用,需要时取消注释并配置
try:
    from src.capabilities.advanced_agents import (
        HITLConfig,
        CheckpointConfig,
        HandoffConfig,
    )
    
    # 示例: 启用 HITL 和 Checkpoint
    # _hitl_config = HITLConfig(
    #     enabled=True,
    #     approval_timeout=300.0,
    #     require_approval_tools=["delete_data", "send_notification"],
    #     auto_approve_tools=["query_data", "get_status"],
    # )
    # _checkpoint_config = CheckpointConfig(
    #     enabled=True,
    #     max_checkpoints=10,
    #     save_on_tool_call=True,
    # )
    # _handoff_config = HandoffConfig(
    #     enabled=True,
    #     default_agent="general",
    # )
    
    # 传递配置给 Orchestrator
    # _orchestrator = AgentOrchestrator(
    #     tool_registry=_tool_registry,
    #     memory_store=_memory_store,
    #     model_router=_model_router,
    #     hitl_config=_hitl_config,
    #     checkpoint_config=_checkpoint_config,
    #     handoff_config=_handoff_config,
    # )
except ImportError:
    # 高级能力模块不可用,使用基础模式
    pass

# 基础模式: 不使用高级能力
_orchestrator = AgentOrchestrator(
    tool_registry=_tool_registry,
    memory_store=_memory_store,
    model_router=_model_router,
)

router = APIRouter(prefix="/chat", tags=["chat"])


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
