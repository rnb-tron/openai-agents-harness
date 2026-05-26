"""
模型弹性调用集成示例

展示如何使用可插拔的降级、重试、超时能力

运行本文件需要配置可访问的模型服务和 API Key。
"""

import asyncio
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# 加载配置
env_file = Path(__file__).parent.parent / "config" / "test.env"
from dotenv import load_dotenv
load_dotenv(env_file, override=True)

from agents import Agent, AsyncOpenAI, OpenAIChatCompletionsModel, Runner
from src.capabilities.model_routing import (
    FallbackConfig,
    ResilienceConfig,
    RetryConfig,
    TimeoutConfig,
    ModelRouter,
)


# ========================================
# 示例 1: 仅启用降级
# ========================================

async def example_fallback_only():
    """示例 1: 仅启用模型降级"""
    print("=" * 60)
    print("示例 1: 仅启用模型降级")
    print("=" * 60)
    
    # 配置: 只启用降级
    config = ResilienceConfig(
        enabled=True,
        fallback=FallbackConfig(
            enabled=True,
            models=["qwen3.5-plus", "gpt-4o-mini"],  # 降级链路
        ),
        retry=RetryConfig(enabled=False),  # 不启用重试
        timeout=TimeoutConfig(enabled=False),  # 不启用超时
    )
    
    # 创建路由器
    router = ModelRouter(
        default_model="qwen3.5-plus",
        resilience_config=config,
    )
    
    # 创建 OpenAI 客户端
    client = AsyncOpenAI(
        api_key=os.getenv("OPENAI_API_KEY"),
        base_url=os.getenv("OPENAI_BASE_URL"),
    )
    
    # 弹性执行
    async def create_agent(model):
        return Runner.run(
            Agent(
                name="Test",
                instructions="You are a helpful assistant.",
                model=OpenAIChatCompletionsModel(model=model, openai_client=client),
            ),
            "Say hello",
        )
    
    result = await router.run_with_resilience(create_agent)
    print(f"✅ 结果: {result.final_output}")
    print(f"📊 指标: {router.last_metrics}")
    print()


# ========================================
# 示例 2: 降级 + 重试
# ========================================

async def example_fallback_with_retry():
    """示例 2: 降级 + 重试"""
    print("=" * 60)
    print("示例 2: 降级 + 重试")
    print("=" * 60)
    
    # 配置: 降级 + 重试
    config = ResilienceConfig(
        enabled=True,
        fallback=FallbackConfig(
            enabled=True,
            models=["qwen3.5-plus", "gpt-4o-mini"],
        ),
        retry=RetryConfig(
            enabled=True,
            max_retries=2,
            initial_delay=1.0,
            max_delay=5.0,
        ),
        timeout=TimeoutConfig(enabled=False),
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
                instructions="You are a helpful assistant.",
                model=OpenAIChatCompletionsModel(model=model, openai_client=client),
            ),
            "What is 2+2?",
        )
    
    result = await router.run_with_resilience(create_agent)
    print(f"✅ 结果: {result.final_output}")
    print(f"📊 指标:")
    print(f"   - 使用模型: {router.last_metrics.success_model}")
    print(f"   - 耗时: {router.last_metrics.total_duration:.2f}s")
    print(f"   - 降级次数: {router.last_metrics.fallback_count}")
    print()


# ========================================
# 示例 3: 完整弹性配置 (降级 + 重试 + 超时)
# ========================================

async def example_full_resilience():
    """示例 3: 完整弹性配置"""
    print("=" * 60)
    print("示例 3: 完整弹性配置 (降级 + 重试 + 超时)")
    print("=" * 60)
    
    # 配置: 降级 + 重试 + 超时
    config = ResilienceConfig(
        enabled=True,
        fallback=FallbackConfig(
            enabled=True,
            models=["qwen3.5-plus", "gpt-4o-mini"],
        ),
        retry=RetryConfig(
            enabled=True,
            max_retries=2,
            initial_delay=1.0,
        ),
        timeout=TimeoutConfig(
            enabled=True,
            total_timeout=30.0,  # 总超时 30 秒
            per_request_timeout=10.0,  # 单次请求超时 10 秒
        ),
    )
    
    router = ModelRouter(
        default_model="qwen3.5-plus",
        reasoning_model="gpt-4o-mini",
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
                instructions="You are a helpful assistant.",
                model=OpenAIChatCompletionsModel(model=model, openai_client=client),
            ),
            "Tell me a joke",
        )
    
    result = await router.run_with_resilience(create_agent, task_type="reasoning")
    print(f"✅ 结果: {result.final_output}")
    print(f"📊 完整指标:")
    metrics = router.last_metrics
    print(f"   - 尝试的模型: {metrics.models_tried}")
    print(f"   - 成功模型: {metrics.success_model}")
    print(f"   - 总耗时: {metrics.total_duration:.2f}s")
    print(f"   - 降级次数: {metrics.fallback_count}")
    print()


# ========================================
# 示例 4: 不启用弹性 (默认行为)
# ========================================

async def example_no_resilience():
    """示例 4: 不启用弹性 (默认行为)"""
    print("=" * 60)
    print("示例 4: 不启用弹性 (默认行为)")
    print("=" * 60)
    
    # 不配置弹性,使用默认路由器
    router = ModelRouter(
        default_model="qwen3.5-plus",
    )
    
    client = AsyncOpenAI(
        api_key=os.getenv("OPENAI_API_KEY"),
        base_url=os.getenv("OPENAI_BASE_URL"),
    )
    
    async def create_agent(model):
        return Runner.run(
            Agent(
                name="Test",
                instructions="You are a helpful assistant.",
                model=OpenAIChatCompletionsModel(model=model, openai_client=client),
            ),
            "Say hi",
        )
    
    result = await router.run_with_resilience(create_agent)
    print(f"✅ 结果: {result.final_output}")
    print()


# ========================================
# 运行所有示例
# ========================================

async def main():
    """运行所有示例"""
    print("\n")
    print("🚀 模型弹性调用示例")
    print("=" * 60)
    print()
    
    # 示例 1: 仅降级
    await example_fallback_only()
    
    # 示例 2: 降级 + 重试
    await example_fallback_with_retry()
    
    # 示例 3: 完整配置
    await example_full_resilience()
    
    # 示例 4: 不启用弹性
    await example_no_resilience()
    
    print("=" * 60)
    print("🎉 所有示例运行完成!")
    print()
    print("💡 提示:")
    print("  - 可插拔设计: 可选择性启用降级、重试、超时")
    print("  - 灵活配置: 自定义降级链路、重试策略、超时时间")
    print("  - 指标追踪: 自动记录执行指标 (模型、耗时、降级次数)")
    print()


if __name__ == "__main__":
    asyncio.run(main())
