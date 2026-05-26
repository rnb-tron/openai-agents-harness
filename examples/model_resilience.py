"""使用 Harness 同一组环境配置执行一次模型弹性调用。

运行前在 ``config/test.env`` 或环境变量中配置模型服务。通过
``MODEL_RESILIENCE_ENABLED``、``MODEL_FALLBACK_*``、``MODEL_RETRY_*`` 与
``MODEL_TIMEOUT_*`` 切换策略，本示例不自行写死供应商模型名称。
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agents import Agent, AsyncOpenAI, OpenAIChatCompletionsModel, Runner

from src.capabilities.model_routing import ModelRouter, ResilienceConfig
from src.core.config import current_settings


def build_router() -> ModelRouter:
    return ModelRouter(
        default_model=current_settings.agent_model_default,
        reasoning_model=current_settings.agent_model_reasoning,
        resilience_config=ResilienceConfig.from_env(),
    )


async def main() -> None:
    config = ResilienceConfig.from_env()
    router = build_router()
    client = AsyncOpenAI(
        api_key=current_settings.openai_api_key,
        base_url=current_settings.openai_base_url,
    )

    async def run_with_model(model: str):
        sdk_model = OpenAIChatCompletionsModel(model=model, openai_client=client)
        agent = Agent(
            name="resilience-example",
            instructions="Answer briefly and clearly.",
            model=sdk_model,
        )
        return Runner.run(agent, "Explain model fallback in one sentence.")

    print("模型弹性示例配置：")
    print(f"- default model: {current_settings.agent_model_default}")
    print(f"- reasoning model: {current_settings.agent_model_reasoning}")
    print(f"- resilience enabled: {config.enabled}")
    print(f"- fallback models: {config.fallback.models or '[initial selected model]'}")
    print(f"- retry enabled: {config.retry.enabled}")
    print(f"- timeout enabled: {config.timeout.enabled}")

    result = await router.run_with_resilience(run_with_model, task_type="reasoning")
    print(f"\n响应：{result.final_output}")

    metrics = router.last_metrics
    if metrics is None:
        print("\n弹性 runner 未启用，因此本次没有 ExecutionMetrics。")
        return
    print("\n执行指标：")
    print(f"- models tried: {metrics.models_tried}")
    print(f"- success model: {metrics.success_model}")
    print(f"- fallback count: {metrics.fallback_count}")
    print(f"- duration: {metrics.total_duration:.2f}s")


if __name__ == "__main__":
    asyncio.run(main())
