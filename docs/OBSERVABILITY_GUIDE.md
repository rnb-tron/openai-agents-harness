# 📊 Langfuse 可观测系统使用指南

## 📋 概述

Langfuse 可观测系统为你的 Agent 应用提供全链路追踪和监控能力,基于 OpenTelemetry 标准实现。

### 核心功能

- ✅ **自动埋点**: LLM 调用、工具执行、Agent 编排自动追踪
- ✅ **手动埋点**: 自定义函数和业务的追踪
- ✅ **请求追踪**: HTTP 请求级别的全链路追踪
- ✅ **错误追踪**: 异常自动捕获和记录
- ✅ **性能分析**: 延迟、Token、成本监控
- ✅ **Prompt 管理**: Langfuse Prompt Management 集成

## 🚀 快速开始

### 1. 注册 Langfuse

#### 方式 1: Langfuse Cloud (推荐)

1. 访问 https://cloud.langfuse.com
2. 注册账号 (免费额度: 10K traces/月)
3. 创建项目
4. 获取 API Key (Project Settings → API Keys)

#### 方式 2: Self-Hosted

```bash
# Docker Compose 部署
git clone https://github.com/langfuse/langfuse.git
cd langfuse
docker-compose up -d

# 访问 http://localhost:3000
```

### 2. 配置环境变量

编辑 `config/test.env`:

```bash
# 启用可观测系统
LANGFUSE_ENABLED=true

# Langfuse API Key (从项目设置中获取)
LANGFUSE_PUBLIC_KEY=pk-lf-xxxxxxxxxxxxx
LANGFUSE_SECRET_KEY=sk-lf-xxxxxxxxxxxxx

# Langfuse 服务地址
LANGFUSE_BASE_URL=https://cloud.langfuse.com

# 可选配置
LANGFUSE_TRACING_ENABLED=true        # 启用追踪
LANGFUSE_METRICS_ENABLED=true        # 启用指标
LANGFUSE_SAMPLING_RATE=1.0           # 采样率 (0.0-1.0)
LANGFUSE_MASK_PII=true               # 脱敏 PII 数据
```

### 3. 启动服务

```bash
# 启动应用
ENVTYPE=test python -m uvicorn src.main:app --host 0.0.0.0 --port 8080 --reload

# 可观测系统会自动初始化
```

## 📖 使用方式

### 方式 1: 自动埋点 (Zero Code Changes)

**无需任何代码改动!** 只要启用了 Langfuse,所有 OpenAI Agents SDK 的操作都会自动被追踪。

```python
from agents import Agent, Runner

# 创建 Agent
agent = Agent(
    name="Assistant",
    instructions="You are a helpful assistant.",
)

# 运行 Agent - 自动追踪
result = await Runner.run(agent, "Hello!")

# Langfuse 自动记录:
# - LLM 调用 (model, tokens, latency, cost)
# - 输入/输出
# - 时间戳
```

### 方式 2: Trace 分组

使用 `trace()` 上下文管理器将多个操作组织在同一个 Trace 下:

```python
from agents import Agent, Runner, trace

async def chat_flow():
    agent = Agent(name="Assistant", instructions="You are helpful.")
    
    # 所有操作在同一个 Trace 下
    with trace("User Chat Session"):
        # 第一次对话
        result1 = await Runner.run(agent, "Tell me a joke")
        
        # 第二次对话 (关联到同一个 Trace)
        result2 = await Runner.run(agent, "Explain the joke")
```

**Langfuse Dashboard 显示**:
```
Trace: User Chat Session
  ├─ Span: Runner.run (Tell me a joke)
  │   └─ LLM Call (gpt-4o)
  └─ Span: Runner.run (Explain the joke)
      └─ LLM Call (gpt-4o)
```

### 方式 3: 自定义埋点

使用 `@observe` 装饰器为自定义函数添加追踪:

```python
from src.capabilities.observability import observe

@observe(name="process_user_input", span_type="TOOL")
async def process_user_input(user_input: str) -> dict:
    """处理用户输入 - 自动追踪"""
    
    # 业务逻辑
    result = {
        "original": user_input,
        "processed": user_input.upper(),
    }
    
    return result

# 调用时自动记录:
# - 输入参数
# - 返回值
# - 执行时间
# - 异常 (如果有)
```

### 方式 4: 性能测量

只记录执行时间,不创建完整的 Span:

```python
from src.capabilities.observability import measure_time

@measure_time("database_query")
async def query_database():
    """数据库查询 - 只记录时间"""
    # 业务逻辑
    pass

# 控制台输出:
# database_query took 125.34ms
```

### 方式 5: 工具执行追踪

工具的执行会被自动追踪:

```python
from agents import Agent, Runner, function_tool

@function_tool
def get_weather(city: str) -> str:
    """天气查询工具"""
    return f"The weather in {city} is sunny"

agent = Agent(
    name="Weather Assistant",
    tools=[get_weather],
)

result = await Runner.run(agent, "What's the weather in Tokyo?")

# Langfuse 自动记录:
# - Tool: get_weather
# - Input: {"city": "Tokyo"}
# - Output: "The weather in Tokyo is sunny"
# - Duration: 50ms
```

### 方式 6: Multi-Agent Handoff 追踪

Agent 之间的 Handoff 会被自动追踪:

```python
from agents import Agent, Runner

spanish_agent = Agent(name="Spanish", instructions="Solo hablo español.")
english_agent = Agent(name="English", instructions="I only speak English.")

triage_agent = Agent(
    name="Triage",
    instructions="Route to the appropriate agent.",
    handoffs=[spanish_agent, english_agent],
)

result = await Runner.run(triage_agent, "Hola!")

# Langfuse 显示:
# - Triage Agent 决策过程
# - Handoff 到 Spanish Agent
# - Spanish Agent 的 LLM 调用
```

## 🎛️ 配置说明

### 完整配置项

```python
# config/test.env

# 基础配置
LANGFUSE_ENABLED=false                    # 是否启用可观测系统
LANGFUSE_PUBLIC_KEY=pk-lf-xxx            # Public Key
LANGFUSE_SECRET_KEY=sk-lf-xxx            # Secret Key
LANGFUSE_BASE_URL=https://cloud.langfuse.com  # 服务地址

# 功能开关
LANGFUSE_TRACING_ENABLED=true             # 启用追踪
LANGFUSE_METRICS_ENABLED=true             # 启用指标

# 性能优化
LANGFUSE_SAMPLING_RATE=1.0               # 采样率 (0.0-1.0)
                                         # 0.0 = 不采样, 1.0 = 全部采样

# 隐私保护
LANGFUSE_MASK_PII=true                   # 自动脱敏 PII 数据
```

### 生产环境建议

```bash
# 生产环境配置
LANGFUSE_ENABLED=true
LANGFUSE_SAMPLING_RATE=0.1              # 10% 采样 (降低成本)
LANGFUSE_MASK_PII=true                   # 必须脱敏
```

## 📊 Langfuse Dashboard

### 主要功能

1. **Traces**: 完整的请求链路追踪
   - 查看每个请求的完整执行流程
   - 分析 LLM 调用、工具执行、Agent 编排

2. **Generations**: LLM 调用详情
   - Model 使用情况
   - Token 消耗统计
   - 成本分析
   - 延迟分析

3. **Spans**: 工具和函数执行
   - 输入/输出
   - 执行时间
   - 错误信息

4. **Users**: 用户行为分析
   - 用户活跃度
   - 使用模式
   - 偏好分析

5. **Sessions**: 会话分析
   - 会话长度
   - 会话轮数
   - 会话质量

6. **Prompts**: Prompt 管理
   - 版本控制
   - A/B 测试
   - 效果分析

### 常用查询

```python
# 获取 Trace URL
from src.capabilities.observability import get_tracer_manager

tracer = get_tracer_manager()
url = tracer.get_trace_url(trace_id="xxx")
print(f"View trace: {url}")
```

## 🔧 高级用法

### 1. 关联 Request ID

```python
# HTTP 请求自动关联 Request ID
# Response Headers 中包含:
# - X-Request-ID: 请求 ID
# - X-Trace-ID: Trace ID
```

### 2. 自定义元数据

```python
from opentelemetry import trace

tracer = trace.get_tracer("custom")

with tracer.start_as_current_span("custom_operation") as span:
    span.set_attribute("user.id", "user_123")
    span.set_attribute("session.id", "session_456")
    span.set_attribute("custom.field", "value")
```

### 3. 错误处理

```python
from src.capabilities.observability import observe

@observe(capture_exceptions=True)
async def risky_operation():
    try:
        # 可能失败的操作
        result = await some_api_call()
        return result
    except Exception as e:
        # 异常会被自动记录
        raise
```

### 4. 性能优化

```python
# 异步上报 (不阻塞主流程)
LANGFUSE_ASYNC=true

# 批量大小
LANGFUSE_BATCH_SIZE=100

# 刷新间隔 (秒)
LANGFUSE_FLUSH_INTERVAL=5
```

## 📈 监控指标

### 关键指标

| 指标 | 说明 | 告警阈值 |
|------|------|---------|
| Latency | 请求延迟 | > 5s |
| Token Usage | Token 消耗 | > 10K/请求 |
| Cost | 成本 | > $0.1/请求 |
| Error Rate | 错误率 | > 5% |
| Throughput | 吞吐量 | < 10 req/s |

### 查看指标

在 Langfuse Dashboard 中:
1. 进入 **Analytics** 页面
2. 选择时间范围
3. 查看各项指标的趋势和分布

## 🐛 故障排查

### 问题 1: Langfuse 未上报数据

**检查清单**:
```bash
# 1. 检查配置
LANGFUSE_ENABLED=true

# 2. 检查 API Key
LANGFUSE_PUBLIC_KEY=pk-lf-xxx
LANGFUSE_SECRET_KEY=sk-lf-xxx

# 3. 检查网络连接
curl https://cloud.langfuse.com/api/health

# 4. 查看日志
grep "observability" logs/*.log
```

### 问题 2: 认证失败

```bash
# 检查认证
python -c "
from langfuse import get_client
langfuse = get_client()
print('Auth:', langfuse.auth_check())
"
```

### 问题 3: 性能问题

```bash
# 降低采样率
LANGFUSE_SAMPLING_RATE=0.1

# 启用异步
LANGFUSE_ASYNC=true

# 增加批量大小
LANGFUSE_BATCH_SIZE=200
```

## 📝 最佳实践

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

### 3. 成本控制

- 生产环境使用采样 (10-50%)
- 设置预算告警
- 定期审查 Token 使用
- 优化 Prompt 长度

### 4. 隐私保护

- 启用 PII 脱敏
- 不记录敏感字段
- 限制输入/输出长度
- 定期清理旧数据

## 🎓 示例代码

完整的示例代码在 `examples/observability_example.py`:

```bash
# 运行示例
python examples/observability_example.py
```

示例包含:
1. 自动埋点
2. Trace 分组
3. 工具执行追踪
4. 自定义埋点
5. Multi-Agent Handoff
6. 错误追踪

## 🔗 相关链接

- [Langfuse 官方文档](https://langfuse.com/docs)
- [OpenAI Agents SDK](https://github.com/openai/openai-agents-python)
- [OpenTelemetry](https://opentelemetry.io)
- [Langfuse Cloud](https://cloud.langfuse.com)

## 💬 获取帮助

- 查看日志: `logs/default.log`
- 查看文档: `docs/LANGFUSE_INTEGRATION_PLAN.md`
- 提交 Issue: GitHub Issues

---

*文档版本: v1.0*
*更新时间: 2026-05-19*
