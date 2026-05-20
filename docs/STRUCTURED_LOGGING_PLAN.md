# 结构化日志技术方案

## 📋 需求分析

### 当前问题

现有日志系统虽然支持 JSON 格式,但存在以下不足:

1. **日志格式不统一** - 不同模块使用不同的日志格式
2. **缺少核心字段** - 没有标准化的业务字段(如 session_id, user_id, tool_name 等)
3. **难以检索和分析** - 日志结构不一致,不利于 ELK/Loki 等日志系统分析
4. **缺少日志级别规范** - 不清楚何时使用 INFO/WARN/ERROR
5. **敏感信息可能泄露** - 没有统一的脱敏机制

### 目标

实现**完全标准化的结构化日志**,包含:
- ✅ 统一的 JSON 格式
- ✅ 标准化的核心字段
- ✅ 业务上下文追踪
- ✅ 敏感信息自动脱敏
- ✅ 日志级别规范
- ✅ 性能监控指标

---

## 🎯 技术方案

### 方案概述

基于现有的 `logging.py`,增强为**企业级结构化日志系统**:

```
┌─────────────────────────────────────────────────┐
│           结构化日志系统                          │
├─────────────────────────────────────────────────┤
│                                                 │
│  1. 标准日志格式 (JSON)                          │
│  2. 核心字段规范                                  │
│  3. 业务上下文追踪                               │
│  4. 敏感信息脱敏                                 │
│  5. 日志级别规范                                 │
│  6. 性能指标记录                                 │
│                                                 │
└─────────────────────────────────────────────────┘
```

---

## 📐 日志格式设计

### 标准日志结构

```json
{
  "timestamp": "2026-05-20T12:30:45.123",
  "level": "INFO",
  "logger": "agent_runtime",
  "message": "Agent 调用完成",
  
  "rid": "abc123def456",
  "session_id": "session-001",
  "user_id": "user-123",
  
  "event": "agent_call_completed",
  "event_category": "agent",
  "event_action": "call",
  
  "module": "agent_runtime",
  "function": "run",
  "line": 120,
  
  "context": {
    "model": "qwen3.5-plus",
    "tool_calls_count": 2,
    "memory_size": 5
  },
  
  "performance": {
    "duration_ms": 1250,
    "tokens_used": 500,
    "cost_usd": 0.0025
  },
  
  "metadata": {
    "app_version": "1.0.0",
    "env": "production"
  }
}
```

---

## 🔑 核心字段规范

### 必填字段 (所有日志必须包含)

| 字段 | 类型 | 说明 | 示例 |
|------|------|------|------|
| `timestamp` | string | ISO 8601 时间戳 | `2026-05-20T12:30:45.123` |
| `level` | string | 日志级别 | `INFO`, `WARN`, `ERROR` |
| `logger` | string | 日志器名称 | `agent_runtime` |
| `message` | string | 日志消息 | `Agent 调用完成` |
| `rid` | string | 请求 ID | `abc123def456` |

### 业务字段 (根据场景添加)

| 字段 | 类型 | 说明 | 何时使用 |
|------|------|------|----------|
| `session_id` | string | 会话 ID | Agent 调用相关日志 |
| `user_id` | string | 用户 ID | 用户相关日志 |
| `event` | string | 事件名称 | 所有事件日志 |
| `event_category` | string | 事件分类 | 所有事件日志 |
| `event_action` | string | 事件动作 | 所有事件日志 |

### 上下文字段 (可选)

| 字段 | 类型 | 说明 | 示例 |
|------|------|------|------|
| `context` | object | 业务上下文 | `{model: "qwen3.5-plus"}` |
| `performance` | object | 性能指标 | `{duration_ms: 1250}` |
| `metadata` | object | 元数据 | `{app_version: "1.0.0"}` |

---

## 📂 事件分类规范

### 事件分类

| 分类 | 说明 | 示例事件 |
|------|------|----------|
| `agent` | Agent 相关 | `agent_call_started`, `agent_call_completed` |
| `tool` | 工具调用 | `tool_called`, `tool_approval_required` |
| `memory` | 记忆系统 | `memory_retrieved`, `memory_stored` |
| `model` | 模型调用 | `model_selected`, `model_fallback_triggered` |
| `hitl` | 人工审批 | `approval_requested`, `approval_approved` |
| `checkpoint` | 检查点 | `checkpoint_saved`, `checkpoint_restored` |
| `error` | 错误 | `api_error`, `timeout_error` |

### 事件命名规范

格式: `{resource}_{action}_{status}`

示例:
- `agent_call_started`
- `agent_call_completed`
- `tool_call_failed`
- `memory_retrieval_succeeded`

---

## 🔐 日志级别规范

### 级别定义

| 级别 | 使用场景 | 示例 |
|------|----------|------|
| `DEBUG` | 调试信息,详细参数 | 工具调用参数、模型选择细节 |
| `INFO` | 正常业务流程 | Agent 调用开始/完成、工具调用成功 |
| `WARN` | 警告但不影响流程 | 模型降级触发、记忆检索失败 |
| `ERROR` | 错误但系统可恢复 | API 调用失败、超时重试 |
| `CRITICAL` | 严重错误,系统不可用 | 数据库连接失败、配置错误 |

### 使用示例

```python
# DEBUG - 调试信息
logger.debug("选择模型", extra={
    "event": "model_selected",
    "context": {"task_type": "complex", "model": "gpt-4"}
})

# INFO - 正常流程
log_event(logger, "agent_call_completed", 
    session_id=session_id,
    user_id=user_id,
    model=selected_model,
    duration_ms=duration_ms
)

# WARN - 警告
log_event(logger, "model_fallback_triggered", level=logging.WARN,
    original_model="gpt-4",
    fallback_model="qwen3.5-plus",
    reason="rate_limit_exceeded"
)

# ERROR - 错误
log_event(logger, "api_call_failed", level=logging.ERROR,
    error_type="TimeoutError",
    error_message="Request timeout after 30s",
    retry_count=3
)
```

---

## 🛡️ 敏感信息脱敏

### 脱敏规则

```python
SENSITIVE_FIELDS = {
    "api_key", "secret", "password", "token", "authorization",
    "credit_card", "phone", "email", "id_card"
}

def sanitize_value(field: str, value: Any) -> Any:
    """脱敏敏感字段"""
    if field.lower() in SENSITIVE_FIELDS:
        if isinstance(value, str):
            if len(value) <= 8:
                return "***"
            return value[:4] + "***" + value[-4:]
        return "***"
    return value
```

### 脱敏示例

```json
{
  "context": {
    "api_key": "sk-l***xyz",
    "user_email": "use***@example.com",
    "phone": "138***1234"
  }
}
```

---

## 📊 性能指标记录

### 性能字段

```json
{
  "performance": {
    "duration_ms": 1250,
    "tokens_prompt": 300,
    "tokens_completion": 200,
    "tokens_total": 500,
    "cost_usd": 0.0025,
    "cache_hit": false
  }
}
```

### 记录方式

```python
import time

async def run_with_performance_tracking():
    start_time = time.time()
    
    try:
        # 执行操作
        result = await agent.run()
        
        duration_ms = (time.time() - start_time) * 1000
        
        log_event(logger, "operation_completed",
            duration_ms=duration_ms,
            result_status="success"
        )
        
        return result
    except Exception as e:
        duration_ms = (time.time() - start_time) * 1000
        
        log_event(logger, "operation_failed", level=logging.ERROR,
            duration_ms=duration_ms,
            error=str(e)
        )
        raise
```

---

## 🔧 实现方案

### 1. 增强日志配置

**文件**: `src/core/logging.py`

```python
# 新增: 结构化日志辅助函数

def log_event(
    logger: logging.Logger,
    event: str,
    level: int = logging.INFO,
    session_id: str | None = None,
    user_id: str | None = None,
    **fields: Any
) -> None:
    """记录结构化事件日志"""
    
    # 解析事件分类和动作
    parts = event.split("_")
    if len(parts) >= 2:
        event_category = parts[0]
        event_action = "_".join(parts[1:])
    else:
        event_category = "general"
        event_action = event
    
    # 构建结构化字段
    structured_fields = {
        "event": event,
        "event_category": event_category,
        "event_action": event_action,
    }
    
    if session_id:
        structured_fields["session_id"] = session_id
    if user_id:
        structured_fields["user_id"] = user_id
    
    # 分离性能字段
    performance_fields = {}
    business_context = {}
    
    for key, value in fields.items():
        if key.startswith(("duration_", "tokens_", "cost_")):
            performance_fields[key] = value
        else:
            business_context[key] = value
    
    if business_context:
        structured_fields["context"] = _log_safe(business_context)
    if performance_fields:
        structured_fields["performance"] = performance_fields
    
    # 记录日志
    logger.log(level, event, extra={
        "event": event,
        "structured_fields": _log_safe(structured_fields)
    })
```

### 2. 增强 JSON 格式化器

```python
class EnhancedJsonLogFormatter(logging.Formatter):
    """增强的 JSON 日志格式化器"""
    
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "timestamp": datetime.fromtimestamp(
                record.created
            ).isoformat(timespec="milliseconds"),
            "level": record.levelname,
            "logger": record.name,
            "message": _single_line_text(record.getMessage()),
            "rid": getattr(record, "rid", "-"),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
        }
        
        # 添加结构化字段
        fields = getattr(record, "structured_fields", {})
        if fields:
            payload.update(fields)
        
        # 添加上下文
        context = getattr(record, "context", None)
        if context:
            payload["context"] = _sanitize_context(context)
        
        # 添加异常信息
        if record.exc_info:
            payload["exc_info"] = {
                "type": record.exc_info[0].__name__,
                "message": str(record.exc_info[1]),
                "traceback": _single_line_text(
                    self.formatException(record.exc_info)
                )
            }
        
        # 添加元数据
        payload["metadata"] = {
            "app_version": os.getenv("APP_VERSION", "unknown"),
            "env": current_settings.env_type,
        }
        
        return _compact_json(payload)
```

### 3. 日志上下文管理器

```python
from contextlib import contextmanager

@contextmanager
def log_context(session_id: str | None = None, user_id: str | None = None, **fields):
    """日志上下文管理器"""
    
    context = {
        "session_id": session_id,
        "user_id": user_id,
        **fields
    }
    
    token = bind_log_context(**context)
    try:
        yield
    finally:
        reset_log_context(token)
```

---

## 📝 使用示例

### 示例 1: Agent 调用日志

```python
from src.core.logging import service_logger, log_event

async def run_agent(session, user_input):
    session_id = session.session_id
    user_id = session.user_id
    
    # 开始日志
    log_event(service_logger, "agent_call_started",
        session_id=session_id,
        user_id=user_id,
        input_length=len(user_input)
    )
    
    start_time = time.time()
    
    try:
        # 执行 Agent 调用
        result = await orchestrator.run(session, user_input)
        
        duration_ms = (time.time() - start_time) * 1000
        
        # 完成日志
        log_event(service_logger, "agent_call_completed",
            session_id=session_id,
            user_id=user_id,
            model=result["model"],
            tool_calls_count=len(result["tool_calls"]),
            duration_ms=duration_ms,
            output_length=len(result["output"])
        )
        
        return result
        
    except Exception as e:
        duration_ms = (time.time() - start_time) * 1000
        
        # 错误日志
        log_event(service_logger, "agent_call_failed", level=logging.ERROR,
            session_id=session_id,
            user_id=user_id,
            error_type=type(e).__name__,
            error_message=str(e),
            duration_ms=duration_ms
        )
        raise
```

### 示例 2: 工具调用日志

```python
log_event(service_logger, "tool_called",
    session_id=session_id,
    tool_name="create_ticket",
    tool_args={"title": "问题描述"},
    approval_required=False
)

# 如果需要审批
log_event(service_logger, "approval_requested",
    session_id=session_id,
    tool_name="delete_ticket",
    approval_id=request.id,
    reviewer="admin"
)
```

### 示例 3: 模型降级日志

```python
log_event(service_logger, "model_fallback_triggered", level=logging.WARN,
    session_id=session_id,
    original_model="gpt-4",
    fallback_model="qwen3.5-plus",
    reason="rate_limit_exceeded",
    retry_count=3
)
```

---

## 🎯 实施步骤

### Phase 1: 核心增强 (1-2 天)

- [ ] 增强 `log_event` 函数
- [ ] 增强 `JsonLogFormatter`
- [ ] 添加 `log_context` 管理器
- [ ] 添加敏感信息脱敏

### Phase 2: 集成到现有代码 (2-3 天)

- [ ] 更新 `AgentOrchestrator` 日志
- [ ] 更新工具调用日志
- [ ] 更新模型路由日志
- [ ] 更新记忆系统日志

### Phase 3: 高级能力日志 (1-2 天)

- [ ] HITL 审批日志
- [ ] Checkpoint 日志
- [ ] Handoff 日志

### Phase 4: 测试和文档 (1-2 天)

- [ ] 编写单元测试
- [ ] 编写使用文档
- [ ] 验证日志格式

---

## 📊 预期效果

### 日志示例

**Agent 调用成功**:
```json
{
  "timestamp": "2026-05-20T12:30:45.123",
  "level": "INFO",
  "logger": "service",
  "message": "agent_call_completed",
  "rid": "abc123",
  "session_id": "session-001",
  "user_id": "user-123",
  "event": "agent_call_completed",
  "event_category": "agent",
  "event_action": "call_completed",
  "context": {
    "model": "qwen3.5-plus",
    "tool_calls_count": 2
  },
  "performance": {
    "duration_ms": 1250
  },
  "metadata": {
    "app_version": "1.0.0",
    "env": "production"
  }
}
```

**错误日志**:
```json
{
  "timestamp": "2026-05-20T12:30:46.456",
  "level": "ERROR",
  "logger": "service",
  "message": "agent_call_failed",
  "rid": "abc123",
  "session_id": "session-001",
  "event": "agent_call_failed",
  "event_category": "agent",
  "context": {
    "error_type": "RateLimitError",
    "error_message": "API rate limit exceeded"
  },
  "performance": {
    "duration_ms": 3500
  },
  "exc_info": {
    "type": "RateLimitError",
    "message": "API rate limit exceeded",
    "traceback": "..."
  }
}
```

---

## ✅ 可行性评估

### 技术可行性: ✅ 完全可行

- ✅ 基于现有日志系统增强,不需要重写
- ✅ Python 标准库 `logging` 完全支持
- ✅ JSON 格式已实现,只需增强字段
- ✅ 上下文追踪使用 `ContextVar`,性能优秀

### 性能影响: ✅ 极小

- JSON 序列化: ~0.1ms/条
- 上下文追踪: ~0.01ms/条
- 脱敏处理: ~0.05ms/条
- **总开销**: < 0.2ms/条 (可忽略)

### 实施风险: ✅ 低风险

- ✅ 向后兼容,不影响现有日志
- ✅ 渐进式实施,可逐步替换
- ✅ 可随时回滚

### 维护成本: ✅ 低

- ✅ 统一规范,易于理解
- ✅ 自动化脱敏,减少人工错误
- ✅ 标准化格式,便于分析

---

## 🎓 总结

### 方案优势

1. **标准化** - 统一格式,便于分析
2. **可追踪** - 完整的业务上下文
3. **安全性** - 自动脱敏敏感信息
4. **可观测** - 性能指标自动记录
5. **易维护** - 清晰的规范和使用指南

### 建议

- ✅ **立即实施** - 技术成熟,风险低
- ✅ **渐进式** - 分 4 个 Phase 实施
- ✅ **先核心后扩展** - 先实现核心功能,再逐步完善

---

## 🔗 相关文档

- [现有日志系统](../src/core/logging.py)
- [可观测性指南](./OBSERVABILITY_GUIDE.md)
- [架构设计](./ARCHITECTURE_DESIGN.md)
