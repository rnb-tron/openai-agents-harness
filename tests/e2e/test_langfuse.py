"""
Langfuse 可观测系统测试

使用前准备:
1. 访问 Langfuse 平台: http://agent-otel-test.ke.com
2. 创建项目并获取 API Keys
3. 更新 config/test.env 中的配置:
   LANGFUSE_ENABLED=true
   LANGFUSE_PUBLIC_KEY=pk-lf-xxx
   LANGFUSE_SECRET_KEY=sk-lf-xxx
   LANGFUSE_BASE_URL=http://agent-otel-test.ke.com
"""

import asyncio
import os
from pathlib import Path
from dotenv import load_dotenv

# 加载配置
env_file = Path(__file__).parents[2] / "config" / "test.env"
load_dotenv(env_file, override=True)

from agents import Agent, Runner, trace, function_tool


# ========================================
# 工具定义
# ========================================

@function_tool
def calculate(expression: str) -> str:
    """计算器工具"""
    try:
        result = eval(expression, {"__builtins__": {}}, {})
        return f"计算结果: {result}"
    except Exception as e:
        return f"计算错误: {str(e)}"


@function_tool
def get_weather(city: str) -> str:
    """天气查询工具"""
    return f"{city} 的天气: 晴天, 25°C"


# ========================================
# 测试 1: Langfuse 连接测试
# ========================================

async def test_langfuse_connection():
    """测试 1: Langfuse 连接"""
    print("=" * 60)
    print("测试 1: Langfuse 连接测试")
    print("=" * 60)
    
    try:
        from langfuse import get_client
        
        # 初始化 Langfuse 客户端
        langfuse = get_client()
        
        # 验证连接
        if langfuse.auth_check():
            print("✅ Langfuse 连接成功!")
            print()
            return True
        else:
            print("❌ Langfuse 认证失败")
            print("请检查:")
            print("  1. LANGFUSE_PUBLIC_KEY 是否正确")
            print("  2. LANGFUSE_SECRET_KEY 是否正确")
            print("  3. LANGFUSE_BASE_URL 是否正确")
            print()
            return False
            
    except Exception as e:
        print(f"❌ Langfuse 连接失败: {e}")
        print()
        return False


# ========================================
# 测试 2: 简单 Agent + Langfuse
# ========================================

async def test_simple_agent_with_langfuse():
    """测试 2: 简单 Agent + Langfuse 追踪"""
    print("=" * 60)
    print("测试 2: 简单 Agent + Langfuse 追踪")
    print("=" * 60)
    
    try:
        # 初始化可观测系统
        from src.capabilities.observability import init_observability, ObservabilityConfig
        
        config = ObservabilityConfig.from_env()
        await init_observability(config)
        
        print("✅ 可观测系统初始化成功")
        print()
        
        # 创建 Agent
        agent = Agent(
            name="Assistant",
            instructions="You are a helpful assistant.",
            model="qwen3.5-plus",
        )
        
        print("📤 用户: Tell me about Python programming")
        print()
        
        # 运行 Agent (自动被 Langfuse 追踪)
        result = await Runner.run(agent, "Tell me about Python programming")
        
        print(f"🤖 Agent: {result.final_output[:200]}...")
        print()
        print("✅ Agent 运行成功!")
        print("📊 在 Langfuse Dashboard 中查看完整 Trace:")
        print(f"   {config.base_url}")
        print()
        
        # 关闭可观测系统
        from src.capabilities.observability import shutdown_observability
        await shutdown_observability()
        
        return True
        
    except Exception as e:
        print(f"❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        print()
        return False


# ========================================
# 测试 3: 工具执行 + Langfuse
# ========================================

async def test_tools_with_langfuse():
    """测试 3: 工具执行 + Langfuse 追踪"""
    print("=" * 60)
    print("测试 3: 工具执行 + Langfuse 追踪")
    print("=" * 60)
    
    try:
        # 初始化可观测系统
        from src.capabilities.observability import init_observability, ObservabilityConfig
        
        config = ObservabilityConfig.from_env()
        await init_observability(config)
        
        # 创建带工具的 Agent
        agent = Agent(
            name="Assistant",
            instructions="You are a helpful assistant with tools.",
            tools=[calculate, get_weather],
        )
        
        print("📤 用户: What is 123 * 456?")
        print()
        
        # 测试计算工具
        result1 = await Runner.run(agent, "What is 123 * 456?")
        print(f"🤖 Agent: {result1.final_output}")
        print()
        
        print("📤 用户: What's the weather in Beijing?")
        print()
        
        # 测试天气工具
        result2 = await Runner.run(agent, "What's the weather in Beijing?")
        print(f"🤖 Agent: {result2.final_output}")
        print()
        
        print("✅ 工具执行成功!")
        print("📊 在 Langfuse 中可以查看:")
        print("   - 工具调用参数")
        print("   - 工具返回值")
        print("   - 执行时间")
        print()
        
        # 关闭
        from src.capabilities.observability import shutdown_observability
        await shutdown_observability()
        
        return True
        
    except Exception as e:
        print(f"❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        print()
        return False


# ========================================
# 测试 4: Trace 分组 + Langfuse
# ========================================

async def test_trace_grouping():
    """测试 4: Trace 分组"""
    print("=" * 60)
    print("测试 4: Trace 分组 (多个操作在同一 Trace)")
    print("=" * 60)
    
    try:
        # 初始化
        from src.capabilities.observability import init_observability, ObservabilityConfig
        config = ObservabilityConfig.from_env()
        await init_observability(config)
        
        agent = Agent(
            name="Joke Generator",
            instructions="You are a comedian.",
        )
        
        # 使用 trace() 分组
        with trace("Joke Workflow"):
            print("📤 用户: Tell me a joke")
            print()
            
            result1 = await Runner.run(agent, "Tell me a joke")
            print(f"🤖 Joke: {result1.final_output}")
            print()
            
            print("📤 用户: Rate this joke")
            print()
            
            result2 = await Runner.run(
                agent,
                f"Rate this joke 1-10: {result1.final_output}"
            )
            print(f"🤖 Rating: {result2.final_output}")
            print()
        
        print("✅ Trace 分组成功!")
        print("📊 在 Langfuse 中所有操作在同一 Trace 下")
        print()
        
        # 关闭
        from src.capabilities.observability import shutdown_observability
        await shutdown_observability()
        
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
    """运行所有 Langfuse 测试"""
    print("\n")
    print("🚀 Langfuse 可观测系统测试")
    print("=" * 60)
    print()
    
    # 检查配置
    langfuse_enabled = os.getenv("LANGFUSE_ENABLED", "false").lower() == "true"
    public_key = os.getenv("LANGFUSE_PUBLIC_KEY", "")
    secret_key = os.getenv("LANGFUSE_SECRET_KEY", "")
    
    if not langfuse_enabled:
        print("⚠️  Langfuse 未启用")
        print()
        print("请先在 config/test.env 中配置:")
        print("  LANGFUSE_ENABLED=true")
        print("  LANGFUSE_PUBLIC_KEY=pk-lf-xxx")
        print("  LANGFUSE_SECRET_KEY=sk-lf-xxx")
        print("  LANGFUSE_BASE_URL=http://agent-otel-test.ke.com")
        print()
        return
    
    if not public_key or not secret_key:
        print("❌ API Key 未配置")
        print()
        print("请获取 Langfuse API Keys:")
        print("  1. 访问 http://agent-otel-test.ke.com")
        print("  2. 创建项目")
        print("  3. Settings → API Keys")
        print("  4. 复制 Public Key 和 Secret Key")
        print()
        return
    
    print(f"✅ Langfuse 已启用")
    print(f"📊 Public Key: {public_key[:15]}...")
    print(f"🔒 Secret Key: {secret_key[:10]}...")
    print()
    
    results = {}
    
    # 测试 1: 连接
    results["Langfuse 连接"] = await test_langfuse_connection()
    
    if not results["Langfuse 连接"]:
        print("❌ Langfuse 连接失败,跳过后续测试")
        return
    
    # 测试 2: 简单 Agent
    results["简单 Agent 追踪"] = await test_simple_agent_with_langfuse()
    
    # 测试 3: 工具执行
    results["工具执行追踪"] = await test_tools_with_langfuse()
    
    # 测试 4: Trace 分组
    results["Trace 分组"] = await test_trace_grouping()
    
    # 汇总
    print("=" * 60)
    print("📊 测试结果汇总")
    print("=" * 60)
    
    for test_name, success in results.items():
        status = "✅ 通过" if success else "❌ 失败"
        print(f"{test_name:20s} {status}")
    
    print()
    
    passed = sum(1 for s in results.values() if s)
    total = len(results)
    
    if passed == total:
        print(f"🎉 所有测试通过! ({passed}/{total})")
        print()
        print("Langfuse 可观测系统完全正常!")
        print()
        print("查看你的 Traces:")
        print(f"  👉 {os.getenv('LANGFUSE_BASE_URL', 'http://agent-otel-test.ke.com')}")
    else:
        print(f"⚠️  部分测试失败 ({passed}/{total} 通过)")
    
    print()


if __name__ == "__main__":
    asyncio.run(main())
