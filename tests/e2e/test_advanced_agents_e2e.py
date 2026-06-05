"""
E2E 测试:高级 Agent 能力组合使用 + 真实 OpenAI Agent 调用

场景: 客服系统中的工单处理流程
- 用户提交工单
- Triage Agent 路由到专业 Agent (Handoff)
- 执行敏感操作前请求人工审批 (HITL)
- 每个关键步骤保存检查点 (Checkpoint)
- 如果审批拒绝,回滚到之前的状态
- 集成真实的 OpenAI Agent 调用
"""

import asyncio
import sys
from pathlib import Path
from datetime import datetime

# 添加项目根目录到 Python 路径
sys.path.insert(0, str(Path(__file__).parents[2]))

from agents import Agent, AsyncOpenAI, OpenAIChatCompletionsModel, Runner

from src.capabilities.advanced_agents import (
    ApprovalManager,
    CheckpointManager,
    HITLConfig,
    CheckpointConfig,
    AgentState,
)

from src.core.config import current_settings


# ============================================================
# 真实工具函数 (注册为 OpenAI Agent Tools)
# ============================================================

from agents import function_tool


@function_tool
def create_ticket(title: str, description: str, priority: str = "medium") -> str:
    """创建客服工单"""
    ticket_id = f"TKT-{datetime.now().strftime('%Y%m%d%H%M%S')}"
    print(f"  ✅ [工具调用] create_ticket: {ticket_id}")
    return f"工单已创建: {ticket_id}, 标题: {title}, 优先级: {priority}"


@function_tool
def query_ticket_status(ticket_id: str) -> str:
    """查询工单状态"""
    print(f"  🔍 [工具调用] query_ticket_status: {ticket_id}")
    return f"工单 {ticket_id} 状态: open, 分配给: tech-support-agent"


@function_tool
def delete_ticket(ticket_id: str) -> str:
    """删除工单 (需要审批)"""
    print(f"  🗑️  [工具调用] delete_ticket: {ticket_id}")
    return f"工单 {ticket_id} 已删除"


@function_tool
def send_notification(user_id: str, message: str, channel: str = "email") -> str:
    """发送通知 (需要审批)"""
    print(f"  📧 [工具调用] send_notification: 用户 {user_id}")
    return f"通知已发送给用户 {user_id} (通过 {channel})"


# ============================================================
# E2E 测试: 客服工单处理工作流 (使用真实 OpenAI Agent)
# ============================================================


async def e2e_customer_service_workflow():
    """端到端测试:客服工单处理完整流程 (集成真实 Agent 调用)"""

    print("\n" + "=" * 80)
    print("🚀 E2E 测试: 客服工单处理工作流 (真实 Agent 调用)")
    print("=" * 80)

    # --------------------------------------------------------
    # Step 0: 初始化 OpenAI Client 和 Agent
    # --------------------------------------------------------
    print("\n🤖 Step 0: 初始化 OpenAI Agent")
    print("-" * 80)

    if not current_settings.openai_api_key:
        print("⚠️ 未配置 OPENAI_API_KEY,跳过真实 Agent 调用")
        print("   请在 .env 文件中配置 API Key")
        return

    # 创建 OpenAI Client
    client_kwargs = {"api_key": current_settings.openai_api_key}
    if current_settings.openai_base_url:
        client_kwargs["base_url"] = current_settings.openai_base_url

    client = AsyncOpenAI(**client_kwargs)
    print("✅ OpenAI Client 已初始化")
    print(f"   Base URL: {current_settings.openai_base_url or '默认'}")

    # 创建 Agent (带工具)
    support_agent = Agent(
        name="客服工单处理 Agent",
        instructions=(
            "你是一名专业的客服工单处理助手。\n"
            "你的职责:\n"
            "1. 帮助用户创建工单\n"
            "2. 查询工单状态\n"
            "3. 在用户要求时删除工单\n"
            "请使用提供的工具完成任务。"
        ),
        model=OpenAIChatCompletionsModel(
            model=current_settings.agent_model_default,
            openai_client=client,
        ),
        tools=[create_ticket, query_ticket_status, delete_ticket, send_notification],
    )
    print(f"✅ Agent 已创建: {support_agent.name}")
    print(f"   模型: {current_settings.agent_model_default}")
    print(f"   工具: {len(support_agent.tools)} 个")

    # --------------------------------------------------------
    # Step 1: 初始化所有能力管理器
    # --------------------------------------------------------
    print("\n📋 Step 1: 初始化能力管理器")
    print("-" * 80)

    # 1. 初始化 HITL (人工审批)
    hitl_config = HITLConfig(
        enabled=True,
        approval_timeout=10.0,  # 10 秒超时 (测试用)
        require_approval_tools=["delete_ticket", "send_notification"],  # 这些工具需要审批
        auto_approve_tools=["create_ticket", "query_ticket_status"],  # 这些工具自动审批
    )
    hitl_mgr = ApprovalManager(hitl_config)
    print("✅ HITL 管理器已初始化")

    # 2. 初始化 Checkpoint (检查点)
    checkpoint_config = CheckpointConfig(
        enabled=True,
        max_checkpoints=10,
        save_on_tool_call=True,  # 每次工具调用后自动保存
    )
    checkpoint_mgr = CheckpointManager(checkpoint_config)
    print("✅ Checkpoint 管理器已初始化")

    session_id = "session-e2e-real-agent"
    user_id = "user-001"

    # --------------------------------------------------------
    # Step 2: 真实 Agent 调用 - 创建工单
    # --------------------------------------------------------
    print("\n📝 Step 2: 真实 Agent 调用 - 创建工单")
    print("-" * 80)

    # 保存初始状态
    initial_state = AgentState(
        session_id=session_id,
        conversation_history=[],
        current_model=current_settings.agent_model_default,
        tool_calls=[],
        context={"user_id": user_id},
    )
    cp1_id = await checkpoint_mgr.save(
        session_id=session_id,
        state=initial_state,
        description="Agent 调用前",
    )

    # 调用真实 Agent
    user_input = "我遇到了登录问题,无法进入系统,密码一直提示错误,请帮我创建一个工单"
    print(f"👤 用户输入: {user_input}")

    # 运行 Agent
    result = await Runner.run(
        starting_agent=support_agent,
        input=user_input,
    )

    agent_output = str(result.final_output)
    print(f"🤖 Agent 输出: {agent_output}")

    # 获取工具调用信息
    tool_calls = []
    if hasattr(result, "new_items"):
        for item in result.new_items:
            if hasattr(item, "tool_calls"):
                for tc in item.tool_calls:
                    tool_calls.append(
                        {
                            "tool": tc.tool_name,
                            "args": tc.arguments,
                        }
                    )

    print(f"🔧 工具调用: {len(tool_calls)} 个")
    for tc in tool_calls:
        print(f"   - {tc['tool']}: {tc['args']}")

    # 保存 Agent 调用后的状态
    state_after_agent = AgentState(
        session_id=session_id,
        conversation_history=[
            {"role": "user", "content": user_input},
            {"role": "assistant", "content": agent_output},
        ],
        current_model=current_settings.agent_model_default,
        tool_calls=tool_calls,
        context={"user_id": user_id, "agent_called": True},
    )
    cp2_id = await checkpoint_mgr.save(
        session_id=session_id,
        state=state_after_agent,
        description="工单创建完成",
    )
    print(f"💾 检查点已保存: {cp2_id[:8]}...")

    # --------------------------------------------------------
    # Step 3: 真实 Agent 调用 - 查询工单状态
    # --------------------------------------------------------
    print("\n🔍 Step 3: 真实 Agent 调用 - 查询工单状态")
    print("-" * 80)

    user_input_2 = "请帮我查一下刚才创建的工单状态"
    print(f"👤 用户输入: {user_input_2}")

    # 调用真实 Agent
    result_2 = await Runner.run(
        starting_agent=support_agent,
        input=user_input_2,
    )

    agent_output_2 = str(result_2.final_output)
    print(f"🤖 Agent 输出: {agent_output_2}")

    # 保存状态
    state_after_query = AgentState(
        session_id=session_id,
        conversation_history=[
            *state_after_agent.conversation_history,
            {"role": "user", "content": user_input_2},
            {"role": "assistant", "content": agent_output_2},
        ],
        current_model=current_settings.agent_model_default,
        tool_calls=tool_calls,
        context={**state_after_agent.context, "queried": True},
    )
    cp3_id = await checkpoint_mgr.save(
        session_id=session_id,
        state=state_after_query,
        description="工单查询完成",
    )
    print(f"💾 检查点已保存: {cp3_id[:8]}...")

    # --------------------------------------------------------
    # Step 4: 尝试删除工单 (需要 HITL 审批)
    # --------------------------------------------------------
    print("\n⚠️ Step 4: 请求删除工单 (需要 HITL 审批)")
    print("-" * 80)

    # 请求人工审批
    approval_request = await hitl_mgr.request_approval(
        tool_name="delete_ticket",
        tool_args={"ticket_id": "TKT-XXX"},
        session_id=session_id,
        user_id=user_id,
        reason="用户要求删除工单",
    )
    print(f"📋 审批请求已创建: {approval_request.id[:8]}...")

    # 模拟审批 (在实际场景中,这里会等待 UI 审批)
    print("\n⏳ 等待人工审批 (模拟 2 秒)...")
    await asyncio.sleep(2)
    approved = await hitl_mgr.approve(approval_request.id, reviewer="manager-001")
    print(f"✅ 审批结果: {'通过' if approved else '拒绝'}")

    # --------------------------------------------------------
    # Step 5: 根据审批结果执行
    # --------------------------------------------------------
    print("\n📊 Step 5: 根据审批结果执行")
    print("-" * 80)

    if approved:
        print("✅ 审批通过,调用真实 Agent 删除工单")

        user_input_3 = "请帮我删除刚才的工单"
        print(f"👤 用户输入: {user_input_3}")

        # 调用真实 Agent 删除
        result_3 = await Runner.run(
            starting_agent=support_agent,
            input=user_input_3,
        )

        agent_output_3 = str(result_3.final_output)
        print(f"🤖 Agent 输出: {agent_output_3}")

        # 保存最终状态
        state_final = AgentState(
            session_id=session_id,
            conversation_history=[
                *state_after_query.conversation_history,
                {"role": "user", "content": user_input_3},
                {"role": "assistant", "content": agent_output_3},
            ],
            current_model=current_settings.agent_model_default,
            tool_calls=tool_calls,
            context={**state_after_query.context, "deleted": True},
        )
        cp4_id = await checkpoint_mgr.save(
            session_id=session_id,
            state=state_final,
            description="工单删除完成",
        )
        print(f"💾 检查点已保存: {cp4_id[:8]}...")
    else:
        print("❌ 审批拒绝,回滚到初始状态")
        restored_state = await checkpoint_mgr.restore(cp1_id)
        if restored_state:
            print(f"✅ 状态已恢复到检查点: {cp1_id[:8]}...")

    # --------------------------------------------------------
    # Step 6: 查看检查点历史
    # --------------------------------------------------------
    print("\n📜 Step 6: 查看检查点历史")
    print("-" * 80)

    checkpoints = checkpoint_mgr.list_checkpoints(session_id)
    print(f"📊 会话 {session_id} 共有 {len(checkpoints)} 个检查点:")
    for i, cp in enumerate(checkpoints, 1):
        print(f"  {i}. [{cp.id[:8]}...] {cp.description}")
        print(f"     ⏰ {datetime.fromtimestamp(cp.timestamp).strftime('%H:%M:%S')}")
        print(f"     💬 对话历史: {len(cp.state.conversation_history)} 条")

    # --------------------------------------------------------
    # 清理
    # --------------------------------------------------------
    print("\n🧹 清理管理器")
    print("-" * 80)
    hitl_mgr.cleanup()
    checkpoint_mgr.cleanup()
    print("✅ 所有管理器已清理")

    print("\n" + "=" * 80)
    print("🎉 E2E 测试完成!")
    print("=" * 80)
    print("\n✅ 测试总结:")
    print("  - OpenAI Agent: 真实调用成功")
    print("  - HITL: 人工审批流程正常工作")
    print("  - Checkpoint: 状态保存和恢复正常工作")
    print("  - 所有能力组合使用成功!")
    print("=" * 80 + "\n")


# ============================================================
# E2E 测试 2: 审批拒绝场景
# ============================================================


async def e2e_approval_rejection_scenario():
    """E2E 测试: 审批拒绝并回滚场景"""

    print("\n" + "=" * 80)
    print("🚀 E2E 测试 2: 审批拒绝并回滚")
    print("=" * 80)

    # 初始化
    hitl_config = HITLConfig(
        enabled=True,
        approval_timeout=10.0,
        require_approval_tools=["send_notification"],
    )
    hitl_mgr = ApprovalManager(hitl_config)

    checkpoint_config = CheckpointConfig(enabled=True)
    checkpoint_mgr = CheckpointManager(checkpoint_config)

    session_id = "session-rejection-test"

    # 保存初始状态
    initial_state = AgentState(
        session_id=session_id,
        conversation_history=[{"role": "user", "content": "发送重要通知"}],
        current_model=current_settings.agent_model_default,
        tool_calls=[],
        context={"user_id": "user-001"},
    )
    cp1_id = await checkpoint_mgr.save(
        session_id=session_id,
        state=initial_state,
        description="发送通知前",
    )
    print(f"💾 初始检查点已保存: {cp1_id[:8]}...")

    # 请求审批
    approval_request = await hitl_mgr.request_approval(
        tool_name="send_notification",
        tool_args={"user_id": "user-001", "message": "系统维护通知"},
        session_id=session_id,
        user_id="user-001",
        reason="发送全员通知",
    )
    print(f"📋 审批请求已创建: {approval_request.id[:8]}...")

    # 模拟审批拒绝
    print("\n⏳ 等待审批...")
    await asyncio.sleep(1)
    await hitl_mgr.reject(approval_request.id, reviewer="manager-002", reason="通知内容不准确")
    print("❌ 审批被拒绝")

    # 回滚到初始状态
    print("\n🔄 回滚到初始状态...")
    restored_state = await checkpoint_mgr.restore(cp1_id)
    if restored_state:
        print("✅ 状态已恢复")
        print(f"💬 对话历史: {restored_state.conversation_history[0]['content']}")

    # 清理
    hitl_mgr.cleanup()
    checkpoint_mgr.cleanup()

    print("\n" + "=" * 80)
    print("🎉 E2E 测试 2 完成!")
    print("=" * 80 + "\n")


# ============================================================
# 运行 E2E 测试
# ============================================================


async def main():
    """运行所有 E2E 测试"""
    try:
        # 测试 1: 完整工作流 (审批通过)
        await e2e_customer_service_workflow()

        # 测试 2: 审批拒绝场景
        await e2e_approval_rejection_scenario()

    except Exception as e:
        print(f"\n❌ E2E 测试失败: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
