"""AgentOrchestrator: 基于 CapabilityRegistry 的 Agent 编排入口

主流程只负责:
  1. 选模型
  2. 构造 RunContext, 触发 BEFORE_RUN 让 capabilities 注入上下文
  3. 调用 OpenAI Agents SDK Runner
  4. 触发 AFTER_RUN 让 capabilities 持久化结果, 失败触发 ON_ERROR

具体能力 (Memory / HITL / Checkpoint / ...) 通过实现 ``Capability`` 协议接入,
未启用的能力零开销, 不再有散落的 ``if mgr is not None`` 判断。
"""

from collections.abc import AsyncIterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any

from agents import Agent, AsyncOpenAI, ModelSettings, OpenAIChatCompletionsModel, Runner, RunState, set_tracing_disabled
from agents.stream_events import AgentUpdatedStreamEvent, RawResponsesStreamEvent
from langfuse import propagate_attributes
from openai.types.responses.response_reasoning_summary_text_delta_event import (
    ResponseReasoningSummaryTextDeltaEvent,
)
from openai.types.responses.response_text_delta_event import ResponseTextDeltaEvent
from openai.types.shared import Reasoning

from src.capabilities.memory.capability import (
    LongTermMemoryCapability,
    MemoryCapability,
    VectorSearchCapability,
)
from src.capabilities.memory.manager import MemoryManager
from src.capabilities.memory.store import MemoryStore
from src.capabilities.model_routing.router import ModelRouter
from src.capabilities.observability import get_tracer_manager
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
        HandoffCapability,
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
    HandoffCapability = None
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
    - Handoff (可选, 启用后通过 SDK 原生 ``Agent.handoffs`` 执行)
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
        self._advanced_execution: dict[str, dict[str, Any]] = {}

        # 能力注册表：所有可插拔能力的统一调度入口
        self.registry = capability_registry or CapabilityRegistry()
        if tracing_disabled is not None:
            set_tracing_disabled(tracing_disabled)

        # 1) Memory 能力 (始终注册; 长期记忆由 settings + manager 决定是否启用)
        self.registry.register(
            MemoryCapability(
                memory_store=memory_store,
                memory_manager=memory_manager,
                long_term_enabled=memory_manager is not None,
            )
        )
        long_term_enabled = (
            getattr(self.settings, "memory_long_term_enabled", False)
            and memory_manager is not None
        )
        self.registry.register(
            LongTermMemoryCapability(enabled=long_term_enabled)
        )
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
            if (
                handoff_config is not None
                and HandoffManager is not None
                and HandoffCapability is not None
            ):
                self.handoff_mgr = HandoffManager(handoff_config)
                self.registry.register(HandoffCapability(self.handoff_mgr))

    async def setup(self) -> None:
        """供应用启动期调用, 触发所有能力的 setup"""
        await self.registry.setup_all()

    async def teardown(self) -> None:
        """供应用关闭期调用"""
        await self.registry.teardown_all()

    @contextmanager
    def _observe_agent_run(
        self,
        *,
        session: AgentSession,
        user_input: str,
        trace_name: str,
    ):
        """可观测启用时创建 Langfuse 根 observation。"""
        tracer_manager = get_tracer_manager()
        langfuse = (
            tracer_manager.langfuse
            if tracer_manager is not None and tracer_manager.is_initialized
            else None
        )
        if langfuse is None:
            yield None
            return

        with langfuse.start_as_current_observation(
            name=trace_name,
            as_type="agent",
            input=user_input,
        ) as observation:
            with propagate_attributes(
                trace_name=trace_name,
                session_id=session.session_id,
                user_id=session.user_id,
                tags=["chat"],
            ):
                # 自建 Langfuse 仍可能展示旧版 trace 级 input/output 列。
                langfuse.set_current_trace_io(input=user_input)
                yield observation

    def _update_observation(self, observation: Any, result: dict[str, Any]) -> None:
        if observation is None:
            return
        output: Any = result.get("output")
        if result.get("interrupted"):
            output = {
                "interrupted": True,
                "interruptions": result.get("interruptions", []),
            }
        observation.update(
            output=output,
            metadata={
                "model": result.get("model", ""),
                "interrupted": bool(result.get("interrupted", False)),
                **dict(result.get("metadata") or {}),
            },
        )
        tracer_manager = get_tracer_manager()
        if tracer_manager is not None and tracer_manager.langfuse is not None:
            tracer_manager.langfuse.set_current_trace_io(output=output)

    @staticmethod
    def _mark_observation_error(observation: Any, error: Exception) -> None:
        if observation is not None:
            observation.update(level="ERROR", status_message=str(error))

    @staticmethod
    def _execution_agent_name(run_result: Any) -> str:
        for attribute in ("current_agent", "last_agent"):
            agent = getattr(run_result, attribute, None)
            name = getattr(agent, "name", None)
            if isinstance(name, str) and name:
                return name
        return "MinimalChatAgent"

    @staticmethod
    def _agent_path(executing_agent: str) -> list[str]:
        if executing_agent == "MinimalChatAgent":
            return [executing_agent]
        return ["MinimalChatAgent", executing_agent]

    async def _memory_size(self, session_id: str) -> int:
        if self.memory_manager is not None and hasattr(self.memory_manager, "short_term"):
            try:
                return len(await self.memory_manager.short_term.get_all(session_id))
            except Exception:
                logger.warning("memory_size_read_failed", extra={"session_id": session_id})
        return len(self.memory_store.get(session_id))

    def advanced_state(
        self,
        session_id: str,
        *,
        executing_agent: str | None = None,
        agent_path: list[str] | None = None,
    ) -> dict[str, Any]:
        """返回 UI 验收 advanced agent 能力时需要的状态证据。"""
        if executing_agent is not None or agent_path is not None:
            self._advanced_execution[session_id] = {
                "executing_agent": executing_agent,
                "agent_path": list(agent_path or []),
            }
        execution = self._advanced_execution.get(session_id, {})
        hitl_enabled = bool(self.hitl_mgr is not None and self.hitl_mgr.is_enabled())
        checkpoint_enabled = bool(
            self.checkpoint_mgr is not None and self.checkpoint_mgr.is_enabled()
        )
        handoff_enabled = bool(
            self.handoff_mgr is not None and self.handoff_mgr.config.enabled
        )
        approvals = (
            [request.to_dict() for request in self.hitl_mgr.list_requests(session_id)]
            if hitl_enabled
            else []
        )
        checkpoints = (
            [
                {
                    "id": checkpoint.id,
                    "timestamp": checkpoint.timestamp,
                    "description": checkpoint.description,
                    "model": checkpoint.state.current_model,
                    "tool_calls": checkpoint.state.tool_calls,
                }
                for checkpoint in self.checkpoint_mgr.list_checkpoints(session_id)
            ]
            if checkpoint_enabled
            else []
        )
        handoff_targets = []
        if handoff_enabled:
            handoff_targets = [
                name
                for name, definition in self.handoff_mgr.config.agents.items()
                if definition.get("enabled", True)
            ]
        return {
            "enabled": {
                "hitl": hitl_enabled,
                "checkpoint": checkpoint_enabled,
                "handoff": handoff_enabled,
            },
            "executing_agent": execution.get("executing_agent"),
            "agent_path": execution.get("agent_path", []),
            "handoff_targets": handoff_targets,
            "approvals": approvals,
            "checkpoints": checkpoints,
        }

    async def run(self, session: AgentSession, user_input: str) -> dict[str, Any]:
        with self._observe_agent_run(
            session=session,
            user_input=user_input,
            trace_name="agent.chat",
        ) as observation:
            try:
                result = await self._run(session, user_input)
            except Exception as exc:
                self._mark_observation_error(observation, exc)
                raise
            self._update_observation(observation, result)
            return result

    async def _run(self, session: AgentSession, user_input: str) -> dict[str, Any]:
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

        client = self._create_openai_client()
        instructions = await self._resolve_instructions(task_type, ctx)

        async def run_with_model(model: str):
            agent = self._build_agent(model=model, client=client, instructions=instructions)
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

        interruptions = list(getattr(run_result, "interruptions", []) or [])
        if interruptions:
            run_state = run_result.to_state().to_json()
            approval_requests = []
            if self.hitl_mgr is not None:
                run_state, requests = await self.hitl_mgr.request_approvals_from_result(
                    run_result,
                    session_id=ctx.session_id,
                    user_id=ctx.user_id or "anonymous",
                )
                approval_requests = [request.to_dict() for request in requests]
            else:
                approval_requests = [
                    {
                        "tool_name": getattr(item, "qualified_name", None)
                        or getattr(item, "name", None)
                        or "unknown",
                        "arguments": getattr(item, "arguments", None),
                        "call_id": getattr(item, "call_id", None),
                        "sdk_interruption_index": index,
                    }
                    for index, item in enumerate(interruptions)
                ]

            ctx.metadata["hitl"] = {
                "interrupted": True,
                "approval_requests": approval_requests,
            }
            result = {
                "session_id": session.session_id,
                "input": user_input,
                "output": None,
                "model": selected_model,
                "tool_calls": [],
                "memory_size": await self._memory_size(session.session_id),
                "metadata": dict(ctx.metadata),
                "interrupted": True,
                "interruptions": approval_requests,
                "run_state": run_state,
            }
            executing_agent = self._execution_agent_name(run_result)
            result["advanced"] = self.advanced_state(
                session.session_id,
                executing_agent=executing_agent,
                agent_path=self._agent_path(executing_agent),
            )
            return result

        ctx.final_output = str(run_result.final_output)
        ctx.tool_calls = parse_tool_calls_from_result(run_result)

        # 触发 AFTER_RUN: 让所有 capabilities 持久化 (memory write / checkpoint post-save)
        await self.registry.dispatch(RunPhase.AFTER_RUN, ctx)

        session.context["last_model"] = selected_model

        result = {
            "session_id": session.session_id,
            "input": user_input,
            "output": ctx.final_output,
            "model": selected_model,
            "tool_calls": ctx.tool_calls,
            "memory_size": await self._memory_size(session.session_id),
            "metadata": dict(ctx.metadata),
        }
        executing_agent = self._execution_agent_name(run_result)
        result["advanced"] = self.advanced_state(
            session.session_id,
            executing_agent=executing_agent,
            agent_path=self._agent_path(executing_agent),
        )
        return result

    async def run_stream(
        self,
        session: AgentSession,
        user_input: str,
    ) -> AsyncIterator[dict[str, Any]]:
        with self._observe_agent_run(
            session=session,
            user_input=user_input,
            trace_name="agent.chat.stream",
        ) as observation:
            try:
                async for event in self._run_stream(session, user_input):
                    if event["type"] == "done":
                        self._update_observation(observation, event["data"])
                    yield event
            except Exception as exc:
                self._mark_observation_error(observation, exc)
                raise

    async def _run_stream(
        self,
        session: AgentSession,
        user_input: str,
    ) -> AsyncIterator[dict[str, Any]]:
        """运行已选模型，先产出文本增量，最后产出完整结果。

        重试和模型 fallback 仍保留在非流式 ``run`` 上；一旦流式增量已经发给客户端，
        再透明切换模型会破坏客户端可见的输出流。
        """
        if not self.settings.openai_api_key:
            raise RuntimeError("OPENAI_API_KEY is required for /chat endpoint")

        task_type = self.model_router.infer_task_type(user_input)
        selected_model = self.model_router.select(task_type=task_type)
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
        agent = self._build_agent(model=selected_model, client=client, instructions=instructions)

        agent_path = ["MinimalChatAgent"]
        yield {
            "type": "start",
            "session_id": session.session_id,
            "model": selected_model,
            "advanced": self.advanced_state(
                session.session_id,
                executing_agent=agent_path[-1],
                agent_path=agent_path,
            ),
        }
        try:
            run_result = Runner.run_streamed(starting_agent=agent, input=ctx.enriched_input)
            async for event in run_result.stream_events():
                if isinstance(event, RawResponsesStreamEvent) and isinstance(
                    event.data, ResponseTextDeltaEvent
                ):
                    yield {"type": "delta", "delta": event.data.delta}
                elif isinstance(event, RawResponsesStreamEvent) and isinstance(
                    event.data, ResponseReasoningSummaryTextDeltaEvent
                ):
                    yield {
                        "type": "reasoning_summary_delta",
                        "delta": event.data.delta,
                    }
                elif isinstance(event, AgentUpdatedStreamEvent):
                    executing_agent = getattr(event.new_agent, "name", None)
                    if isinstance(executing_agent, str) and agent_path[-1] != executing_agent:
                        agent_path.append(executing_agent)
                    yield {
                        "type": "agent_updated",
                        "agent": executing_agent or agent_path[-1],
                        "agent_path": list(agent_path),
                    }
        except Exception as exc:
            await self.registry.dispatch(RunPhase.ON_ERROR, ctx, error=exc)
            raise

        interruptions = list(getattr(run_result, "interruptions", []) or [])
        if interruptions:
            run_state = run_result.to_state().to_json()
            approval_requests = []
            if self.hitl_mgr is not None:
                run_state, requests = await self.hitl_mgr.request_approvals_from_result(
                    run_result,
                    session_id=ctx.session_id,
                    user_id=ctx.user_id or "anonymous",
                )
                approval_requests = [request.to_dict() for request in requests]
            else:
                approval_requests = [
                    {
                        "tool_name": getattr(item, "qualified_name", None)
                        or getattr(item, "name", None)
                        or "unknown",
                        "arguments": getattr(item, "arguments", None),
                        "call_id": getattr(item, "call_id", None),
                        "sdk_interruption_index": index,
                    }
                    for index, item in enumerate(interruptions)
                ]
            ctx.metadata["hitl"] = {
                "interrupted": True,
                "approval_requests": approval_requests,
            }
            executing_agent = self._execution_agent_name(run_result)
            if agent_path[-1] != executing_agent:
                agent_path.append(executing_agent)
            yield {
                "type": "done",
                "data": {
                    "session_id": session.session_id,
                    "input": user_input,
                    "output": None,
                    "model": selected_model,
                    "tool_calls": [],
                    "memory_size": await self._memory_size(session.session_id),
                    "metadata": dict(ctx.metadata),
                    "interrupted": True,
                    "interruptions": approval_requests,
                    "run_state": run_state,
                    "advanced": self.advanced_state(
                        session.session_id,
                        executing_agent=executing_agent,
                        agent_path=agent_path,
                    ),
                },
            }
            return

        ctx.final_output = str(run_result.final_output)
        ctx.tool_calls = parse_tool_calls_from_result(run_result)
        await self.registry.dispatch(RunPhase.AFTER_RUN, ctx)
        session.context["last_model"] = selected_model
        executing_agent = self._execution_agent_name(run_result)
        if agent_path[-1] != executing_agent:
            agent_path.append(executing_agent)
        yield {
            "type": "done",
            "data": {
                "session_id": session.session_id,
                "input": user_input,
                "output": ctx.final_output,
                "model": selected_model,
                "tool_calls": ctx.tool_calls,
                "memory_size": await self._memory_size(session.session_id),
                "metadata": dict(ctx.metadata),
                "interrupted": False,
                "advanced": self.advanced_state(
                    session.session_id,
                    executing_agent=executing_agent,
                    agent_path=agent_path,
                ),
            },
        }

    async def resume_with_approval(
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
    ) -> dict[str, Any]:
        with self._observe_agent_run(
            session=session,
            user_input=user_input,
            trace_name="agent.chat.resume",
        ) as observation:
            try:
                result = await self._resume_with_approval(
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
                )
            except Exception as exc:
                self._mark_observation_error(observation, exc)
                raise
            self._update_observation(observation, result)
            return result

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
        """审批后恢复 SDK 中断，并流式返回最终响应。"""
        with self._observe_agent_run(
            session=session,
            user_input=user_input,
            trace_name="agent.chat.resume.stream",
        ) as observation:
            try:
                async for event in self._resume_stream_with_approval(
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
                    if event["type"] == "done":
                        self._update_observation(observation, event["data"])
                    yield event
            except Exception as exc:
                self._mark_observation_error(observation, exc)
                raise

    async def _complete_rejected_resume(
        self,
        *,
        session: AgentSession,
        ctx: RunContext,
        selected_model: str,
        tool_name: str,
        tool_args: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """完成被拒绝的动作，避免模型编造工具执行结果。"""
        ctx.final_output = (
            f"操作已被拒绝，未执行工具 {tool_name}。"
            "因此无法基于该工具的查询结果提供信息或建议。"
        )
        ctx.tool_calls = [
            {
                "name": tool_name,
                "input": tool_args or {},
                "output": {"error": "rejected_by_user"},
                "status": "rejected",
            }
        ]
        ctx.metadata["hitl"] = {"decision": "rejected", "tool_executed": False}
        await self.registry.dispatch(RunPhase.AFTER_RUN, ctx)
        session.context["last_model"] = selected_model
        result = {
            "session_id": session.session_id,
            "input": ctx.user_input,
            "output": ctx.final_output,
            "model": selected_model,
            "tool_calls": ctx.tool_calls,
            "memory_size": await self._memory_size(session.session_id),
            "metadata": dict(ctx.metadata),
            "interrupted": False,
            "decision": "rejected",
            "tool_executed": False,
        }
        result["advanced"] = self.advanced_state(
            session.session_id,
            executing_agent="MinimalChatAgent",
            agent_path=["MinimalChatAgent"],
        )
        return result

    async def _resume_with_approval(
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
    ) -> dict[str, Any]:
        """人工决策后恢复 OpenAI Agents SDK 中断运行。"""
        if not self.settings.openai_api_key:
            raise RuntimeError("OPENAI_API_KEY is required for /chat endpoint")

        task_type = self.model_router.infer_task_type(user_input) if user_input else None
        selected_model = model or self.model_router.select(task_type=task_type)
        ctx = RunContext(
            session_id=session.session_id,
            user_id=session.user_id,
            user_input=user_input,
            enriched_input=user_input,
            selected_model=selected_model,
        )
        client = self._create_openai_client()
        instructions = await self._resolve_instructions(task_type, ctx)
        agent = self._build_agent(
            model=selected_model,
            client=client,
            instructions=instructions,
        )
        sdk_state = await RunState.from_json(agent, run_state)
        rejected_tool_name = "requested_tool"
        rejected_tool_args: dict[str, Any] = {}
        if self.hitl_mgr is not None:
            if not approval_request_id:
                raise ValueError("HITL 已启用，恢复请求必须包含 approval_request_id")
            reviewed_request = await self.hitl_mgr.review_sdk_approval(
                request_id=approval_request_id,
                session_id=session.session_id,
                interruption_index=interruption_index,
                run_state=run_state,
                approved=approved,
                reviewer=reviewer,
                comment=rejection_message or "",
            )
            rejected_tool_name = reviewed_request.tool_name
            rejected_tool_args = reviewed_request.tool_args
            self.hitl_mgr.apply_approval_to_state(
                sdk_state,
                interruption_index=interruption_index,
                approved=approved,
                always=always,
                rejection_message=rejection_message,
            )
        else:
            interruptions = sdk_state.get_interruptions()
            if interruption_index < 0 or interruption_index >= len(interruptions):
                raise ValueError(f"审批中断不存在: {interruption_index}")
            interruption = interruptions[interruption_index]
            rejected_tool_name = (
                getattr(interruption, "qualified_name", None)
                or getattr(interruption, "name", None)
                or rejected_tool_name
            )
            if approved:
                sdk_state.approve(interruption, always_approve=always)
            else:
                sdk_state.reject(
                    interruption,
                    always_reject=always,
                    rejection_message=rejection_message,
                )

        if not approved:
            return await self._complete_rejected_resume(
                session=session,
                ctx=ctx,
                selected_model=selected_model,
                tool_name=rejected_tool_name,
                tool_args=rejected_tool_args,
            )

        try:
            run_result = await Runner.run(starting_agent=agent, input=sdk_state)
        except Exception as e:
            await self.registry.dispatch(RunPhase.ON_ERROR, ctx, error=e)
            raise

        interruptions = list(getattr(run_result, "interruptions", []) or [])
        if interruptions:
            next_state = run_result.to_state().to_json()
            approval_requests = []
            if self.hitl_mgr is not None:
                next_state, requests = await self.hitl_mgr.request_approvals_from_result(
                    run_result,
                    session_id=ctx.session_id,
                    user_id=ctx.user_id or "anonymous",
                )
                approval_requests = [request.to_dict() for request in requests]
            else:
                approval_requests = [
                    {
                        "tool_name": getattr(item, "qualified_name", None)
                        or getattr(item, "name", None)
                        or "unknown",
                        "arguments": getattr(item, "arguments", None),
                        "call_id": getattr(item, "call_id", None),
                        "sdk_interruption_index": index,
                    }
                    for index, item in enumerate(interruptions)
                ]
            ctx.metadata["hitl"] = {
                "interrupted": True,
                "approval_requests": approval_requests,
            }
            result = {
                "session_id": session.session_id,
                "input": user_input,
                "output": None,
                "model": selected_model,
                "tool_calls": [],
                "memory_size": await self._memory_size(session.session_id),
                "metadata": dict(ctx.metadata),
                "interrupted": True,
                "interruptions": approval_requests,
                "run_state": next_state,
            }
            executing_agent = self._execution_agent_name(run_result)
            result["advanced"] = self.advanced_state(
                session.session_id,
                executing_agent=executing_agent,
                agent_path=self._agent_path(executing_agent),
            )
            return result

        ctx.final_output = str(run_result.final_output)
        ctx.tool_calls = parse_tool_calls_from_result(run_result)
        await self.registry.dispatch(RunPhase.AFTER_RUN, ctx)
        session.context["last_model"] = selected_model

        result = {
            "session_id": session.session_id,
            "input": user_input,
            "output": ctx.final_output,
            "model": selected_model,
            "tool_calls": ctx.tool_calls,
            "memory_size": await self._memory_size(session.session_id),
            "metadata": dict(ctx.metadata),
            "interrupted": False,
        }
        executing_agent = self._execution_agent_name(run_result)
        result["advanced"] = self.advanced_state(
            session.session_id,
            executing_agent=executing_agent,
            agent_path=self._agent_path(executing_agent),
        )
        return result

    async def _resume_stream_with_approval(
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
        """审批决策后流式返回后续执行结果。"""
        if not approved:
            result = await self._resume_with_approval(
                session,
                run_state=run_state,
                interruption_index=interruption_index,
                approved=False,
                approval_request_id=approval_request_id,
                reviewer=reviewer,
                model=model,
                user_input=user_input,
                always=always,
                rejection_message=rejection_message,
            )
            yield {
                "type": "start",
                "session_id": session.session_id,
                "model": result["model"],
                "advanced": result["advanced"],
            }
            for delta in (
                "操作已被拒绝，",
                f"未执行工具 {result['tool_calls'][0]['name']}。",
                "因此无法基于该工具的查询结果提供信息或建议。",
            ):
                yield {"type": "delta", "delta": delta}
            yield {"type": "done", "data": result}
            return

        if not self.settings.openai_api_key:
            raise RuntimeError("OPENAI_API_KEY is required for /chat endpoint")
        task_type = self.model_router.infer_task_type(user_input) if user_input else None
        selected_model = model or self.model_router.select(task_type=task_type)
        ctx = RunContext(
            session_id=session.session_id,
            user_id=session.user_id,
            user_input=user_input,
            enriched_input=user_input,
            selected_model=selected_model,
        )
        client = self._create_openai_client()
        instructions = await self._resolve_instructions(task_type, ctx)
        agent = self._build_agent(model=selected_model, client=client, instructions=instructions)
        sdk_state = await RunState.from_json(agent, run_state)
        if self.hitl_mgr is not None:
            if not approval_request_id:
                raise ValueError("HITL 已启用，恢复请求必须包含 approval_request_id")
            await self.hitl_mgr.review_sdk_approval(
                request_id=approval_request_id,
                session_id=session.session_id,
                interruption_index=interruption_index,
                run_state=run_state,
                approved=True,
                reviewer=reviewer,
                comment=rejection_message or "",
            )
            self.hitl_mgr.apply_approval_to_state(
                sdk_state,
                interruption_index=interruption_index,
                approved=True,
                always=always,
            )
        else:
            interruptions = sdk_state.get_interruptions()
            if interruption_index < 0 or interruption_index >= len(interruptions):
                raise ValueError(f"审批中断不存在: {interruption_index}")
            sdk_state.approve(interruptions[interruption_index], always_approve=always)

        agent_path = ["MinimalChatAgent"]
        yield {
            "type": "start",
            "session_id": session.session_id,
            "model": selected_model,
            "advanced": self.advanced_state(
                session.session_id,
                executing_agent=agent_path[-1],
                agent_path=agent_path,
            ),
        }
        try:
            result = Runner.run_streamed(starting_agent=agent, input=sdk_state)
            async for event in result.stream_events():
                if isinstance(event, RawResponsesStreamEvent) and isinstance(
                    event.data, ResponseTextDeltaEvent
                ):
                    yield {"type": "delta", "delta": event.data.delta}
                elif isinstance(event, RawResponsesStreamEvent) and isinstance(
                    event.data, ResponseReasoningSummaryTextDeltaEvent
                ):
                    yield {
                        "type": "reasoning_summary_delta",
                        "delta": event.data.delta,
                    }
                elif isinstance(event, AgentUpdatedStreamEvent):
                    executing_agent = getattr(event.new_agent, "name", None)
                    if isinstance(executing_agent, str) and agent_path[-1] != executing_agent:
                        agent_path.append(executing_agent)
                    yield {
                        "type": "agent_updated",
                        "agent": executing_agent or agent_path[-1],
                        "agent_path": list(agent_path),
                    }
        except Exception as exc:
            await self.registry.dispatch(RunPhase.ON_ERROR, ctx, error=exc)
            raise

        interruptions = list(getattr(result, "interruptions", []) or [])
        if interruptions:
            next_state = result.to_state().to_json()
            requests = []
            if self.hitl_mgr is not None:
                next_state, pending = await self.hitl_mgr.request_approvals_from_result(
                    result,
                    session_id=ctx.session_id,
                    user_id=ctx.user_id or "anonymous",
                )
                requests = [request.to_dict() for request in pending]
            yield {
                "type": "done",
                "data": {
                    "session_id": session.session_id,
                    "input": user_input,
                    "output": None,
                    "model": selected_model,
                    "tool_calls": [],
                    "memory_size": await self._memory_size(session.session_id),
                    "metadata": dict(ctx.metadata),
                    "interrupted": True,
                    "interruptions": requests,
                    "run_state": next_state,
                    "advanced": self.advanced_state(
                        session.session_id,
                        executing_agent=self._execution_agent_name(result),
                        agent_path=agent_path,
                    ),
                },
            }
            return

        ctx.final_output = str(result.final_output)
        ctx.tool_calls = parse_tool_calls_from_result(result)
        await self.registry.dispatch(RunPhase.AFTER_RUN, ctx)
        session.context["last_model"] = selected_model
        executing_agent = self._execution_agent_name(result)
        if agent_path[-1] != executing_agent:
            agent_path.append(executing_agent)
        yield {
            "type": "done",
            "data": {
                "session_id": session.session_id,
                "input": user_input,
                "output": ctx.final_output,
                "model": selected_model,
                "tool_calls": ctx.tool_calls,
                "memory_size": await self._memory_size(session.session_id),
                "metadata": dict(ctx.metadata),
                "interrupted": False,
                "advanced": self.advanced_state(
                    session.session_id,
                    executing_agent=executing_agent,
                    agent_path=agent_path,
                ),
            },
        }

    def _create_openai_client(self) -> AsyncOpenAI:
        client_kwargs: dict[str, Any] = {"api_key": self.settings.openai_api_key}
        if self.settings.openai_base_url:
            client_kwargs["base_url"] = self.settings.openai_base_url
        return AsyncOpenAI(**client_kwargs)

    def _build_agent(
        self,
        *,
        model: str,
        client: AsyncOpenAI,
        instructions: str,
    ) -> Agent:
        sdk_model = OpenAIChatCompletionsModel(model=model, openai_client=client)
        handoffs = []
        if self.handoff_mgr is not None:
            handoffs = self.handoff_mgr.build_configured_handoffs(sdk_model)
            if handoffs:
                from agents.extensions.handoff_prompt import prompt_with_handoff_instructions

                instructions = prompt_with_handoff_instructions(instructions)
        model_settings = ModelSettings()
        if getattr(self.settings, "reasoning_summary_enabled", False):
            model_settings = ModelSettings(
                reasoning=Reasoning(
                    summary=getattr(self.settings, "reasoning_summary_mode", "auto")
                )
            )
        return Agent(
            name="MinimalChatAgent",
            instructions=instructions,
            model=sdk_model,
            model_settings=model_settings,
            tools=self.tool_registry.list_agent_tools(),
            handoffs=handoffs,
        )

    def _default_instructions(self) -> str:
        return (
            "You are a concise assistant. Use tools when useful. "
            "If a tool is used, include the final user-facing conclusion in plain text."
        )

    async def _resolve_instructions(self, task_type: str, ctx: RunContext) -> str:
        instructions = self._default_instructions()
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
        return instructions
