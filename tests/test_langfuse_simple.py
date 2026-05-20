"""Langfuse 连接测试 - 简化版"""

import os
from pathlib import Path
from dotenv import load_dotenv

# 先加载环境变量
env_file = Path(__file__).parent.parent / "config" / "test.env"
load_dotenv(env_file, override=True)

print("=" * 60)
print("Langfuse 连接测试")
print("=" * 60)
print()

# 验证环境变量
print("📋 配置信息:")
print(f"  LANGFUSE_ENABLED: {os.getenv('LANGFUSE_ENABLED')}")
print(f"  LANGFUSE_PUBLIC_KEY: {os.getenv('LANGFUSE_PUBLIC_KEY', '')[:15]}...")
print(f"  LANGFUSE_SECRET_KEY: {os.getenv('LANGFUSE_SECRET_KEY', '')[:10]}...")
print(f"  LANGFUSE_BASE_URL: {os.getenv('LANGFUSE_BASE_URL')}")
print()

try:
    from langfuse import get_client
    
    # 初始化客户端
    print("📡 正在连接 Langfuse...")
    langfuse = get_client()
    
    # 验证连接
    if langfuse.auth_check():
        print("✅ Langfuse 连接成功!")
        print("✅ API Key 认证通过")
        print()
        print("🎉 Langfuse 可观测系统可以使用了!")
        print()
        print("📊 查看 Traces:")
        print(f"   {os.getenv('LANGFUSE_BASE_URL')}")
    else:
        print("❌ 认证失败")
        print("请检查 API Key 是否正确")
        
except Exception as e:
    print(f"❌ 连接失败: {e}")
    print()
    print("请检查:")
    print("  1. LANGFUSE_PUBLIC_KEY 是否正确")
    print("  2. LANGFUSE_SECRET_KEY 是否正确")  
    print("  3. LANGFUSE_BASE_URL 是否可访问")
    import traceback
    traceback.print_exc()

print()
