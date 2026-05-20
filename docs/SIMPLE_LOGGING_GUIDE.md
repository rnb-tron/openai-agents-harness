# 简洁结构化日志使用指南

## 🎯 核心原则

**使用方式保持简单,只需 `logger.info()` / `logger.error()`,自动获得增强能力**

---

## 📝 使用方式

### ✅ 推荐: 直接传递结构化字段

```python
from src.core.logging import service_logger

# INFO 级别
logger.info(
    "execution_succeeded",
    model="qwen3.5-plus",
    duration_ms=1250,
    fallback_count=1
)

# WARN 级别  
logger.warning(
    "model_fallback_triggered",
    model="gpt-4",
    error_type="RateLimitError"
)

# ERROR 级别
logger.error(
    "execution_failed",
    error_type="TimeoutError",
    error_message=str(e)
)
```

**输出日志** (JSON 格式):
```json
{
  "timestamp": "2026-05-20T14:30:45.123",
  "level": "INFO",
  "logger": "service",
  "message": "execution_succeeded",
  "rid": "a1b2c3d4e5f6",
  "module": "runner",
  "function": "run",
  "line": 109,
  "event": "execution_succeeded",
  "fields": {
    "model": "qwen3.5-plus",
    "duration_ms": 1250,
    "fallback_count": 1
  },
  "metadata": {
    "app_version": "1.0.0",
    "env": "test"
  }
}
```

---

## ✨ 自动增强能力

### 1. 敏感信息自动脱敏

```python
# 代码中传递原始值
logger.info(
    "api_call",
    api_key="sk-live-1234567890abcdef",
    user_email="user@example.com"
)

# 日志中自动脱敏
{
  "fields": {
    "api_key": "sk-l***cdef",      // ✅ 自动脱敏
    "user_email": "use***.com"     // ✅ 自动脱敏
  }
}
```

**支持的敏感字段**:
- `api_key`, `secret`, `password`, `token`, `authorization`
- `phone`, `mobile`, `email`, `id_card`
- `credit_card`, `card_number`, `bank_account`

---

### 2. 异常信息结构化

```python
try:
    raise TimeoutError("请求超时")
except Exception as e:
    logger.error(
        "operation_failed",
        error_type=type(e).__name__,
        error_message=str(e),
        exc_info=True  # 自动捕获异常堆栈
    )
```

**输出日志**:
```json
{
  "level": "ERROR",
  "message": "operation_failed",
  "fields": {
    "error_type": "TimeoutError",
    "error_message": "请求超时"
  },
  "exc_info": {
    "type": "TimeoutError",
    "message": "请求超时"
  }
}
```

---

### 3. 日志上下文管理器

```python
from src.core.logging import service_logger, log_context

# 在上下文中,所有日志自动包含 session_id 和 user_id
with log_context(session_id="session-001", user_id="user-123"):
    service_logger.info("开始处理")
    service_logger.info("处理完成")
    
# 输出:
# {"session_id": "session-001", "user_id": "user-123", ...}
```

---

### 4. 元数据自动添加

每条日志自动添加:
```json
{
  "metadata": {
    "app_version": "1.0.0",  // 从环境变量 APP_VERSION 读取
    "env": "test"            // 从配置读取
  }
}
```

---

## 📊 实际示例

### 示例 1: 模型执行成功 (runner.py)

```python
logger.info(
    "execution_succeeded",
    model=self.metrics.success_model,
    duration_ms=int(self.metrics.total_duration * 1000),
    fallback_count=self.metrics.fallback_count
)
```

**输出**:
```json
{
  "event": "execution_succeeded",
  "fields": {
    "model": "qwen3.5-plus",
    "duration_ms": 1250,
    "fallback_count": 1
  }
}
```

---

### 示例 2: 模型降级触发 (fallback.py)

```python
logger.warning(
    "model_fallback_triggered",
    model=model,
    error_type=type(e).__name__,
    error_message=str(e)
)
```

**输出**:
```json
{
  "event": "model_fallback_triggered",
  "fields": {
    "model": "gpt-4",
    "error_type": "RateLimitError",
    "error_message": "API rate limit exceeded"
  }
}
```

---

### 示例 3: 重试失败 (retry.py)

```python
logger.error(
    "max_retries_exceeded",
    max_retries=self.config.max_retries,
    last_error_type=type(last_error).__name__,
    last_error_message=str(last_error)
)
```

**输出**:
```json
{
  "event": "max_retries_exceeded",
  "fields": {
    "max_retries": 3,
    "last_error_type": "RateLimitError",
    "last_error_message": "API rate limit exceeded"
  }
}
```

---

## 🔧 对比: 优化前 vs 优化后

### ❌ 优化前: 纯文本日志

```python
logger.info(
    f"Execution succeeded: "
    f"model={self.metrics.success_model}, "
    f"duration={self.metrics.total_duration:.2f}s, "
    f"fallbacks={self.metrics.fallback_count}"
)
```

**问题**:
- ❌ 难以解析和查询
- ❌ 无法按字段过滤
- ❌ 无敏感信息脱敏
- ❌ 无结构化元数据

---

### ✅ 优化后: 结构化日志

```python
logger.info(
    "execution_succeeded",
    model=self.metrics.success_model,
    duration_ms=int(self.metrics.total_duration * 1000),
    fallback_count=self.metrics.fallback_count
)
```

**优势**:
- ✅ JSON 格式,易于解析
- ✅ 可按字段查询 (`fields.model="qwen3.5-plus"`)
- ✅ 敏感信息自动脱敏
- ✅ 自动添加元数据
- ✅ **使用方式完全不变**

---

## 💡 最佳实践

### 1. 事件命名规范

使用 `resource_action_status` 格式:

```python
# ✅ 推荐
"agent_call_completed"
"tool_called"
"model_fallback_triggered"
"approval_requested"

# ❌ 不推荐
"call agent completed"
"tool call"
```

### 2. 字段命名规范

- 性能字段: `duration_ms`, `tokens_total`, `cost_usd`
- 错误字段: `error_type`, `error_message`
- 业务字段: 根据实际业务命名

### 3. 日志级别选择

| 级别 | 使用场景 | 示例 |
|------|----------|------|
| **DEBUG** | 调试信息 | 详细的内存检索结果 |
| **INFO** | 正常流程 | Agent 调用完成 |
| **WARNING** | 警告 | 模型降级触发 |
| **ERROR** | 错误 | API 调用失败 |

---

## 📈 增强能力总结

| 能力 | 说明 | 使用方式 |
|------|------|----------|
| **敏感脱敏** | 自动脱敏 20+ 种敏感字段 | 无需额外代码 |
| **异常结构化** | 异常信息结构化为 type/message | 传递 `exc_info=True` |
| **元数据** | 自动添加 app_version/env | 无需额外代码 |
| **上下文管理** | 批量日志包含共同字段 | 使用 `log_context()` |
| **事件分类** | 记录 event 字段 | 第一个参数为事件名 |

---

## ✅ 向后兼容

所有原有用法保持不变:

```python
# 原有用法仍然有效
logger.info("简单消息")
logger.warning(f"格式化消息: {value}")
logger.error("错误消息", exc_info=True)

# 新增: 结构化字段
logger.info("事件名", field1=value1, field2=value2)
```

---

## 🎯 总结

**核心理念**: 
- 使用方式保持简单: `logger.info("event", **fields)`
- 自动获得增强: 脱敏、元数据、异常结构化
- 零学习成本: 与原有用法完全一致
