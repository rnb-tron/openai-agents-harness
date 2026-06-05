"""
结构化日志示例演示

展示按照 STRUCTURED_LOGGING_PLAN.md 方案实现的日志输出效果
"""

import json


def print_separator(title):
    print("\n" + "=" * 80)
    print(f"  {title}")
    print("=" * 80)


def print_log(title, log_data):
    print(f"\n📝 {title}:")
    print("-" * 80)
    print(json.dumps(log_data, indent=2, ensure_ascii=False))
    print("-" * 80)


# ============================================================
# 示例 1: Agent 调用成功
# ============================================================

print_separator("示例 1: Agent 调用成功")

agent_call_success = {
    "timestamp": "2026-05-20T14:30:45.123",
    "level": "INFO",
    "logger": "service",
    "message": "agent_call_completed",
    "rid": "a1b2c3d4e5f6",
    "session_id": "session-001",
    "user_id": "user-123",
    "event": "agent_call_completed",
    "event_category": "agent",
    "event_action": "call_completed",
    "module": "agent_runtime",
    "function": "run",
    "line": 152,
    "context": {"model": "qwen3.5-plus", "tool_calls_count": 2, "output_length": 156, "memory_size": 5},
    "performance": {
        "duration_ms": 1250,
        "tokens_prompt": 300,
        "tokens_completion": 200,
        "tokens_total": 500,
        "cost_usd": 0.0025,
    },
    "metadata": {"app_version": "1.0.0", "env": "production"},
}

print_log("Agent 调用成功", agent_call_success)


# ============================================================
# 示例 2: Agent 调用失败 (API 限流)
# ============================================================

print_separator("示例 2: Agent 调用失败 (API 限流)")

agent_call_failed = {
    "timestamp": "2026-05-20T14:30:46.456",
    "level": "ERROR",
    "logger": "service",
    "message": "agent_call_failed",
    "rid": "a1b2c3d4e5f6",
    "session_id": "session-001",
    "user_id": "user-123",
    "event": "agent_call_failed",
    "event_category": "agent",
    "event_action": "call_failed",
    "module": "agent_runtime",
    "function": "run",
    "line": 175,
    "context": {
        "error_type": "RateLimitError",
        "error_message": "当前使用试用额度,每分钟最多请求5次",
        "retry_count": 3,
    },
    "performance": {"duration_ms": 45000},
    "exc_info": {
        "type": "RateLimitError",
        "message": "API rate limit exceeded",
        "traceback": 'Traceback (most recent call last):\\n  File "agent_runtime.py", line 152, in run\\n    result = await Runner.run(...)\\nopenai.RateLimitError: Error code: 429',
    },
    "metadata": {"app_version": "1.0.0", "env": "production"},
}

print_log("Agent 调用失败", agent_call_failed)


# ============================================================
# 示例 3: 工具调用成功
# ============================================================

print_separator("示例 3: 工具调用成功")

tool_call_success = {
    "timestamp": "2026-05-20T14:30:45.500",
    "level": "INFO",
    "logger": "service",
    "message": "tool_called",
    "rid": "a1b2c3d4e5f6",
    "session_id": "session-001",
    "user_id": "user-123",
    "event": "tool_called",
    "event_category": "tool",
    "event_action": "called",
    "module": "agent_runtime",
    "function": "run",
    "line": 140,
    "context": {
        "tool_name": "create_ticket",
        "tool_args": {"title": "登录问题", "description": "无法登录系统"},
        "approval_required": False,
    },
    "metadata": {"app_version": "1.0.0", "env": "production"},
}

print_log("工具调用成功", tool_call_success)


# ============================================================
# 示例 4: HITL 审批请求
# ============================================================

print_separator("示例 4: HITL 人工审批请求")

hitl_approval_request = {
    "timestamp": "2026-05-20T14:30:46.100",
    "level": "INFO",
    "logger": "service",
    "message": "approval_requested",
    "rid": "a1b2c3d4e5f6",
    "session_id": "session-001",
    "user_id": "user-123",
    "event": "approval_requested",
    "event_category": "hitl",
    "event_action": "requested",
    "module": "agent_runtime",
    "function": "run",
    "line": 165,
    "context": {
        "tool_name": "delete_ticket",
        "tool_args": {"ticket_id": "TKT-20260520123"},
        "approval_id": "8ce28d77-xxx",
        "reason": "用户要求删除工单",
        "approval_timeout": 300.0,
    },
    "metadata": {"app_version": "1.0.0", "env": "production"},
}

print_log("HITL 审批请求", hitl_approval_request)


# ============================================================
# 示例 5: HITL 审批通过
# ============================================================

print_separator("示例 5: HITL 审批通过")

hitl_approval_approved = {
    "timestamp": "2026-05-20T14:30:48.200",
    "level": "INFO",
    "logger": "service",
    "message": "approval_approved",
    "rid": "a1b2c3d4e5f6",
    "session_id": "session-001",
    "user_id": "user-123",
    "event": "approval_approved",
    "event_category": "hitl",
    "event_action": "approved",
    "module": "hitl",
    "function": "approve",
    "line": 120,
    "context": {
        "approval_id": "8ce28d77-xxx",
        "tool_name": "delete_ticket",
        "reviewer": "manager-001",
        "wait_duration_ms": 2100,
    },
    "metadata": {"app_version": "1.0.0", "env": "production"},
}

print_log("HITL 审批通过", hitl_approval_approved)


# ============================================================
# 示例 6: Checkpoint 保存
# ============================================================

print_separator("示例 6: Checkpoint 保存")

checkpoint_saved = {
    "timestamp": "2026-05-20T14:30:45.200",
    "level": "INFO",
    "logger": "service",
    "message": "checkpoint_saved",
    "rid": "a1b2c3d4e5f6",
    "session_id": "session-001",
    "user_id": "user-123",
    "event": "checkpoint_saved",
    "event_category": "checkpoint",
    "event_action": "saved",
    "module": "checkpoint",
    "function": "save",
    "line": 85,
    "context": {
        "checkpoint_id": "69592743-xxx",
        "description": "Agent 调用前",
        "conversation_history_length": 2,
        "tool_calls_count": 1,
    },
    "metadata": {"app_version": "1.0.0", "env": "production"},
}

print_log("Checkpoint 保存", checkpoint_saved)


# ============================================================
# 示例 7: 模型降级触发
# ============================================================

print_separator("示例 7: 模型降级触发 (警告)")

model_fallback = {
    "timestamp": "2026-05-20T14:30:47.300",
    "level": "WARN",
    "logger": "service",
    "message": "model_fallback_triggered",
    "rid": "a1b2c3d4e5f6",
    "session_id": "session-001",
    "user_id": "user-123",
    "event": "model_fallback_triggered",
    "event_category": "model",
    "event_action": "fallback_triggered",
    "module": "model_routing",
    "function": "execute_fallback",
    "line": 95,
    "context": {
        "original_model": "gpt-4",
        "fallback_model": "qwen3.5-plus",
        "reason": "rate_limit_exceeded",
        "retry_count": 3,
        "error_message": "API rate limit exceeded",
    },
    "performance": {"fallback_delay_ms": 500},
    "metadata": {"app_version": "1.0.0", "env": "production"},
}

print_log("模型降级触发", model_fallback)


# ============================================================
# 示例 8: 记忆检索
# ============================================================

print_separator("示例 8: 记忆检索")

memory_retrieval = {
    "timestamp": "2026-05-20T14:30:45.050",
    "level": "INFO",
    "logger": "service",
    "message": "memory_retrieved",
    "rid": "a1b2c3d4e5f6",
    "session_id": "session-001",
    "user_id": "user-123",
    "event": "memory_retrieved",
    "event_category": "memory",
    "event_action": "retrieved",
    "module": "memory_manager",
    "function": "get_context",
    "line": 120,
    "context": {
        "memory_type": "long_term",
        "retrieved_turns": 3,
        "relevance_scores": [0.95, 0.87, 0.72],
        "total_memories_in_store": 156,
    },
    "performance": {"retrieval_duration_ms": 45},
    "metadata": {"app_version": "1.0.0", "env": "production"},
}

print_log("记忆检索", memory_retrieval)


# ============================================================
# 示例 9: 敏感信息脱敏
# ============================================================

print_separator("示例 9: 敏感信息脱敏")

sensitive_data_sanitized = {
    "timestamp": "2026-05-20T14:30:45.080",
    "level": "DEBUG",
    "logger": "service",
    "message": "api_request_sent",
    "rid": "a1b2c3d4e5f6",
    "event": "api_request_sent",
    "event_category": "agent",
    "event_action": "request_sent",
    "context": {
        "api_key": "sk-liv***xyz",
        "user_email": "use***@example.com",
        "phone": "138***1234",
        "id_card": "110101***001X",
        "password": "***",
        "authorization": "Bear***xyz",
    },
    "metadata": {"app_version": "1.0.0", "env": "production"},
}

print_log("敏感信息脱敏", sensitive_data_sanitized)


# ============================================================
# 示例 10: Handoff Agent 路由
# ============================================================

print_separator("示例 10: Handoff Agent 路由")

handoff_routing = {
    "timestamp": "2026-05-20T14:30:46.000",
    "level": "INFO",
    "logger": "service",
    "message": "handoff_routing",
    "rid": "a1b2c3d4e5f6",
    "session_id": "session-001",
    "user_id": "user-123",
    "event": "handoff_routing",
    "event_category": "agent",
    "event_action": "handoff",
    "module": "handoff",
    "function": "route_to_agent",
    "line": 150,
    "context": {
        "triage_agent": "customer_service",
        "target_agent": "tech_support",
        "routing_reason": "technical_issue",
        "available_agents": ["tech_support", "billing", "general"],
        "handoff_count": 1,
    },
    "metadata": {"app_version": "1.0.0", "env": "production"},
}

print_log("Handoff Agent 路由", handoff_routing)


# ============================================================
# 总结
# ============================================================

print_separator("日志格式总结")

print("""
✅ 标准化字段:
   - timestamp: ISO 8601 格式时间戳
   - level: 日志级别 (DEBUG/INFO/WARN/ERROR/CRITICAL)
   - logger: 日志器名称
   - message: 日志消息
   - rid: 请求 ID (追踪整个请求链路)
   - session_id: 会话 ID
   - user_id: 用户 ID
   - event: 事件名称
   - event_category: 事件分类
   - event_action: 事件动作
   - context: 业务上下文
   - performance: 性能指标
   - metadata: 元数据

✅ 事件分类:
   - agent: Agent 相关
   - tool: 工具调用
   - memory: 记忆系统
   - model: 模型调用
   - hitl: 人工审批
   - checkpoint: 检查点
   - error: 错误

✅ 敏感信息脱敏:
   - api_key: sk-liv***xyz
   - email: use***@example.com
   - phone: 138***1234
   - password: ***

✅ 性能指标:
   - duration_ms: 耗时
   - tokens_*: Token 使用量
   - cost_usd: 成本

✅ 日志级别规范:
   - DEBUG: 调试信息
   - INFO: 正常流程
   - WARN: 警告但不影响
   - ERROR: 错误但可恢复
   - CRITICAL: 严重错误
""")

print("=" * 80)
print("🎉 结构化日志示例演示完成!")
print("=" * 80 + "\n")
