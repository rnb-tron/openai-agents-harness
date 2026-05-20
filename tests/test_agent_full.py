"""
完整的 Agent 功能测试

测试内容:
1. 简单 Agent 对话
2. 带工具的 Agent
3. 多 Agent 协作
4. Agent 流式输出
"""

import asyncio
import os
from pathlib import Path
from dotenv import load_dotenv

# 加载配置
env_file = Path(__file__).parent.parent / "config" / "test.env"
load_dotenv(env_file)

from agents import Agent, Runner, trace, function_tool


# ========================================
# 测试 1: 简单 Agent 对话
# ========================================

async def test_simple_agent():
    """测试 1: 简单 Agent 对话"""
    print("=" * 60)
    print("测试 1: 简单 Agent 对话")
    print("=" * 60)
    
    try:
        # 创建 Agent
        agent = Agent(
            name="Assistant",
            instructions="You are a helpful assistant. Be concise and friendly.",
        )
        
        print("📤 用户: Tell me a fun fact about AI")
        print()
        
        # 运行 Agent
        result = await Runner.run(agent, "Tell me a fun fact about AI")
        
        print(f"🤖 Agent: {result.final_output}")
        print()
        print("✅ 简单 Agent 测试成功!")
        print()
        return True
        
    except Exception as e:
        print(f"❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        print()
        return False


# ========================================
# 测试 2: 带工具的 Agent
# ========================================

@function_tool
def calculate(expression: str) -> str:
    """
    计算器工具
    
    Args:
        expression: 数学表达式,例如 "2 + 3 * 4"
    """
    try:
        # 安全的计算
        result = eval(expression, {"__builtins__": {}}, {})
        return f"计算结果: {result}"
    except Exception as e:
        return f"计算错误: {str(e)}"


@function_tool
def get_current_time() -> str:
    """获取当前时间"""
    from datetime import datetime
    now = datetime.now()
    return f"当前时间: {now.strftime('%Y-%m-%d %H:%M:%S')}"


async def test_agent_with_tools():
    """测试 2: 带工具的 Agent"""
    print("=" * 60)
    print("测试 2: 带工具的 Agent")
    print("=" * 60)
    
    try:
        # 创建带工具的 Agent
        agent = Agent(
            name="Math Assistant",
            instructions="You are a helpful assistant with calculation capabilities.",
            tools=[calculate, get_current_time],
        )
        
        print("📤 用户: What is 25 * 48 + 100?")
        print()
        
        # 测试计算工具
        result1 = await Runner.run(agent, "What is 25 * 48 + 100?")
        print(f"🤖 Agent: {result1.final_output}")
        print()
        
        print("📤 用户: What time is it now?")
        print()
        
        # 测试时间工具
        result2 = await Runner.run(agent, "What time is it now?")
        print(f"🤖 Agent: {result2.final_output}")
        print()
        
        print("✅ 带工具的 Agent 测试成功!")
        print()
        return True
        
    except Exception as e:
        print(f"❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        print()
        return False


# ========================================
# 测试 3: 多 Agent 协作
# ========================================

async def test_multi_agent():
    """测试 3: 多 Agent 协作"""
    print("=" * 60)
    print("测试 3: 多 Agent 协作")
    print("=" * 60)
    
    try:
        # 创建不同角色的 Agent
        spanish_agent = Agent(
            name="Spanish Agent",
            instructions="You only speak Spanish. Respond in Spanish.",
        )
        
        english_agent = Agent(
            name="English Agent",
            instructions="You only speak English. Respond in English.",
        )
        
        # Triage Agent - 根据语言路由
        triage_agent = Agent(
            name="Triage Agent",
            instructions="Handoff to the appropriate agent based on the language of the request.",
            handoffs=[spanish_agent, english_agent],
        )
        
        print("📤 用户 (英文): Hello, how are you?")
        print()
        
        result1 = await Runner.run(triage_agent, "Hello, how are you?")
        print(f"🤖 Agent: {result1.final_output}")
        print()
        
        print("📤 用户 (西文): Hola, ¿cómo estás?")
        print()
        
        result2 = await Runner.run(triage_agent, "Hola, ¿cómo estás?")
        print(f"🤖 Agent: {result2.final_output}")
        print()
        
        print("✅ 多 Agent 协作测试成功!")
        print()
        return True
        
    except Exception as e:
        print(f"❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        print()
        return False


# ========================================
# 测试 4: Trace 分组
# ========================================

async def test_trace_grouping():
    """测试 4: Trace 分组"""
    print("=" * 60)
    print("测试 4: Trace 分组 (多个操作在同一 Trace 下)")
    print("=" * 60)
    
    try:
        agent = Agent(
            name="Joke Generator",
            instructions="You are a comedian. Tell funny jokes.",
        )
        
        # 使用 trace() 将多个操作分组
        with trace("Joke Workflow"):
            print("📤 用户: Tell me a joke about programming")
            print()
            
            result1 = await Runner.run(agent, "Tell me a joke about programming")
            print(f"🤖 Agent: {result1.final_output}")
            print()
            
            print("📤 用户: Rate this joke from 1-10")
            print()
            
            result2 = await Runner.run(
                agent,
                f"Rate this joke from 1-10: {result1.final_output}"
            )
            print(f"🤖 Agent: {result2.final_output}")
            print()
        
        print("✅ Trace 分组测试成功!")
        print()
        return True
        
    except Exception as e:
        print(f"❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        print()
        return False


# ========================================
# 测试 5: 复杂任务
# ========================================

async def test_complex_task():
    """测试 5: 复杂任务"""
    print("=" * 60)
    print("测试 5: 复杂任务 (多步骤)")
    print("=" * 60)
    
    try:
        agent = Agent(
            name="Creative Assistant",
            instructions="""You are a creative assistant. Help users with:
            1. Brainstorming ideas
            2. Writing content
            3. Problem solving
            Be detailed and helpful.""",
        )
        
        print("📤 用户: Help me plan a tech team building activity")
        print()
        
        result = await Runner.run(
            agent,
            """Help me plan a tech team building activity.
            Please provide:
            1. 3 activity ideas
            2. Duration and cost estimate
            3. Pros and cons of each"""
        )
        
        print(f"🤖 Agent:")
        print(f"{result.final_output}")
        print()
        
        print("✅ 复杂任务测试成功!")
        print()
        return True
        
    except Exception as e:
        print(f"❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        print()
        return False


# ========================================
# 运行所有测试
# ========================================

async def main():
    """运行所有 Agent 测试"""
    print("\n")
    print("🚀 Agent 功能完整测试")
    print("=" * 60)
    print(f"模型: {os.getenv('AGENT_MODEL_DEFAULT', 'unknown')}")
    print(f"Base URL: {os.getenv('OPENAI_BASE_URL', 'unknown')}")
    print("=" * 60)
    print()
    
    results = {}
    
    # 测试 1: 简单 Agent
    results["简单 Agent"] = await test_simple_agent()
    
    # 测试 2: 带工具的 Agent
    results["带工具的 Agent"] = await test_agent_with_tools()
    
    # 测试 3: 多 Agent 协作
    results["多 Agent 协作"] = await test_multi_agent()
    
    # 测试 4: Trace 分组
    results["Trace 分组"] = await test_trace_grouping()
    
    # 测试 5: 复杂任务
    results["复杂任务"] = await test_complex_task()
    
    # 汇总结果
    print("=" * 60)
    print("📊 测试结果汇总")
    print("=" * 60)
    
    for test_name, success in results.items():
        status = "✅ 通过" if success else "❌ 失败"
        print(f"{test_name:20s} {status}")
    
    print()
    
    # 统计
    passed = sum(1 for success in results.values() if success)
    total = len(results)
    
    if passed == total:
        print(f"🎉 所有测试通过! ({passed}/{total})")
        print()
        print("你的 Agent 功能完全正常!")
        print("可以继续使用:")
        print("  - 简单对话 Agent")
        print("  - 带工具的 Agent")
        print("  - 多 Agent 协作")
        print("  - 完整的工作流")
    else:
        print(f"⚠️  部分测试失败 ({passed}/{total} 通过)")
        print()
        print("请检查:")
        print("  1. API Key 是否有效")
        print("  2. 模型是否支持所需功能")
        print("  3. 网络连接是否正常")
    
    print()


if __name__ == "__main__":
    asyncio.run(main())
