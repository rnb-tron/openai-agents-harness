"""AgentOrchestrator: 基于 CapabilityRegistry 的 Agent 编排入口

主流程只负责:
  1. 选模型
  2. 构造 RunContext, 触发 BEFORE_RUN 让 capabilities 注入上下文
  3. 调用 OpenAI Agents SDK Runner
  4. 触发 AFTER_RUN 让 capabilities 持久化结果, 失败触发 ON_ERROR

具体能力 (Memory / HITL / Checkpoint / ...) 通过实现 ``Capability`` 协议接入,
未启用的能力零开销, 不再有散落的 ``if mgr is not None`` 判断。
"""

from dataclasses import dataclass, field
from typing import Any

from agents import Agent, AsyncOpenAI, OpenAIChatCompletionsModel, Runner, set_tracing_disabled

from src.capabilities.memory import MemoryCapability
from src.capabilities.memory.manager import MemoryManager
from src.capabilities.memory.store import MemoryStore
from src.capabilities.model_routing.router import ModelRouter
from src.capabilities.plugin import CapabilityRegistry, RunContext, RunPhase
from src.capabilities.tools.registry import ToolRegistry
from src.core.agents_result_parser import parse_tool_calls_from_result
from src.core.config import current_settings
from src.core.logging import setup_logger

# 可选导入: 高级 Agent 能力
try:
    from src.capabilities.advanced_agents import (
        ApprovalManager,
        CheckpointCapability,
        CheckpointManager,
        HandoffConfig,
        HandoffManager,
        HITLCapability,
        HITLConfig,
        CheckpointConfig,
    )
    ADVANCED_AGENTS_AVAILABLE = True
except ImportError:
    ADVANCED_AGENTS_AVAILABLE = False
    ApprovalManager = None
    CheckpointManager = None
    HandoffManager = None
    CheckpointCapability = None
    HITLCapability = None
    HITLConfig = None
    CheckpointConfig = None
    HandoffConfig = None

logger = setup_logger("orchestration.agent_runtime")
set_tracing_disabled(True)


@dataclass
class AgentSession:
    session_id: str
    user_id: str | None = None
    context: dict[str, Any] = field(default_factory=dict)


class AgentOrchestrator:
    """基于 CapabilityRegistry 的最小 Agent 编排器

    可插拔能力:
    - Memory (短期 + 可选长期, 始终注册, 由 ``MemoryCapability`` 内部判断)
    - HITL / Checkpoint (可选, 仅在传入对应 config 时注册)
    - Handoff (当前不参与主流程钩子, 仅暴露 manager 供业务直接调用)
    """

    def __init__(
        self,
        tool_registry: ToolRegistry,
        memory_store: MemoryStore,
        model_router: ModelRouter,
        memory_manager: MemoryManager | None = None,
        # 高级 Agent 能力 (完全可选)
        hitl_config: "HITLConfig | None" = None,
        checkpoint_config: "CheckpointConfig | None" = None,
        handoff_config: "HandoffConfig | None" = None,
    ) -> None:
        # 基础依赖
        self.tool_registry = tool_registry
        self.memory_store = memory_store
        self.model_router = model_router
        self.memory_manager = memory_manager

        # Capability Registry: 所有可插拔能力的统一调度入口
        self.registry = CapabilityRegistry()

        # 1) Memory 能力 (始终注册; 长期记忆由 settings + manager 决定是否启用)
        self.registry.register(
            MemoryCapability(
                memory_store=memory_store,
                memory_manager=memory_manager,
                long_term_enabled=current_settings.memory_enabled,
            )
        )

        # 2) 高级能力 (可选)
        self.handoff_mgr: HandoffManager | None = None
        if ADVANCED_AGENTS_AVAILABLE:
            if hitl_config is not None and ApprovalManager is not None and HITLCapability is not None:
                self.registry.register(HITLCapability(ApprovalManager(hitl_config)))
            if (
                checkpoint_config is not None
                and CheckpointManager is not None
                and CheckpointCapability is not None
            ):
                self.registry.register(
                    CheckpointCapability(CheckpointManager(checkpoint_config))
                )
            # Handoff 不参与 BEFORE/AFTER_RUN 钩子, 直接暴露给上层使用
            if handoff_config is not None and HandoffManager is not None:
                self.handoff_mgr = HandoffManager(handoff_config)

    async def setup(self) -> None:
        """供应用启动期调用, 触发所有能力的 setup"""
        await self.registry.setup_all()

    async def teardown(self) -> None:
        """供应用关闭期调用"""
        await self.registry.teardown_all()

    async def run(self, session: AgentSession, user_input: str) -> dict[str, Any]:
        if not current_settings.openai_api_key:
            raise RuntimeError("OPENAI_API_KEY is required for /chat endpoint")

        task_type = self.model_router.infer_task_type(user_input)
        selected_model = self.model_router.select(task_type=task_type)

        # 一次 run 的统一上下文
        ctx = RunContext(
            session_id=session.session_id,
            user_id=session.user_id,
            user_input=user_input,
            enriched_input=user_input,  # 默认与 user_input 相同, MemoryCapability 会改写
            selected_model=selected_model,
        )

        # 触发 BEFORE_RUN: 让所有 capabilities 注入上下文 (memory / checkpoint pre-save)
        await self.registry.dispatch(RunPhase.BEFORE_RUN, ctx)

        # 构造 OpenAI Agents SDK 客户端与 Agent
        client_kwargs: dict[str, Any] = {"api_key": current_settings.openai_api_key}
        if current_settings.openai_base_url:
            client_kwargs["base_url"] = current_settings.openai_base_url
        client = AsyncOpenAI(**client_kwargs)

        agent = Agent(
            name="MinimalChatAgent",
            instructions=(
                "You are a concise assistant. Use tools when useful. "
                "If a tool is used, include the final user-facing conclusion in plain text."
            ),
            model=OpenAIChatCompletionsModel(model=selected_model, openai_client=client),
            tools=self.tool_registry.list_agent_tools(),
        )

        # 执行 Agent 调用; 失败触发 ON_ERROR 后向上抛
        try:
            run_result = await Runner.run(starting_agent=agent, input=ctx.enriched_input)
        except Exception as e:
            await self.registry.dispatch(RunPhase.ON_ERROR, ctx, error=e)
            raise

        ctx.final_output = str(run_result.final_output)
        ctx.tool_calls = parse_tool_calls_from_result(run_result)

        # 触发 AFTER_RUN: 让所有 capabilities 持久化 (memory write / checkpoint post-save / hitl 审批)
        await self.registry.dispatch(RunPhase.AFTER_RUN, ctx)

        session.context["last_model"] = selected_model

        return {
            "session_id": session.session_id,
            "input": user_input,
            "output": ctx.final_output,
            "model": selected_model,
            "tool_calls": ctx.tool_calls,
            "memory_size": len(self.memory_store.get(session.session_id)),
        }
