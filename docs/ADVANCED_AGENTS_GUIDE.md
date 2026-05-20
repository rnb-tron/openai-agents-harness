# 高级 Agent 能力使用指南

本文档介绍如何使用 Agent Harness 的三个高级能力:
- **HITL (Human-in-the-Loop)** - 人工审批流程
- **Checkpoint** - 检查点状态管理
- **Handoff** - 多 Agent 协作路由

---

## 📋 目录

- [快速开始](#快速开始)
- [1. HITL 人工审批](#1-hitl-人工审批)
- [2. Checkpoint 检查点](#2-checkpoint-检查点)
- [3. Handoff Agent 协作](#3-handoff-agent-协作)
- [4. 组合使用](#4-组合使用)
- [完整 E2E 示例](#完整-e2e-示例)

---

## 快速开始

### 安装依赖

```bash
pip install openai-agents
```

### 导入模块

```python
from src.capabilities.advanced_agents import (
    ApprovalManager,
    CheckpointManager,
    HandoffManager,
    HITLConfig,
    CheckpointConfig,
    HandoffConfig,
    AgentState,
)
```

---

## 1. HITL 人工审批

### 使用场景

- 删除敏感数据前需要人工确认
- 发送重要通知前需要审核
- 执行高风险操作前的审批流程

### 基本使用

```python
import asyncio
from src.capabilities.advanced_agents import ApprovalManager, HITLConfig

async def main():
    # 1. 配置 HITL
    config = HITLConfig(
        enabled=True,  # 启用 HITL
        approval_timeout=300.0,  # 审批超时 5 分钟
        require_approval_tools=["delete_user", "send_notification"],  # 需要审批的工具
        auto_approve_tools=["query_user", "get_status"],  # 自动审批的工具
    )
    
    # 2. 初始化管理器
    manager = ApprovalManager(config)
    
    # 3. 检查工具是否需要审批
    if manager.requires_approval("delete_user"):
        print("此操作需要人工审批")
        
        # 4. 创建审批请求
        request = await manager.request_approval(
            tool_name="delete_user",
            tool_args={"user_id": "user-123"},
            session_id="session-001",
            user_id="admin-001",
            reason="删除违规用户",
        )
        
        # 5. 等待审批 (在实际应用中,这会在 UI 中显示给审批人)
        approved = await manager.wait_for_approval(request.id)
        
        if approved:
            # 审批通过,执行操作
            await delete_user("user-123")
        else:
            # 审批拒绝或超时
            print("操作被拒绝")
    
    # 6. 清理
    manager.cleanup()

asyncio.run(main())
```

### 批准/拒绝操作

```python
# 审批人批准请求
await manager.approve(request.id, reviewer="admin-manager", comment="确认删除")

# 审批人拒绝请求
await manager.reject(request.id, reviewer="admin-manager", reason="用户不应删除")
```

### 异步等待审批

```python
# 模拟审批人在 UI 中批准
async def approve_later():
    await asyncio.sleep(10)  # 10 秒后批准
    await manager.approve(request.id, reviewer="admin")

# 启动审批任务
asyncio.create_task(approve_later())

# 等待审批结果 (最多等待 30 秒)
result = await manager.wait_for_approval(request.id, timeout=30.0)
```

---

## 2. Checkpoint 检查点

### 使用场景

- 长时间运行的任务,需要保存进度
- 错误恢复和回滚
- 状态审计和追踪

### 基本使用

```python
import asyncio
from src.capabilities.advanced_agents import CheckpointManager, CheckpointConfig, AgentState

async def main():
    # 1. 配置 Checkpoint
    config = CheckpointConfig(
        enabled=True,
        max_checkpoints=10,  # 最多保留 10 个检查点
        save_on_tool_call=True,  # 工具调用后自动保存
    )
    
    # 2. 初始化管理器
    manager = CheckpointManager(config)
    session_id = "session-001"
    
    # 3. 保存初始状态
    state = AgentState(
        session_id=session_id,
        conversation_history=[
            {"role": "user", "content": "你好"},
        ],
        current_model="qwen3.5-plus",
        tool_calls=[],
        context={"user_id": "user-123"},
    )
    
    cp1_id = await manager.save(
        session_id=session_id,
        state=state,
        description="初始状态",
    )
    print(f"检查点已保存: {cp1_id}")
    
    # 4. 执行一些操作...
    # ...
    
    # 5. 保存新状态
    new_state = AgentState(
        session_id=session_id,
        conversation_history=[
            {"role": "user", "content": "你好"},
            {"role": "assistant", "content": "你好!有什么可以帮你的?"},
        ],
        current_model="qwen3.5-plus",
        tool_calls=[{"tool": "greet", "result": "success"}],
        context={"user_id": "user-123", "greeted": True},
    )
    
    cp2_id = await manager.save(session_id, new_state, "完成问候")
    
    # 6. 恢复到之前的检查点
    restored_state = await manager.restore(cp1_id)
    if restored_state:
        print(f"已恢复到检查点: {cp1_id}")
        print(f"对话历史: {len(restored_state.conversation_history)} 条")
    
    # 7. 列出所有检查点
    checkpoints = manager.list_checkpoints(session_id)
    for cp in checkpoints:
        print(f"- {cp.description} ({cp.timestamp})")
    
    # 8. 清理
    manager.cleanup()

asyncio.run(main())
```

### 获取最新检查点

```python
latest_cp = await manager.get_latest(session_id)
if latest_cp:
    print(f"最新检查点: {latest_cp.description}")
```

### 检查点数据结构

```python
@dataclass
class Checkpoint:
    id: str                  # 检查点 ID
    session_id: str          # 会话 ID
    timestamp: float         # 时间戳
    state: AgentState        # Agent 状态
    description: str         # 描述
    metadata: dict           # 额外元数据
```

---

## 3. Handoff Agent 协作

### 使用场景

- Triage Agent 智能路由到专业 Agent
- 多 Agent 协作处理复杂任务
- 动态 Agent 选择

### 基本使用

```python
import asyncio
from src.capabilities.advanced_agents import HandoffManager, HandoffConfig
from openai_agents import Agent
from openai_agents.models import OpenAIChatCompletionsModel

async def main():
    # 1. 配置 Handoff
    config = HandoffConfig(
        enabled=True,
        default_agent="general",
    )
    
    # 2. 初始化模型
    model = OpenAIChatCompletionsModel(
        model="qwen3.5-plus",
        api_key="your-api-key",
        base_url="https://your-api-url.com",
    )
    
    # 3. 初始化管理器
    manager = HandoffManager(config, model=model)
    
    # 4. 注册专业 Agent
    manager.register_agent(
        name="tech_support",
        display_name="技术支持 Agent",
        description="处理技术问题",
        instructions="你是一名技术支持专家,负责处理技术问题。",
    )
    
    manager.register_agent(
        name="billing",
        display_name="账单 Agent",
        description="处理账单和支付问题",
        instructions="你是一名账单专家。",
    )
    
    manager.register_agent(
        name="general",
        display_name="通用 Agent",
        description="处理一般性问题",
        instructions="你是一名通用客服。",
    )
    
    # 5. 创建 Agent 实例
    tech_agent = manager.create_agent(
        name="tech_support",
        instructions="处理技术问题",
        tools=[query_knowledge_base],
    )
    
    billing_agent = manager.create_agent(
        name="billing",
        instructions="处理账单问题",
        tools=[query_billing],
    )
    
    # 6. 创建 Triage Agent (带 Handoff 能力)
    triage_agent = manager.create_triage_agent(
        name="triage",
        instructions="你是一个客服路由器,根据用户问题路由到合适的专业 Agent。",
        handoff_agents=["tech_support", "billing", "general"],
    )
    
    # 7. 检查 Agent 可用性
    if manager.is_agent_available("tech_support"):
        print("技术支持 Agent 可用")
    
    # 8. 获取所有可用 Agent
    available = manager.get_available_agents()
    print(f"可用 Agent: {available}")
    
    # 9. 清理
    manager.cleanup()

asyncio.run(main())
```

### Handoff 工作原理

1. Triage Agent 接收用户输入
2. 根据意图判断需要路由到哪个专业 Agent
3. 调用 OpenAI Agents SDK 的 Handoff 机制
4. 专业 Agent 处理问题并返回结果

---

## 4. 组合使用

### 完整业务流程示例

```python
import asyncio
from src.capabilities.advanced_agents import (
    ApprovalManager,
    CheckpointManager,
    HandoffManager,
    HITLConfig,
    CheckpointConfig,
    HandoffConfig,
    AgentState,
)

async def customer_service_workflow():
    """客服工单处理完整流程"""
    
    # 初始化所有管理器
    hitl_mgr = ApprovalManager(HITLConfig(
        enabled=True,
        require_approval_tools=["delete_ticket", "send_notification"],
    ))
    
    checkpoint_mgr = CheckpointManager(CheckpointConfig(
        enabled=True,
        max_checkpoints=10,
    ))
    
    handoff_mgr = HandoffManager(HandoffConfig(enabled=True))
    
    session_id = "session-12345"
    user_id = "user-001"
    
    # Step 1: 用户提交工单
    print("Step 1: 提交工单")
    initial_state = AgentState(
        session_id=session_id,
        conversation_history=[{"role": "user", "content": "我要提交工单"}],
        current_model="qwen3.5-plus",
        tool_calls=[],
        context={"user_id": user_id},
    )
    cp1 = await checkpoint_mgr.save(session_id, initial_state, "工单提交前")
    
    # Step 2: Triage Agent 路由到技术支持
    print("Step 2: 路由到技术支持 Agent")
    handoff_mgr.register_agent("tech_support", "技术支持", "处理技术问题")
    
    # Step 3: 查询工单状态
    print("Step 3: 查询工单状态")
    state_after_query = AgentState(
        session_id=session_id,
        conversation_history=[
            {"role": "user", "content": "我要提交工单"},
            {"role": "assistant", "content": "工单已创建"},
        ],
        current_model="qwen3.5-plus",
        tool_calls=[{"tool": "query_ticket", "result": {"status": "open"}}],
        context={"user_id": user_id, "ticket_id": "TKT-1234"},
    )
    cp2 = await checkpoint_mgr.save(session_id, state_after_query, "查询后")
    
    # Step 4: 尝试删除工单 (需要审批)
    print("Step 4: 请求删除工单审批")
    request = await hitl_mgr.request_approval(
        tool_name="delete_ticket",
        tool_args={"ticket_id": "TKT-1234"},
        session_id=session_id,
        user_id=user_id,
        reason="用户要求删除",
    )
    
    # 等待审批
    approved = await hitl_mgr.wait_for_approval(request.id, timeout=30.0)
    
    if approved:
        print("审批通过,删除工单")
        # await delete_ticket("TKT-1234")
    else:
        print("审批拒绝,回滚状态")
        restored = await checkpoint_mgr.restore(cp1)
        if restored:
            print(f"已恢复到初始状态")
    
    # 清理
    hitl_mgr.cleanup()
    checkpoint_mgr.cleanup()
    handoff_mgr.cleanup()

asyncio.run(customer_service_workflow())
```

---

## 完整 E2E 示例

查看完整的端到端测试文件:
- `tests/test_advanced_agents_e2e.py` - 客服工单处理完整工作流

运行测试:
```bash
python tests/test_advanced_agents_e2e.py
```

运行示例:
```bash
python examples/advanced_agents_example.py
```

---

## 📚 更多资源

- [架构设计文档](ARCHITECTURE_DESIGN.md)
- [模型弹性指南](MODEL_RESILIENCE_GUIDE.md)
- [可观测性指南](OBSERVABILITY_GUIDE.md)

---

**提示**: 所有能力都是可插拔的,你可以根据需要启用/禁用特定功能,而不会影响其他模块。
