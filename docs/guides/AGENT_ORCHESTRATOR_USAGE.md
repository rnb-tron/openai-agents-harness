# AgentOrchestrator 可插拔能力集成指南

本文档说明如何使用 `AgentOrchestrator` 的三种模式:简单模式、中等模式、完整模式。

> 状态：使用指南。装配能力与生成前组合校验以 [架构设计](../architecture/ARCHITECTURE_DESIGN.md) 为准。

---

## 📋 架构概述

`AgentOrchestrator` 现在支持**完全可插拔**的能力组合:

```
┌─────────────────────────────────────────────────┐
│           AgentOrchestrator                      │
├─────────────────────────────────────────────────┤
│                                                 │
│  基础能力 (必需):                                │
│  ✓ ToolRegistry      (工具注册)                  │
│  ✓ ModelRouter       (模型路由)                  │
│  ✓ MemoryStore       (短期记忆)                  │
│                                                 │
│  可选能力 1: MemoryManager (长期记忆)            │
│  ✓ 长期记忆存储                                  │
│  ✓ 向量检索                                      │
│                                                 │
│  可选能力 2: Advanced Agents (高级能力)          │
│  ✓ HITL       (人工审批)                         │
│  ✓ Checkpoint (状态检查点)                       │
│  ✓ Handoff    (多Agent协作)                      │
│                                                 │
└─────────────────────────────────────────────────┘
```

---

## 🎯 三种使用模式

### 模式 1: 简单模式 (基础能力)

**适用场景**: 简单的问答机器人,不需要高级功能

```python
from src.application.orchestration.agent_runtime import AgentOrchestrator, AgentSession
from src.capabilities.memory.store import MemoryStore
from src.capabilities.model_routing.router import ModelRouter
from src.capabilities.tools.registry import ToolRegistry

# 初始化基础能力
memory_store = MemoryStore()
tool_registry = ToolRegistry()
tool_registry.register_defaults()
model_router = ModelRouter()

# 创建 Orchestrator (仅使用基础能力)
orchestrator = AgentOrchestrator(
    tool_registry=tool_registry,
    memory_store=memory_store,
    model_router=model_router,
)

# 使用
session = AgentSession(session_id="session-001", user_id="user-001")
result = await orchestrator.run(session, "你好,请帮我查询一下数据")
```

**特点**:
- ✅ 轻量级,启动快
- ✅ 支持工具调用
- ✅ 支持短期记忆
- ✅ 支持模型路由
- ❌ 无长期记忆
- ❌ 无高级能力

---

### 模式 2: 中等模式 (基础 + 长期记忆)

**适用场景**: 需要记住用户历史和偏好的场景

```python
from src.application.orchestration.agent_runtime import AgentOrchestrator, AgentSession
from src.capabilities.memory.store import MemoryStore
from src.capabilities.memory.manager import MemoryManager
from src.capabilities.model_routing.router import ModelRouter
from src.capabilities.tools.registry import ToolRegistry
from src.core.config import current_settings

# 初始化基础能力
memory_store = MemoryStore()
tool_registry = ToolRegistry()
tool_registry.register_defaults()
model_router = ModelRouter()

# 初始化长期记忆管理器
memory_manager = MemoryManager(
    redis_enabled=current_settings.memory_enabled,
    es_enabled=current_settings.memory_long_term_enabled,
)

# 创建 Orchestrator (基础 + 长期记忆)
orchestrator = AgentOrchestrator(
    tool_registry=tool_registry,
    memory_store=memory_store,
    model_router=model_router,
    memory_manager=memory_manager,  # 添加长期记忆
)

# 使用
session = AgentSession(session_id="session-001", user_id="user-001")
result = await orchestrator.run(session, "我之前提到过的那个项目怎么样了?")
```

**特点**:
- ✅ 包含简单模式所有功能
- ✅ 支持长期记忆存储
- ✅ 支持向量检索
- ✅ 支持用户画像
- ❌ 无高级能力

---

### 模式 3: 完整模式 (基础 + 长期记忆 + 高级能力)

**适用场景**: 企业级应用,需要审批流程、状态管理、多Agent协作

```python
from src.application.orchestration.agent_runtime import AgentOrchestrator, AgentSession
from src.capabilities.memory.store import MemoryStore
from src.capabilities.memory.manager import MemoryManager
from src.capabilities.model_routing.router import ModelRouter
from src.capabilities.tools.registry import ToolRegistry
from src.capabilities.advanced_agents import (
    HITLConfig,
    CheckpointConfig,
    HandoffConfig,
)
from src.core.config import current_settings

# 初始化基础能力
memory_store = MemoryStore()
tool_registry = ToolRegistry()
tool_registry.register_defaults()
model_router = ModelRouter()

# 初始化长期记忆
memory_manager = MemoryManager(
    redis_enabled=current_settings.memory_enabled,
    es_enabled=current_settings.memory_long_term_enabled,
)

# 配置高级能力
hitl_config = HITLConfig(
    enabled=True,  # 启用人工审批
    approval_timeout=300.0,  # 审批超时 5 分钟
    require_approval_tools=["delete_data", "send_notification"],  # 需要审批的工具
    auto_approve_tools=["query_data", "get_status"],  # 自动审批的工具
)

checkpoint_config = CheckpointConfig(
    enabled=True,  # 启用检查点
    max_checkpoints=10,  # 最多保留 10 个检查点
    save_on_tool_call=True,  # 工具调用后自动保存
)

handoff_config = HandoffConfig(
    enabled=True,  # 启用 Handoff
    default_agent="general",  # 默认 Agent
)

# 创建 Orchestrator (完整模式)
orchestrator = AgentOrchestrator(
    tool_registry=tool_registry,
    memory_store=memory_store,
    model_router=model_router,
    memory_manager=memory_manager,
    hitl_config=hitl_config,           # 添加 HITL
    checkpoint_config=checkpoint_config,  # 添加 Checkpoint
    handoff_config=handoff_config,     # 添加 Handoff
)

# 使用
session = AgentSession(session_id="session-001", user_id="user-001")
result = await orchestrator.run(session, "请帮我删除这些数据")
```

**特点**:
- ✅ 包含中等模式所有功能
- ✅ 支持人工审批流程 (HITL)
- ✅ 支持状态检查点 (Checkpoint)
- ✅ 支持多Agent协作 (Handoff)
- ✅ 支持错误恢复和回滚

---

## 🔧 在 FastAPI 路由中配置

### 示例 1: 简单模式 (默认)

```python
# src/api/routers/chat.py

from src.application.orchestration.agent_runtime import AgentOrchestrator
from src.capabilities.memory.store import MemoryStore
from src.capabilities.model_routing.router import ModelRouter
from src.capabilities.tools.registry import ToolRegistry

_memory_store = MemoryStore()
_tool_registry = ToolRegistry()
_tool_registry.register_defaults()
_model_router = ModelRouter()

# 简单模式
_orchestrator = AgentOrchestrator(
    tool_registry=_tool_registry,
    memory_store=_memory_store,
    model_router=_model_router,
)
```

### 示例 2: 完整模式 (启用高级能力)

```python
# src/api/routers/chat.py

from src.application.orchestration.agent_runtime import AgentOrchestrator
from src.capabilities.memory.store import MemoryStore
from src.capabilities.model_routing.router import ModelRouter
from src.capabilities.tools.registry import ToolRegistry
from src.capabilities.advanced_agents import (
    HITLConfig,
    CheckpointConfig,
)

_memory_store = MemoryStore()
_tool_registry = ToolRegistry()
_tool_registry.register_defaults()
_model_router = ModelRouter()

# 配置高级能力
_hitl_config = HITLConfig(
    enabled=True,
    require_approval_tools=["delete_ticket"],
)

_checkpoint_config = CheckpointConfig(
    enabled=True,
    max_checkpoints=10,
)

# 完整模式
_orchestrator = AgentOrchestrator(
    tool_registry=_tool_registry,
    memory_store=_memory_store,
    model_router=_model_router,
    hitl_config=_hitl_config,
    checkpoint_config=_checkpoint_config,
)
```

---

## 📊 能力对比表

| 能力 | 简单模式 | 中等模式 | 完整模式 |
|------|---------|---------|---------|
| **ToolRegistry** | ✅ | ✅ | ✅ |
| **ModelRouter** | ✅ | ✅ | ✅ |
| **MemoryStore** | ✅ | ✅ | ✅ |
| **MemoryManager** | ❌ | ✅ | ✅ |
| **HITL** | ❌ | ❌ | ✅ |
| **Checkpoint** | ❌ | ❌ | ✅ |
| **Handoff** | ❌ | ❌ | ✅ |
| **启动速度** | ⚡ 快 | 🐢 中 | 🐌 慢 |
| **内存占用** | 💚 低 | 💛 中 | 🧡 高 |
| **适用场景** | 简单问答 | 个性化服务 | 企业级应用 |

---

## 🎓 最佳实践

### 1. 按需启用

```python
# ✅ 推荐: 根据环境变量决定是否启用高级能力
import os

if os.getenv("ENABLE_HITL", "false").lower() == "true":
    hitl_config = HITLConfig(enabled=True, ...)
else:
    hitl_config = None

orchestrator = AgentOrchestrator(
    ...,
    hitl_config=hitl_config,  # None 表示不启用
)
```

### 2. 配置分离

```python
# config/advanced_agents.py
from src.capabilities.advanced_agents import HITLConfig, CheckpointConfig

# 开发环境: 不启用高级能力
DEV_CONFIG = {
    "hitl": None,
    "checkpoint": None,
}

# 生产环境: 启用高级能力
PROD_CONFIG = {
    "hitl": HITLConfig(
        enabled=True,
        require_approval_tools=["delete", "update"],
    ),
    "checkpoint": CheckpointConfig(
        enabled=True,
        max_checkpoints=20,
    ),
}
```

### 3. 优雅降级

```python
# 高级能力失败不影响主流程
try:
    if self.hitl_mgr:
        request = await self.hitl_mgr.request_approval(...)
        approved = await self.hitl_mgr.wait_for_approval(request.id)
except Exception as e:
    # 记录错误,但不阻断流程
    logger.warning(f"HITL failed: {e}, continuing without approval")
```

---

## 🔗 相关文件

- [AgentOrchestrator 源码](../../src/application/orchestration/agent_runtime.py)
- [Chat 路由配置](../../src/api/routers/chat.py)
- [高级能力指南](./ADVANCED_AGENTS_GUIDE.md)
- [高级能力集成设计记录](../design-notes/ADVANCED_AGENTS_INTEGRATION.md)

---

## 💡 总结

`AgentOrchestrator` 的**可插拔设计**让你可以:

1. **简单场景**: 只使用基础能力,快速启动
2. **中等场景**: 添加长期记忆,提供个性化服务
3. **复杂场景**: 启用所有高级能力,构建企业级应用

所有能力都是**完全可选**的,你可以根据业务需求灵活组合! 🎉
