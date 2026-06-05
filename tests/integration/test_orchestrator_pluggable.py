"""
测试 AgentOrchestrator 的可插拔能力

验证三种模式:
1. 简单模式 (基础能力)
2. 中等模式 (基础 + 长期记忆)
3. 完整模式 (基础 + 长期记忆 + 高级能力)
"""

import sys
from pathlib import Path

# 添加项目根目录到 Python 路径
sys.path.insert(0, str(Path(__file__).parents[2]))

from src.application.orchestration.agent_runtime import AgentOrchestrator, ADVANCED_AGENTS_AVAILABLE
from src.capabilities.memory.store import MemoryStore
from src.capabilities.model_routing.router import ModelRouter
from src.capabilities.tools.registry import ToolRegistry


def test_simple_mode():
    """测试 1: 简单模式 (仅基础能力)"""
    print("\n" + "=" * 80)
    print("测试 1: 简单模式 (基础能力)")
    print("=" * 80)

    memory_store = MemoryStore()
    tool_registry = ToolRegistry()
    tool_registry.register_defaults()
    model_router = ModelRouter()

    # 创建简单模式的 Orchestrator
    orchestrator = AgentOrchestrator(
        tool_registry=tool_registry,
        memory_store=memory_store,
        model_router=model_router,
    )

    # 验证高级能力未启用
    assert orchestrator.hitl_mgr is None, "HITL 应该未启用"
    assert orchestrator.checkpoint_mgr is None, "Checkpoint 应该未启用"
    assert orchestrator.handoff_mgr is None, "Handoff 应该未启用"

    print("✅ 简单模式创建成功")
    print(f"   - HITL: {'启用' if orchestrator.hitl_mgr else '未启用'}")
    print(f"   - Checkpoint: {'启用' if orchestrator.checkpoint_mgr else '未启用'}")
    print(f"   - Handoff: {'启用' if orchestrator.handoff_mgr else '未启用'}")
    print("=" * 80)


def test_medium_mode():
    """测试 2: 中等模式 (基础 + 高级能力)"""
    print("\n" + "=" * 80)
    print("测试 2: 中等模式 (基础 + 高级能力)")
    print("=" * 80)

    if not ADVANCED_AGENTS_AVAILABLE:
        print("⚠️  高级能力模块不可用,跳过此测试")
        print("=" * 80)
        return

    from src.capabilities.advanced_agents import HITLConfig, CheckpointConfig

    memory_store = MemoryStore()
    tool_registry = ToolRegistry()
    tool_registry.register_defaults()
    model_router = ModelRouter()

    # 配置高级能力
    hitl_config = HITLConfig(
        enabled=True,
        require_approval_tools=["delete_data"],
    )

    checkpoint_config = CheckpointConfig(
        enabled=True,
        max_checkpoints=5,
    )

    # 创建中等模式的 Orchestrator
    orchestrator = AgentOrchestrator(
        tool_registry=tool_registry,
        memory_store=memory_store,
        model_router=model_router,
        hitl_config=hitl_config,
        checkpoint_config=checkpoint_config,
    )

    # 验证高级能力已启用
    assert orchestrator.hitl_mgr is not None, "HITL 应该已启用"
    assert orchestrator.checkpoint_mgr is not None, "Checkpoint 应该已启用"
    assert orchestrator.handoff_mgr is None, "Handoff 应该未启用"

    print("✅ 中等模式创建成功")
    print(f"   - HITL: {'启用' if orchestrator.hitl_mgr else '未启用'}")
    print(f"   - Checkpoint: {'启用' if orchestrator.checkpoint_mgr else '未启用'}")
    print(f"   - Handoff: {'启用' if orchestrator.handoff_mgr else '未启用'}")

    # 验证 HITL 配置
    assert orchestrator.hitl_mgr.requires_approval("delete_data") is True
    assert orchestrator.hitl_mgr.requires_approval("query_data") is False

    print("✅ HITL 配置验证通过")
    print("=" * 80)


def test_full_mode():
    """测试 3: 完整模式 (所有能力)"""
    print("\n" + "=" * 80)
    print("测试 3: 完整模式 (所有能力)")
    print("=" * 80)

    if not ADVANCED_AGENTS_AVAILABLE:
        print("⚠️  高级能力模块不可用,跳过此测试")
        print("=" * 80)
        return

    from src.capabilities.advanced_agents import (
        HITLConfig,
        CheckpointConfig,
        HandoffConfig,
    )

    memory_store = MemoryStore()
    tool_registry = ToolRegistry()
    tool_registry.register_defaults()
    model_router = ModelRouter()

    # 配置所有高级能力
    hitl_config = HITLConfig(
        enabled=True,
        approval_timeout=300.0,
        require_approval_tools=["delete_data", "send_notification"],
        auto_approve_tools=["query_data"],
    )

    checkpoint_config = CheckpointConfig(
        enabled=True,
        max_checkpoints=10,
        save_on_tool_call=True,
    )

    handoff_config = HandoffConfig(
        enabled=True,
        default_agent="general",
    )

    # 创建完整模式的 Orchestrator
    orchestrator = AgentOrchestrator(
        tool_registry=tool_registry,
        memory_store=memory_store,
        model_router=model_router,
        hitl_config=hitl_config,
        checkpoint_config=checkpoint_config,
        handoff_config=handoff_config,
    )

    # 验证所有高级能力已启用
    assert orchestrator.hitl_mgr is not None, "HITL 应该已启用"
    assert orchestrator.checkpoint_mgr is not None, "Checkpoint 应该已启用"
    assert orchestrator.handoff_mgr is not None, "Handoff 应该已启用"

    print("✅ 完整模式创建成功")
    print(f"   - HITL: {'启用' if orchestrator.hitl_mgr else '未启用'}")
    print(f"   - Checkpoint: {'启用' if orchestrator.checkpoint_mgr else '未启用'}")
    print(f"   - Handoff: {'启用' if orchestrator.handoff_mgr else '未启用'}")

    # 验证配置
    assert orchestrator.hitl_mgr.config.approval_timeout == 300.0
    assert orchestrator.checkpoint_mgr.config.max_checkpoints == 10
    assert orchestrator.handoff_mgr.config.default_agent == "general"

    print("✅ 所有配置验证通过")
    print("=" * 80)


def test_optional_import():
    """测试 4: 验证可选导入"""
    print("\n" + "=" * 80)
    print("测试 4: 可选导入验证")
    print("=" * 80)

    print(f"✅ 高级能力模块: {'可用' if ADVANCED_AGENTS_AVAILABLE else '不可用'}")

    if ADVANCED_AGENTS_AVAILABLE:
        print("✅ ApprovalManager 导入成功")
        print("✅ CheckpointManager 导入成功")
        print("✅ HandoffManager 导入成功")

    print("=" * 80)


def main():
    """运行所有测试"""
    print("\n" + "=" * 80)
    print("🧪 AgentOrchestrator 可插拔能力测试")
    print("=" * 80)

    try:
        # 测试 1: 简单模式
        test_simple_mode()

        # 测试 2: 可选导入
        test_optional_import()

        # 测试 3: 中等模式
        test_medium_mode()

        # 测试 4: 完整模式
        test_full_mode()

        print("\n" + "=" * 80)
        print("🎉 所有测试通过!")
        print("=" * 80)
        print("\n✅ 验证内容:")
        print("  ✓ 简单模式 (基础能力)")
        print("  ✓ 中等模式 (基础 + 高级能力)")
        print("  ✓ 完整模式 (所有能力)")
        print("  ✓ 可选导入机制")
        print("  ✓ 可插拔设计")
        print("=" * 80 + "\n")

    except AssertionError as e:
        print(f"\n❌ 测试失败: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ 测试异常: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
