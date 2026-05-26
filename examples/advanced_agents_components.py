"""高级 Agent 能力的组件级演示。

本文件不调用远程模型，用于理解 manager 层行为。HTTP 应用的主接入路径是：

- HITL: Harness 配置受控工具，由 ``POST /chat/resume`` 恢复 SDK 中断。
- Checkpoint: capability 按 ``CHECKPOINT_AUTO_SAVE`` 在运行边界保存摘要。
- Handoff: ``HANDOFF_AGENTS_JSON`` 生成 SDK 原生 ``Agent.handoffs`` 目标。
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agents import AsyncOpenAI, OpenAIChatCompletionsModel

from src.capabilities.advanced_agents import (
    AgentState,
    ApprovalManager,
    CheckpointConfig,
    CheckpointManager,
    HandoffConfig,
    HandoffManager,
    HITLConfig,
)


def build_demo_model() -> OpenAIChatCompletionsModel:
    """创建类型正确的 SDK model；构建 handoff 目标不会请求服务。"""
    client = AsyncOpenAI(api_key="example-not-used")
    return OpenAIChatCompletionsModel(model="example-model", openai_client=client)


async def example_hitl_policy() -> None:
    """演示进程内审批记录；真实执行中中断由 SDK 产生。"""
    print("\n示例 1: HITL 审批记录")
    manager = ApprovalManager(
        HITLConfig(
            enabled=True,
            require_approval_tools=["delete_user"],
            auto_approve_tools=["query_user"],
        )
    )

    assert manager.requires_approval("delete_user")
    request = await manager.request_approval(
        tool_name="delete_user",
        tool_args={"user_id": "user-123"},
        session_id="session-001",
        user_id="reviewer-demo",
        reason="敏感操作演示",
    )
    await manager.approve(request.id, reviewer="demo-reviewer")
    print(f"- delete_user: {request.status.value}")
    print(f"- query_user requires approval: {manager.requires_approval('query_user')}")
    manager.cleanup()


async def example_checkpoint_snapshot() -> None:
    """演示可回看的内存摘要，不将其表述为 SDK RunState 恢复。"""
    print("\n示例 2: Checkpoint 运行摘要")
    manager = CheckpointManager(
        CheckpointConfig(enabled=True, max_checkpoints=5, auto_save=True)
    )
    state = AgentState(
        session_id="session-001",
        conversation_history=[{"role": "user", "content": "你好"}],
        current_model="example-model",
        tool_calls=[],
        context={"user_id": "user-123"},
    )
    checkpoint_id = await manager.save("session-001", state, "运行开始摘要")
    restored = await manager.restore(checkpoint_id)
    print(f"- snapshot id: {checkpoint_id[:8]}...")
    print(f"- restored turns: {len(restored.conversation_history) if restored else 0}")
    print("- boundary: snapshot is not SDK RunState persistence")
    manager.cleanup()


def example_configured_handoffs() -> None:
    """演示和 Harness 一致的配置驱动 SDK handoff 装配。"""
    print("\n示例 3: 配置驱动 Handoff")
    manager = HandoffManager(
        HandoffConfig(
            enabled=True,
            agents={
                "billing": {
                    "description": "处理账单问题",
                    "instructions": "仅处理账单与退款咨询。",
                },
                "support": {
                    "description": "处理技术支持",
                    "instructions": "仅处理技术故障排查。",
                },
            },
        )
    )
    targets = manager.build_configured_handoffs(build_demo_model())
    for target in targets:
        print(f"- {target.name}: {target.handoff_description}")
    manager.cleanup()


async def main() -> None:
    await example_hitl_policy()
    await example_checkpoint_snapshot()
    example_configured_handoffs()
    print("\n组件演示完成。运行中的 Harness 请使用配置开关与 HTTP API。")


if __name__ == "__main__":
    asyncio.run(main())
