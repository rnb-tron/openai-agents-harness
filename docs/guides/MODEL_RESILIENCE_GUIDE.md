# 模型弹性调用使用指南

## 📋 概述

模型弹性调用能力提供了**可插拔**的降级、重试、超时控制,让你的 Agent 应用更稳定、更可靠。

> 状态：当前能力使用指南。示例运行依赖可访问的模型服务配置。

### 核心特性

✅ **完全可插拔**: 可选择性启用降级、重试、超时  
✅ **灵活配置**: 自定义降级链路、重试策略、超时时间  
✅ **自动指标**: 记录执行指标 (模型、耗时、降级次数)  
✅ **零侵入**: 不启用时不影响现有代码  

---

## 🚀 快速开始

### 1. 基本使用 (不启用弹性)

```python
from src.capabilities.model_routing import ModelRouter

# 默认行为,不启用弹性
router = ModelRouter(default_model="qwen3.5-plus")

# 使用方式不变
result = await router.run_with_resilience(create_agent)
```

### 2. 启用降级

```python
from src.capabilities.model_routing import (
    ModelRouter,
    ResilienceConfig,
    FallbackConfig,
)

config = ResilienceConfig(
    enabled=True,
    fallback=FallbackConfig(
        enabled=True,
        models=["qwen3.5-plus", "gpt-4o-mini"],  # 降级链路
    ),
)

router = ModelRouter(
    default_model="qwen3.5-plus",
    resilience_config=config,
)

result = await router.run_with_resilience(create_agent)
```

### 3. 启用重试

```python
from src.capabilities.model_routing import RetryConfig

config = ResilienceConfig(
    enabled=True,
    retry=RetryConfig(
        enabled=True,
        max_retries=2,          # 最多重试 2 次
        initial_delay=1.0,      # 初始延迟 1 秒
        max_delay=5.0,          # 最大延迟 5 秒
    ),
)
```

### 4. 启用超时

```python
from src.capabilities.model_routing import TimeoutConfig

config = ResilienceConfig(
    enabled=True,
    timeout=TimeoutConfig(
        enabled=True,
        total_timeout=30.0,     # 总超时 30 秒
        per_request_timeout=10.0,  # 单次请求超时 10 秒
    ),
)
```

### 5. 完整配置

```python
config = ResilienceConfig(
    enabled=True,
    fallback=FallbackConfig(
        enabled=True,
        models=["qwen3.5-plus", "qwen3.0", "gpt-4o-mini"],
    ),
    retry=RetryConfig(
        enabled=True,
        max_retries=2,
        initial_delay=1.0,
    ),
    timeout=TimeoutConfig(
        enabled=True,
        total_timeout=30.0,
    ),
)
```

---

## 📊 查看执行指标

```python
result = await router.run_with_resilience(create_agent)

# 获取指标
metrics = router.last_metrics

print(f"使用模型: {metrics.success_model}")
print(f"总耗时: {metrics.total_duration:.2f}s")
print(f"降级次数: {metrics.fallback_count}")
print(f"尝试的模型: {metrics.models_tried}")
```

---

## 🔧 环境变量配置

在 `.env` 文件中配置:

```bash
# 启用弹性调用
MODEL_RESILIENCE_ENABLED=true

# 降级配置
MODEL_FALLBACK_ENABLED=true
MODEL_FALLBACK_CHAIN=qwen3.5-plus,qwen3.0,gpt-4o-mini

# 重试配置
MODEL_RETRY_ENABLED=true
MODEL_MAX_RETRIES=2
MODEL_RETRY_DELAY=1.0
MODEL_RETRY_MAX_DELAY=10.0

# 超时配置
MODEL_TIMEOUT_ENABLED=true
MODEL_TOTAL_TIMEOUT=30.0
MODEL_PER_REQUEST_TIMEOUT=10.0
```

然后从环境变量创建:

```python
from src.capabilities.model_routing import ResilienceConfig

config = ResilienceConfig.from_env()
router = ModelRouter(resilience_config=config)
```

---

## 💡 使用场景

### 场景 1: 高可用性要求

```python
# 多级降级 + 重试 + 超时
config = ResilienceConfig(
    enabled=True,
    fallback=FallbackConfig(
        enabled=True,
        models=["qwen3.5-plus", "qwen3.0", "gpt-4o-mini", "gpt-3.5-turbo"],
    ),
    retry=RetryConfig(
        enabled=True,
        max_retries=3,
        initial_delay=1.0,
    ),
    timeout=TimeoutConfig(
        enabled=True,
        total_timeout=60.0,
    ),
)
```

### 场景 2: 成本优化

```python
# 优先使用便宜模型,失败后降级到高质量模型
config = ResilienceConfig(
    enabled=True,
    fallback=FallbackConfig(
        enabled=True,
        models=["gpt-4o-mini", "qwen3.5-plus"],  # 便宜 → 高质量
    ),
    retry=RetryConfig(enabled=False),  # 不重试,节省成本
)
```

### 场景 3: 快速失败

```python
# 单次尝试,快速失败
config = ResilienceConfig(
    enabled=True,
    timeout=TimeoutConfig(
        enabled=True,
        total_timeout=5.0,  # 5 秒超时
    ),
    fallback=FallbackConfig(enabled=False),
    retry=RetryConfig(enabled=False),
)
```

---

## 📁 文件结构

```
src/capabilities/model_routing/
├── __init__.py           # 统一导出
├── config.py             # 配置模型
├── fallback.py           # 降级策略
├── retry.py              # 重试策略
├── timeout.py            # 超时控制
├── runner.py             # 弹性运行器
└── router.py             # 模型路由器 (已增强)
```

---

## ⚠️ 注意事项

### 1. 成本控制
- 降级和重试会增加调用次数
- 建议设置每日预算上限

### 2. 异常分类
- **可重试异常**: 网络错误、超时、限流
- **不可重试异常**: 认证失败、无效请求
- 系统会自动区分

### 3. 超时分配
- 总超时需合理分配
- 建议: 总超时 / (降级链长度 × 重试次数)

### 4. 降级链路
- 按优先级排序
- 确保最终有一个兜底模型

---

## 🧪 测试

运行测试:

```bash
python tests/test_model_resilience.py
```

查看示例:

```bash
python examples/model_resilience.py
```

---

## 🎯 总结

| 能力 | 配置项 | 说明 |
|------|--------|------|
| **降级** | `fallback.enabled` + `fallback.models` | 多级模型降级 |
| **重试** | `retry.enabled` + `retry.max_retries` | 指数退避重试 |
| **超时** | `timeout.enabled` + `timeout.total_timeout` | 总超时控制 |

**核心优势**:
- ✅ 完全可插拔
- ✅ 零侵入设计
- ✅ 自动指标追踪
- ✅ 灵活配置

开始使用吧! 🚀
