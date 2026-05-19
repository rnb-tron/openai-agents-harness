# 🏗️ Agent Harness 工程脚手架 - 目录结构设计

## 📐 设计原则

1. **分层清晰**: 严格按照职责分层,每层职责单一
2. **可插拔**: 能力模块独立,支持按需启用/禁用
3. **易拓展**: 新增能力不影响现有代码
4. **标准化**: 遵循 Python 和 FastAPI 最佳实践
5. **可维护**: 文件组织清晰,易于理解和维护

---

## 📁 推荐目录结构

```
openai-agent-sdk/
├── 📦 .github/                          # GitHub 配置
│   ├── workflows/                       #   CI/CD 工作流
│   │   ├── ci.yml                       #     持续集成
│   │   ├── cd.yml                       #     持续部署
│   │   └── codeql.yml                   #     安全扫描
│   ├── ISSUE_TEMPLATE/                  #   Issue 模板
│   └── PULL_REQUEST_TEMPLATE.md         #   PR 模板
│
├── 📁 config/                           # 配置文件
│   ├── settings/                        #   配置模块
│   │   ├── __init__.py
│   │   ├── base.py                      #     基础配置
│   │   ├── development.py               #     开发环境
│   │   ├── production.py                #     生产环境
│   │   └── test.py                      #     测试环境
│   ├── .env.example                     #   环境变量模板
│   └── migrations/                      #   数据库迁移
│       └── memory_migration.sql
│
├── 📁 src/                              # 源代码 (核心)
│   ├── 📁 api/                          # API 层
│   │   ├── __init__.py
│   │   ├── middleware/                  #   中间件
│   │   │   ├── __init__.py
│   │   │   ├── auth.py                  #     认证中间件
│   │   │   ├── logging.py               #     日志中间件
│   │   │   ├── rate_limit.py            #     限流中间件
│   │   │   └── cors.py                  #     CORS 中间件
│   │   ├── routers/                     #   路由
│   │   │   ├── __init__.py
│   │   │   ├── chat.py                  #     聊天接口
│   │   │   ├── health.py                #     健康检查
│   │   │   ├── memory.py                #     记忆管理
│   │   │   └── tools.py                 #     工具管理
│   │   ├── schemas/                     #   请求/响应模型
│   │   │   ├── __init__.py
│   │   │   ├── chat.py                  #     聊天相关
│   │   │   ├── memory.py                #     记忆相关
│   │   │   └── common.py                #     通用模型
│   │   └── dependencies.py              #   依赖注入
│   │
│   ├── 📁 application/                  # 应用层
│   │   ├── __init__.py
│   │   ├── orchestration/               #   编排层
│   │   │   ├── __init__.py
│   │   │   ├── agent_orchestrator.py    #     Agent 编排器
│   │   │   ├── workflow.py              #     工作流引擎
│   │   │   └── pipeline.py              #     处理管道
│   │   ├── services/                    #   服务层
│   │   │   ├── __init__.py
│   │   │   ├── chat_service.py          #     聊天服务
│   │   │   ├── memory_service.py        #     记忆服务
│   │   │   └── tool_service.py          #     工具服务
│   │   └── dtos/                        #   数据传输对象
│   │       ├── __init__.py
│   │       ├── chat_dto.py
│   │       └── memory_dto.py
│   │
│   ├── 📁 capabilities/                 # 原子能力层 (可插拔)
│   │   ├── __init__.py
│   │   ├── memory/                      #   记忆系统
│   │   │   ├── __init__.py
│   │   │   ├── manager.py               #     统一管理器
│   │   │   ├── short_term.py            #     短期记忆
│   │   │   ├── long_term.py             #     长期记忆
│   │   │   ├── context_manager.py       #     上下文管理
│   │   │   ├── vector_store.py          #     向量存储
│   │   │   ├── repository.py            #     数据访问
│   │   │   ├── lifecycle.py             #     生命周期管理
│   │   │   ├── models.py                #     数据模型
│   │   │   ├── embedding.py             #     嵌入模型
│   │   │   └── tasks.py                 #     定时任务
│   │   ├── tools/                       #   工具系统
│   │   │   ├── __init__.py
│   │   │   ├── registry.py              #     工具注册中心
│   │   │   ├── base.py                  #     工具基类
│   │   │   ├── builtin/                 #     内置工具
│   │   │   │   ├── web_search.py
│   │   │   │   ├── calculator.py
│   │   │   │   └── code_executor.py
│   │   │   └── custom/                  #     自定义工具
│   │   ├── model_routing/               #   模型路由
│   │   │   ├── __init__.py
│   │   │   ├── router.py                #     路由器
│   │   │   ├── strategies.py            #     路由策略
│   │   │   └── fallback.py              #     降级策略
│   │   └── plugin/                      #   插件系统
│   │       ├── __init__.py
│   │       ├── base.py                  #     插件基类
│   │       ├── loader.py                #     插件加载器
│   │       └── manager.py               #     插件管理器
│   │
│   ├── 📁 domain/                       # 领域层
│   │   ├── __init__.py
│   │   ├── entities/                    #   实体
│   │   │   ├── __init__.py
│   │   │   ├── agent.py                 #     Agent 实体
│   │   │   ├── session.py               #     会话实体
│   │   │   └── memory.py                #     记忆实体
│   │   ├── value_objects/               #   值对象
│   │   │   ├── __init__.py
│   │   │   ├── message.py               #     消息
│   │   │   └── context.py               #     上下文
│   │   ├── repositories/                #   仓储接口
│   │   │   ├── __init__.py
│   │   │   ├── memory_repository.py
│   │   │   └── session_repository.py
│   │   └── services/                    #   领域服务
│   │       ├── __init__.py
│   │       └── agent_service.py
│   │
│   ├── 📁 infrastructure/               # 基础设施层
│   │   ├── __init__.py
│   │   ├── database/                    #   数据库
│   │   │   ├── __init__.py
│   │   │   ├── connection.py            #     连接管理
│   │   │   ├── models.py                #     ORM 模型
│   │   │   └── repositories/            #     仓储实现
│   │   │       ├── memory_repo_impl.py
│   │   │       └── session_repo_impl.py
│   │   ├── cache/                       #   缓存
│   │   │   ├── __init__.py
│   │   │   ├── redis.py                 #     Redis 客户端
│   │   │   └── decorators.py            #     缓存装饰器
│   │   ├── message_queue/               #   消息队列
│   │   │   ├── __init__.py
│   │   │   ├── kafka.py                 #     Kafka 客户端
│   │   │   └── rabbitmq.py              #     RabbitMQ 客户端
│   │   ├── storage/                     #   对象存储
│   │   │   ├── __init__.py
│   │   │   ├── s3.py                    #     AWS S3
│   │   │   └── minio.py                 #     MinIO
│   │   └── external/                    #   外部服务
│   │       ├── __init__.py
│   │       ├── openai_client.py         #     OpenAI 客户端
│   │       └── embedding_client.py      #     嵌入模型客户端
│   │
│   ├── 📁 agents/                       # Agent 定义层
│   │   ├── __init__.py
│   │   ├── base/                        #   基础 Agent
│   │   │   ├── __init__.py
│   │   │   ├── base_agent.py            #     Agent 基类
│   │   │   └── agent_factory.py         #     Agent 工厂
│   │   ├── chat/                        #   对话 Agent
│   │   │   ├── __init__.py
│   │   │   ├── chat_agent.py            #     聊天 Agent
│   │   │   └── prompts.py               #     提示词
│   │   ├── assistant/                   #   助手 Agent
│   │   │   ├── __init__.py
│   │   │   └── assistant_agent.py
│   │   └── custom/                      #   自定义 Agent
│   │       └── README.md
│   │
│   ├── 📁 core/                         # 核心工具层
│   │   ├── __init__.py
│   │   ├── config.py                    #   配置管理
│   │   ├── logging.py                   #   日志系统
│   │   ├── exceptions.py                #   异常定义
│   │   ├── decorators.py                #   装饰器
│   │   ├── validators.py                #   验证器
│   │   ├── converters.py                #   转换器
│   │   ├── snowflake.py                 #   ID 生成器
│   │   ├── event_bus.py                 #   事件总线
│   │   ├── rate_limiter.py              #   限流器
│   │   ├── http_client.py               #   HTTP 客户端
│   │   └── security.py                  #   安全工具
│   │
│   ├── 📁 utils/                        # 通用工具
│   │   ├── __init__.py
│   │   ├── string_utils.py
│   │   ├── time_utils.py
│   │   ├── json_utils.py
│   │   └── response.py
│   │
│   └── main.py                          # 应用入口
│
├── 📁 tests/                            # 测试
│   ├── __init__.py
│   ├── conftest.py                      #   Pytest 配置
│   ├── fixtures/                        #   测试夹具
│   │   ├── database.py
│   │   └── mock_data.py
│   ├── unit/                            #   单元测试
│   │   ├── test_api/
│   │   ├── test_services/
│   │   ├── test_capabilities/
│   │   └── test_agents/
│   ├── integration/                     #   集成测试
│   │   ├── test_chat_flow.py
│   │   └── test_memory_flow.py
│   └── e2e/                             #   端到端测试
│       └── test_full_pipeline.py
│
├── 📁 docs/                             # 文档
│   ├── architecture/                    #   架构文档
│   │   ├── overview.md
│   │   ├── memory_system.md
│   │   └── deployment.md
│   ├── api/                             #   API 文档
│   │   └── openapi.yaml
│   ├── guides/                          #   使用指南
│   │   ├── getting_started.md
│   │   ├── configuration.md
│   │   ├── capabilities.md
│   │   └── development.md
│   └── changelog.md
│
├── 📁 scripts/                          # 脚本
│   ├── setup.sh                         #   环境初始化
│   ├── run.sh                           #   启动脚本
│   ├── test.sh                          #   测试脚本
│   └── deploy.sh                        #   部署脚本
│
├── 📁 docker/                           # Docker 配置
│   ├── Dockerfile
│   ├── docker-compose.yml
│   ├── docker-compose.dev.yml
│   └── docker-compose.prod.yml
│
├── .gitignore
├── .env.example                         # 环境变量模板
├── pyproject.toml                       # Python 项目配置
├── requirements.txt                     # 依赖文件
├── requirements-dev.txt                 # 开发依赖
├── Makefile                             # Make 命令
├── README.md                            # 项目说明
├── LICENSE                              # 开源协议
└── CHANGELOG.md                         # 变更日志
```

---

## 🎯 核心分层说明

### 1. **API 层** (`src/api/`)
- **职责**: HTTP 接口、请求验证、响应格式化
- **包含**: 路由、中间件、Schemas
- **依赖**: 只依赖 Application 层

### 2. **Application 层** (`src/application/`)
- **职责**: 业务编排、用例实现、事务管理
- **包含**: 编排器、服务、DTOs
- **依赖**: 依赖 Domain 层和 Capabilities 层

### 3. **Capabilities 层** (`src/capabilities/`)
- **职责**: 可插拔的原子能力
- **包含**: Memory、Tools、Model Routing、Plugins
- **特点**: 每个能力独立,支持热插拔

### 4. **Domain 层** (`src/domain/`)
- **职责**: 核心业务逻辑、领域模型
- **包含**: 实体、值对象、仓储接口、领域服务
- **特点**: 不依赖任何外部框架

### 5. **Infrastructure 层** (`src/infrastructure/`)
- **职责**: 技术实现细节
- **包含**: 数据库、缓存、消息队列、外部服务
- **特点**: 实现 Domain 层定义的接口

### 6. **Agents 层** (`src/agents/`)
- **职责**: Agent 定义和配置
- **包含**: Agent 实现、提示词、工具绑定
- **特点**: 基于 OpenAI Agents SDK

---

## 📊 依赖关系

```
API 层
  ↓
Application 层
  ↓
┌─────────────────────────────────┐
│ Domain 层  ←  Capabilities 层    │
└─────────────────────────────────┘
  ↓
Infrastructure 层
```

**依赖规则**:
- 上层可以依赖下层
- 同层之间不能相互依赖
- Domain 层不依赖任何外部库
- Capabilities 层可被任何层调用

---

## 🔌 可插拔设计

### 能力注册机制

```python
# src/capabilities/__init__.py
from .registry import CapabilityRegistry

registry = CapabilityRegistry()

# 注册能力
registry.register("memory", MemoryManager)
registry.register("tools", ToolRegistry)
registry.register("model_routing", ModelRouter)

# 启用/禁用能力
registry.enable("memory")
registry.disable("tools")
```

### 配置文件控制

```python
# config/settings/base.py
CAPABILITIES = {
    "memory": {
        "enabled": True,
        "config": {...}
    },
    "tools": {
        "enabled": False,
        "config": {...}
    }
}
```

---

## 📝 命名规范

### 目录命名
- 使用 **小写字母 + 下划线**: `capabilities/`, `model_routing/`
- 复数形式表示集合: `routers/`, `services/`

### 文件命名
- 模块文件: `snake_case.py`
- 测试文件: `test_<module>.py`
- 配置文件: `*.yaml` 或 `*.py`

### 类命名
- 类名: `PascalCase` (如 `MemoryManager`)
- 抽象类: 前缀 `Abstract` 或 `Base` (如 `BaseAgent`)
- 接口: 前缀 `I` (如 `IMemoryRepository`)

### 函数/变量命名
- 函数/方法: `snake_case` (如 `get_context()`)
- 常量: `UPPER_CASE` (如 `MAX_RETRIES`)
- 私有变量: 前缀 `_` (如 `_cache`)

---

## 🚀 快速开始

### 1. 添加新的能力模块

```bash
# 创建能力目录
mkdir -p src/capabilities/new_capability

# 创建必要文件
touch src/capabilities/new_capability/__init__.py
touch src/capabilities/new_capability/manager.py
touch src/capabilities/new_capability/config.py

# 注册能力
# 在 capabilities/__init__.py 中添加
registry.register("new_capability", NewCapabilityManager)
```

### 2. 添加新的 Agent

```bash
# 创建 Agent 目录
mkdir -p src/agents/custom/my_agent

# 创建 Agent 实现
touch src/agents/custom/my_agent/__init__.py
touch src/agents/custom/my_agent/agent.py
touch src/agents/custom/my_agent/prompts.py
```

### 3. 添加新的 API 端点

```bash
# 创建路由文件
touch src/api/routers/new_feature.py

# 在 __init__.py 中注册
from .new_feature import router as new_feature_router
```

---

## 📋 迁移指南

### 当前结构 → 新结构

| 当前路径 | 新路径 | 说明 |
|---------|--------|------|
| `app/api/` | `src/api/` | API 层 |
| `app/application/` | `src/application/` | 应用层 |
| `app/capabilities/` | `src/capabilities/` | 能力层 |
| `app/core/` | `src/core/` | 核心工具 |
| `app/models/` | `src/infrastructure/database/models.py` | 数据模型 |
| `app/routers/` | `src/api/routers/` | 路由 |
| `app/shared/` | 分散到各层 | 共享代码 |
| `app/utils/` | `src/utils/` | 通用工具 |

---

## ✨ 优势总结

1. **清晰的分层**: 每层职责明确,易于理解
2. **可插拔设计**: 能力模块独立,按需启用
3. **易于测试**: 分层清晰,单元测试简单
4. **便于维护**: 文件组织合理,易于定位问题
5. **支持拓展**: 新增功能不影响现有代码
6. **标准化**: 遵循行业最佳实践
7. **团队协作**: 多人开发不易冲突

---

## 🎯 下一步

1. **逐步迁移**: 从现有结构逐步迁移到新结构
2. **保持兼容**: 迁移过程中保持 API 兼容
3. **补充测试**: 为新结构添加完整的测试
4. **更新文档**: 同步更新架构文档

---

*设计时间: 2026-05-19*
*版本: v1.0*
