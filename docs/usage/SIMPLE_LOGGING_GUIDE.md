# 结构化日志指南

> 状态：当前实现指南。日志基于 Python `logging`，结构化业务字段通过 `log_event()` 或 `extra` 写入。

## Logger 与输出

```python
from src.core.logging import service_logger, setup_logger

logger = setup_logger("my.component")
service_logger.info("service started")
```

`setup_logger()` 创建两类输出：

| 输出 | 格式 | 默认目标 |
| --- | --- | --- |
| Console | 单行文本 | stdout/stderr handler |
| File | JSON 单行 | `data/logs/default.log` |

所有 handler 自动带 `rid`。文件日志额外输出时间、级别、logger、模块、函数、行号、事件字段与环境元数据。

## 结构化事件

推荐使用 `log_event()`：

```python
import logging
from src.core.logging import log_event, service_logger

log_event(
    service_logger,
    "agent_call_completed",
    session_id="session-001",
    model="gpt-4o-mini",
    duration_ms=1250,
)

log_event(
    service_logger,
    "model_call_failed",
    level=logging.ERROR,
    session_id="session-001",
    error_type="TimeoutError",
)
```

也可使用 Python logging 的标准 `extra` 形式：

```python
service_logger.info(
    "agent_call_completed",
    extra={
        "event": "agent_call_completed",
        "structured_fields": {"model": "gpt-4o-mini", "duration_ms": 1250},
    },
)
```

不要使用 `logger.info("event", model="...")` 这样的任意关键字参数；标准 `logging.Logger` 不支持这种调用。

## 请求与业务上下文

HTTP 请求通过 request context middleware 自动设置 `X-Request-ID` 和日志 `rid`。

非 HTTP 或需要额外业务字段时：

```python
from src.core.logging import log_context, service_logger

with log_context(session_id="session-001", user_id="user-123"):
    service_logger.info("processing")
```

`log_context()` 将字段绑定到日志上下文；如需将业务字段写入 JSON `fields`，仍应调用 `log_event()`。

## 脱敏

`JsonLogFormatter` 对 `structured_fields` 中常见敏感键递归脱敏，例如：

```python
log_event(
    service_logger,
    "external_request",
    api_key="sk-sensitive-value",
    email="person@example.com",
)
```

当前脱敏作用于结构化字段，不应依赖它清洗已拼接进 message 的密钥、模型输入输出或 trace 属性。敏感内容不要先格式化进普通日志消息。

## 异常

```python
try:
    raise RuntimeError("operation failed")
except RuntimeError:
    service_logger.exception("operation_failed")
```

带 `exc_info` 的文件日志会记录异常类型和消息，不输出完整 traceback JSON 字段。

## 相关文件与测试

```bash
venv/bin/python -m pytest tests/integration/test_structured_logging.py -q
```

- `src/core/logging.py`
- `src/api/middleware/request_context.py`
