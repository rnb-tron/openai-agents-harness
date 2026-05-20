# 测试模块

## 测试文件说明

### Agent 功能测试
- `test_agent_full.py` - 完整的 Agent 功能测试 (5个测试用例)
  - 简单 Agent 对话
  - 带工具的 Agent
  - 多 Agent 协作
  - Trace 分组
  - 复杂任务

### Langfuse 可观测性测试
- `test_langfuse.py` - 完整的 Langfuse 集成测试 (4个测试用例)
  - Langfuse 连接测试
  - 简单 Agent 追踪
  - 工具执行追踪
  - Trace 分组
  
- `test_langfuse_simple.py` - Langfuse 连接快速测试

### Memory 系统测试
- `test_memory_system.py` - Memory 系统功能测试

### 其他测试
- `test_model_name.py` - 模型名称在 Langfuse 中的显示测试

## 运行测试

```bash
# 激活虚拟环境
source venv/bin/activate

# 运行单个测试
python tests/test_langfuse_simple.py

# 运行所有测试
python tests/test_agent_full.py
python tests/test_langfuse.py

# 使用 pytest (如果安装了)
pytest tests/ -v
```

## 测试配置

所有测试使用 `config/test.env` 中的配置。
