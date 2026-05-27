# 📊 Langfuse 可观测层技术方案

> 文档类型：设计记录。当前可观测能力使用方式请参考 [可观测性指南](../guides/OBSERVABILITY_GUIDE.md)。

## 📋 方案概述

基于 Langfuse + OpenTelemetry 实现 Agent 应用的全链路可观测性,包括:
- **Trace 追踪**: 完整的请求链路追踪
- **Span 埋点**: LLM 调用、工具执行、Agent 编排的详细埋点
- **指标监控**: Token 消耗、延迟、成本、错误率
- **Prompt 管理**: Langfuse Prompt Management 集成

## 🏗️ 技术架构

```
┌─────────────────────────────────────────────────┐
│            Agent 应用层                          │
│  src/application/orchestration/                  │
└──────────────────┬──────────────────────────────┘
                   │
┌──────────────────▼──────────────────────────────┐
│      OpenAI Agents SDK                           │
│  Agent / Runner / Tools / Handoffs              │
└──────────────────┬──────────────────────────────┘
                   │
┌──────────────────▼──────────────────────────────┐
│  OpenTelemetry 自动埋点                          │
│  OpenAIAgentsInstrumentor                       │
└──────────────────┬──────────────────────────────┘
                   │
┌──────────────────▼──────────────────────────────┐
│      OpenTelemetry SDK                           │
│  TracerProvider / SpanProcessor                 │
└──────────────────┬──────────────────────────────┘
                   │
        ┌──────────┴──────────┐
        ▼                     ▼
┌──────────────┐      ┌──────────────┐
│   Langfuse   │      │  自定义处理   │
│   Cloud/Self │      │  (日志/指标)  │
└──────────────┘      └──────────────┘
```

## 🎯 核心功能

### 1. 自动埋点 (Zero Code Changes)
- ✅ LLM 调用自动追踪 (输入/输出/Token/延迟)
- ✅ 工具执行自动追踪 (参数/返回值/异常)
- ✅ Agent 编排自动追踪 (Handoffs/工作流)
- ✅ 异常自动捕获和记录

### 2. 手动埋点 (Custom Tracing)
- ✅ 业务逻辑自定义 Trace
- ✅ 性能瓶颈分析
- ✅ 用户行为追踪
- ✅ 自定义指标上报

### 3. Prompt 管理
- ✅ Langfuse Prompt Management
- ✅ 版本控制
- ✅ A/B 测试
- ✅ Prompt 效果分析

### 4. 成本监控
- ✅ Token 消耗统计
- ✅ 成本计算
- ✅ 预算告警
- ✅ 使用量分析

## 📁 目录结构

```
src/capabilities/
└── observability/              # 可观测能力
    ├── __init__.py
    ├── config.py               # Langfuse 配置
    ├── tracer.py               # Trace 管理器
    ├── span_processor.py       # 自定义 Span 处理器
    ├── metrics.py              # 指标收集器
    ├── prompt_manager.py       # Prompt 管理器
    ├── decorators.py           # 装饰器 (手动埋点)
    └── middleware.py           # FastAPI 中间件
```

## 🔧 技术实现

### 1. 依赖包

```txt
langfuse>=2.50.0
openinference-instrumentation-openai-agents>=0.1.0
opentelemetry-api>=1.27.0
opentelemetry-sdk>=1.27.0
opentelemetry-exporter-otlp>=1.27.0
```

### 2. 初始化流程

```python
# 1. 安装依赖
pip install langfuse openinference-instrumentation-openai-agents

# 2. 配置环境变量
LANGFUSE_PUBLIC_KEY=pk-lf-xxx
LANGFUSE_SECRET_KEY=sk-lf-xxx
LANGFUSE_BASE_URL=http://agent-otel-test.ke.com

# 3. 应用启动时初始化
from src.capabilities.observability import init_observability

init_observability()
```

### 3. 使用示例

#### 自动埋点 (默认启用)

```python
from agents import Agent, Runner

# 所有操作自动被 Langfuse 追踪
agent = Agent(name="Assistant", instructions="You are helpful.")
result = await Runner.run(agent, "Hello")
```

#### 手动 Trace 分组

```python
from agents import trace

async def chat_flow():
    with trace("User Chat Session"):
        # 所有操作在同一个 Trace 下
        result1 = await Runner.run(agent1, "input1")
        result2 = await Runner.run(agent2, "input2")
```

#### 自定义埋点

```python
from src.capabilities.observability import observe

@observe(name="process_user_input")
async def process_user_input(user_input: str):
    # 业务逻辑自动追踪
    return result
```

## 📊 可观测数据

### Trace 包含的信息

| 字段 | 说明 | 示例 |
|------|------|------|
| trace_id | 追踪 ID | "abc123" |
| user_id | 用户 ID | "user_456" |
| session_id | 会话 ID | "session_789" |
| metadata | 自定义元数据 | {"version": "1.0"} |
| tags | 标签 | ["production", "chat"] |

### Span 包含的信息

| 字段 | 说明 | 示例 |
|------|------|------|
| name | Span 名称 | "LLM Call" |
| type | 类型 | "GENERATION" |
| input | 输入 | {"prompt": "..."} |
| output | 输出 | {"completion": "..."} |
| metadata | 元数据 | {"model": "gpt-4"} |
| start_time | 开始时间 | "2024-01-01T00:00:00Z" |
| end_time | 结束时间 | "2024-01-01T00:00:01Z" |
| status | 状态 | "OK" / "ERROR" |

### 指标统计

| 指标 | 说明 | 单位 |
|------|------|------|
| latency | 延迟 | ms |
| tokens | Token 数量 | count |
| cost | 成本 | USD |
| error_rate | 错误率 | % |
| throughput | 吞吐量 | req/s |

## 🚀 部署方案

### 方案 1: Langfuse Cloud (推荐)

```bash
# 注册账号
http://agent-otel-test.ke.com

# 获取 API Key
LANGFUSE_PUBLIC_KEY=pk-lf-xxx
LANGFUSE_SECRET_KEY=sk-lf-xxx
LANGFUSE_BASE_URL=http://agent-otel-test.ke.com
```

**优势**:
- ✅ 零运维成本
- ✅ 自动备份
- ✅ 全球 CDN
- ✅ 免费额度充足

### 方案 2: Self-Hosted

```bash
# Docker Compose 部署
docker-compose up -d

# 配置
LANGFUSE_BASE_URL=http://localhost:3000
```

**优势**:
- ✅ 数据完全可控
- ✅ 无数据量限制
- ✅ 可定制

## 📈 监控面板

### Langfuse 提供的面板

1. **Traces**: 完整的请求链路追踪
2. **Generations**: LLM 调用详情
3. **Spans**: 工具执行和函数调用
4. **Users**: 用户行为分析
5. **Sessions**: 会话分析
6. **Prompts**: Prompt 管理
7. **Datasets**: 数据集管理
8. **Playground**: 测试环境

### 自定义面板

```python
# 自定义指标
from src.capabilities.observability import MetricsCollector

metrics = MetricsCollector()
metrics.increment("chat.requests")
metrics.histogram("chat.latency", duration_ms)
```

## 🔐 安全与隐私

### 数据脱敏

```python
# 自动脱敏配置
LANGFUSE_MASK_PII = true

# 自定义脱敏
from src.capabilities.observability import sanitize_input

safe_input = sanitize_input(user_input, fields=["email", "phone"])
```

### 权限控制

- **Project 级别**: 项目隔离
- **API Key 级别**: 读写分离
- **Team 级别**: 团队协作
- **Role 级别**: 角色权限

## 💰 成本估算

### Langfuse Cloud 定价

| 计划 | 价格 | Trace 数量 | 功能 |
|------|------|-----------|------|
| Free | $0 | 10K/月 | 基础功能 |
| Pro | $50 | 100K/月 | 全部功能 |
| Enterprise | 自定义 | 无限 | 企业支持 |

### 优化建议

1. **采样策略**: 生产环境采样 10-50%
2. **批量上报**: 减少 API 调用
3. **本地缓存**: 减少网络传输
4. **异步上报**: 不阻塞主流程

## 🎯 最佳实践

### 1. Trace 命名规范

```python
# 格式: {模块}.{操作}.{标识}
trace("chat.agent.run")
trace("memory.retrieve.long_term")
trace("tool.execute.web_search")
```

### 2. 元数据标准化

```python
metadata = {
    "user_id": "user_123",
    "session_id": "session_456",
    "request_id": "req_789",
    "environment": "production",
    "version": "1.0.0",
}
```

### 3. 错误处理

```python
try:
    result = await Runner.run(agent, input)
except Exception as e:
    # 自动记录错误
    logger.error(f"Agent execution failed: {e}")
    raise
```

### 4. 性能优化

```python
# 异步上报,不阻塞主流程
LANGFUSE_ASYNC = true

# 批量大小
LANGFUSE_BATCH_SIZE = 100

# 刷新间隔 (秒)
LANGFUSE_FLUSH_INTERVAL = 5
```

## 📝 下一步

1. ✅ 创建 `observability/` 模块
2. ✅ 实现初始化和配置
3. ✅ 集成 OpenAI Agents SDK
4. ✅ 添加自定义装饰器
5. ✅ 实现 FastAPI 中间件
6. ✅ 添加配置和文档
7. ⏳ 添加测试用例
8. ⏳ 添加监控面板

---

*设计时间: 2026-05-19*
*版本: v1.0*
