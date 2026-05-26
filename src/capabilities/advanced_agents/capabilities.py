"""高级 Agent 能力的 Capability 适配器

把 ``CheckpointManager / ApprovalManager / HandoffManager`` 包装为可被
``CapabilityRegistry`` 统一调度的 ``Capability``, 让 ``agent_runtime`` 不再
关心具体能力的开关与 try/except, 全部通过 ``registry.dispatch`` 完成。
"""

from __future__ import annotations

from src.capabilities.plugin import Capability, RunContext
from src.harness.manifest import CapabilityKind, CapabilityManifest

from .checkpoint import CheckpointManager
from .config import AgentState
from .handoff import HandoffManager
from .hitl import ApprovalManager


class CheckpointCapability(Capability):
    """Checkpoint 状态保存能力

    - ``before_run``: 保存调用前的初始状态
    - ``after_run``:  保存调用完成后的终态 (含对话与工具调用)
    """

    name = "checkpoint"
    manifest = CapabilityManifest(
        name="checkpoint",
        kind=CapabilityKind.RUNTIME,
        config_section="checkpoint",
        provides=("run_checkpoints",),
        install_order=40,
    )

    def __init__(self, manager: CheckpointManager) -> None:
        self._manager = manager

    def is_enabled(self) -> bool:
        return self._manager.is_enabled()

    async def before_run(self, ctx: RunContext) -> None:
        if not self._manager.config.auto_save:
            return
        initial_state = AgentState(
            session_id=ctx.session_id,
            conversation_history=[],
            current_model=ctx.selected_model,
            tool_calls=[],
            context={"user_id": ctx.user_id or "anonymous"},
        )
        await self._manager.save(
            session_id=ctx.session_id,
            state=initial_state,
            description="Agent 调用前",
        )

    async def after_run(self, ctx: RunContext) -> None:
        if not self._manager.config.auto_save:
            return
        final_state = AgentState(
            session_id=ctx.session_id,
            conversation_history=[
                {"role": "user", "content": ctx.user_input},
                {"role": "assistant", "content": ctx.final_output or ""},
            ],
            current_model=ctx.selected_model,
            tool_calls=ctx.tool_calls,
            context={"user_id": ctx.user_id or "anonymous"},
        )
        await self._manager.save(
            session_id=ctx.session_id,
            state=final_state,
            description="Agent 调用完成",
        )


class HITLCapability(Capability):
    """Human-in-the-Loop 审批能力

    作为 HITL 能力声明与生命周期入口。实际审批请求由 SDK 原生
    ``interruptions`` 产生，并由 Runtime 转交给 ``ApprovalManager``，
    避免工具执行完成后重复申请审批。
    """

    name = "hitl"
    manifest = CapabilityManifest(
        name="hitl",
        kind=CapabilityKind.RUNTIME,
        config_section="hitl",
        depends_on=("tool_registry",),
        provides=("approval_requests",),
        install_order=50,
    )

    def __init__(self, manager: ApprovalManager) -> None:
        self._manager = manager

    def is_enabled(self) -> bool:
        return self._manager.is_enabled()


class HandoffCapability(Capability):
    """SDK 原生 handoff 的声明型能力；执行由 ``Agent.handoffs`` 完成。"""

    name = "handoff"
    manifest = CapabilityManifest(
        name="handoff",
        kind=CapabilityKind.RUNTIME,
        config_section="handoff",
        depends_on=("model_router",),
        provides=("agent_handoffs",),
        install_order=45,
    )

    def __init__(self, manager: HandoffManager) -> None:
        self._manager = manager

    def is_enabled(self) -> bool:
        return self._manager.is_enabled()
