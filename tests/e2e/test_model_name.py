"""测试模型名称在 Langfuse 中的显示"""

import os
from pathlib import Path
from dotenv import load_dotenv
import pytest

env_file = Path(__file__).parents[2] / "config" / "test.env"
load_dotenv(env_file, override=True)

pytestmark = pytest.mark.skipif(
    os.getenv("RUN_EXTERNAL_TESTS", "false").lower() != "true",
    reason="requires external OpenAI/Langfuse services; set RUN_EXTERNAL_TESTS=true",
)

import asyncio
from agents import Agent, Runner, trace


async def test_model_name():
    """测试模型名称"""
    print("=" * 60)
    print("测试模型名称追踪")
    print("=" * 60)
    
    # 初始化可观测系统
    from src.capabilities.observability import init_observability, ObservabilityConfig
    config = ObservabilityConfig.from_env()
    await init_observability(config)
    
    print()
    print(f"📋 配置的模型: qwen3.5-plus")
    print()
    
    # 方式 1: 使用默认模型 (让 SDK 自动选择)
    print("📤 测试 1: 使用默认模型")
    agent1 = Agent(
        name="Assistant",
        instructions="You are a helpful assistant.",
    )
    result1 = await Runner.run(agent1, "Say hello")
    print(f"🤖 回答: {result1.final_output}")
    print()
    
    # 方式 2: 显式指定模型
    print("📤 测试 2: 显式指定模型为 qwen3.5-plus")
    agent2 = Agent(
        name="Assistant",
        instructions="You are a helpful assistant.",
        model="qwen3.5-plus",  # 显式指定
    )
    result2 = await Runner.run(agent2, "Say hello")
    print(f"🤖 回答: {result2.final_output}")
    print()
    
    print("✅ 测试完成!")
    print()
    print("📊 请查看 Langfuse Dashboard:")
    print("   http://agent-otel-test.ke.com")
    print()
    print("检查:")
    print("  - 测试 1 的模型名称显示为什么?")
    print("  - 测试 2 的模型名称是否显示为 'qwen3.5-plus'?")
    
    # 关闭
    from src.capabilities.observability import shutdown_observability
    await shutdown_observability()


if __name__ == "__main__":
    asyncio.run(test_model_name())
