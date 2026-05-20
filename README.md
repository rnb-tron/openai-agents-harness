# OpenAI Agent SDK - Agent Harness 工程脚手架

> 基于 OpenAI Agents SDK 的可插拔 Agent 工程底座,提供完整的工程化能力和标准化架构。

## 🎯 项目定位

这是一个 **Agent Harness 工程脚手架**,不包含具体业务逻辑,而是提供 Agent 应用开发所需的通用工程能力:

- ✅ **标准化架构**: 六层清晰分层,职责明确
- ✅ **可插拔设计**: 能力模块独立,按需启用/禁用
- ✅ **完整基础设施**: 日志、限流、缓存、消息队列、数据库
- ✅ **Memory 系统**: 三层记忆架构(短期/长期/向量检索)
- ✅ **易于拓展**: 新增能力不影响现有代码
- ✅ **最佳实践**: 遵循 Python 和 FastAPI 标准

## 📚 快速导航

### 🚀 快速开始
- [**快速入门指南**](./docs/QUICKSTART.md) - 5 分钟上手 (新!)
- [**项目文档索引**](./docs/PROJECT_DOCUMENTATION.md) - 所有文档导航 (新!)

### 📖 核心文档
- [**AgentOrchestrator 使用指南**](./docs/AGENT_ORCHESTRATOR_USAGE.md) - 三种模式详解 (新!)
- [**高级能力指南**](./docs/ADVANCED_AGENTS_GUIDE.md) - HITL/Checkpoint/Handoff (新!)
- [**架构设计**](./docs/ARCHITECTURE_DESIGN.md) - 六层架构详解
- [**记忆系统**](./docs/MEMORY_SYSTEM.md) - 短期/长期记忆
- [**模型弹性指南**](./docs/MODEL_RESILIENCE_GUIDE.md) - 降级/重试/超时
- [**可观测性指南**](./docs/OBSERVABILITY_GUIDE.md) - Langfuse 集成

## 🏗️ 架构设计

### 六层架构

```
┌─────────────────────────────────────────┐
│           API 层 (接口)                  │
│  路由 / 中间件 / Schemas                 │
└─────────────────┬───────────────────────┘
                  │
┌─────────────────▼───────────────────────┐
│      Application 层 (业务编排)           │
│  编排器 / 服务 / DTOs                    │
└─────────────────┬───────────────────────┘
                  │
    ┌─────────────┴─────────────┐
    │                           │
┌───▼──────────┐    ┌──────────▼──────────┐
│ Domain 层    │◄──►│ Capabilities 层     │
│ 业务逻辑     │    │ 可插拔能力           │
│ 实体/值对象  │    │ Memory/Tools/Plugin │
└───┬──────────┘    └──────────┬──────────┘
    │                          │
┌───▼──────────────────────────▼──────────┐
│     Infrastructure 层 (基础设施)         │
│  DB / Cache / MQ / External Services    │
└─────────────────────────────────────────┘
```

### 目录结构

```text
openai-agent-sdk/
├── src/                              # 源代码 (核心)
│   ├── api/                          #   API 层
│   │   ├── middleware/               #     中间件 (认证/日志/限流)
│   │   ├── routers/                  #     路由 (chat/health/memory)
│   │   └── schemas/                  #     请求/响应模型
│   ├── application/                  #   应用层
│   │   ├── orchestration/            #     Agent 编排器
│   │   ├── services/                 #     业务服务
│   │   └── dtos/                     #     数据传输对象
│   ├── capabilities/                 #   原子能力层 (可插拔)
│   │   ├── memory/                   #     记忆系统
│   │   │   ├── short_term.py         #     短期记忆 (Redis)
│   │   │   ├── long_term.py          #     长期记忆 (MySQL)
│   │   │   ├── vector_store.py       #     向量存储 (ES)
│   │   │   ├── context_manager.py    #     上下文管理
│   │   │   ├── lifecycle.py          #     生命周期管理
│   │   │   └── manager.py            #     统一管理器
│   │   ├── tools/                    #     工具系统
│   │   │   ├── registry.py           #     工具注册中心
│   │   │   ├── builtin/              #     内置工具
│   │   │   └── custom/               #     自定义工具
│   │   ├── model_routing/            #     模型路由
│   │   └── plugin/                   #     插件系统
│   ├── domain/                       #   领域层
│   │   ├── entities/                 #     领域实体
│   │   ├── value_objects/            #     值对象
│   │   ├── repositories/             #     仓储接口
│   │   └── services/                 #     领域服务
│   ├── infrastructure/               #   基础设施层
│   │   ├── database/                 #     数据库连接和仓储
│   │   ├── cache/                    #     Redis 缓存
│   │   ├── message_queue/            #     Kafka/RabbitMQ
│   │   ├── storage/                  #     对象存储 (S3/MinIO)
│   │   └── external/                 #     外部服务客户端
│   ├── agents/                       #   Agent 定义层
│   │   ├── base/                     #     基础 Agent
│   │   ├── chat/                     #     对话 Agent
│   │   ├── assistant/                #     助手 Agent
│   │   └── custom/                   #     自定义 Agent
│   ├── core/                         #   核心工具层
│   │   ├── config.py                 #     配置管理
│   │   ├── logging.py                #     结构化日志
│   │   ├── database.py               #     数据库连接
│   │   ├── redis_client.py           #     Redis 客户端
│   │   ├── kafka_producer.py         #     Kafka 生产者
│   │   ├── http_client.py            #     HTTP 客户端
│   │   ├── rate_limiter.py           #     限流器
│   │   ├── event_bus.py              #     事件总线
│   │   ├── snowflake.py              #     ID 生成器
│   │   └── time_utils.py             #     时间工具
│   ├── utils/                        #   通用工具
│   └── main.py                       #   应用入口
├── config/                           # 配置文件
│   ├── test.env.example              #   环境变量模板
│   └── migrations/                   #   数据库迁移脚本
├── tests/                            # 测试
│   ├── unit/                         #   单元测试
│   ├── integration/                  #   集成测试
│   └── e2e/                          #   端到端测试
├── docs/                             # 文档
│   ├── ARCHITECTURE_DESIGN.md        #   架构设计
│   ├── MIGRATION_REPORT.md           #   迁移报告
│   └── MEMORY_SYSTEM.md              #   Memory 系统文档
├── docker/                           # Docker 配置
├── scripts/                          # 脚本
├── pyproject.toml                    # Python 项目配置
├── Makefile                          # 常用命令
├── .env.example                      # 环境变量模板
└── requirements.txt                  # 依赖列表
```

## 🚀 快速开始

### 环境要求

- Python >= 3.11
- pip >= 23.0

### 安装和启动

```bash
# 1. 克隆项目
git clone https://github.com/rnb-tron/openai-agent-sdk.git
cd openai-agent-sdk

# 2. 创建虚拟环境
python3.11 -m venv venv
source venv/bin/activate

# 3. 安装依赖
pip install -r requirements.txt

# 4. 配置环境变量
cp config/test.env.example config/test.env
# 编辑 config/test.env,配置你的 OpenAI API Key

# 5. 启动服务
make run
# 或: ENVTYPE=test python -m uvicorn src.main:app --host 0.0.0.0 --port 8080 --reload

# 6. 测试健康检查
curl http://localhost:8080/health/ok
```

### 使用 Makefile

```bash
# 查看所有可用命令
make help

# 安装依赖
make install

# 启动服务 (开发模式)
make run

# 运行测试
make test

# 代码格式化
make format

# 代码检查
make lint

# 清理缓存
make clean
```

## 🔌 核心能力

### 1. Memory 系统 (三层记忆)

- **短期记忆**: Redis/内存存储,支持 TTL 自动过期
- **长期记忆**: MySQL 持久化存储
- **向量检索**: Elasticsearch 向量相似度检索
- **上下文管理**: 短期+长期记忆智能合并,Token 优化
- **生命周期**: 重要性评分、遗忘策略、相似去重

```python
# 使用 Memory 系统
from src.capabilities.memory import MemoryManager

memory_manager = MemoryManager(settings, session)
await memory_manager.add_memory(
    session_id="session-123",
    user_id="user-456",
    role="user",
    content="用户输入内容",
    memory_type="long_term"
)

context = await memory_manager.get_context(
    session_id="session-123",
    user_id="user-456",
    user_input="当前输入"
)
```

### 2. 工具系统 (Tool Registry)

```python
# 注册工具
from src.capabilities.tools import ToolRegistry

registry = ToolRegistry()
registry.register("web_search", WebSearchTool())
registry.register("calculator", CalculatorTool())

# 使用工具
tool = registry.get("calculator")
result = await tool.execute(expression="3 + 5")
```

### 3. 模型路由 (Model Routing)

```python
# 智能模型选择
from src.capabilities.model_routing import ModelRouter

router = ModelRouter()
model = router.route(task_type="chat")  # 自动选择最优模型
```

### 4. 基础设施

- **结构化日志**: RID 上下文追踪,文件轮转
- **限流器**: Redis 限流,装饰器支持
- **事件总线**: 轻量级事件驱动
- **HTTP 客户端**: 全局异步 HTTP 客户端
- **数据库**: SQLAlchemy 异步 ORM
- **缓存**: Redis 主从分离
- **消息队列**: Kafka 异步生产者

## 📋 配置说明

### 环境变量

复制 `.env.example` 或 `config/test.env.example` 并配置:

```bash
# OpenAI 配置
OPENAI_API_KEY=your-api-key-here
AGENT_MODEL_DEFAULT=gpt-4o-mini

# 数据库 (可选)
DATABASE_URL=mysql+aiomysql://user:pass@localhost:3306/dbname

# Redis (可选)
REDIS_URL=redis://localhost:6379/0

# Memory 系统 (可选)
MEMORY_ENABLED=true
MEMORY_ES_HOSTS=http://localhost:9200
```

### 能力开关

```python
# config/test.env
REDIS_ENABLED=false
KAFKA_ENABLED=false
DATABASE_ENABLED=false
MEMORY_ENABLED=false
```

所有能力均可通过配置启用/禁用,实现真正的可插拔。

## 🧪 测试

```bash
# 运行所有测试
make test

# 运行测试并生成覆盖率报告
make test-cov

# 运行特定测试
python -m pytest tests/unit/test_memory.py -v
```

## 📖 文档

- [架构设计文档](docs/ARCHITECTURE_DESIGN.md) - 完整的架构设计和最佳实践
- [迁移报告](docs/MIGRATION_REPORT.md) - 从旧结构到新结构的迁移指南
- [Memory 系统文档](docs/MEMORY_SYSTEM.md) - Memory 系统的详细使用说明

## 🛠️ 技术栈

- **Web 框架**: FastAPI 0.116
- **Agent 框架**: OpenAI Agents SDK 0.17
- **ORM**: SQLAlchemy 2.0
- **缓存**: Redis 7.x
- **搜索引擎**: Elasticsearch 9.x
- **消息队列**: Kafka (aiokafka)
- **HTTP 客户端**: httpx
- **日志**: structlog + loguru
- **定时任务**: APScheduler
- **Token 计数**: tiktoken

## 🤝 贡献指南

1. Fork 本仓库
2. 创建特性分支 (`git checkout -b feature/amazing-feature`)
3. 提交更改 (`git commit -m 'feat: add amazing feature'`)
4. 推送到分支 (`git push origin feature/amazing-feature`)
5. 提交 Pull Request

## 📝 开发建议

### 添加新的能力模块

```bash
# 1. 创建能力目录
mkdir -p src/capabilities/new_capability

# 2. 创建必要文件
touch src/capabilities/new_capability/__init__.py
touch src/capabilities/new_capability/manager.py

# 3. 在配置中添加能力开关
# config/test.env
NEW_CAPABILITY_ENABLED=false
```

### 添加新的 Agent

```bash
# 1. 创建 Agent 目录
mkdir -p src/agents/custom/my_agent

# 2. 实现 Agent
touch src/agents/custom/my_agent/__init__.py
touch src/agents/custom/my_agent/agent.py

# 3. 在编排器中注册
```

### 添加新的 API 端点

```bash
# 1. 创建路由文件
touch src/api/routers/new_feature.py

# 2. 实现路由逻辑

# 3. 在 main.py 中注册
from src.api.routers import new_feature as new_feature_router
app.include_router(new_feature_router.router)
```

## 📄 开源协议

MIT License

## 🌟 Star History

如果这个项目对你有帮助,请给个 Star ⭐️ 支持一下!

---

**GitHub**: https://github.com/rnb-tron/openai-agent-sdk  
**文档**: https://github.com/rnb-tron/openai-agent-sdk/docs
