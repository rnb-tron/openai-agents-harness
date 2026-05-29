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

![Agent Harness Architecture](docs/assets/agent-harness-architecture-cn-v6.png)

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

当前 `CapabilityManifest` 已可支持能力目录与组合校验，但运行时装配仍由 `HarnessBuilder` 和 `AgentOrchestrator` 显式实现；本仓库是可演进的工程底座，而不是已完成的全动态生成平台。

## 🧰 可插拔能力

平台面向业务选择的是能力项，而不是 Python、FastAPI、OpenAI Agents SDK 等基础技术栈。基础栈负责让工程可运行；下表列出 Harness 能装配或因依赖自动引入的能力，是后续脚手架进行选择、裁剪与生成配置的范围。

| 能力域 | 能力项 | 类型 / 状态 | 技术选型 | 当前技术实现方案 | 装配入口 |
| --- | --- | --- | --- | --- | --- |
| 工具执行 | `tool_registry` | runtime / 已实现，基础必选 | OpenAI Agents SDK `function_tool` | `ToolRegistry` 注册工具元数据并转换为 SDK Tool；审批策略可附加到工具定义 | Harness 默认创建 |
| 模型访问 | `model_router` | runtime / 已实现，基础必选 | OpenAI Agents SDK + OpenAI-compatible API | `ModelRouter` 按任务选择默认或推理模型，并由 `AgentOrchestrator` 调用 SDK `Runner` | Harness 默认创建 |
| 模型稳定性 | `model_resilience` | runtime / 部分实现 | 自研 Retry / Timeout / Fallback | 按弹性配置构建 runner 包装与 fallback 模型链，隔离模型调用故障 | `MODEL_RESILIENCE_ENABLED` |
| 会话记录 | `session_store` | resource / 已实现 | MySQL + SQLAlchemy Async | 持久化用户会话、完整消息流水和后续事件扩展，供 UI 历史会话与审计使用 | `SESSION_STORE_ENABLED` |
| 会话记忆 | `memory_session` | runtime / 已实现 | Redis ShortTermMemory / 进程内降级 | 在 Agent 执行前后读取、写入当前会话最近上下文；启用 Mem0 manager 时由 Redis 短期记忆承载 | 默认装配 |
| 长期记忆 | `long_term_memory` | runtime / 已实现 | Mem0 | 由 Mem0 负责用户偏好与长期记忆抽取、写入和搜索；业务层不预判长期记忆类型 | `MEMORY_ENABLED` |
| 长期记忆资源 | `memory_manager` | resource / 已实现，依赖自动引入 | Mem0 SDK | 持有 Mem0 适配器和 Redis 短期会话缓存；长期向量存储可选 Mem0 默认、pgvector 或 Elasticsearch；读取偏好时同一维度只注入最新生效项 | 选择长期记忆时自动引入 |
| 语义召回 | `vector_search` | runtime / 已实现 | Mem0 Search + pgvector/ES 可选 | 由 Mem0 搜索返回偏好和长期记忆；偏好类查询会做冲突消解；向量后端通过 `MEMORY_VECTOR_STORE` 选择 | `MEMORY_ENABLED` |
| Prompt 管理 | `prompt` | runtime / 已实现 | Langfuse Prompt + Local YAML | `PromptManager` 负责拉取、TTL 缓存与渲染；`CompositeStore` 支持远端失败时本地降级 | `PROMPT_ENABLED` |
| 上下文治理 | `context_compression` | runtime / 已实现 | tiktoken + 可配置 LLM Summary | 提供 token budget 截断、rolling summary 与 hybrid 策略，在执行前压缩上下文 | `COMPRESSION_ENABLED` |
| 人工审批 | `hitl` | runtime / 部分实现 | OpenAI Agents SDK 原生 HITL | 工具标记 `needs_approval` 触发中断；`/chat/resume` 与流式恢复接口处理同意或拒绝 | `HITL_ENABLED` |
| 状态快照 | `checkpoint` | runtime / 部分实现 | 进程内 Checkpoint Manager | 保存执行摘要与状态展示信息，当前不等同于持久化 SDK `RunState` | `CHECKPOINT_ENABLED` |
| Agent 协作 | `handoff` | runtime / 部分实现 | OpenAI Agents SDK 原生 Handoff | 按配置构建目标 Agent，并注入主 Agent 的 `handoffs` 列表完成专家转交 | `HANDOFF_ENABLED` |
| 身份认证 | `auth` | protocol / 已实现 | PyJWT | `AuthPlugin` 在 HTTP 请求链解析 JWT，并写入 `request.state.principal` | `AUTH_ENABLED` |
| 用户限流 | `rate_limit` | protocol / 已实现 | Token Bucket + Redis / Memory backend | `RateLimitPlugin` 默认使用 Auth 产生的 principal 作为限流键；可显式选择 IP 兼容策略 | `RATE_LIMIT_ENABLED` |
| 可观测性 | `observability` | resource + protocol adapter / 已实现 | Langfuse + OpenTelemetry + OpenInference | `ObservabilityCapability` 由 Harness 管理 tracer 生命周期；HTTP plugin 只贡献请求 span 入口 | `LANGFUSE_ENABLED` |

装配边界：

- `runtime` 能力进入 Agent 执行过程，由 `HarnessBuilder` 创建资源并注入 `AgentOrchestrator`。
- `protocol` 能力进入 HTTP 请求链，当前显式顺序为 `RequestContext -> Observability -> Auth -> RateLimit`。
- `resource` 能力由 Harness 负责初始化与释放，可向 runtime 或 protocol 提供共享资源。

当前尚未形成独立 capability 的候选能力包括 `RAG`、`Audit` 和 Kafka 事件发布；它们属于后续平台能力规划，不应在当前能力清单中标记为已具备。

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
| `long_term_memory` | runtime | ✅ 已实现 | Mem0 后端已接入 |
| `vector_search` | runtime | ✅ 已实现 | Mem0 Search |
| `prompt` | runtime | ✅ 已实现 | Harness 构建 PromptManager，并注入 Runtime |
| `context_compression` | runtime | ✅ 已实现 | 支持 token budget、rolling summary、hybrid |
| `auth` | protocol | ✅ 已实现 | JWT 中间件插件 |
| `rate_limit` | protocol | ✅ 已实现 | Redis/内存限流中间件插件 |
| `observability` | resource | ✅ 已实现 | Langfuse/OpenTelemetry 生命周期，并向 HTTP 链路贡献追踪入口 |
| `hitl` | runtime | 🟡 部分实现 | 配置驱动装配，已接入 SDK 原生中断与 `POST /chat/resume` |
| `checkpoint` | runtime | 🟡 部分实现 | 配置驱动的进程内执行快照，不等同于 SDK `RunState` 存储 |
| `handoff` | runtime | 🟡 部分实现 | 配置驱动装配，主 Agent 已接入 SDK 原生 `handoffs` |

## 🏗️ 当前目录结构

```text
src/
├── api/
│   ├── app.py               # FastAPI app factory 与接入层装配
│   ├── middleware/          # ProtocolPlugin、Auth / RateLimit / 请求上下文
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
└── main.py                  # 仅导出 ASGI app

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
| 资源装配 | `HarnessBuilder` 统一构建 manager 与共享数据库资源；`api.app` 组装 HTTP 接入 |
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
make test      -> 74 passed
make test-all  -> 146 passed, 10 skipped
```

依赖外部模型服务的 E2E 测试默认跳过；`tests/e2e/test_langfuse.py` 当前会随全量测试执行。如需显式运行外部模型用例：

```bash
RUN_EXTERNAL_TESTS=true make test-all
```

## ⚙️ 常用配置开关

```bash
MEMORY_ENABLED=false
COMPRESSION_ENABLED=false
PROMPT_ENABLED=false
HITL_ENABLED=false
HANDOFF_ENABLED=false
AUTH_ENABLED=false
RATE_LIMIT_ENABLED=false
LANGFUSE_ENABLED=false
MODEL_RESILIENCE_ENABLED=false
```

基础资源参数具备默认值，通常无需配置；部署容量或外呼策略变化时可覆盖：

```bash
HTTP_TIMEOUT_SECONDS=30
HTTP_CONNECT_TIMEOUT_SECONDS=10
HTTP_MAX_CONNECTIONS=100
HTTP_MAX_KEEPALIVE_CONNECTIONS=20
DATABASE_POOL_SIZE=10
DATABASE_MAX_OVERFLOW=20
DATABASE_POOL_TIMEOUT_SECONDS=30
DATABASE_POOL_RECYCLE_SECONDS=1800
RATE_LIMIT_FAIL_OPEN=false
```

通用 HTTP Client 默认允许使用但采用懒加载，不会因未被能力或工具使用而在启动阶段创建连接。数据库由 Harness 统一持有一套共享连接池，Memory 不再建立独立 pool。使用 Redis 限流时必须同时启用 Redis；限流启动探活或请求阶段后端失败默认阻止服务/返回 `503`，仅在显式设置 `RATE_LIMIT_FAIL_OPEN=true` 时降级放行。

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

Mem0 Memory Backend：

```bash
SESSION_STORE_ENABLED=true
DATABASE_URL=mysql+aiomysql://agent:secret@localhost:3306/agent
REDIS_ENABLED=true
REDIS_URL=redis://localhost:6379/0
MEMORY_ENABLED=true
MEMORY_MEM0_MODE=local
MEMORY_VECTOR_STORE=none
# MEMORY_VECTOR_STORE=pgvector 时配置 MEMORY_PGVECTOR_DATABASE_URL
# MEMORY_VECTOR_STORE=elasticsearch 时配置 MEMORY_ES_HOSTS / MEMORY_ES_INDEX
MEMORY_PREFERENCE_CACHE_TTL_SEC=900
MEMORY_SESSION_SUMMARY_ENABLED=true
MEMORY_SESSION_SUMMARY_CACHE_TTL=2592000
MEMORY_SESSION_SUMMARY_INITIAL_MESSAGES=4
MEMORY_SESSION_SUMMARY_UPDATE_MESSAGES=6
MEMORY_SESSION_SUMMARY_MODEL=
MEMORY_SESSION_SUMMARY_MAX_TOKENS=512
# 可选：需要完全自定义 Mem0 OSS 配置时再设置 MEMORY_MEM0_CONFIG_JSON
```

会话记录、短期会话记忆、会话摘要、长期记忆分层管理：MySQL 保存完整会话与消息流水；Redis 保存当前会话最近上下文；MySQL 持久化 LLM 会话摘要并用 Redis 做快速缓存；Mem0 统一管理用户偏好、长期记忆抽取和语义检索。`before_run` 只读取已有摘要，不同步重建；`after_run` 后台更新摘要，避免请求链路被历史消息读取和 LLM 摘要阻塞。

Mem0 local 模式默认复用主模型配置：`llm.config` 使用 `OPENAI_API_KEY`、`OPENAI_BASE_URL` 和 `AGENT_MODEL_DEFAULT`；`embedder.config` 使用 `OPENAI_API_KEY`、`OPENAI_BASE_URL` 和 `MEMORY_EMBEDDING_MODEL`。传给 Mem0 SDK 时，网关地址字段使用 Mem0 兼容的 `openai_base_url`。

长期写入边界：`after_run` 只异步过滤空内容、寒暄、工具失败和拒绝执行等明显噪声；通过过滤的 user/assistant 对话会提交给 Mem0，由 Mem0 判断是否抽取、合并、更新或忽略长期记忆。

偏好记忆采用“保留历史、注入生效版本”的策略：写入时直接把 user/assistant messages 提交给 Mem0，由 Mem0 判断是否抽取为用户偏好或其他长期记忆；检索或注入上下文时，业务层再对偏好类结果做轻量冲突消解，同一偏好维度只保留最新一条。这样既不破坏 Mem0 中的历史记忆，又避免“中文回答”和“英文回答”等冲突偏好同时进入 prompt。使用 Mem0 Platform 时，将 `MEMORY_MEM0_MODE=platform` 并配置 `MEMORY_MEM0_API_KEY`。

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

响应中的 `resolved_selection` 包含基础能力与可自动装配的内部依赖，`external_requirements` 描述需要平台生成配置的外部资源。例如选择 `vector_search` 时，会推导 `long_term_memory` 与内部 `memory_manager`；Mem0 管理 embedding 与长期检索，不再要求业务数据库或单独的 embedding provider。

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

- `vector_search` 已切换为 Mem0 Search；检索质量、索引参数和成本仍需在真实数据规模下验证。
- HITL 已支持配置驱动的 SDK 原生工具审批和 HTTP 恢复，审批状态当前仅保存在进程内，持久化与审计闭环仍待完善。
- `checkpoint` 当前是进程内执行摘要快照，不承担 SDK 中断状态持久化或灾难恢复职责。
- `handoff` 当前支持静态专家目标接入 SDK 原生转交，动态专家注册与专家工具集仍待后续评估。
- `/chat` 与 `/memory/*` 还没有按认证主体或租户绑定会话/记忆资源，生产部署前需要补齐对象级授权。
- 部分历史文档仍记录旧阶段设计，已通过文档索引标注用途，后续会逐步收敛。
- 依赖外部模型服务的 E2E 测试默认跳过，需要显式开启；Langfuse E2E 用例当前默认执行。

## 🧭 下一步建议

1. 在能力选择校验结果上定义模板裁剪规则和配置字段生成映射。
2. 为 Mem0 接入增加批量写入、成本观测、失败重试和租户隔离策略。
3. 为 HITL 补充审批状态持久化、审批列表和审计闭环，避免生产环境由客户端长期保管 `RunState`。
4. 输出能力依赖图和配置矩阵，作为平台勾选能力的元数据来源。

## 📄 许可证

MIT
