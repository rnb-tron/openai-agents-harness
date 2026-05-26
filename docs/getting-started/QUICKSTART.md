# Agent Harness 快速入门指南

欢迎使用 **Agent Harness** - 一个基于 OpenAI Agents SDK 的可插拔 Agent 工程脚手架!

> 状态：入门指南。高级能力的推荐主路径以 [架构设计](../architecture/ARCHITECTURE_DESIGN.md) 中的 SDK 原生中断恢复和 Handoff 说明为准。

---

## 📋 目录

- [什么是 Agent Harness](#什么是-agent-harness)
- [快速开始](#快速开始)
  - [环境要求](#环境要求)
  - [安装依赖](#安装依赖)
  - [配置环境变量](#配置环境变量)
  - [启动服务](#启动服务)
- [使用模式](#使用模式)
  - [模式 1: 简单模式](#模式-1-简单模式)
  - [模式 2: 中等模式](#模式-2-中等模式)
  - [模式 3: 完整模式](#模式-3-完整模式)
- [API 使用](#api-使用)
- [高级能力](#高级能力)
  - [HITL 人工审批](#hitl-人工审批)
  - [Checkpoint 检查点](#checkpoint-检查点)
  - [Handoff 多Agent协作](#handoff-多agent协作)
- [配置指南](#配置指南)
- [常见问题](#常见问题)
- [更多文档](#更多文档)

---

## 什么是 Agent Harness

**Agent Harness** 是一个企业级的 Agent 工程脚手架,提供:

✅ **可插拔架构** - 按需启用能力,零侵入设计  
✅ **六层分层** - 清晰的架构设计,易于维护  
✅ **OpenAI Agents SDK** - 基于最新的 Agent 框架  
✅ **记忆系统** - 短期记忆 + 长期记忆  
✅ **模型路由** - 智能选择最优模型  
✅ **工具注册** - 灵活的工具管理  
✅ **可观测性** - 集成 Langfuse  
✅ **弹性设计** - 降级、重试、超时控制  

---

## 快速开始

### 环境要求

- Python 3.11+
- OpenAI API Key (或兼容的 API)
- (可选) Redis - 用于短期记忆缓存
- (可选) MySQL 或 PostgreSQL - 用于长期关系记忆
- (可选) Elasticsearch 或 PostgreSQL + pgvector - 用于向量检索

### 安装依赖

```bash
# 克隆项目
git clone https://github.com/rnb-tron/openai-agent-sdk.git
cd openai-agent-sdk

# 创建虚拟环境
python -m venv venv
source venv/bin/activate  # macOS/Linux
# 或
venv\Scripts\activate     # Windows

# 安装依赖
pip install -r requirements.txt
```

### 配置环境变量

```bash
# 复制配置模板
cp config/test.env.example config/test.env

# 编辑配置文件
vim config/test.env
```

**必需配置**:
```env
# OpenAI API 配置
OPENAI_API_KEY=your-api-key-here
OPENAI_BASE_URL=https://your-api-endpoint.com/v1
AGENT_MODEL_DEFAULT=qwen3.5-plus
```

**可选配置**:
```env
# 记忆系统
MEMORY_ENABLED=true
MEMORY_LONG_TERM_ENABLED=true
DATABASE_URL=postgresql+asyncpg://agent:password@localhost:5432/agent_harness
MEMORY_VECTOR_BACKEND=pgvector
MEMORY_EMBEDDING_PROVIDER=openai
MEMORY_EMBEDDING_MODEL=text-embedding-3-small

# 可观测性
LANGFUSE_ENABLED=true
LANGFUSE_HOST=https://your-langfuse-host.com
LANGFUSE_PUBLIC_KEY=pk-xxx
LANGFUSE_SECRET_KEY=sk-xxx
```

### 启动服务

```bash
# 启动 FastAPI 服务
uvicorn src.main:app --host 0.0.0.0 --port 8080 --reload

# 访问文档
open http://localhost:8080/docs
```

---

## 使用模式

Agent Harness 支持**三种使用模式**,根据业务需求选择:

### 模式 1: 简单模式

**适用场景**: 简单问答机器人,快速原型开发

```python
# main.py
from src.application.orchestration.agent_runtime import AgentOrchestrator, AgentSession
from src.capabilities.memory.store import MemoryStore
from src.capabilities.model_routing.router import ModelRouter
from src.capabilities.tools.registry import ToolRegistry

# 初始化基础组件
memory_store = MemoryStore()
tool_registry = ToolRegistry()
tool_registry.register_defaults()  # 注册默认工具
model_router = ModelRouter()

# 创建 Orchestrator (简单模式)
orchestrator = AgentOrchestrator(
    tool_registry=tool_registry,
    memory_store=memory_store,
    model_router=model_router,
)

# 使用
session = AgentSession(session_id="session-001")
result = await orchestrator.run(session, "你好,请帮我查询数据")
print(result["output"])
```

**特点**:
- ✅ 轻量级,启动快 (< 1秒)
- ✅ 内存占用低 (~50MB)
- ✅ 支持工具调用
- ✅ 支持短期记忆
- ❌ 无长期记忆
- ❌ 无高级能力

---

### 模式 2: 中等模式

**适用场景**: 需要记住用户历史和偏好的应用

```python
from src.capabilities.memory.manager import MemoryManager
from src.core.config import current_settings

# 初始化长期记忆管理器
memory_manager = MemoryManager(
    redis_enabled=current_settings.memory_enabled,
    es_enabled=current_settings.memory_long_term_enabled,
)

# 创建 Orchestrator (中等模式)
orchestrator = AgentOrchestrator(
    tool_registry=tool_registry,
    memory_store=memory_store,
    model_router=model_router,
    memory_manager=memory_manager,  # 添加长期记忆
)

# 使用 - Agent 会记住上下文
session = AgentSession(session_id="session-001", user_id="user-123")
result1 = await orchestrator.run(session, "我喜欢科幻小说")
result2 = await orchestrator.run(session, "推荐几本书")  # 会记住偏好
```

**特点**:
- ✅ 包含简单模式所有功能
- ✅ 支持长期记忆存储
- ✅ 支持向量检索
- ✅ 支持用户画像
- ⚠️ 需要 Redis (可选)
- ⚠️ 需要 Elasticsearch (可选)

---

### 模式 3: 完整模式

**适用场景**: 企业级应用,需要审批流程、状态管理

```python
from src.capabilities.advanced_agents import (
    HITLConfig,
    CheckpointConfig,
    HandoffConfig,
)

# 配置高级能力
hitl_config = HITLConfig(
    enabled=True,
    approval_timeout=300.0,  # 审批超时 5 分钟
    require_approval_tools=["delete_data", "send_notification"],
    auto_approve_tools=["query_data"],
)

checkpoint_config = CheckpointConfig(
    enabled=True,
    max_checkpoints=10,
    save_on_tool_call=True,
)

# 创建 Orchestrator (完整模式)
orchestrator = AgentOrchestrator(
    tool_registry=tool_registry,
    memory_store=memory_store,
    model_router=model_router,
    memory_manager=memory_manager,
    hitl_config=hitl_config,
    checkpoint_config=checkpoint_config,
)

# 使用 - 敏感操作会自动触发审批
session = AgentSession(session_id="session-001", user_id="user-123")
result = await orchestrator.run(session, "删除这些数据")  # 需要审批
```

**特点**:
- ✅ 包含中等模式所有功能
- ✅ 支持人工审批 (HITL)
- ✅ 支持状态检查点 (Checkpoint)
- ✅ 支持多Agent协作 (Handoff)
- ✅ 支持错误恢复
- ⚠️ 启动稍慢 (~2秒)

---

## API 使用

### 1. 发送消息

```bash
curl -X POST http://localhost:8080/chat \
  -H "Content-Type: application/json" \
  -d '{
    "message": "你好,请帮我查询订单状态",
    "session_id": "session-001",
    "user_id": "user-123"
  }'
```

**响应**:
```json
{
  "code": 200,
  "data": {
    "session_id": "session-001",
    "input": "你好,请帮我查询订单状态",
    "output": "好的,我来帮你查询...",
    "model": "qwen3.5-plus",
    "tool_calls": [
      {
        "tool": "query_order",
        "args": {"order_id": "ORD-123"}
      }
    ],
    "memory_size": 2
  }
}
```

### 2. 健康检查

```bash
curl http://localhost:8080/health
```

---

## 高级能力

### HITL 人工审批

**场景**: 删除数据、发送通知等敏感操作需要人工确认

```python
# 配置需要审批的工具
hitl_config = HITLConfig(
    enabled=True,
    require_approval_tools=["delete_ticket", "send_email"],
)

# 在 AgentOrchestrator 中自动生效
# 当 Agent 调用需要审批的工具时,会自动创建审批请求
# 实际应用中,这里会通过 UI 或消息队列等待人工审批
```

**工作流程**:
```
用户请求 → Agent 调用工具 → 检查是否需要审批
  ↓
需要审批 → 创建审批请求 → 等待人工审批
  ↓
审批通过 → 继续执行
审批拒绝 → 回滚状态
```

---

### Checkpoint 检查点

**场景**: 长时间任务、错误恢复、状态审计

```python
# 启用 Checkpoint
checkpoint_config = CheckpointConfig(
    enabled=True,
    max_checkpoints=10,
    save_on_tool_call=True,
)

# 自动保存检查点
# 每次 Agent 调用前后都会保存状态
# 发生错误时可以恢复到之前的状态
```

**使用示例**:
```python
# 查看检查点历史
checkpoints = checkpoint_mgr.list_checkpoints(session_id)
for cp in checkpoints:
    print(f"{cp.description} - {cp.timestamp}")

# 恢复到指定检查点
restored_state = await checkpoint_mgr.restore(checkpoint_id)
```

---

### Handoff 多Agent协作

**场景**: Triage Agent 智能路由到专业 Agent

```python
# 配置 Handoff
handoff_config = HandoffConfig(
    enabled=True,
    default_agent="general",
)

# 注册专业 Agent
handoff_mgr = HandoffManager(handoff_config)
handoff_mgr.register_agent("tech_support", "技术支持", "处理技术问题")
handoff_mgr.register_agent("billing", "账单专家", "处理账单问题")

# 创建 Triage Agent
triage_agent = handoff_mgr.create_triage_agent(
    name="triage",
    instructions="根据用户问题路由到合适的 Agent",
    handoff_agents=["tech_support", "billing"],
)
```

---

## 配置指南

### 开发环境配置

```env
# config/dev.env
APP_PROFILE=development
DEBUG=true
LOG_LEVEL=DEBUG

# OpenAI API
OPENAI_API_KEY=your-dev-key
OPENAI_BASE_URL=https://dev-api.com/v1
AGENT_MODEL_DEFAULT=qwen3.5-plus

# 开发环境不启用高级能力
MEMORY_ENABLED=false
LANGFUSE_ENABLED=false
```

### 生产环境配置

```env
# config/prod.env
APP_PROFILE=production
DEBUG=false
LOG_LEVEL=INFO

# OpenAI API
OPENAI_API_KEY=your-prod-key
OPENAI_BASE_URL=https://prod-api.com/v1
AGENT_MODEL_DEFAULT=qwen3.5-plus

# 生产环境启用所有能力
MEMORY_ENABLED=true
REDIS_URL=redis://prod-redis:6379/0
MEMORY_LONG_TERM_ENABLED=true
MEMORY_ES_HOSTS=http://prod-es:9200

LANGFUSE_ENABLED=true
LANGFUSE_HOST=https://prod-langfuse.com
LANGFUSE_PUBLIC_KEY=pk-xxx
LANGFUSE_SECRET_KEY=sk-xxx
```

### 启用高级能力

在 `src/api/routers/chat.py` 中:

```python
# 取消注释以下代码启用高级能力

from src.capabilities.advanced_agents import (
    HITLConfig,
    CheckpointConfig,
)

_hitl_config = HITLConfig(
    enabled=True,
    require_approval_tools=["delete_data"],
)

_checkpoint_config = CheckpointConfig(
    enabled=True,
    max_checkpoints=10,
)

_orchestrator = AgentOrchestrator(
    tool_registry=_tool_registry,
    memory_store=_memory_store,
    model_router=_model_router,
    hitl_config=_hitl_config,
    checkpoint_config=_checkpoint_config,
)
```

---

## 常见问题

### Q1: 如何添加自定义工具?

```python
from agents import function_tool
from src.capabilities.tools.registry import ToolRegistry

@function_tool
def my_custom_tool(param1: str, param2: int) -> str:
    """我的自定义工具"""
    return f"结果: {param1}, {param2}"

# 注册工具
tool_registry = ToolRegistry()
tool_registry.register(my_custom_tool)
```

### Q2: 如何切换模型?

```python
# 方式 1: 配置文件
AGENT_MODEL_DEFAULT=qwen3.5-plus

# 方式 2: 代码中指定
from src.capabilities.model_routing.router import ModelRouter

model_router = ModelRouter()
model_router.register_model("complex", "gpt-4")
model_router.register_model("simple", "qwen3.5-plus")
```

### Q3: 如何禁用某个能力?

```python
# 方式 1: 不传递配置 (推荐)
orchestrator = AgentOrchestrator(
    ...,
    hitl_config=None,  # 不启用 HITL
)

# 方式 2: 配置中设置 enabled=False
hitl_config = HITLConfig(enabled=False)
```

### Q4: API 限流怎么办?

```python
# 添加重试机制
import asyncio
from openai import RateLimitError

async def call_with_retry(func, max_retries=3):
    for attempt in range(max_retries):
        try:
            return await func()
        except RateLimitError:
            wait_time = 15 * (attempt + 1)
            await asyncio.sleep(wait_time)
    raise Exception("重试次数已用完")
```

### Q5: 如何查看日志?

```bash
# 查看控制台日志
# 启动时配置 LOG_LEVEL=DEBUG

# 查看 Langfuse Dashboard
open https://your-langfuse-host.com/traces
```

---

## 更多文档

- 📖 [架构设计](../architecture/ARCHITECTURE_DESIGN.md) - Harness 架构与脚手架适配
- 📖 [高级能力指南](../guides/ADVANCED_AGENTS_GUIDE.md) - HITL/Checkpoint/Handoff
- 📖 [Orchestrator 使用指南](../guides/AGENT_ORCHESTRATOR_USAGE.md) - 运行时接入
- 📖 [记忆系统](../guides/MEMORY_SYSTEM.md) - 短期/长期记忆
- 📖 [可观测性](../guides/OBSERVABILITY_GUIDE.md) - Langfuse 集成
- 📖 [模型弹性](../guides/MODEL_RESILIENCE_GUIDE.md) - 降级/重试/超时
- 📖 [高级能力集成设计记录](../design-notes/ADVANCED_AGENTS_INTEGRATION.md) - 历史设计背景

---

## 🎓 下一步

1. **阅读架构文档** - 了解六层架构设计
2. **运行测试** - 验证环境配置
   ```bash
   python tests/test_orchestrator_pluggable.py
   ```
3. **启动服务** - 体验 API
   ```bash
   uvicorn src.main:app --reload
   ```
4. **启用高级能力** - 根据业务需求配置
5. **部署到生产** - 参考配置指南

---

## 💡 支持

- GitHub Issues: https://github.com/rnb-tron/openai-agent-sdk/issues
- 邮箱: your-email@example.com

---

**祝你使用愉快!** 🚀
