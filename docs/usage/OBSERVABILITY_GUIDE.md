# 可观测性指南

> 状态：当前实现指南。当前能力接入 Langfuse/OpenTelemetry，并提供 Agents SDK 与 HTTP 请求追踪入口。

## 当前实现

启用 `LANGFUSE_ENABLED=true` 时：

1. `HarnessBuilder` 装配 `ObservabilityCapability`，由 capability 生命周期初始化/关闭 `TracerManager`。
2. 初始化阶段校验 Langfuse 凭证并安装 `OpenAIAgentsInstrumentor`。
3. 协议层 `ObservabilityPlugin` 仅安装 HTTP interceptor，为请求创建 span 并返回 `X-Trace-ID`。
4. 该 interceptor 位于 Auth 与 RateLimit 外侧，因此认证失败与限流拒绝也可观测。
5. 基础 Request Context 始终返回 `X-Request-ID`，供日志和 trace 关联。

因此能力资源所有权在 Harness 中，HTTP 入口适配仍位于显式的
`ProtocolRequestChain` 中。

## 配置

当前从环境变量读取并生效的配置：

```env
LANGFUSE_ENABLED=true
LANGFUSE_PUBLIC_KEY=pk-lf-xxx
LANGFUSE_SECRET_KEY=sk-lf-xxx
LANGFUSE_BASE_URL=http://agent-otel-test.ke.com
LANGFUSE_TRACING_ENABLED=true
LANGFUSE_METRICS_ENABLED=true
LANGFUSE_SAMPLING_RATE=1.0
LANGFUSE_MASK_PII=true
```

其中启动校验会检查 key 与 sampling rate；Agents SDK instrumentation 受 `LANGFUSE_TRACING_ENABLED` 控制。`metrics_enabled`、sampling 与 PII 字段目前保留在配置模型中，尚未看到业务侧对采样或 payload 脱敏的完整执行策略，不能将其视为数据合规保障。

启动：

```bash
ENVTYPE=test venv/bin/python -m uvicorn src.main:app --host 0.0.0.0 --port 8080
```

## 自动追踪

Runtime 调用 Agents SDK `Runner.run_streamed()` 时，instrumentor 负责 SDK spans。HTTP 层会补充请求 span：

```bash
curl -i -X POST http://localhost:8080/chat \
  -H 'Content-Type: application/json' \
  -H 'X-Request-ID: demo-rid' \
  -d '{"query":"hello","userId":"demo-user"}'
```

响应头包含：

```text
X-Request-ID: demo-rid
X-Trace-ID: <trace id>
```

## 手动 span

```python
from src.capabilities.observability import measure_time, observe

@observe(name="lookup_order", span_type="TOOL", capture_input=False)
async def lookup_order(order_id: str) -> dict:
    return {"id": order_id}

@measure_time("cache_lookup")
async def cache_lookup() -> None:
    return None
```

`observe` 默认把输入和输出的字符串摘要记录到 span 属性中。处理凭证、个人信息或敏感工具参数时，应显式设置 `capture_input=False` / `capture_output=False` 或在进入装饰器前脱敏。

## HTTP 数据边界

当前 HTTP interceptor 会记录请求 URL、客户端信息和 query string。请勿把 API key、token 或敏感用户数据放在 URL 查询参数中；现有 trace middleware 未对 query 参数执行字段级脱敏。

## Prompt 集成

Prompt 管理由 `src/capabilities/prompt/` 独立提供；选择 Langfuse 作为 prompt backend 时可与同一服务配合使用，但它不是 ObservabilityCapability 自动完成的附加功能。

## 测试与示例

```bash
venv/bin/python -m pytest tests/unit/test_observability_plugin.py \
  tests/unit/test_observability_capability.py -q
venv/bin/python examples/observability.py
```

示例中的 SDK 调用需要有效模型配置；查看远端 trace 时还需设置 `LANGFUSE_ENABLED=true` 并提供有效 Langfuse 凭证。

## 相关文件

- `src/capabilities/observability/plugin.py`
- `src/capabilities/observability/capability.py`
- `src/capabilities/observability/tracer.py`
- `src/capabilities/observability/middleware.py`
- `src/api/middleware/request_context.py`
