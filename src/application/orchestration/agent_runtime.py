"""AgentOrchestrator: 基于 CapabilityRegistry 的 Agent 编排入口。

这个文件只保留请求级编排主流程。容易膨胀的职责已经拆到旁路组件：

- ``AgentFactory``：OpenAI client、SDK Agent、instructions 构造。
- ``AgentRunObserver``：Langfuse observation 包装。
- ``AgentResumeRuntime``：SDK interruption / HITL 审批恢复流程。
- ``AdvancedAgentRuntime``：HITL / Checkpoint / Handoff 的可选接入。
- ``iter_stream_events``：OpenAI Agents SDK 流事件到本服务事件的转换。

主流程只负责：
  1. 选模型
  2. 构造 RunContext, 触发 BEFORE_RUN 让 capabilities 注入上下文
  3. 调用 OpenAI Agents SDK Runner
  4. 触发 AFTER_RUN 让 capabilities 持久化结果, 失败触发 ON_ERROR

具体能力 (Memory / HITL / Checkpoint / ...) 通过实现 ``Capability`` 协议接入,
未启用的能力不会进入热路径。
"""

from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any

from agents import Agent, AsyncOpenAI, Runner, set_tracing_disabled

from src.application.orchestration.advanced_runtime import (
    AdvancedAgentRuntime,
    CheckpointConfig,
    HandoffConfig,
    HITLConfig,
)
from src.application.orchestration.agent_factory import AgentFactory
from src.application.orchestration.agent_observation import AgentRunObserver
from src.application.orchestration.agent_resume import AgentResumeRuntime
from src.application.orchestration.stream_events import iter_stream_events
from src.capabilities.memory.capability import (
    LongTermMemoryCapability,
    MemoryCapability,
    VectorSearchCapability,
)
from src.capabilities.memory.mem0_manager import Mem0MemoryManager
from src.capabilities.memory.store import MemoryStore
from src.capabilities.model_routing.router import ModelRouter
from src.capabilities.plugin import CapabilityRegistry, RunContext, RunPhase
from src.capabilities.prompt.manager import PromptManager
from src.capabilities.tools.registry import ToolRegistry
from src.core.agents_result_parser import parse_tool_calls_from_result
from src.core.config import current_settings
from src.core.config import Settings
from src.core.logging import setup_logger

logger = setup_logger("orchestration.agent_runtime")


@dataclass
class AgentSession:
    """一次会话在运行时侧的最小身份信息。

    HTTP 层负责从请求中提取 ``session_id`` / ``user_id``；Runtime 只关心这两个
    标识以及少量请求间上下文，例如最近一次使用的模型。持久化会话历史由
    ``session_store`` 在路由层和 memory capability 中处理。
    """

    session_id: str
    user_id: str | None = None
    context: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class PreparedAgentRun:
    """一次普通 Agent run 在调用 SDK 前已经准备好的全部材料。"""

    task_type: str | None
    selected_model: str
    ctx: RunContext
    agent: Agent


class AgentOrchestrator:
    """基于 CapabilityRegistry 的最小 Agent 编排器

    可插拔能力:
    - Memory (短期 + 可选长期, 始终注册, 由 ``MemoryCapability`` 内部判断)
    - HITL / Checkpoint (可选, 仅在传入对应 config 时注册)
    - Handoff (可选, 启用后通过 SDK 原生 ``Agent.handoffs`` 执行)

    如果业务希望完全自定义 Agent 编排，优先替换这个类或 ``_run_stream``；
    如果只是替换 Agent 构造、prompt 或 handoff 注入，优先改 ``AgentFactory``。
    """

    def __init__(
        self,
        tool_registry: ToolRegistry,
        memory_store: MemoryStore,
        model_router: ModelRouter,
        memory_manager: Mem0MemoryManager | None = None,
        prompt_manager: PromptManager | None = None,
        settings: Settings | None = None,
        capability_registry: CapabilityRegistry | None = None,
        tracing_disabled: bool | None = None,
        # 高级 Agent 能力 (完全可选)
        hitl_config: "HITLConfig | None" = None,
        checkpoint_config: "CheckpointConfig | None" = None,
        handoff_config: "HandoffConfig | None" = None,
    ) -> None:
        # 基础依赖：这些对象由 HarnessBuilder 装配好后注入，Runtime 不负责创建外部资源。
        self.settings = settings or current_settings
        self.tool_registry = tool_registry
        self.memory_store = memory_store
        self.model_router = model_router
        self.memory_manager = memory_manager
        self.prompt_manager = prompt_manager

        # 能力注册表是增强能力的统一调度入口。主流程只在固定阶段 dispatch，
        # 各 capability 自己决定是否启用、如何修改 RunContext。
        self.registry = capability_registry or CapabilityRegistry()
        if tracing_disabled is not None:
            set_tracing_disabled(tracing_disabled)

        # 1) Memory 能力始终注册。短期/长期开关由 capability 内部和 settings 判断，
        # 这样主流程不用散落 MEMORY_* 判断。
        self.registry.register(
            MemoryCapability(
                memory_store=memory_store,
                memory_manager=memory_manager,
                long_term_enabled=memory_manager is not None,
            )
        )
        long_term_enabled = getattr(self.settings, "memory_long_term_enabled", False) and memory_manager is not None
        self.registry.register(LongTermMemoryCapability(enabled=long_term_enabled))
        self.registry.register(
            VectorSearchCapability(
                enabled=(
                    long_term_enabled
                    and (
                        bool(getattr(memory_manager, "supports_vector_search", False))
                        or (
                            getattr(memory_manager, "vector_store", None) is not None
                            and getattr(memory_manager, "embedding_provider", None) is not None
                        )
                    )
                ),
            )
        )

        # 2) 上下文压缩默认关闭；开启后在 Memory 注入上下文之后再压缩。
        if self.settings.compression_enabled:
            from src.capabilities.context_compression import ContextCompressionCapability

            self.registry.register(
                ContextCompressionCapability.from_settings(
                    self.settings,
                    model_router=model_router,
                    prompt_manager=self.prompt_manager,
                )
            )

        # 3) Prompt 管理默认关闭；manager 由 HarnessBuilder 组装，这里只注册能力。
        if self.settings.prompt_enabled and self.prompt_manager is not None:
            from src.capabilities.prompt import PromptCapability

            warmup_names = [
                n.strip() for n in (getattr(self.settings, "prompt_warmup_names", "") or "").split(",") if n.strip()
            ]
            self.registry.register(
                PromptCapability(
                    manager=self.prompt_manager,
                    warmup_names=warmup_names,
                    enabled=True,
                )
            )

        # 4) 高级能力完全可选。不开 HITL / Checkpoint / Handoff 时，
        # AdvancedAgentRuntime 只是一个空包装，不会改动主流程。
        self.advanced = AdvancedAgentRuntime(
            registry=self.registry,
            hitl_config=hitl_config,
            checkpoint_config=checkpoint_config,
            handoff_config=handoff_config,
        )
        self.hitl_mgr = self.advanced.hitl_mgr
        self.checkpoint_mgr = self.advanced.checkpoint_mgr
        self.handoff_mgr = self.advanced.handoff_mgr

        # AgentFactory 负责所有 SDK Agent 构造细节。这里保留同名代理方法，
        # 是为了兼容现有测试和少量内部调用，后续可逐步直接依赖 factory。
        self.agent_factory = AgentFactory(
            settings=self.settings,
            tool_registry=self.tool_registry,
            prompt_manager=self.prompt_manager,
            handoff_builder=self.advanced.build_handoffs,
            logger=logger,
        )
        self.observer = AgentRunObserver()
        self.resume_runtime = AgentResumeRuntime(self)

    async def setup(self) -> None:
        """供应用启动期调用，触发所有已注册能力的 setup。"""
        await self.registry.setup_all()

    async def teardown(self) -> None:
        """供应用关闭期调用，释放 capability 持有的资源。"""
        await self.registry.teardown_all()

    @staticmethod
    def _execution_agent_name(run_result: Any) -> str:
        """尽量从 SDK 结果中拿到最终执行 Agent 名称。

        该信息只用于 agent_updated 流事件路径维护和调试展示，不参与业务判断。
        不同 SDK 返回对象可能暴露 ``current_agent`` 或 ``last_agent``，这里兼容两者。
        """
        for attribute in ("current_agent", "last_agent"):
            agent = getattr(run_result, attribute, None)
            name = getattr(agent, "name", None)
            if isinstance(name, str) and name:
                return name
        return "MinimalChatAgent"

    async def _memory_size(self, session_id: str) -> int:
        """读取当前会话记忆规模，用于响应元信息。

        优先读 memory_manager 的短期记忆；如果未启用 manager，则回退到进程内
        ``MemoryStore``。读取失败只记录 warning，不影响主回答链路。
        """
        if self.memory_manager is not None and hasattr(self.memory_manager, "short_term"):
            try:
                return len(await self.memory_manager.short_term.get_all(session_id))
            except Exception:
                logger.warning("memory_size_read_failed", extra={"session_id": session_id})
        return len(self.memory_store.get(session_id))

    async def _prepare_agent_run(
        self,
        session: AgentSession,
        user_input: str,
        *,
        model: str | None = None,
    ) -> PreparedAgentRun:
        """准备一次 SDK run，不实际调用模型。

        业务方要自定义“如何选模型、如何构造上下文、如何构造主 Agent”，通常优先改
        这个方法或 ``AgentFactory``，而不是修改流式事件处理和 HITL resume 逻辑。
        """
        task_type = self.model_router.infer_task_type(user_input) if user_input else None
        selected_model = model or self.model_router.select(task_type=task_type)
        ctx = RunContext(
            session_id=session.session_id,
            user_id=session.user_id,
            user_input=user_input,
            enriched_input=user_input,
            selected_model=selected_model,
        )
        ctx.metadata["tools"] = {
            "available": self.tool_registry.list_tools(),
            "approval_required": self.tool_registry.list_approval_required(),
        }

        await self.registry.dispatch(RunPhase.BEFORE_RUN, ctx)
        client = self._create_openai_client()
        instructions = await self._resolve_instructions(task_type, ctx)
        agent = self._build_agent(
            model=selected_model,
            client=client,
            instructions=instructions,
        )
        return PreparedAgentRun(
            task_type=task_type,
            selected_model=selected_model,
            ctx=ctx,
            agent=agent,
        )

    async def _build_interrupted_result(
        self,
        *,
        session: AgentSession,
        user_input: str,
        run: PreparedAgentRun,
        run_result: Any,
    ) -> dict[str, Any]:
        """把 SDK interruption 转成统一 done payload。"""
        run_state, approval_requests = await self.advanced.request_approvals_from_result(
            run_result,
            session_id=run.ctx.session_id,
            user_id=run.ctx.user_id or "anonymous",
        )
        run.ctx.metadata["hitl"] = {
            "interrupted": True,
            "approval_requests": approval_requests,
        }
        return {
            "session_id": session.session_id,
            "input": user_input,
            "output": None,
            "model": run.selected_model,
            "tool_calls": [],
            "memory_size": await self._memory_size(session.session_id),
            "metadata": dict(run.ctx.metadata),
            "interrupted": True,
            "interruptions": approval_requests,
            "run_state": run_state,
        }

    async def _complete_successful_run(
        self,
        *,
        session: AgentSession,
        user_input: str,
        run: PreparedAgentRun,
        run_result: Any,
    ) -> dict[str, Any]:
        """完成普通成功路径，并触发 AFTER_RUN capability。"""
        run.ctx.final_output = str(run_result.final_output)
        run.ctx.tool_calls = parse_tool_calls_from_result(run_result)
        await self.registry.dispatch(RunPhase.AFTER_RUN, run.ctx)
        session.context["last_model"] = run.selected_model
        return {
            "session_id": session.session_id,
            "input": user_input,
            "output": run.ctx.final_output,
            "model": run.selected_model,
            "tool_calls": run.ctx.tool_calls,
            "memory_size": await self._memory_size(session.session_id),
            "metadata": dict(run.ctx.metadata),
            "interrupted": False,
        }

    async def run_stream(
        self,
        session: AgentSession,
        user_input: str,
    ) -> AsyncIterator[dict[str, Any]]:
        """对外流式入口：包一层 observation，真正编排交给 ``_run_stream``。"""
        with self.observer.observe(
            session_id=session.session_id,
            user_id=session.user_id,
            user_input=user_input,
            trace_name="agent.chat.stream",
        ) as observation:
            try:
                async for event in self._run_stream(session, user_input):
                    if event["type"] == "done":
                        self.observer.update(observation, event["data"])
                    yield event
            except Exception as exc:
                self.observer.mark_error(observation, exc)
                raise

    async def _run_stream(
        self,
        session: AgentSession,
        user_input: str,
    ) -> AsyncIterator[dict[str, Any]]:
        """普通聊天热路径。

        这里刻意保持为一条线性流程：
        选模型 -> 构造上下文 -> BEFORE_RUN -> 构造 Agent -> SDK stream ->
        处理中断或完成 -> AFTER_RUN。

        增强能力只通过 ``registry.dispatch`` 或 ``AdvancedAgentRuntime`` 接入，
        避免主流程持续膨胀。
        """
        if not self.settings.openai_api_key:
            raise RuntimeError("OPENAI_API_KEY is required for /chat endpoint")

        run = await self._prepare_agent_run(session, user_input)

        # agent_path 仅用于把 SDK handoff 过程透传给前端/调用方。
        # 即使 handoff 未启用，它也只包含主 Agent。
        agent_path = ["MinimalChatAgent"]
        yield {
            "type": "start",
            "session_id": session.session_id,
            "model": run.selected_model,
        }
        try:
            run_result = Runner.run_streamed(
                starting_agent=run.agent,
                input=run.ctx.enriched_input,
            )
            async for event in iter_stream_events(run_result, agent_path=agent_path):
                yield event
        except Exception as exc:
            # ON_ERROR 让能力有机会做清理或打点；异常仍然向上抛给路由层转成 error 事件。
            await self.registry.dispatch(RunPhase.ON_ERROR, run.ctx, error=exc)
            raise

        # SDK 原生中断通常来自需要人工审批的 tool。这里不直接处理审批决定，
        # 只把中断和可恢复 run_state 返回给调用方，后续由 resume 接口继续。
        interruptions = list(getattr(run_result, "interruptions", []) or [])
        if interruptions:
            yield {
                "type": "done",
                "data": await self._build_interrupted_result(
                    session=session,
                    user_input=user_input,
                    run=run,
                    run_result=run_result,
                ),
            }
            return

        # 无中断时才进入正常完成路径：解析最终输出和工具调用，再触发 AFTER_RUN。
        # Memory/session summary 等持久化动作都应该挂在 AFTER_RUN capability 上。
        yield {
            "type": "done",
            "data": await self._complete_successful_run(
                session=session,
                user_input=user_input,
                run=run,
                run_result=run_result,
            ),
        }

    async def resume_stream_with_approval(
        self,
        session: AgentSession,
        *,
        run_state: dict[str, Any],
        interruption_index: int,
        approved: bool,
        approval_request_id: str | None = None,
        reviewer: str = "anonymous",
        model: str | None = None,
        user_input: str = "",
        always: bool = False,
        rejection_message: str | None = None,
    ) -> AsyncIterator[dict[str, Any]]:
        """公开的 HITL 恢复入口，保留在 ``AgentOrchestrator`` 上供路由调用。

        这个方法适合继续放在 ``AgentOrchestrator`` 上，原因是 HTTP 层只应该依赖
        一个 runtime 门面：普通聊天调用 ``run_stream``，审批恢复调用
        ``resume_stream_with_approval``。这样路由不需要知道内部是否拆出了
        ``AgentResumeRuntime``，后续替换恢复实现也不会影响 API 层。

        真正的审批恢复、SDK ``RunState`` approve/reject、拒绝时的受控响应、
        二次 interruption 处理都在 ``AgentResumeRuntime`` 中完成。这里仅做参数
        透传和事件转发，是一个稳定门面方法。
        """
        async for event in self.resume_runtime.resume_stream_with_approval(
            session,
            run_state=run_state,
            interruption_index=interruption_index,
            approved=approved,
            approval_request_id=approval_request_id,
            reviewer=reviewer,
            model=model,
            user_input=user_input,
            always=always,
            rejection_message=rejection_message,
        ):
            yield event

    def _create_openai_client(self) -> AsyncOpenAI:
        return self.agent_factory.create_client()

    def _build_agent(
        self,
        *,
        model: str,
        client: AsyncOpenAI,
        instructions: str,
    ) -> Agent:
        return self.agent_factory.build_agent(
            model=model,
            client=client,
            instructions=instructions,
        )

    def _default_instructions(self) -> str:
        return self.agent_factory.default_instructions()

    async def _resolve_instructions(self, task_type: str | None, ctx: RunContext) -> str:
        return await self.agent_factory.resolve_instructions(task_type, ctx)
