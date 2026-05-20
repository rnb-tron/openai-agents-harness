"""简化版测试 - 避免触发限流"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import asyncio
import os
from dotenv import load_dotenv

env_file = Path(__file__).parent.parent / "config" / "test.env"
load_dotenv(env_file, override=True)

import time
from agents import Agent, AsyncOpenAI, OpenAIChatCompletionsModel, Runner
from src.capabilities.model_routing import (
    FallbackConfig,
    ResilienceConfig,
    RetryConfig,
    TimeoutConfig,
    ModelRouter,
)


async def test_1_basic():
    """Test 1: 基本路由"""
    print("=" * 60)
    print("Test 1: Basic Routing (No Resilience)")
    print("=" * 60)
    
    router = ModelRouter(default_model="qwen3.5-plus")
    
    client = AsyncOpenAI(
        api_key=os.getenv("OPENAI_API_KEY"),
        base_url=os.getenv("OPENAI_BASE_URL"),
    )
    
    async def create_agent(model):
        return Runner.run(
            Agent(
                name="Test",
                instructions="You are helpful.",
                model=OpenAIChatCompletionsModel(model=model, openai_client=client),
            ),
            "Say hello",
        )
    
    result = await router.run_with_resilience(create_agent)
    print(f"OK: {result.final_output}")
    print()
    return True


async def test_2_with_delay():
    """Test 2: 带延迟的测试 (避免限流)"""
    print("=" * 60)
    print("Test 2: Fallback Configuration")
    print("=" * 60)
    
    # 等待限流重置
    print("Waiting 15s for rate limit reset...")
    await asyncio.sleep(15)
    
    config = ResilienceConfig(
        enabled=True,
        fallback=FallbackConfig(
            enabled=True,
            models=["qwen3.5-plus"],
        ),
    )
    
    router = ModelRouter(
        default_model="qwen3.5-plus",
        resilience_config=config,
    )
    
    client = AsyncOpenAI(
        api_key=os.getenv("OPENAI_API_KEY"),
        base_url=os.getenv("OPENAI_BASE_URL"),
    )
    
    async def create_agent(model):
        return Runner.run(
            Agent(
                name="Test",
                instructions="You are helpful.",
                model=OpenAIChatCompletionsModel(model=model, openai_client=client),
            ),
            "What is 2+2?",
        )
    
    try:
        result = await router.run_with_resilience(create_agent)
        print(f"OK: {result.final_output}")
        print(f"Metrics - Model: {router.last_metrics.success_model}")
        print(f"Metrics - Duration: {router.last_metrics.total_duration:.2f}s")
        print()
        return True
    except Exception as e:
        print(f"Error: {e}")
        print()
        return False


async def test_3_timeout():
    """Test 3: 超时配置"""
    print("=" * 60)
    print("Test 3: Timeout Configuration")
    print("=" * 60)
    
    # 等待限流重置
    print("Waiting 15s for rate limit reset...")
    await asyncio.sleep(15)
    
    config = ResilienceConfig(
        enabled=True,
        timeout=TimeoutConfig(
            enabled=True,
            total_timeout=30.0,
        ),
    )
    
    router = ModelRouter(
        default_model="qwen3.5-plus",
        resilience_config=config,
    )
    
    client = AsyncOpenAI(
        api_key=os.getenv("OPENAI_API_KEY"),
        base_url=os.getenv("OPENAI_BASE_URL"),
    )
    
    async def create_agent(model):
        return Runner.run(
            Agent(
                name="Test",
                instructions="You are helpful.",
                model=OpenAIChatCompletionsModel(model=model, openai_client=client),
            ),
            "Tell me something short",
        )
    
    try:
        result = await router.run_with_resilience(create_agent)
        print(f"OK: {result.final_output}")
        print(f"Metrics - Duration: {router.last_metrics.total_duration:.2f}s")
        print()
        return True
    except Exception as e:
        print(f"Error: {e}")
        print()
        return False


async def main():
    """Run tests with delays."""
    print("\n")
    print("Model Resilience Tests (Rate Limit Aware)")
    print("=" * 60)
    print()
    
    results = {}
    
    # Test 1
    results["Basic"] = await test_1_basic()
    
    # Test 2 (with delay)
    results["Fallback"] = await test_2_with_delay()
    
    # Test 3 (with delay)
    results["Timeout"] = await test_3_timeout()
    
    # Summary
    print("=" * 60)
    print("Test Results Summary")
    print("=" * 60)
    
    for name, success in results.items():
        status = "PASS" if success else "FAIL"
        print(f"{name:20s} {status}")
    
    print()
    
    passed = sum(1 for s in results.values() if s)
    total = len(results)
    
    if passed == total:
        print(f"All tests passed! ({passed}/{total})")
    else:
        print(f"Some tests failed ({passed}/{total})")
    
    print()


if __name__ == "__main__":
    asyncio.run(main())
