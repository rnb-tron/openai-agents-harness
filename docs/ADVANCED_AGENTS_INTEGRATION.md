# 如何将高级能力集成到真实 Agent 调用

本文档说明如何将 HITL、Checkpoint、Handoff 三个高级能力与现有的 `AgentOrchestrator` 集成。

---

## 📋 现有的 AgentOrchestrator 架构

当前的 `AgentOrchestrator` 已经包含了:
- ✅ Model Router (模型路由)
- ✅ Memory Store (记忆存储)
- ✅ Tool Registry (工具注册)
- ✅ OpenAI Agent 调用

**文件位置**: `src/application/orchestration/agent_runtime.py`

---

## 🔧 集成方案

### 方案 1: 在 AgentOrchestrator 中添加高级能力

修改 `AgentOrchestrator` 类,添加三个管理器作为可选依赖:

```python
# src/application/orchestration/agent_runtime.py

from src.capabilities.advanced_agents import (
    ApprovalManager,
    CheckpointManager,
    HandoffManager,
    HITLConfig,
    CheckpointConfig,
    HandoffConfig,
    AgentState,
)

class AgentOrchestrator:
    def __init__(
        self,
        tool_registry: ToolRegistry,
        memory_store: MemoryStore,
        model_router: ModelRouter,
        memory_manager: MemoryManager | None = None,
        # 新增: 高级能力管理器 (可选)
        hitl_config: HITLConfig | None = None,
        checkpoint_config: CheckpointConfig | None = None,
        handoff_config: HandoffConfig | None = None,
    ):
        self.tool_registry = tool_registry
        self.memory_store = memory_store
        self.model_router = model_router
        self.memory_manager = memory_manager
        
        # 新增: 初始化高级能力管理器
        self.hitl_mgr = ApprovalManager(hitl_config) if hitl_config else None
        self.checkpoint_mgr = CheckpointManager(checkpoint_config) if checkpoint_config else None
        self.handoff_mgr = HandoffManager(handoff_config) if handoff_config else None
    
    async def run(self, session: AgentSession, user_input: str) -> dict[str, Any]:
        # 1. 保存检查点 (如果启用)
        if self.checkpoint_mgr:
            state = AgentState(
                session_id=session.session_id,
                conversation_history=[],
                current_model=selected_model,
                tool_calls=[],
                context={"user_id": session.user_id},
            )
            await self.checkpoint_mgr.save(session.session_id, state, "Agent 调用前")
        
        # 2. 检查工具是否需要审批 (如果启用 HITL)
        if self.hitl_mgr and self.hitl_mgr.requires_approval(tool_name):
            request = await self.hitl_mgr.request_approval(
                tool_name=tool_name,
                tool_args=tool_args,
                session_id=session.session_id,
                user_id=session.user_id,
            )
            approved = await self.hitl_mgr.wait_for_approval(request.id)
            if not approved:
                raise PermissionError("操作未获批准")
        
        # 3. 执行 Agent 调用 (现有逻辑)
        agent = Agent(...)
        run_result = await Runner.run(starting_agent=agent, input=enriched_input)
        
        # 4. 保存调用后的检查点
        if self.checkpoint_mgr:
            state_after = AgentState(...)
            await self.checkpoint_mgr.save(session.session_id, state_after, "Agent 调用后")
        
        return {...}
```

---

### 方案 2: 使用装饰器模式 (推荐)

创建一个装饰器,在不修改原有代码的情况下添加高级能力:

```python
# src/capabilities/advanced_agents/decorators.py

from functools import wraps
from typing import Any

def with_advanced_capabilities(
    hitl_mgr: ApprovalManager | None = None,
    checkpoint_mgr: CheckpointManager | None = None,
):
    """高级能力装饰器"""
    def decorator(func):
        @wraps(func)
        async def wrapper(session: AgentSession, user_input: str, *args, **kwargs):
            # 1. 保存检查点
            if checkpoint_mgr:
                state = AgentState(...)
                await checkpoint_mgr.save(session.session_id, state, "调用前")
            
            try:
                # 2. 执行原始函数
                result = await func(session, user_input, *args, **kwargs)
                
                # 3. 保存成功检查点
                if checkpoint_mgr:
                    await checkpoint_mgr.save(session.session_id, state, "调用成功")
                
                return result
            
            except Exception as e:
                # 4. 发生错误时回滚
                if checkpoint_mgr:
                    restored = await checkpoint_mgr.restore(checkpoint_id)
                raise
        
        return wrapper
    return decorator
```

使用方式:

```python
# 在初始化 AgentOrchestrator 时添加装饰器
orchestrator = AgentOrchestrator(...)

# 应用高级能力
if hitl_config or checkpoint_config:
    orchestrator.run = with_advanced_capabilities(
        hitl_mgr=hitl_mgr,
        checkpoint_mgr=checkpoint_mgr,
    )(orchestrator.run)
```

---

## 📝 E2E 测试示例 (真实 Agent 调用)

以下是在真实场景中集成所有能力的完整示例:

```python
import asyncio
from agents import Agent, AsyncOpenAI, OpenAIChatCompletionsModel, Runner, function_tool
from src.capabilities.advanced_agents import (
    ApprovalManager,
    CheckpointManager,
    HITLConfig,
    CheckpointConfig,
    AgentState,
)
from src.core.config import current_settings

# 1. 定义工具
@function_tool
def create_ticket(title: str, description: str) -> str:
    return f"工单已创建: {title}"

@function_tool
def delete_ticket(ticket_id: str) -> str:
    return f"工单 {ticket_id} 已删除"

# 2. 配置高级能力
hitl_config = HITLConfig(
    enabled=True,
    require_approval_tools=["delete_ticket"],
)
checkpoint_config = CheckpointConfig(enabled=True)

hitl_mgr = ApprovalManager(hitl_config)
checkpoint_mgr = CheckpointManager(checkpoint_config)

# 3. 创建 Agent
client = AsyncOpenAI(api_key=current_settings.openai_api_key)
agent = Agent(
    name="客服 Agent",
    instructions="你是客服助手",
    model=OpenAIChatCompletionsModel(
        model=current_settings.agent_model_default,
        openai_client=client,
    ),
    tools=[create_ticket, delete_ticket],
)

# 4. 执行工作流
async def main():
    session_id = "session-001"
    
    # 保存检查点
    state = AgentState(session_id, [], current_settings.agent_model_default, [], {})
    cp_id = await checkpoint_mgr.save(session_id, state, "开始")
    
    # 用户输入
    user_input = "请帮我创建一个工单"
    
    # 调用 Agent
    result = await Runner.run(starting_agent=agent, input=user_input)
    print(f"Agent 输出: {result.final_output}")
    
    # 检查是否需要审批
    if hitl_mgr.requires_approval("delete_ticket"):
        request = await hitl_mgr.request_approval(
            tool_name="delete_ticket",
            tool_args={"ticket_id": "TKT-123"},
            session_id=session_id,
            user_id="user-001",
        )
        approved = await hitl_mgr.wait_for_approval(request.id)
        
        if approved:
            # 继续执行
            result2 = await Runner.run(starting_agent=agent, input="删除工单")
        else:
            # 回滚
            await checkpoint_mgr.restore(cp_id)

asyncio.run(main())
```

---

## ✅ 集成检查清单

- [ ] 在 `AgentOrchestrator.__init__` 中添加高级能力管理器参数
- [ ] 在 `run()` 方法开始处保存检查点
- [ ] 在工具调用前检查是否需要审批
- [ ] 在工具调用后保存检查点
- [ ] 在错误发生时回滚到检查点
- [ ] 在配置文件中添加高级能力配置项
- [ ] 编写集成测试验证功能

---

## 🔗 相关文件

- [AgentOrchestrator 源码](../src/application/orchestration/agent_runtime.py)
- [HITL 管理器](../src/capabilities/advanced_agents/hitl.py)
- [Checkpoint 管理器](../src/capabilities/advanced_agents/checkpoint.py)
- [Handoff 管理器](../src/capabilities/advanced_agents/handoff.py)
- [E2E 测试](../tests/test_advanced_agents_e2e.py)
