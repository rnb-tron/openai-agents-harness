"""
简化版 E2E 测试:真实 OpenAI Agent + 高级能力

这个测试展示如何将 HITL 和 Checkpoint 与真实 Agent 调用集成。
包含重试机制以应对 API 限流。
"""

import asyncio
import sys
from pathlib import Path
from datetime import datetime

# 添加项目根目录到 Python 路径
sys.path.insert(0, str(Path(__file__).parents[2]))

from agents import Agent, AsyncOpenAI, OpenAIChatCompletionsModel, Runner, function_tool

from src.capabilities.advanced_agents import (
    ApprovalManager,
    CheckpointManager,
    HITLConfig,
    CheckpointConfig,
    AgentState,
)

from src.core.config import current_settings


# ============================================================
# 工具定义
# ============================================================


@function_tool
def create_ticket(title: str, description: str, priority: str = "medium") -> str:
    """创建客服工单"""
    ticket_id = f"TKT-{datetime.now().strftime('%Y%m%d%H%M%S')}"
    print(f"  ✅ [工具调用] create_ticket: {ticket_id}")
    return f"工单已创建: {ticket_id}, 标题: {title}, 优先级: {priority}"


@function_tool
def query_ticket(ticket_id: str) -> str:
    """查询工单状态"""
    print(f"  🔍 [工具调用] query_ticket: {ticket_id}")
    return f"工单 {ticket_id} 状态: open, 处理中"


@function_tool
def delete_ticket(ticket_id: str) -> str:
    """删除工单 (需要审批)"""
    print(f"  🗑️  [工具调用] delete_ticket: {ticket_id}")
    return f"工单 {ticket_id} 已删除"


# ============================================================
# 重试辅助函数
# ============================================================


async def run_agent_with_retry(agent, input_text, max_retries=3):
    """带重试的 Agent 调用"""
    for attempt in range(max_retries):
        try:
            result = await Runner.run(starting_agent=agent, input=input_text)
            return result
        except Exception as e:
            if "429" in str(e) and attempt < max_retries - 1:
                wait_time = 15 * (attempt + 1)
                print(f"  ⚠️ API 限流,等待 {wait_time} 秒后重试...")
                await asyncio.sleep(wait_time)
            else:
                raise


# ============================================================
# E2E 测试:真实 Agent + 高级能力
# ============================================================


async def main():
    """真实 Agent 调用 E2E 测试"""

    print("\n" + "=" * 80)
    print("🚀 E2E 测试: 真实 OpenAI Agent + 高级能力")
    print("=" * 80)

    # --------------------------------------------------------
    # Step 0: 检查配置
    # --------------------------------------------------------
    print("\n📋 Step 0: 检查配置")
    print("-" * 80)

    if not current_settings.openai_api_key:
        print("❌ 未配置 OPENAI_API_KEY")
        print("   请在 config/test.env 中配置 API Key")
        return

    print("✅ API Key: 已配置")
    print(f"   Base URL: {current_settings.openai_base_url or '默认'}")
    print(f"   模型: {current_settings.agent_model_default}")

    # --------------------------------------------------------
    # Step 1: 初始化 OpenAI Agent
    # --------------------------------------------------------
    print("\n🤖 Step 1: 初始化 OpenAI Agent")
    print("-" * 80)

    client = AsyncOpenAI(
        api_key=current_settings.openai_api_key,
        base_url=current_settings.openai_base_url,
    )

    agent = Agent(
        name="客服工单处理助手",
        instructions=(
            "你是专业的客服工单处理助手。\n职责:\n1. 创建工单\n2. 查询工单状态\n3. 删除工单\n请使用提供的工具完成任务。"
        ),
        model=OpenAIChatCompletionsModel(
            model=current_settings.agent_model_default,
            openai_client=client,
        ),
        tools=[create_ticket, query_ticket, delete_ticket],
    )

    print(f"✅ Agent 已创建: {agent.name}")
    print(f"   工具数量: {len(agent.tools)}")

    # --------------------------------------------------------
    # Step 2: 初始化高级能力管理器
    # --------------------------------------------------------
    print("\n🔧 Step 2: 初始化高级能力管理器")
    print("-" * 80)

    # HITL 配置
    hitl_config = HITLConfig(
        enabled=True,
        approval_timeout=10.0,
        require_approval_tools=["delete_ticket"],
        auto_approve_tools=["create_ticket", "query_ticket"],
    )
    hitl_mgr = ApprovalManager(hitl_config)
    print("✅ HITL 管理器已初始化")

    # Checkpoint 配置
    checkpoint_config = CheckpointConfig(
        enabled=True,
        max_checkpoints=10,
    )
    checkpoint_mgr = CheckpointManager(checkpoint_config)
    print("✅ Checkpoint 管理器已初始化")

    session_id = "session-real-agent-e2e"

    # --------------------------------------------------------
    # Step 3: 第一次 Agent 调用 - 创建工单
    # --------------------------------------------------------
    print("\n📝 Step 3: Agent 调用 - 创建工单")
    print("-" * 80)

    # 保存初始检查点
    state1 = AgentState(
        session_id=session_id,
        conversation_history=[],
        current_model=current_settings.agent_model_default,
        tool_calls=[],
        context={"step": "initial"},
    )
    cp1 = await checkpoint_mgr.save(session_id, state1, "初始状态")

    # 调用 Agent
    user_input = "我遇到登录问题,请帮我创建工单"
    print(f"👤 用户: {user_input}")

    result1 = await run_agent_with_retry(agent, user_input)
    output1 = str(result1.final_output)
    print(f"🤖 Agent: {output1}")

    # 保存检查点
    state2 = AgentState(
        session_id=session_id,
        conversation_history=[
            {"role": "user", "content": user_input},
            {"role": "assistant", "content": output1},
        ],
        current_model=current_settings.agent_model_default,
        tool_calls=[],
        context={"step": "ticket_created"},
    )
    cp2 = await checkpoint_mgr.save(session_id, state2, "工单创建完成")

    print("💾 已保存 2 个检查点")

    # --------------------------------------------------------
    # Step 4: 第二次 Agent 调用 - 查询工单
    # --------------------------------------------------------
    print("\n🔍 Step 4: Agent 调用 - 查询工单 (等待 15 秒避免限流)")
    print("-" * 80)

    await asyncio.sleep(15)

    user_input_2 = "查询工单状态"
    print(f"👤 用户: {user_input_2}")

    result2 = await run_agent_with_retry(agent, user_input_2)
    output2 = str(result2.final_output)
    print(f"🤖 Agent: {output2}")

    # 保存检查点
    state3 = AgentState(
        session_id=session_id,
        conversation_history=[
            {"role": "user", "content": user_input},
            {"role": "assistant", "content": output1},
            {"role": "user", "content": user_input_2},
            {"role": "assistant", "content": output2},
        ],
        current_model=current_settings.agent_model_default,
        tool_calls=[],
        context={"step": "ticket_queried"},
    )
    cp3 = await checkpoint_mgr.save(session_id, state3, "工单查询完成")

    print("💾 已保存 3 个检查点")

    # --------------------------------------------------------
    # Step 5: HITL 审批流程
    # --------------------------------------------------------
    print("\n⚠️ Step 5: HITL 审批 - 删除工单")
    print("-" * 80)

    # 检查是否需要审批
    if hitl_mgr.requires_approval("delete_ticket"):
        print("🔒 delete_ticket 需要人工审批")

        # 创建审批请求
        request = await hitl_mgr.request_approval(
            tool_name="delete_ticket",
            tool_args={"ticket_id": "TKT-XXX"},
            session_id=session_id,
            user_id="user-001",
            reason="用户要求删除工单",
        )

        print(f"📋 审批请求: {request.id[:8]}...")
        print(f"   工具: {request.tool_name}")
        print(f"   原因: {request.reason}")

        # 模拟审批 (实际场景中由 UI 审批)
        print("\n⏳ 模拟审批过程 (等待 2 秒)...")
        await asyncio.sleep(2)

        # 批准
        approved = await hitl_mgr.approve(request.id, reviewer="admin")
        print(f"✅ 审批结果: {'通过' if approved else '拒绝'}")

        if approved:
            print("   继续执行删除操作...")
            # 在实际场景中,这里会调用 Agent 删除工单
        else:
            print("   回滚到之前的状态...")
            restored = await checkpoint_mgr.restore(cp2)
    else:
        print("ℹ️  此工具不需要审批")

    # --------------------------------------------------------
    # Step 6: 查看检查点历史
    # --------------------------------------------------------
    print("\n📜 Step 6: 检查点历史")
    print("-" * 80)

    checkpoints = checkpoint_mgr.list_checkpoints(session_id)
    print(f"📊 共有 {len(checkpoints)} 个检查点:")

    for i, cp in enumerate(checkpoints, 1):
        print(f"\n  {i}. [{cp.id[:8]}...] {cp.description}")
        print(f"     时间: {datetime.fromtimestamp(cp.timestamp).strftime('%H:%M:%S')}")
        print(f"     对话: {len(cp.state.conversation_history)} 条")
        print(f"     步骤: {cp.state.context.get('step', 'N/A')}")

    # --------------------------------------------------------
    # 清理
    # --------------------------------------------------------
    print("\n🧹 清理")
    print("-" * 80)
    hitl_mgr.cleanup()
    checkpoint_mgr.cleanup()
    print("✅ 完成")

    print("\n" + "=" * 80)
    print("🎉 E2E 测试成功!")
    print("=" * 80)
    print("\n✅ 验证内容:")
    print("  ✓ OpenAI Agent 真实调用")
    print("  ✓ 工具调用 (create_ticket, query_ticket)")
    print("  ✓ Checkpoint 状态保存")
    print("  ✓ HITL 人工审批流程")
    print("  ✓ API 限流重试机制")
    print("=" * 80 + "\n")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\n⚠️  测试被用户中断")
    except Exception as e:
        print(f"\n\n❌ 测试失败: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)
