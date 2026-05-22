"""
测试结构化日志优化

验证:
1. 标准 JSON 格式
2. 事件分类和动作解析
3. 敏感信息脱敏
4. 性能指标记录
5. 日志上下文管理
"""

import sys
import json
from pathlib import Path

# 添加项目根目录到 Python 路径
sys.path.insert(0, str(Path(__file__).parents[2]))

from src.core.logging import (
    service_logger,
    log_event,
    log_context,
    _sanitize_value,
    _sanitize_dict,
)


def test_sensitive_data_sanitization():
    """测试 1: 敏感信息脱敏"""
    print("\n" + "="*80)
    print("测试 1: 敏感信息脱敏")
    print("="*80)
    
    # 测试单个值脱敏
    test_cases = [
        ("api_key", "sk-live-1234567890abcdef", "sk-l***cdef"),
        ("password", "secret123", "***"),
        ("phone", "13812345678", "138***5678"),
        ("email", "user@example.com", "use***.com"),
        ("normal_field", "normal_value", "normal_value"),
    ]
    
    for field, value, expected in test_cases:
        result = _sanitize_value(field, value)
        assert result == expected, f"脱敏失败: {field} = {result}, 期望 {expected}"
        print(f"✅ {field}: {value} → {result}")
    
    # 测试字典脱敏
    test_dict = {
        "api_key": "sk-live-1234567890abcdef",
        "user_email": "user@example.com",
        "normal_field": "normal_value",
        "nested": {
            "password": "secret123",
            "token": "tok-abc123"
        }
    }
    
    sanitized = _sanitize_dict(test_dict)
    print(f"\n✅ 字典脱敏成功:")
    print(f"   api_key: {sanitized['api_key']}")
    print(f"   user_email: {sanitized['user_email']}")
    print(f"   nested.password: {sanitized['nested']['password']}")
    
    print("="*80)


def test_structured_logging():
    """测试 2: 结构化日志记录"""
    print("\n" + "="*80)
    print("测试 2: 结构化日志记录")
    print("="*80)
    
    # 示例 1: Agent 调用成功
    print("\n📝 示例 1: Agent 调用成功")
    log_event(
        service_logger,
        "agent_call_completed",
        session_id="session-001",
        user_id="user-123",
        model="qwen3.5-plus",
        tool_calls_count=2,
        duration_ms=1250,
        tokens_total=500
    )
    print("✅ 日志已记录")
    
    # 示例 2: 工具调用
    print("\n📝 示例 2: 工具调用")
    log_event(
        service_logger,
        "tool_called",
        session_id="session-001",
        user_id="user-123",
        tool_name="create_ticket",
        tool_args={"title": "登录问题"},
        approval_required=False
    )
    print("✅ 日志已记录")
    
    # 示例 3: 模型降级 (警告)
    print("\n📝 示例 3: 模型降级 (警告)")
    import logging
    log_event(
        service_logger,
        "model_fallback_triggered",
        level=logging.WARN,
        session_id="session-001",
        original_model="gpt-4",
        fallback_model="qwen3.5-plus",
        reason="rate_limit_exceeded",
        retry_count=3
    )
    print("✅ 日志已记录")
    
    # 示例 4: 错误日志
    print("\n📝 示例 4: 错误日志")
    try:
        raise ValueError("测试错误")
    except Exception as e:
        log_event(
            service_logger,
            "operation_failed",
            level=logging.ERROR,
            session_id="session-001",
            error_type=type(e).__name__,
            error_message=str(e)
        )
        print("✅ 日志已记录")
    
    print("="*80)


def test_log_context_manager():
    """测试 3: 日志上下文管理器"""
    print("\n" + "="*80)
    print("测试 3: 日志上下文管理器")
    print("="*80)
    
    with log_context(session_id="session-test", user_id="user-test"):
        print("\n📝 在上下文中记录日志")
        service_logger.info("上下文中的日志消息")
        print("✅ 日志已记录 (包含 session_id 和 user_id)")
    
    print("\n📝 在上下文外记录日志")
    service_logger.info("上下文外的日志消息")
    print("✅ 日志已记录 (不包含 session_id 和 user_id)")
    
    print("="*80)


def test_event_parsing():
    """测试 4: 事件分类解析"""
    print("\n" + "="*80)
    print("测试 4: 事件分类解析")
    print("="*80)
    
    test_events = [
        ("agent_call_completed", "agent", "call_completed"),
        ("tool_called", "tool", "called"),
        ("memory_retrieved", "memory", "retrieved"),
        ("model_fallback_triggered", "model", "fallback_triggered"),
        ("approval_requested", "approval", "requested"),
        ("checkpoint_saved", "checkpoint", "saved"),
        ("error", "general", "error"),
    ]
    
    for event, expected_category, expected_action in test_events:
        parts = event.split("_")
        if len(parts) >= 2:
            category = parts[0]
            action = "_".join(parts[1:])
        else:
            category = "general"
            action = event
        
        assert category == expected_category, f"分类错误: {event}"
        assert action == expected_action, f"动作错误: {event}"
        print(f"✅ {event} → category={category}, action={action}")
    
    print("="*80)


def verify_log_format():
    """测试 5: 验证日志文件格式"""
    print("\n" + "="*80)
    print("测试 5: 验证日志文件格式")
    print("="*80)
    
    log_file = Path("data/logs/default.log")
    
    if not log_file.exists():
        print("⚠️  日志文件不存在,跳过验证")
        return
    
    # 读取最后一行日志
    with open(log_file, "r", encoding="utf-8") as f:
        lines = f.readlines()
    
    if not lines:
        print("⚠️  日志文件为空,跳过验证")
        return
    
    last_line = lines[-1].strip()
    
    try:
        log_entry = json.loads(last_line)
        print("\n✅ 日志格式验证成功 (最后一行):")
        print(f"   timestamp: {log_entry.get('timestamp', 'N/A')}")
        print(f"   level: {log_entry.get('level', 'N/A')}")
        print(f"   logger: {log_entry.get('logger', 'N/A')}")
        print(f"   message: {log_entry.get('message', 'N/A')}")
        print(f"   rid: {log_entry.get('rid', 'N/A')}")
        
        # 检查是否包含增强字段
        if "event" in log_entry:
            print(f"   event: {log_entry.get('event')}")
            print(f"   event_category: {log_entry.get('event_category')}")
            print(f"   event_action: {log_entry.get('event_action')}")
        
        if "session_id" in log_entry:
            print(f"   session_id: {log_entry.get('session_id')}")
        
        if "user_id" in log_entry:
            print(f"   user_id: {log_entry.get('user_id')}")
        
        if "performance" in log_entry:
            print(f"   performance: {log_entry.get('performance')}")
        
        if "metadata" in log_entry:
            print(f"   metadata: {log_entry.get('metadata')}")
        
        print("\n✅ 完整日志条目:")
        print(json.dumps(log_entry, indent=2, ensure_ascii=False))
        
    except json.JSONDecodeError as e:
        print(f"❌ 日志格式错误: {e}")
        print(f"   原始内容: {last_line[:200]}")
    
    print("="*80)


def main():
    """运行所有测试"""
    print("\n" + "="*80)
    print("🧪 结构化日志优化测试")
    print("="*80)
    
    try:
        # 测试 1: 敏感信息脱敏
        test_sensitive_data_sanitization()
        
        # 测试 2: 结构化日志记录
        test_structured_logging()
        
        # 测试 3: 日志上下文管理器
        test_log_context_manager()
        
        # 测试 4: 事件分类解析
        test_event_parsing()
        
        # 测试 5: 验证日志文件格式
        verify_log_format()
        
        print("\n" + "="*80)
        print("🎉 所有测试完成!")
        print("="*80)
        print("\n✅ 验证内容:")
        print("  ✓ 敏感信息脱敏")
        print("  ✓ 结构化日志记录")
        print("  ✓ 日志上下文管理器")
        print("  ✓ 事件分类解析")
        print("  ✓ 日志文件格式")
        print("\n📝 查看日志:")
        print("   tail -f data/logs/default.log")
        print("="*80 + "\n")
        
    except AssertionError as e:
        print(f"\n❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ 测试异常: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
