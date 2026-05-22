"""
高级 Agent 能力单元测试

测试:
- HITL 审批流程
- Checkpoint 检查点管理
- AgentState 数据模型
"""

import asyncio
import sys
import pytest
from pathlib import Path
from datetime import datetime

# 添加项目根目录到 Python 路径
sys.path.insert(0, str(Path(__file__).parents[2]))

from src.capabilities.advanced_agents import (
    ApprovalManager,
    CheckpointManager,
    HITLConfig,
    CheckpointConfig,
    AgentState,
    ApprovalStatus,
)


class TestHITL:
    """测试 HITL 人工审批"""
    
    @pytest.mark.asyncio
    async def test_approval_required(self):
        """测试需要审批的工具"""
        config = HITLConfig(
            enabled=True,
            require_approval_tools=["delete_user", "send_notification"],
        )
        manager = ApprovalManager(config)
        
        assert manager.requires_approval("delete_user") is True
        assert manager.requires_approval("send_notification") is True
        assert manager.requires_approval("query_user") is False
        
        manager.cleanup()
    
    @pytest.mark.asyncio
    async def test_auto_approve(self):
        """测试自动审批的工具"""
        config = HITLConfig(
            enabled=True,
            auto_approve_tools=["query_user", "get_status"],
            require_approval_tools=["delete_user"],
        )
        manager = ApprovalManager(config)
        
        # 自动审批列表中的工具不需要审批
        assert manager.requires_approval("query_user") is False
        assert manager.requires_approval("get_status") is False
        
        # 需要审批列表中的工具需要审批
        assert manager.requires_approval("delete_user") is True
        
        manager.cleanup()
    
    @pytest.mark.asyncio
    async def test_disabled(self):
        """测试禁用 HITL"""
        config = HITLConfig(enabled=False)
        manager = ApprovalManager(config)
        
        assert manager.is_enabled() is False
        assert manager.requires_approval("delete_user") is False
        
        manager.cleanup()
    
    @pytest.mark.asyncio
    async def test_approval_flow(self):
        """测试完整审批流程"""
        config = HITLConfig(enabled=True, approval_timeout=5.0)
        manager = ApprovalManager(config)
        
        # 创建审批请求
        request = await manager.request_approval(
            tool_name="delete_user",
            tool_args={"user_id": "user-123"},
            session_id="session-001",
            user_id="admin-001",
            reason="删除违规用户",
        )
        
        assert request.status == ApprovalStatus.PENDING
        assert request.tool_name == "delete_user"
        
        # 批准
        await manager.approve(request.id, reviewer="admin-manager")
        assert request.status == ApprovalStatus.APPROVED
        assert request.reviewed_by == "admin-manager"
        
        manager.cleanup()
    
    @pytest.mark.asyncio
    async def test_rejection_flow(self):
        """测试拒绝流程"""
        config = HITLConfig(enabled=True, approval_timeout=5.0)
        manager = ApprovalManager(config)
        
        request = await manager.request_approval(
            tool_name="delete_user",
            tool_args={"user_id": "user-123"},
            session_id="session-001",
            user_id="admin-001",
        )
        
        # 拒绝
        await manager.reject(
            request.id,
            reviewer="admin-manager",
            reason="用户不应删除",
        )
        assert request.status == ApprovalStatus.REJECTED
        assert request.review_comment == "用户不应删除"
        
        manager.cleanup()
    
    @pytest.mark.asyncio
    async def test_timeout(self):
        """测试审批超时"""
        config = HITLConfig(enabled=True, approval_timeout=1.0)
        manager = ApprovalManager(config)
        
        request = await manager.request_approval(
            tool_name="delete_user",
            tool_args={"user_id": "user-123"},
            session_id="session-001",
            user_id="admin-001",
        )
        
        # 等待超时
        result = await manager.wait_for_approval(request.id, timeout=1.0)
        assert result is False
        assert request.status == ApprovalStatus.TIMEOUT
        
        manager.cleanup()
    
    @pytest.mark.asyncio
    async def test_wait_for_approval(self):
        """测试等待审批"""
        config = HITLConfig(enabled=True, approval_timeout=5.0)
        manager = ApprovalManager(config)
        
        request = await manager.request_approval(
            tool_name="delete_user",
            tool_args={"user_id": "user-123"},
            session_id="session-001",
            user_id="admin-001",
        )
        
        # 创建异步任务等待审批
        async def approve_later():
            await asyncio.sleep(0.5)
            await manager.approve(request.id, reviewer="admin")
        
        # 启动审批任务
        asyncio.create_task(approve_later())
        
        # 等待审批
        result = await manager.wait_for_approval(request.id, timeout=2.0)
        assert result is True
        
        manager.cleanup()


class TestCheckpoint:
    """测试 Checkpoint 检查点"""
    
    @pytest.mark.asyncio
    async def test_save_and_load(self):
        """测试保存和加载检查点"""
        config = CheckpointConfig(enabled=True)
        manager = CheckpointManager(config)
        
        state = AgentState(
            session_id="session-001",
            conversation_history=[{"role": "user", "content": "你好"}],
            current_model="qwen3.5-plus",
            tool_calls=[],
            context={"user_id": "user-123"},
        )
        
        # 保存
        cp_id = await manager.save("session-001", state, "测试检查点")
        assert cp_id is not None
        
        # 加载
        checkpoint = await manager.load(cp_id)
        assert checkpoint is not None
        assert checkpoint.description == "测试检查点"
        assert checkpoint.state.session_id == "session-001"
        
        manager.cleanup()
    
    @pytest.mark.asyncio
    async def test_restore(self):
        """测试恢复检查点"""
        config = CheckpointConfig(enabled=True)
        manager = CheckpointManager(config)
        
        state = AgentState(
            session_id="session-001",
            conversation_history=[
                {"role": "user", "content": "你好"},
                {"role": "assistant", "content": "你好!"},
            ],
            current_model="qwen3.5-plus",
            tool_calls=[],
            context={"user_id": "user-123"},
        )
        
        cp_id = await manager.save("session-001", state, "恢复测试")
        
        # 恢复
        restored_state = await manager.restore(cp_id)
        assert restored_state is not None
        assert restored_state.session_id == "session-001"
        assert len(restored_state.conversation_history) == 2
        assert restored_state.context["user_id"] == "user-123"
        
        manager.cleanup()
    
    @pytest.mark.asyncio
    async def test_list_checkpoints(self):
        """测试列出检查点"""
        config = CheckpointConfig(enabled=True, max_checkpoints=5)
        manager = CheckpointManager(config)
        
        session_id = "session-001"
        
        # 保存多个检查点
        for i in range(3):
            state = AgentState(
                session_id=session_id,
                conversation_history=[],
                current_model="qwen3.5-plus",
                tool_calls=[],
                context={"step": i},
            )
            await manager.save(session_id, state, f"步骤 {i}")
        
        # 列出检查点
        checkpoints = manager.list_checkpoints(session_id)
        assert len(checkpoints) == 3
        
        manager.cleanup()
    
    @pytest.mark.asyncio
    async def test_max_checkpoints(self):
        """测试检查点数量限制"""
        config = CheckpointConfig(enabled=True, max_checkpoints=3)
        manager = CheckpointManager(config)
        
        session_id = "session-001"
        
        # 保存超过限制的检查点
        for i in range(5):
            state = AgentState(
                session_id=session_id,
                conversation_history=[],
                current_model="qwen3.5-plus",
                tool_calls=[],
                context={"step": i},
            )
            await manager.save(session_id, state, f"步骤 {i}")
        
        # 应该只保留最新的 3 个
        checkpoints = manager.list_checkpoints(session_id)
        assert len(checkpoints) == 3
        
        manager.cleanup()
    
    @pytest.mark.asyncio
    async def test_disabled(self):
        """测试禁用 Checkpoint"""
        config = CheckpointConfig(enabled=False)
        manager = CheckpointManager(config)
        
        state = AgentState(
            session_id="session-001",
            conversation_history=[],
            current_model="qwen3.5-plus",
            tool_calls=[],
            context={},
        )
        
        cp_id = await manager.save("session-001", state, "测试")
        assert cp_id == ""
        
        manager.cleanup()
    
    @pytest.mark.asyncio
    async def test_get_latest(self):
        """测试获取最新检查点"""
        config = CheckpointConfig(enabled=True)
        manager = CheckpointManager(config)
        
        session_id = "session-001"
        
        # 保存多个检查点
        for i in range(3):
            state = AgentState(
                session_id=session_id,
                conversation_history=[],
                current_model="qwen3.5-plus",
                tool_calls=[],
                context={"step": i},
            )
            await manager.save(session_id, state, f"步骤 {i}")
        
        # 获取最新检查点
        latest = await manager.get_latest(session_id)
        assert latest is not None
        assert latest.context["step"] == 2
        
        manager.cleanup()


async def main():
    """运行测试"""
    print("\n" + "="*80)
    print("运行高级 Agent 能力测试")
    print("="*80)
    
    # 测试 HITL
    print("\n🧪 测试 HITL...")
    test_hitl = TestHITL()
    await test_hitl.test_approval_required()
    await test_hitl.test_auto_approve()
    await test_hitl.test_approval_flow()
    await test_hitl.test_rejection_flow()
    print("✅ HITL 测试通过")
    
    # 测试 Checkpoint
    print("\n🧪 测试 Checkpoint...")
    test_cp = TestCheckpoint()
    await test_cp.test_save_and_load()
    await test_cp.test_restore()
    await test_cp.test_list_checkpoints()
    await test_cp.test_max_checkpoints()
    await test_cp.test_get_latest()
    print("✅ Checkpoint 测试通过")
    
    print("\n" + "="*80)
    print("🎉 所有测试通过!")
    print("="*80 + "\n")


if __name__ == "__main__":
    asyncio.run(main())
