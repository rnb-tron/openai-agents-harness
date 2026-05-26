# 🚀 OpenAI Agent SDK - Agent Harness 工程脚手架

> 基于 OpenAI Agents SDK 的企业级 Agent Harness 工程底座。当前仓库是“完整能力版本”，用于验证能力抽象、运行时边界、可插拔机制，以及后续平台化脚手架生成方案。

## 🎯 项目定位

本项目不是具体业务 Agent，而是一个可复用、可裁剪、可配置生成的 Agent 工程脚手架底座。

未来平台可以让业务研发同学勾选所需能力，例如 `Memory`、`RAG`、`HITL`、`Observability`、`Auth`、`Audit` 等，然后自动生成一个可运行的 Agent 工程。当前仓库保留“完整能力版本”，用于验证能力粒度、依赖关系、运行时装配和工程可维护性。

核心特性：

- ✅ **统一装配**：`HarnessBuilder` 负责组装运行时、资源、注册中心和能力模块。
- ✅ **能力声明**：`CapabilityManifest` 描述能力名称、类型、依赖、产物、安装顺序和标签。
- ✅ **边界清晰**：API 层只依赖 Harness，不直接感知能力组合和具体后端。
- ✅ **显式依赖**：`Runtime` 通过依赖注入使用 `Tool`、`Model Router`、`Memory`、`Prompt` 等能力。
- ✅ **生成友好**：能力图、配置段和资源边界可作为后续脚手架生成的元数据。
- ✅ **SDK 原生路径**：主执行链路基于 OpenAI Agents SDK 的 `Agent`、`Runner`、`function_tool`。

## 🧭 架构总览

```mermaid
flowchart TD
    A["API 层<br/>routers / middleware / schemas"] --> B["Harness 装配层<br/>HarnessBuilder / HarnessContext / Manifest"]
    B --> C["运行时层<br/>AgentOrchestrator + OpenAI Agents SDK Runner"]
    C --> D["能力层<br/>Memory / Tools / Model Router / Prompt / Compression"]
    A --> E["协议能力<br/>Auth / RateLimit / Observability Middleware"]
    D --> F["基础设施层<br/>Database / Redis / Kafka / HTTP Client"]
    B --> G["脚手架生成输入<br/>CapabilityManifest / Config / Resources"]
```

核心原则：

- **轻量化**：默认关闭可选能力，未启用能力不进入运行路径。
- **可插拔**：能力通过统一接口和 manifest 接入，避免散落的硬编码判断。
- **可裁剪**：能力依赖和资源边界可被脚手架生成器读取。
- **可测试**：单元、集成、端到端测试分层，默认测试不依赖外部服务。
- **可维护**：`API`、`Runtime`、`Capability`、`Infrastructure` 边界清晰。

## 🧩 能力体系

能力由 `CapabilityManifest` 描述：

```python
CapabilityManifest(
    name="context_compression",
    kind=CapabilityKind.RUNTIME,
    config_section="compression",
    depends_on=("model_router", "conversation_context"),
    provides=("compressed_context",),
    install_order=30,
)
```

能力类型：

| 类型 | 说明 | 示例 |
| --- | --- | --- |
| `runtime` | 参与 Agent 执行生命周期 | `Memory`、`Prompt`、`Compression`、`Model Router` |
| `protocol` | 参与 HTTP 请求生命周期 | Auth、RateLimit |
| `resource` | 初始化或暴露基础设施/观测资源 | Observability |

当前能力状态：

| 能力 | 类型 | 状态 | 说明 |
| --- | --- | --- | --- |
| `tool_registry` | runtime | ✅ 已实现 | 工具注册、元数据、OpenAI Agents SDK 工具适配 |
| `model_router` | runtime | ✅ 已实现 | 模型选择、任务类型推断 |
| `model_resilience` | runtime | 🟡 部分实现 | 降级、重试、超时 runner 已具备 |
| `memory_session` | runtime | ✅ 已实现 | 短期会话记忆 |
| `long_term_memory` | runtime | 🟡 部分实现 | SQLAlchemy 关系存储支持 MySQL / PostgreSQL，仍需继续产品化 |
| `vector_search` | runtime | ✅ 已实现 | `EmbeddingProvider` 驱动 ES / PostgreSQL pgvector 写入与语义检索 |
| `prompt` | runtime | ✅ 已实现 | Harness 构建 PromptManager，并注入 Runtime |
| `context_compression` | runtime | ✅ 已实现 | 支持 token budget、rolling summary、hybrid |
| `auth` | protocol | ✅ 已实现 | JWT 中间件插件 |
| `rate_limit` | protocol | ✅ 已实现 | Redis/内存限流中间件插件 |
| `observability` | resource | ✅ 已实现 | Langfuse/OpenTelemetry 生命周期和 HTTP Trace |
| `hitl` | runtime | 🟡 部分实现 | 配置驱动装配，已接入 SDK 原生中断与 `POST /chat/resume` |
| `checkpoint` | runtime | 🟡 部分实现 | 配置驱动的进程内执行快照，不等同于 SDK `RunState` 存储 |
| `handoff` | runtime | 🟡 部分实现 | 配置驱动装配，主 Agent 已接入 SDK 原生 `handoffs` |

## 🏗️ 当前目录结构

```text
src/
├── api/
│   ├── middleware/          # 协议层插件：Auth / RateLimit
│   ├── routers/             # HTTP 路由：chat / health / memory
│   └── schemas/             # API 请求/响应模型
├── application/
│   └── orchestration/       # AgentOrchestrator 运行时编排
├── capabilities/
│   ├── advanced_agents/     # HITL / Checkpoint / Handoff
│   ├── context_compression/ # 上下文压缩
│   ├── memory/              # 短期记忆、长期记忆、向量检索
│   ├── model_routing/       # 模型路由、降级、重试、超时
│   ├── observability/       # Langfuse / OpenTelemetry
│   ├── plugin/              # Capability 协议、Registry、RunContext
│   ├── prompt/              # PromptManager 和 PromptStore
│   └── tools/               # ToolRegistry 和工具定义
├── core/                    # 配置、日志、ID、解析工具
├── harness/                 # HarnessBuilder / Context / Manifest / FastAPI deps
├── infrastructure/          # DB / Redis / Kafka / HTTP Client
├── utils/
└── main.py                  # FastAPI 应用入口

tests/
├── unit/                    # 快速单元测试
├── integration/             # 本地集成测试
└── e2e/                     # 端到端/外部服务测试

docs/
├── README.md                # 唯一文档索引
├── getting-started/         # 快速入门
├── architecture/            # 当前架构与脚手架适配
├── guides/                  # 当前能力使用指南
├── design-notes/            # 历史设计记录
└── archive/                 # 阶段性报告归档

examples/
├── README.md                # 示例入口与运行条件
└── *.py                     # 能力与集成示例
```

## 🔄 请求运行流程

```mermaid
sequenceDiagram
    participant U as 用户/API 调用方
    participant API as FastAPI Router
    participant H as Harness
    participant R as AgentOrchestrator
    participant C as CapabilityRegistry
    participant SDK as OpenAI Agents SDK

    U->>API: POST /chat
    API->>H: 获取 app.state.harness
    API->>R: runtime.run(session, input)
    R->>C: BEFORE_RUN
    C-->>R: 注入 memory / prompt / compression 等上下文
    R->>SDK: Runner.run(agent, input)
    SDK-->>R: RunResult / interruptions
    alt 运行完成
        R->>C: AFTER_RUN
        C-->>R: 持久化 memory / checkpoint 等结果
        R-->>API: 标准响应
    else 工具等待审批
        R-->>API: interruptions + run_state
        API-->>U: 待审批响应
        U->>API: POST /chat/resume + 审批决策
        API->>R: resume_with_approval(run_state)
        R->>SDK: Runner.run(agent, RunState)
        SDK-->>R: 恢复后结果
    end
    API-->>U: JSON
```

## 🧬 为什么适合脚手架生成

脚手架生成关注三个问题：选什么、依赖什么、删什么。本项目当前设计围绕这三点展开。

| 生成关注点 | 当前设计 |
| --- | --- |
| 能力选择 | `CapabilityManifest.name` 和配置开关描述能力 |
| 依赖解析 | `depends_on` / `provides` 描述能力依赖图 |
| 安装顺序 | `install_order` 控制能力注册和运行顺序 |
| 配置生成 | `config_section` 映射环境变量和配置段 |
| 资源装配 | `HarnessBuilder` 统一构建 manager、registry、router |
| 代码裁剪 | 能力目录边界清晰，`API` 和 `Runtime` 不直接硬编码具体后端 |
| 测试生成 | `tests/unit`、`tests/integration`、`tests/e2e` 已分层 |
| 目录读取 | `/health/capability-catalog` 输出能力与依赖矩阵 |
| 选择校验 | `/health/capability-selection/validate` 解析能力组合和外部资源要求 |

未来脚手架生成器可以按以下流程工作：

```mermaid
flowchart LR
    A["平台勾选能力"] --> B["读取 CapabilityManifest"]
    B --> C["校验选择并自动补齐依赖"]
    C --> D["生成配置与外部资源列表"]
    D --> E["裁剪能力目录与模板"]
    E --> F["生成可运行 Agent 工程"]
    F --> G["运行单元测试和健康检查"]
```

## 🚀 快速开始

### 1. 准备环境

```bash
python3.11 -m venv venv
source venv/bin/activate
make install
venv/bin/python -m pip install pytest pytest-asyncio
```

### 2. 配置环境变量

```bash
cp config/test.env.example config/test.env
```

最小聊天能力需要：

```bash
OPENAI_API_KEY=your-api-key
AGENT_MODEL_DEFAULT=gpt-4o-mini
```

### 3. 启动服务

```bash
make run
curl http://localhost:8080/health/ok
```

### 4. 运行测试

```bash
make test
make test-all
```

当前本地测试状态：

```text
make test      -> 69 passed
make test-all  -> 136 passed, 10 skipped
```

外部模型和 Langfuse 相关测试默认跳过。如需显式运行：

```bash
RUN_EXTERNAL_TESTS=true make test-all
```

## ⚙️ 常用配置开关

```bash
MEMORY_ENABLED=false
MEMORY_LONG_TERM_ENABLED=false
MEMORY_VECTOR_BACKEND=none
COMPRESSION_ENABLED=false
PROMPT_ENABLED=false
HITL_ENABLED=false
HANDOFF_ENABLED=false
AUTH_ENABLED=false
RATE_LIMIT_ENABLED=false
LANGFUSE_ENABLED=false
MODEL_RESILIENCE_ENABLED=false
```

模型弹性：

```bash
MODEL_RESILIENCE_ENABLED=true
MODEL_FALLBACK_ENABLED=true
MODEL_FALLBACK_CHAIN=gpt-4.1-mini,gpt-4o-mini
MODEL_RETRY_ENABLED=true
MODEL_TIMEOUT_ENABLED=true
```

HITL 原生工具审批：

```bash
HITL_ENABLED=true
HITL_APPROVAL_TIMEOUT=300
HITL_REQUIRE_APPROVAL_TOOLS=get_weather
HITL_AUTO_APPROVE_TOOLS=
```

启用后，命中配置工具的 `/chat` 响应会包含 `input`、`model`、`interruptions` 与 `run_state`。人工决策通过 `POST /chat/resume` 恢复执行，需原样回传 `message=input`、`model` 和 `run_state`；已装配 HITL manager 时，还必须携带 `interruptions[].id` 作为 `approval_request_id`。

Checkpoint 执行快照：

```bash
CHECKPOINT_ENABLED=true
CHECKPOINT_MAX_CHECKPOINTS=10
CHECKPOINT_AUTO_SAVE=true
```

`Checkpoint` 当前仅在进程内记录一次 Agent 执行的运行前/运行后摘要，用于调试与业务状态回看；它不保存 OpenAI Agents SDK 的 `RunState`，不能用于服务重启后的 HITL 恢复。

Handoff 专家转交：

```bash
HANDOFF_ENABLED=true
HANDOFF_AGENTS_JSON={"billing":{"description":"处理账单问题","instructions":"只处理账单相关请求。"}}
```

启用后，`HarnessBuilder` 装配静态专家 Agent，Runtime 将其作为 SDK 原生 `Agent.handoffs` 传入主 Agent。当前仅支持专家描述与指令，不包含专家专属工具集或动态路由规则。

PostgreSQL + pgvector Memory Backend：

```bash
DATABASE_ENABLED=true
DATABASE_URL=postgresql+asyncpg://agent:password@localhost:5432/agent_harness
MEMORY_ENABLED=true
MEMORY_LONG_TERM_ENABLED=true
MEMORY_VECTOR_BACKEND=pgvector
MEMORY_PGVECTOR_TABLE=memory_vectors
MEMORY_EMBEDDING_PROVIDER=openai
MEMORY_EMBEDDING_MODEL=text-embedding-3-small
MEMORY_VECTOR_DIMENSION=1536
```

首次启用前执行 `config/memory_postgres_pgvector_migration.sql`。`MemoryManager` 在启用 `MEMORY_EMBEDDING_PROVIDER=openai` 后自动生成 embedding，并向 pgvector 写入/查询向量；关闭 provider 时只保留关系长期记忆，不产生外部 embedding 调用。

能力目录与依赖矩阵：

```bash
curl http://localhost:8080/health/capability-catalog
```

该接口输出当前 Harness 支持装配的全部能力、当前是否启用、`depends_on` / `provides` 关系和外部资源依赖，可作为平台勾选能力与生成前校验的输入。

能力组合生成前校验：

```bash
curl -X POST http://localhost:8080/health/capability-selection/validate \
  -H 'Content-Type: application/json' \
  -d '{"selected":["vector_search","hitl"]}'
```

响应中的 `resolved_selection` 包含基础能力与可自动装配的内部依赖，`external_requirements` 描述需要平台生成配置的外部资源。例如选择 `vector_search` 时，会推导 `long_term_memory`、内部 `memory_manager` 与 `embedding_provider`，并要求配置 `database` 及 `embedding_api`。

## 🛠️ 常用命令

```bash
make install          # 安装运行依赖
make dev              # 安装开发依赖
make run              # 启动 FastAPI 服务
make test             # 运行单元测试
make test-integration # 运行本地集成测试
make test-e2e         # 运行端到端测试，外部测试默认跳过
make test-all         # 运行全部测试
make test-cov         # 生成单元测试覆盖率
make clean            # 清理缓存和构建产物
```

## 📚 文档导航

- [文档索引](docs/README.md)
- [架构设计](docs/architecture/ARCHITECTURE_DESIGN.md)
- [快速入门](docs/getting-started/QUICKSTART.md)
- [AgentOrchestrator 使用指南](docs/guides/AGENT_ORCHESTRATOR_USAGE.md)
- [Memory 系统](docs/guides/MEMORY_SYSTEM.md)
- [模型弹性指南](docs/guides/MODEL_RESILIENCE_GUIDE.md)
- [可观测性指南](docs/guides/OBSERVABILITY_GUIDE.md)
- [示例索引](examples/README.md)

推荐先运行两个不依赖外部模型的示例：

```bash
venv/bin/python examples/scaffold_selection.py vector_search hitl
venv/bin/python examples/handoff.py
```

## ⚠️ 当前限制

- `vector_search` 已接入可配置 embedding 与 ES / PostgreSQL pgvector 后端；真实数据库扩展、索引规模和外部 Embeddings API 的性能仍需在部署环境验证。
- HITL 已支持配置驱动的 SDK 原生工具审批和 HTTP 恢复，审批状态当前仅保存在进程内，持久化与审计闭环仍待完善。
- `checkpoint` 当前是进程内执行摘要快照，不承担 SDK 中断状态持久化或灾难恢复职责。
- `handoff` 当前支持静态专家目标接入 SDK 原生转交，动态专家注册与专家工具集仍待后续评估。
- 部分历史文档仍记录旧阶段设计，已通过文档索引标注用途，后续会逐步收敛。
- 外部模型和 Langfuse 测试默认跳过，需要显式开启。

## 🧭 下一步建议

1. 在能力选择校验结果上定义模板裁剪规则和配置字段生成映射。
2. 为 `EmbeddingProvider` 增加更多实现或批量化策略，并在真实数据规模下验证 ES / pgvector 索引参数。
3. 为 HITL 补充审批状态持久化、审批列表和审计闭环，避免生产环境由客户端长期保管 `RunState`。
4. 输出能力依赖图和配置矩阵，作为平台勾选能力的元数据来源。

## 📄 许可证

MIT
