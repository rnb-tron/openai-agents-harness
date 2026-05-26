"""通过当前 Observability 能力执行 SDK 与自定义 span 演示。

运行前配置可访问的模型服务；只有 ``LANGFUSE_ENABLED=true`` 且凭证有效时，
本示例才初始化远端导出与 Agents SDK instrumentation。
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agents import Agent, AsyncOpenAI, OpenAIChatCompletionsModel, Runner, function_tool, trace

from src.capabilities.observability import (
    ObservabilityConfig,
    init_observability,
    measure_time,
    observe,
    shutdown_observability,
)
from src.core.config import current_settings


def build_model() -> OpenAIChatCompletionsModel:
    client = AsyncOpenAI(
        api_key=current_settings.openai_api_key,
        base_url=current_settings.openai_base_url,
    )
    return OpenAIChatCompletionsModel(
        model=current_settings.agent_model_default,
        openai_client=client,
    )


@function_tool
def get_weather(city: str) -> str:
    """Return deterministic demo weather data."""
    return f"The weather in {city} is sunny, 25 C."


@observe(
    name="process_user_input",
    span_type="TOOL",
    capture_input=False,
    capture_output=False,
)
async def process_user_input(user_input: str) -> dict[str, object]:
    """展示手动 span；敏感业务输入默认不要直接写入 trace。"""
    return {"length": len(user_input), "word_count": len(user_input.split())}


@measure_time("database_query")
async def query_database() -> list[dict[str, object]]:
    """展示只记录耗时的本地操作。"""
    await asyncio.sleep(0.1)
    return [{"id": 1, "status": "ready"}]


@observe(name="validate_request", capture_input=False, capture_output=False)
async def reject_example_request() -> None:
    """生成一个可预期的异常 span，不依赖模型随机行为。"""
    raise ValueError("example validation failure")


async def example_sdk_tracing(model: OpenAIChatCompletionsModel) -> None:
    print("\n示例 1: Agents SDK 调用与工具追踪")
    agent = Agent(
        name="Weather Assistant",
        instructions="Use the weather tool and answer briefly.",
        model=model,
        tools=[get_weather],
    )
    result = await Runner.run(agent, "What's the weather in Beijing?")
    print(f"- result: {result.final_output}")


async def example_trace_grouping(model: OpenAIChatCompletionsModel) -> None:
    print("\n示例 2: trace() 分组")
    agent = Agent(name="Short Assistant", instructions="Answer briefly.", model=model)
    with trace("Observability Example Workflow"):
        first = await Runner.run(agent, "Reply with one greeting.")
        second = await Runner.run(agent, "Reply with one farewell.")
    print(f"- first: {first.final_output}")
    print(f"- second: {second.final_output}")


async def example_custom_spans() -> None:
    print("\n示例 3: 手动 span 与耗时日志")
    processed = await process_user_input("sensitive input is not captured")
    db_result = await query_database()
    print(f"- processed metadata: {processed}")
    print(f"- local result: {db_result}")


async def example_error_span() -> None:
    print("\n示例 4: 可预期异常 span")
    try:
        await reject_example_request()
    except ValueError as exc:
        print(f"- captured example error: {exc}")


async def main() -> None:
    config = ObservabilityConfig.from_env()
    if config.enabled:
        print("LANGFUSE_ENABLED=true，正在初始化远端追踪导出。")
    else:
        print("LANGFUSE_ENABLED=false，SDK 调用仍会执行，但不会初始化 Langfuse 导出。")

    await init_observability(config)
    try:
        model = build_model()
        await example_sdk_tracing(model)
        await example_trace_grouping(model)
        await example_custom_spans()
        await example_error_span()
    finally:
        await shutdown_observability()


if __name__ == "__main__":
    asyncio.run(main())
