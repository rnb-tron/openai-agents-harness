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

    在 ``after_run`` 检查工具调用是否需要审批, 创建审批请求。
    实际"等待审批 / 拒绝则中断"的逻辑由业务侧通过 ``ApprovalManager`` 自行驱动。
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

    async def after_run(self, ctx: RunContext) -> None:
        if not ctx.tool_calls:
            return
        for tc in ctx.tool_calls:
            tool_name = tc.get("tool", "")
            if self._manager.requires_approval(tool_name):
                await self._manager.request_approval(
                    tool_name=tool_name,
                    tool_args=tc.get("args", {}),
                    session_id=ctx.session_id,
                    user_id=ctx.user_id or "anonymous",
                    reason=f"工具 {tool_name} 需要审批",
                )
