# 模型弹性调用指南

> 状态：当前实现指南。模型调用示例需要可访问的模型服务；默认测试不会发起外部模型请求。

## 作用

`ModelRouter` 负责基础模型选择，并在 `ResilienceConfig.enabled` 时委托 `ResilientModelRunner` 组合以下策略：

| 策略 | 实现 | 说明 |
| --- | --- | --- |
| Fallback | `ModelFallback` | 按配置模型链尝试 |
| Retry | `RetryExecutor` | 对配置的异常类型重试 |
| Timeout | `TimeoutController` | 包住整次弹性执行 |
| Metrics | `ExecutionMetrics` | 记录模型尝试、耗时与成功模型 |

Runtime 已使用 `model_router.run_with_resilience()` 包裹 Agents SDK 调用。

## 配置

```env
MODEL_RESILIENCE_ENABLED=true

MODEL_FALLBACK_ENABLED=true
MODEL_FALLBACK_CHAIN=gpt-4.1-mini,gpt-4o-mini

MODEL_RETRY_ENABLED=true
MODEL_MAX_RETRIES=2
MODEL_RETRY_DELAY=1.0
MODEL_RETRY_MAX_DELAY=10.0

MODEL_TIMEOUT_ENABLED=true
MODEL_TOTAL_TIMEOUT=30.0
MODEL_PER_REQUEST_TIMEOUT=10.0
```

`HarnessBuilder` 使用 `ResilienceConfig.from_env()` 构建 `ModelRouter`，因此运行服务时以环境变量为主。

## 组件级调用

`agent_factory` 接收模型名，并返回一个可 await 的执行对象；Runtime 中该对象就是 `Runner.run(...)`：

```python
from agents import Agent, Runner
from src.capabilities.model_routing import (
    FallbackConfig,
    ModelRouter,
    ResilienceConfig,
    RetryConfig,
    TimeoutConfig,
)

config = ResilienceConfig(
    enabled=True,
    fallback=FallbackConfig(enabled=True, models=["gpt-4.1-mini", "gpt-4o-mini"]),
    retry=RetryConfig(enabled=True, max_retries=2),
    timeout=TimeoutConfig(enabled=True, total_timeout=30.0),
)
router = ModelRouter(default_model="gpt-4o-mini", resilience_config=config)

async def run_with_model(model: str):
    agent = Agent(name="assistant", instructions="Be concise.", model=model)
    return Runner.run(starting_agent=agent, input="hello")

result = await router.run_with_resilience(run_with_model)
metrics = router.last_metrics
```

## 模型选择

未启用弹性时，`select()` 根据任务类型选择 `default_model` 或 `reasoning_model`。当前任务类型推断是轻量关键词判断，不是业务级路由或模型质量评估系统。

## 指标

启用弹性 runner 后可读取：

```python
metrics = router.last_metrics
print(metrics.success_model)
print(metrics.models_tried)
print(metrics.fallback_count)
print(metrics.total_duration)
```

当前指标位于进程对象中，并由日志记录完成/失败事件；没有独立的持久化指标存储。

## 测试与示例

```bash
venv/bin/python -m pytest tests/unit/test_model_routing_capabilities.py -q
venv/bin/python examples/model_resilience.py
```

外部模型端到端验证：

```bash
RUN_EXTERNAL_TESTS=true venv/bin/python -m pytest tests/e2e/test_model_resilience.py -v
```

## 注意事项

- Fallback 与 retry 都可能增加调用次数和费用。
- 中断后的 HITL 恢复会继续使用响应中回传的实际模型，不重新走 fallback 选择。
- 业务级成本路由、预算控制与线上指标告警尚未由该模块实现。
