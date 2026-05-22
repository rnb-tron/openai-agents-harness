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

from src.capabilities.memory.capability import (
    LongTermMemoryCapability,
    MemoryCapability,
    VectorSearchCapability,
)
from src.capabilities.memory.manager import MemoryManager
from src.capabilities.memory.store import MemoryStore
from src.capabilities.model_routing.router import ModelRouter
from src.capabilities.plugin import CapabilityRegistry, RunContext, RunPhase
from src.capabilities.prompt.manager import PromptManager
from src.capabilities.tools.registry import ToolRegistry
from src.core.agents_result_parser import parse_tool_calls_from_result
from src.core.config import current_settings
from src.core.config import Settings
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
        prompt_manager: PromptManager | None = None,
        settings: Settings | None = None,
        capability_registry: CapabilityRegistry | None = None,
        tracing_disabled: bool | None = None,
        # 高级 Agent 能力 (完全可选)
        hitl_config: "HITLConfig | None" = None,
        checkpoint_config: "CheckpointConfig | None" = None,
        handoff_config: "HandoffConfig | None" = None,
    ) -> None:
        # 基础依赖
        self.settings = settings or current_settings
        self.tool_registry = tool_registry
        self.memory_store = memory_store
        self.model_router = model_router
        self.memory_manager = memory_manager
        self.prompt_manager = prompt_manager
        self.hitl_mgr = None
        self.checkpoint_mgr = None

        # Capability Registry: 所有可插拔能力的统一调度入口
        self.registry = capability_registry or CapabilityRegistry()
        if tracing_disabled is not None:
            set_tracing_disabled(tracing_disabled)

        # 1) Memory 能力 (始终注册; 长期记忆由 settings + manager 决定是否启用)
        self.registry.register(
            MemoryCapability(
                memory_store=memory_store,
                memory_manager=memory_manager,
                long_term_enabled=self.settings.memory_enabled,
            )
        )
        long_term_enabled = self.settings.memory_enabled and memory_manager is not None
        self.registry.register(LongTermMemoryCapability(enabled=long_term_enabled))
        self.registry.register(
            VectorSearchCapability(
                enabled=long_term_enabled and getattr(memory_manager, "vector_store", None) is not None
            )
        )

        # 2) 上下文压缩 (默认关, compression_enabled 开启后在 Memory 之后压缩)
        if self.settings.compression_enabled:
            from src.capabilities.context_compression import ContextCompressionCapability

            self.registry.register(
                ContextCompressionCapability.from_settings(
                    self.settings,
                    model_router=model_router,
                    prompt_manager=self.prompt_manager,
                )
            )

        # 3) Prompt management (default off; manager is assembled by HarnessBuilder)
        if self.settings.prompt_enabled and self.prompt_manager is not None:
            from src.capabilities.prompt import PromptCapability

            warmup_names = [
                n.strip()
                for n in (getattr(self.settings, "prompt_warmup_names", "") or "").split(",")
                if n.strip()
            ]
            self.registry.register(
                PromptCapability(
                    manager=self.prompt_manager,
                    warmup_names=warmup_names,
                    enabled=True,
                )
            )

        # 4) 高级能力 (可选)
        self.handoff_mgr: HandoffManager | None = None
        if ADVANCED_AGENTS_AVAILABLE:
            if hitl_config is not None and ApprovalManager is not None and HITLCapability is not None:
                self.hitl_mgr = ApprovalManager(hitl_config)
                self.registry.register(HITLCapability(self.hitl_mgr))
            if (
                checkpoint_config is not None
                and CheckpointManager is not None
                and CheckpointCapability is not None
            ):
                self.checkpoint_mgr = CheckpointManager(checkpoint_config)
                self.registry.register(CheckpointCapability(self.checkpoint_mgr))
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
        if not self.settings.openai_api_key:
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
        ctx.metadata["tools"] = {
            "available": self.tool_registry.list_tools(),
            "approval_required": self.tool_registry.list_approval_required(),
        }

        # 触发 BEFORE_RUN: 让所有 capabilities 注入上下文 (memory / checkpoint pre-save)
        await self.registry.dispatch(RunPhase.BEFORE_RUN, ctx)

        # 构造 OpenAI Agents SDK 客户端与 Agent
        client_kwargs: dict[str, Any] = {"api_key": self.settings.openai_api_key}
        if self.settings.openai_base_url:
            client_kwargs["base_url"] = self.settings.openai_base_url
        client = AsyncOpenAI(**client_kwargs)

        # 默认 instructions: 与历史硬编码语义保持一致 (作为 prompt 失败时的兜底)
        instructions = (
            "You are a concise assistant. Use tools when useful. "
            "If a tool is used, include the final user-facing conclusion in plain text."
        )
        # prompt_enabled 时, 从注入的 PromptManager 取 prompt; 失败走兜底
        if self.settings.prompt_enabled and self.prompt_manager is not None:
            try:
                rendered = await self.prompt_manager.get(
                    "agents.main_chat",
                    task_type=task_type,
                    extra_instructions="",
                )
                instructions = rendered.text
                ctx.metadata["prompt"] = rendered.to_metadata()
            except Exception as exc:
                logger.warning(
                    "prompt_get_failed_using_fallback",
                    extra={
                        "prompt_name": "agents.main_chat",
                        "error_type": type(exc).__name__,
                        "error": str(exc),
                    },
                )
                if not self.settings.prompt_fail_open:
                    raise

        async def run_with_model(model: str):
            agent = Agent(
                name="MinimalChatAgent",
                instructions=instructions,
                model=OpenAIChatCompletionsModel(model=model, openai_client=client),
                tools=self.tool_registry.list_agent_tools(),
            )
            return Runner.run(starting_agent=agent, input=ctx.enriched_input)

        # 执行 Agent 调用; 失败触发 ON_ERROR 后向上抛
        try:
            run_result = await self.model_router.run_with_resilience(
                run_with_model,
                task_type=task_type,
            )
        except Exception as e:
            await self.registry.dispatch(RunPhase.ON_ERROR, ctx, error=e)
            raise

        if self.model_router.last_metrics and self.model_router.last_metrics.success_model:
            selected_model = self.model_router.last_metrics.success_model
            ctx.selected_model = selected_model
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
