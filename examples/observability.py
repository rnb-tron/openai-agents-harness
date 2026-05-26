"""
Langfuse 可观测系统集成示例

展示如何使用可观测能力的各种功能

运行本文件需要配置可访问的模型服务；查看远端追踪还需配置 Langfuse。
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agents import Agent, Runner, trace, function_tool

from src.capabilities.observability import observe, measure_time


# ========================================
# 示例 1: 自动埋点 (无需任何代码改动)
# ========================================

async def example_auto_tracing():
    """
    自动埋点示例
    
    只要初始化了 Langfuse,所有 OpenAI Agents SDK 的操作都会自动被追踪:
    - LLM 调用
    - 工具执行
    - Agent 编排
    - Handoffs
    """
    
    # 创建 Agent
    agent = Agent(
        name="Assistant",
        instructions="You are a helpful assistant.",
    )
    
    # 运行 Agent - 自动被 Langfuse 追踪
    result = await Runner.run(agent, "What is the weather in Tokyo?")
    print(f"Result: {result.final_output}")
    
    # 在 Langfuse Dashboard 中可以看到:
    # - Trace: Runner.run
    #   - Span: LLM Call (gpt-4o)
    #     - Input: "What is the weather in Tokyo?"
    #     - Output: "..."
    #     - Tokens: 50
    #     - Latency: 1.2s
    #     - Cost: $0.001


# ========================================
# 示例 2: 使用 trace() 分组
# ========================================

async def example_trace_grouping():
    """
    Trace 分组示例
    
    使用 OpenAI Agents SDK 的 trace() 上下文管理器
    将多个操作组织在同一个 Trace 下
    """
    
    agent = Agent(name="Joke Generator", instructions="Tell funny jokes.")
    
    # 所有操作在同一个 Trace 下
    with trace("Joke Workflow"):
        # 生成笑话
        first_result = await Runner.run(agent, "Tell me a joke about programming")
        print(f"Joke: {first_result.final_output}")
        
        # 评价笑话
        second_result = await Runner.run(
            agent,
            f"Rate this joke from 1-10: {first_result.final_output}"
        )
        print(f"Rating: {second_result.final_output}")
    
    # 在 Langfuse Dashboard 中:
    # Trace: Joke Workflow
    #   - Span 1: Runner.run (生成笑话)
    #   - Span 2: Runner.run (评价笑话)


# ========================================
# 示例 3: 工具执行追踪
# ========================================

@function_tool
def get_weather(city: str) -> str:
    """
    天气查询工具
    
    这个工具的调用会被自动追踪:
    - 工具名称
    - 参数
    - 返回值
    - 执行时间
    """
    return f"The weather in {city} is sunny, 25°C"


async def example_tool_tracing():
    """工具执行追踪示例"""
    
    agent = Agent(
        name="Weather Assistant",
        instructions="You are a helpful weather assistant.",
        tools=[get_weather],
    )
    
    result = await Runner.run(agent, "What's the weather in Beijing?")
    print(f"Result: {result.final_output}")
    
    # 在 Langfuse Dashboard 中:
    # - Span: Tool Execution
    #   - Tool: get_weather
    #   - Input: {"city": "Beijing"}
    #   - Output: "The weather in Beijing is sunny, 25°C"
    #   - Duration: 50ms


# ========================================
# 示例 4: 自定义埋点
# ========================================

@observe(name="process_user_input", span_type="TOOL")
async def process_user_input(user_input: str) -> dict:
    """
    自定义埋点示例
    
    使用 @observe 装饰器为普通函数添加追踪
    """
    # 业务逻辑
    processed = {
        "original": user_input,
        "length": len(user_input),
        "words": user_input.split(),
    }
    
    return processed


@measure_time("database_query")
async def query_database(query: str) -> list:
    """
    性能测量示例
    
    只记录执行时间,不创建 Span
    """
    # 模拟数据库查询
    await asyncio.sleep(0.1)
    return [{"id": 1, "data": "result"}]


async def example_custom_tracing():
    """自定义埋点示例"""
    
    # 自定义追踪
    result = await process_user_input("Hello, how are you?")
    print(f"Processed: {result}")
    
    # 性能测量
    db_result = await query_database("SELECT * FROM users")
    print(f"DB Result: {db_result}")
    
    # 在 Langfuse Dashboard 中:
    # - Span: process_user_input
    #   - Input: {"args": "...", "kwargs": "..."}
    #   - Output: {"original": "...", "length": 20, ...}
    #   - Duration: 10ms


# ========================================
# 示例 5: Multi-Agent Handoff
# ========================================

async def example_multi_agent_handoff():
    """
    多 Agent Handoff 示例
    
    Handoff 操作会被自动追踪
    """
    
    spanish_agent = Agent(
        name="Spanish Agent",
        instructions="You only speak Spanish.",
    )
    
    english_agent = Agent(
        name="English Agent",
        instructions="You only speak English.",
    )
    
    triage_agent = Agent(
        name="Triage Agent",
        instructions="Handoff to the appropriate agent based on the language.",
        handoffs=[spanish_agent, english_agent],
    )
    
    # 中文请求 -> English Agent
    result1 = await Runner.run(triage_agent, "Hello, how are you?")
    print(f"English: {result1.final_output}")
    
    # 西语请求 -> Spanish Agent
    result2 = await Runner.run(triage_agent, "Hola, ¿cómo estás?")
    print(f"Spanish: {result2.final_output}")
    
    # 在 Langfuse Dashboard 中:
    # Trace: Runner.run
    #   - Span: Triage Agent
    #     - Span: Handoff to English Agent
    #       - Span: LLM Call
    #     - Span: Handoff to Spanish Agent
    #       - Span: LLM Call


# ========================================
# 示例 6: 错误追踪
# ========================================

async def example_error_tracking():
    """
    错误追踪示例
    
    异常会被自动捕获并记录
    """
    
    agent = Agent(
        name="Error Agent",
        instructions="You are a helpful assistant.",
    )
    
    try:
        # 模拟异常
        result = await Runner.run(agent, "This will cause an error...")
    except Exception as e:
        print(f"Error caught: {e}")
    
    # 在 Langfuse Dashboard 中:
    # - Span: Runner.run
    #   - Status: ERROR
    #   - Error: "Exception message..."
    #   - Stack Trace: "..."


# ========================================
# 运行所有示例
# ========================================

async def main():
    """运行所有示例"""
    
    print("=" * 60)
    print("示例 1: 自动埋点")
    print("=" * 60)
    await example_auto_tracing()
    
    print("\n" + "=" * 60)
    print("示例 2: Trace 分组")
    print("=" * 60)
    await example_trace_grouping()
    
    print("\n" + "=" * 60)
    print("示例 3: 工具执行追踪")
    print("=" * 60)
    await example_tool_tracing()
    
    print("\n" + "=" * 60)
    print("示例 4: 自定义埋点")
    print("=" * 60)
    await example_custom_tracing()
    
    print("\n" + "=" * 60)
    print("示例 5: Multi-Agent Handoff")
    print("=" * 60)
    await example_multi_agent_handoff()
    
    print("\n" + "=" * 60)
    print("示例 6: 错误追踪")
    print("=" * 60)
    await example_error_tracking()


if __name__ == "__main__":
    asyncio.run(main())
