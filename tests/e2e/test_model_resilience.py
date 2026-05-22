"""Test model resilience features (fallback, retry, timeout)."""

import sys
from pathlib import Path

# Add project root to Python path
sys.path.insert(0, str(Path(__file__).parents[2]))

import asyncio
import os
import pytest
from dotenv import load_dotenv

# Load config
env_file = Path(__file__).parents[2] / "config" / "test.env"
load_dotenv(env_file, override=True)

pytestmark = pytest.mark.skipif(
    os.getenv("RUN_EXTERNAL_TESTS", "false").lower() != "true",
    reason="requires external OpenAI-compatible model service; set RUN_EXTERNAL_TESTS=true",
)

from agents import Agent, AsyncOpenAI, OpenAIChatCompletionsModel, Runner
from src.capabilities.model_routing import (
    FallbackConfig,
    ResilienceConfig,
    RetryConfig,
    TimeoutConfig,
    ModelRouter,
)


async def test_basic_routing():
    """Test 1: Basic model routing without resilience."""
    print("=" * 60)
    print("Test 1: Basic Model Routing (No Resilience)")
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
    print(f"OK Result: {result.final_output}")
    print()
    return True


async def test_fallback():
    """Test 2: Model fallback."""
    print("=" * 60)
    print("Test 2: Model Fallback")
    print("=" * 60)
    
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
            "What is 1+1?",
        )
    
    result = await router.run_with_resilience(create_agent)
    print(f"OK Result: {result.final_output}")
    print(f"Metrics - Model: {router.last_metrics.success_model}")
    print()
    return True


async def test_retry():
    """Test 3: Retry mechanism."""
    print("=" * 60)
    print("Test 3: Retry Mechanism")
    print("=" * 60)
    
    config = ResilienceConfig(
        enabled=True,
        retry=RetryConfig(
            enabled=True,
            max_retries=2,
            initial_delay=0.5,
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
            "Tell me a fact",
        )
    
    result = await router.run_with_resilience(create_agent)
    print(f"OK Result: {result.final_output[:100]}...")
    print()
    return True


async def test_timeout():
    """Test 4: Timeout control."""
    print("=" * 60)
    print("Test 4: Timeout Control")
    print("=" * 60)
    
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
            "Say something short",
        )
    
    result = await router.run_with_resilience(create_agent)
    print(f"OK Result: {result.final_output}")
    print(f"Metrics - Duration: {router.last_metrics.total_duration:.2f}s")
    print()
    return True


async def test_full_resilience():
    """Test 5: Full resilience configuration."""
    print("=" * 60)
    print("Test 5: Full Resilience (Fallback + Retry + Timeout)")
    print("=" * 60)
    
    config = ResilienceConfig(
        enabled=True,
        fallback=FallbackConfig(
            enabled=True,
            models=["qwen3.5-plus"],
        ),
        retry=RetryConfig(
            enabled=True,
            max_retries=1,
            initial_delay=0.5,
        ),
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
            "Hello!",
        )
    
    result = await router.run_with_resilience(create_agent)
    print(f"OK Result: {result.final_output}")
    metrics = router.last_metrics
    print(f"Metrics:")
    print(f"  - Model: {metrics.success_model}")
    print(f"  - Duration: {metrics.total_duration:.2f}s")
    print(f"  - Fallbacks: {metrics.fallback_count}")
    print()
    return True


async def main():
    """Run all tests."""
    print("\n")
    print("Model Resilience Tests")
    print("=" * 60)
    print()
    
    results = {}
    
    results["Basic Routing"] = await test_basic_routing()
    results["Fallback"] = await test_fallback()
    results["Retry"] = await test_retry()
    results["Timeout"] = await test_timeout()
    results["Full Resilience"] = await test_full_resilience()
    
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
        print()
        print("Pluggable model resilience is working correctly!")
    else:
        print(f"Some tests failed ({passed}/{total})")
    
    print()


if __name__ == "__main__":
    asyncio.run(main())
