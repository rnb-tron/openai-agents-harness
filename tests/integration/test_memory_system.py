#!/usr/bin/env python3
"""
Memory System 功能测试脚本
"""

import asyncio
import sys
from pathlib import Path

import pytest

# 添加项目路径
sys.path.insert(0, str(Path(__file__).parents[2]))

from src.capabilities.memory.store import ShortTermMemory
from src.capabilities.memory.models import MemoryRecord


async def test_short_term_memory():
    """测试短期记忆"""
    print("\n🧪 测试 1: Short-Term Memory (无 Redis 不做内存兜底)")
    print("-" * 50)
    
    memory = ShortTermMemory(redis_client=None, ttl=3600)
    
    # 没有 Redis 时 append 成功但不在进程内保存，读取应回源 MySQL。
    await memory.append("session1", "user", "你好")
    await memory.append("session1", "assistant", "你好!有什么我可以帮你的吗?")
    await memory.append("session1", "user", "Python怎么用?")
    
    memories = await memory.get_recent("session1", max_turns=2)
    print(f"✅ 无 Redis 时短期缓存读取到 {len(memories)} 条")
    assert memories == []
    
    # 测试TTL
    ttl = await memory.get_ttl("session1")
    print(f"✅ TTL: {ttl}秒")
    assert ttl == -2
    
    # 清空记忆
    await memory.clear("session1")
    memories_after = await memory.get_recent("session1")
    print(f"✅ 清空后记忆数量: {len(memories_after)}")
    assert len(memories_after) == 0
    
    print("✅ Short-Term Memory 测试通过!\n")


async def test_memory_record_model():
    """测试MemoryRecord模型"""
    print("🧪 测试 2: MemoryRecord 数据模型")
    print("-" * 50)
    
    # 测试模型创建(不实际写入数据库)
    record = MemoryRecord(
        id=123456789,
        user_id="test_user",
        session_id="test_session",
        memory_type="long_term",
        role="user",
        content="这是一条测试记忆",
        importance_score=0.8,
    )
    
    print(f"✅ 创建MemoryRecord对象成功")
    print(f"  - ID: {record.id}")
    print(f"  - User: {record.user_id}")
    print(f"  - Type: {record.memory_type}")
    print(f"  - Content: {record.content}")
    
    # 测试to_dict方法
    record_dict = record.to_dict()
    print(f"✅ to_dict() 方法正常: {len(record_dict)} 个字段")
    assert "metadata" in record_dict
    
    print("✅ MemoryRecord 模型测试通过!\n")


async def test_context_manager_import():
    """测试Context Manager导入"""
    print("🧪 测试 3: Context Manager 模块导入")
    print("-" * 50)
    
    try:
        from src.capabilities.memory.context_manager import ContextManager
        from src.capabilities.memory.lifecycle import MemoryLifecycleManager
        from src.capabilities.memory.vector_store import ElasticsearchVectorStore
        from src.capabilities.memory.manager import MemoryManager
        
        print("✅ ContextManager 导入成功")
        print("✅ MemoryLifecycleManager 导入成功")
        print("✅ ElasticsearchVectorStore 导入成功")
        print("✅ MemoryManager 导入成功")
        print("✅ Context Manager 模块测试通过!\n")
        
    except ImportError as e:
        print(f"❌ 导入失败: {e}")
        raise


async def test_api_endpoints():
    """测试API端点"""
    pytest.skip("requires a running FastAPI server at localhost:8080")
    print("🧪 测试 4: API 端点可用性")
    print("-" * 50)
    
    import httpx
    
    base_url = "http://localhost:8080"
    
    async with httpx.AsyncClient() as client:
        # 测试健康检查
        response = await client.get(f"{base_url}/health/ok")
        assert response.status_code == 200
        print(f"✅ GET /health/ok - {response.status_code}")
        
        # 测试Memory Stats
        response = await client.get(f"{base_url}/memory/stats")
        assert response.status_code == 200
        print(f"✅ GET /memory/stats - {response.status_code}")
        
        # 测试Memory Cleanup
        response = await client.post(f"{base_url}/memory/cleanup")
        assert response.status_code == 200
        print(f"✅ POST /memory/cleanup - {response.status_code}")
    
    print("✅ API 端点测试通过!\n")


async def main():
    """运行所有测试"""
    print("\n" + "=" * 50)
    print("🚀 Memory System 功能测试开始")
    print("=" * 50)
    
    try:
        await test_short_term_memory()
        await test_memory_record_model()
        await test_context_manager_import()
        await test_api_endpoints()
        
        print("=" * 50)
        print("🎉 所有测试通过! Memory系统运行正常!")
        print("=" * 50 + "\n")
        
        return True
        
    except Exception as e:
        print(f"\n❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)
