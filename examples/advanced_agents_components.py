"""
高级 Agent 能力底层组件示例

展示如何使用:
- ApprovalManager 人工审批状态管理
- Checkpoint 检查点管理
- Handoff 目标注册

注意:
- 本文件用于验证底层 manager，可在本地独立运行。
- 正式应用中的 HITL 主路径是 SDK 原生 ``interruptions`` +
  ``POST /chat/resume``，参见 README 与架构设计文档。
"""

import asyncio
import sys
from pathlib import Path

# 添加项目根目录到 Python 路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.capabilities.advanced_agents import (
    ApprovalManager,
    CheckpointManager,
    HandoffManager,
    HITLConfig,
    CheckpointConfig,
    HandoffConfig,
    AgentState,
)


# ============================================================
# 示例 1: HITL 人工审批
# ============================================================

async def example_hitl_approval():
    """示例 1: 人工审批流程"""
    print("\n" + "="*80)
    print("示例 1: HITL 人工审批")
    print("="*80)
    
    # 配置 HITL
    config = HITLConfig(
        enabled=True,
        approval_timeout=30.0,
        require_approval_tools=["delete_user", "send_notification"],
        auto_approve_tools=["query_user", "get_status"],
    )
    
    manager = ApprovalManager(config)
    
    # 模拟工具调用 - 需要审批
    tool_name = "delete_user"
    if manager.requires_approval(tool_name):
        print(f"\n🔧 工具 '{tool_name}' 需要人工审批")
        
        # 创建审批请求
        request = await manager.request_approval(
            tool_name="delete_user",
            tool_args={"user_id": "user-123"},
            session_id="session-001",
            user_id="admin-001",
            reason="删除违规用户",
        )
        
        # 在实际应用中,这里会等待 UI 或人工审批
        # 这里模拟自动批准
        await asyncio.sleep(1)
        approved = await manager.approve(request.id, reviewer="admin-manager")
        
        if approved:
            print("✅ 审批通过,继续执行删除操作")
            # await delete_user("user-123")
        else:
            print("❌ 审批拒绝,取消操作")
    
    # 模拟工具调用 - 自动审批
    tool_name = "query_user"
    if not manager.requires_approval(tool_name):
        print(f"\n🔧 工具 '{tool_name}' 自动审批,直接执行")
        # result = await query_user("user-123")
    
    manager.cleanup()


# ============================================================
# 示例 2: Checkpoint 检查点管理
# ============================================================

async def example_checkpoint():
    """示例 2: Checkpoint 检查点"""
    print("\n" + "="*80)
    print("示例 2: Checkpoint 检查点管理")
    print("="*80)
    
    config = CheckpointConfig(
        enabled=True,
        max_checkpoints=5,
        save_on_tool_call=True,
    )
    
    manager = CheckpointManager(config)
    session_id = "session-001"
    
    # Step 1: 保存初始状态
    state1 = AgentState(
        session_id=session_id,
        conversation_history=[{"role": "user", "content": "你好"}],
        current_model="qwen3.5-plus",
        tool_calls=[],
        context={"user_id": "user-123"},
    )
    cp1 = await manager.save(session_id, state1, "初始状态")
    
    # Step 2: 执行一些操作后保存
    state2 = AgentState(
        session_id=session_id,
        conversation_history=[
            {"role": "user", "content": "你好"},
            {"role": "assistant", "content": "你好!有什么可以帮你的?"},
        ],
        current_model="qwen3.5-plus",
        tool_calls=[{"tool": "greet", "result": "success"}],
        context={"user_id": "user-123", "greeted": True},
    )
    cp2 = await manager.save(session_id, state2, "完成问候")
    
    # Step 3: 列出所有检查点
    print(f"\n📜 检查点历史:")
    checkpoints = manager.list_checkpoints(session_id)
    for i, cp in enumerate(checkpoints, 1):
        print(f"  {i}. [{cp.id[:8]}...] {cp.description}")
    
    # Step 4: 恢复到之前的检查点
    print(f"\n🔄 恢复到检查点 1...")
    restored_state = await manager.restore(cp1)
    if restored_state:
        print(f"✅ 恢复成功!")
        print(f"   对话历史: {len(restored_state.conversation_history)} 条")
        print(f"   上下文: {restored_state.context}")
    
    manager.cleanup()


# ============================================================
# 示例 3: Handoff Agent 协作
# ============================================================

async def example_handoff():
    """示例 3: Handoff Agent 协作"""
    print("\n" + "="*80)
    print("示例 3: Handoff Agent 协作")
    print("="*80)
    
    config = HandoffConfig(
        enabled=True,
        default_agent="general",
    )
    
    manager = HandoffManager(config)
    
    # 注册专业 Agent
    manager.register_agent(
        name="tech_support",
        display_name="技术支持 Agent",
        description="处理技术问题",
        instructions="你是一名技术支持专家。",
    )
    
    manager.register_agent(
        name="billing",
        display_name="账单 Agent",
        description="处理账单问题",
        instructions="你是一名账单专家。",
    )
    
    # 检查 Agent 可用性
    print(f"\n🔍 检查 Agent 可用性:")
    print(f"   tech_support: {manager.is_agent_available('tech_support')}")
    print(f"   billing: {manager.is_agent_available('billing')}")
    print(f"   unknown: {manager.is_agent_available('unknown')}")
    
    # 获取所有可用 Agent
    print(f"\n📋 已注册 Agent:")
    for name, info in manager.get_registry().items():
        print(f"   - {name}: {info['display_name']}")
    
    manager.cleanup()


# ============================================================
# 示例 4: 组合使用所有能力
# ============================================================

async def example_combined():
    """示例 4: 组合使用所有能力"""
    print("\n" + "="*80)
    print("示例 4: 组合使用所有能力")
    print("="*80)
    
    # 初始化所有管理器
    hitl_mgr = ApprovalManager(HITLConfig(
        enabled=True,
        require_approval_tools=["delete_data"],
    ))
    
    checkpoint_mgr = CheckpointManager(CheckpointConfig(
        enabled=True,
        max_checkpoints=10,
    ))
    
    handoff_mgr = HandoffManager(HandoffConfig(
        enabled=True,
        default_agent="general",
    ))
    
    session_id = "session-combined"
    
    # Step 1: 保存初始状态
    state = AgentState(
        session_id=session_id,
        conversation_history=[],
        current_model="qwen3.5-plus",
        tool_calls=[],
        context={"user_id": "user-001"},
    )
    cp_id = await checkpoint_mgr.save(session_id, state, "初始状态")
    print(f"💾 检查点已保存: {cp_id[:8]}...")
    
    # Step 2: 注册 Agent
    handoff_mgr.register_agent(
        "data_processor",
        "数据处理 Agent",
        "处理数据操作",
    )
    
    # Step 3: 尝试敏感操作 (需要审批)
    if hitl_mgr.requires_approval("delete_data"):
        print(f"\n🔧 敏感操作需要审批...")
        request = await hitl_mgr.request_approval(
            tool_name="delete_data",
            tool_args={"data_id": "data-123"},
            session_id=session_id,
            user_id="user-001",
        )
        
        # 模拟审批
        await asyncio.sleep(1)
        await hitl_mgr.approve(request.id, reviewer="admin")
    
    # Step 4: 保存最终状态
    final_state = AgentState(
        session_id=session_id,
        conversation_history=[
            {"role": "system", "content": "所有操作完成"},
        ],
        current_model="qwen3.5-plus",
        tool_calls=[{"tool": "delete_data", "result": "success"}],
        context={"user_id": "user-001", "completed": True},
    )
    await checkpoint_mgr.save(session_id, final_state, "完成")
    
    print(f"\n✅ 所有能力组合使用成功!")
    
    # 清理
    hitl_mgr.cleanup()
    checkpoint_mgr.cleanup()
    handoff_mgr.cleanup()


# ============================================================
# 运行所有示例
# ============================================================

async def main():
    """运行所有示例"""
    try:
        await example_hitl_approval()
        await example_checkpoint()
        await example_handoff()
        await example_combined()
        
        print("\n" + "="*80)
        print("🎉 所有示例运行完成!")
        print("="*80 + "\n")
    except Exception as e:
        print(f"\n❌ 示例运行失败: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
