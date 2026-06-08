# 🏗️ Agent Harness 架构设计

本文档描述当前仓库的实际架构。目标不是描述一个理想蓝图，而是说明当前代码如何构成可 fork、可配置、可扩展的 Agent Harness 底座。

> 状态：当前实现基准文档。架构判断应优先以本文和代码为准。

## 管理者决策视图：原子能力为什么需要 Harness

这张图用于判断整体技术方向，而不是呈现某一次请求的所有实现细节。它把当前代码中已经存在的装配路径、插件边界和仍待平台化的部分放在一张图里。

```mermaid
flowchart TB
    Product["业务方 fork 后配置<br/>启用 Memory、Prompt、Observability、Auth、RateLimit、HITL 等"]:::decision
    Settings["Settings / Env<br/>能力开关与后端参数"]:::config
    Catalog["CapabilityManifest + Catalog<br/>kind / depends_on / provides / install_order"]:::control
    Validate["运行态依赖校验<br/>检查已启用能力的资源与依赖"]:::control

    Product --> Catalog --> Validate
    Product --> Settings

    subgraph Assembly["装配边界：create_app() + HarnessBuilder"]
        direction LR
        AppFactory["App Factory<br/>创建应用并管理总生命周期"]:::assembly
        ProtocolAssembly["ProtocolRequestChain<br/>显式 HTTP 请求链"]:::assembly
        HarnessBuilder["HarnessBuilder<br/>资源创建、依赖注入、能力注册、依赖校验"]:::assembly
        Harness["Harness + HarnessContext<br/>已装配系统快照 / shared resources"]:::assembly

        AppFactory --> ProtocolAssembly
        AppFactory --> HarnessBuilder --> Harness
    end

    Settings --> AppFactory
    Validate -. "当前提供运行态依赖校验" .-> HarnessBuilder

    subgraph Protocol["协议原子能力：请求进入系统前"]
        direction LR
        RequestCtx["Request Context<br/>Request-ID"]:::protocol
        ObsHttp["Observability HTTP<br/>Trace-ID"]:::protocol
        Auth["Auth<br/>principal"]:::protocol
        Rate["RateLimit<br/>traffic policy"]:::protocol
        Router["FastAPI Routers"]:::runtime
        RequestCtx --> ObsHttp --> Auth --> Rate --> Router
    end

    ProtocolAssembly --> RequestCtx

    subgraph Runtime["运行时原子能力：一次 Agent Run"]
        direction LR
        Orchestrator["AgentOrchestrator<br/>稳定主流程"]:::runtime
        Registry["CapabilityRegistry<br/>setup / before_run / after_run / on_error / teardown"]:::runtime
        Before["Before Run<br/>Memory / Prompt / Compression / Checkpoint"]:::capability
        Model["ModelRouter<br/>Fallback / Retry / Timeout"]:::capability
        SDK["OpenAI Agents SDK<br/>Agent / Runner / Tools / Handoff / HITL"]:::sdk
        After["After Run / Error<br/>Memory write / Checkpoint / audit hooks"]:::capability

        Orchestrator --> Registry --> Before --> Model --> SDK --> After
        Registry --> After
    end

    Router --> Orchestrator
    Harness --> Orchestrator

    subgraph Resources["资源原子能力：被复用且统一释放"]
        direction LR
        Tools["ToolRegistry"]:::resource
        DB["DatabaseResource<br/>shared pool"]:::resource
        MemoryMgr["Mem0MemoryManager<br/>memory context / long-term"]:::resource
        PromptMgr["PromptManager"]:::resource
        Langfuse["Langfuse / OTel"]:::resource
        Infra["Redis / Kafka / HTTP Client"]:::resource
        DB --> MemoryMgr
    end

    Harness --> Tools
    Harness --> DB
    Harness --> PromptMgr
    ProtocolAssembly --> Langfuse
    AppFactory --> Infra
    Tools --> SDK
    MemoryMgr --> Before
    PromptMgr --> Before
    Langfuse --> ObsHttp

    Boundary["当前边界<br/>Manifest 描述能力目录和依赖；<br/>实际实例创建由 Builder / App Factory 显式编码"]:::boundary
    Catalog -.-> Boundary
    HarnessBuilder -.-> Boundary

    classDef decision fill:#13315c,color:#fff,stroke:#13315c;
    classDef config fill:#e9f1ff,stroke:#5677a6,color:#15263d;
    classDef control fill:#e9f5ed,stroke:#48865e,color:#173527;
    classDef assembly fill:#fff2d9,stroke:#bd8324,color:#3f2b0b,stroke-width:2px;
    classDef protocol fill:#e8f1fb,stroke:#4175ae,color:#142d48;
    classDef runtime fill:#eee9fb,stroke:#6850a3,color:#292040;
    classDef capability fill:#efe9fb,stroke:#8465bf,color:#292040;
    classDef resource fill:#e7f6f4,stroke:#37847d,color:#133b38;
    classDef sdk fill:#122a44,color:#fff,stroke:#122a44;
    classDef boundary fill:#fff0f0,stroke:#b45252,color:#4b2020,stroke-dasharray: 4 3;
```

### 读图结论

1. **原子能力不是直接拼到 Router 或 SDK 上。** 每项能力只承担一类职责：协议治理、运行期钩子或共享资源；统一由装配层决定是否启用、实例化和释放。
2. **Harness 是把“可选模块”变成“可运行系统”的必要边界。** 它集中处理依赖注入、资源复用、生命周期、能力顺序和依赖校验，使 `AgentOrchestrator` 保持稳定，新增能力无需持续扩张主执行路径。
3. **SDK 仍然是执行内核。** Harness 没有重写 Agent 引擎；Tools、Handoff、HITL 和模型调用最终仍交给 OpenAI Agents SDK，这能控制自研复杂度。
4. **保持显式装配。** `CapabilityManifest` 当前用于能力目录、依赖说明和运行态检查；实际 `HarnessBuilder`、`AgentOrchestrator` 与 `build_protocol_chain()` 显式装配具体实例，避免引入自动生成业务代码的复杂度。

### 方向校验闸门

| 判断问题 | 当前代码证据 | 判断 |
| --- | --- | --- |
| 关闭能力会不会污染主流程？ | `Capability.is_enabled()`、Registry 仅调度 enabled 能力；Protocol Plugin 按设置注册 | 基本满足 |
| 共享资源会不会由各能力重复创建？ | `HarnessBuilder` 持有 `DatabaseResource`、`PromptManager`、`Mem0MemoryManager` 并注入 Runtime | 方向正确 |
| 能力依赖是否可提前发现？ | `CapabilityManifest.depends_on/provides`、`context.validate_dependencies()` | 已具备基线 |
| 新增能力是否必须修改主 Runtime？ | 通用钩子能力可注册接入；但部分高级能力和资源创建仍在 Builder / Runtime 显式编码 | 部分满足，需继续收敛 |
| HTTP 治理与 Agent 能力是否混杂？ | `ProtocolRequestChain` 与 `CapabilityRegistry` 分离，Observability 仅跨边界贡献 HTTP interceptor | 边界合理 |

## 🎯 架构目标

Agent Harness 的目标是提供一个可复用的工程底座。业务团队 fork 本仓库后，自行开发业务 Agent、业务工具和业务流程，并通过 env 配置启用所需通用能力。

核心目标：

- **可插拔**：能力可以按配置启用或关闭。
- **可配置**：通过 env 文件选择启用或关闭通用能力。
- **可维护**：`API`、`Runtime`、`Capability`、`Infrastructure` 边界清晰。
- **可观测**：请求、运行时、模型调用和工具调用具备追踪入口。
- **可测试**：能力抽象可被单元测试验证，完整链路可由集成测试覆盖。
- **贴合 OpenAI Agents SDK**：Runtime 主路径基于 `Agent`、`Runner`、`function_tool`。

## 🧭 分层设计

```mermaid
flowchart TD
    A["API 接入层<br/>App Factory / Routers / Protocol Plugins"] --> B["Harness 装配层<br/>Builder / Context / Manifest"]
    B --> C["运行时层<br/>AgentOrchestrator"]
    C --> D["Capability 层<br/>Memory / Prompt / Tools / Model Router / Compression"]
    A --> E["协议能力<br/>Auth / RateLimit"]
    A --> O["横切观测接入<br/>Observability HTTP Interceptor"]
    D --> F["基础设施层<br/>DatabaseResource / Redis / Kafka / HTTP Client"]
```

### API 接入层

位置：`src/api`

职责：

- 通过 `create_app()` 暴露并装配 HTTP API。
- 从 FastAPI app state 获取 `Harness`。
- 不直接创建 `Runtime`，不直接判断能力组合。
- 安装协议插件，例如 Auth、RateLimit，以及 Observability 提供的 HTTP 追踪入口。
- 始终安装基础请求上下文，统一负责 Request ID 与日志关联。

代表模块：

- `src/api/app.py`
- `src/api/routers/chat.py`
- `src/api/routers/health.py`
- `src/api/routers/memory.py`
- `src/api/middleware/*`

Auth 与 RateLimit 是协议治理能力。Observability 本体仍是横切资源能力；其 HTTP interceptor 与协议插件共享安装链路，仅因为需要观察 HTTP 请求，并不改变能力归属。

### Harness 装配层

位置：`src/harness`

职责：

- 读取 settings。
- 构建 `ToolRegistry`、`ModelRouter`、`Mem0MemoryManager`、`PromptManager` 等资源。
- 注册基础 capability marker。
- 生成 `HarnessContext`。
- 管理能力资源生命周期。

代表模块：

- `src/harness/builder.py`
- `src/harness/context.py`
- `src/harness/manifest.py`
- `src/harness/config.py`

### 运行时层

位置：`src/application/orchestration`

职责：

- 选择模型。
- 构造 `RunContext`。
- 触发 capability 生命周期钩子。
- 调用 OpenAI Agents SDK `Runner.run_streamed()`。
- 返回 NDJSON 流式事件和最终 `done` 结果。

`Runtime` 不负责直接创建具体资源，资源由 `HarnessBuilder` 注入。

### Capability 层

位置：`src/capabilities`

职责：

- 提供可插拔能力。
- 通过 `Capability` 协议接入运行生命周期。
- 通过 `CapabilityManifest` 暴露能力目录和依赖元信息。

当前能力包括：

- Tools
- Model Routing
- Memory
- Prompt
- Context Compression
- Observability
- Auth
- RateLimit
- HITL / Checkpoint / Handoff

### 基础设施层

位置：`src/infrastructure`

职责：

- 封装数据库、Redis、Kafka、HTTP Client 等基础设施。
- 数据库由 Harness 持有单一 `DatabaseResource`，将同一连接池会话注入 Memory 等消费者。
- 通用 HTTP Client 默认可使用但按需创建，超时与连接限制由配置覆盖。
- 不感知业务 Agent。
- 被 Harness 或 Capability 按需使用。

## 🧩 Capability 抽象

核心接口位于 `src/capabilities/plugin`。

能力通过两个维度描述：

1. **运行接口**：是否参与 `setup`、`before_run`、`after_run`、`on_error`、`teardown`。
2. **生成元数据**：能力名称、类型、依赖、产物、安装顺序。

```mermaid
classDiagram
    class Capability {
        +name
        +manifest
        +is_enabled()
        +setup()
        +before_run(ctx)
        +after_run(ctx)
        +on_error(ctx, error)
        +teardown()
    }

    class CapabilityManifest {
        +name
        +kind
        +config_section
        +depends_on
        +provides
        +install_order
        +tags
    }

    Capability --> CapabilityManifest
```

示例：

```python
CapabilityManifest(
    name="prompt",
    kind=CapabilityKind.RUNTIME,
    config_section="prompt",
    provides=("prompt_manager", "prompt_rendering"),
    install_order=10,
)
```

## 🔄 运行时执行流程

```mermaid
sequenceDiagram
    participant API as API Router
    participant Runtime as AgentOrchestrator
    participant Registry as CapabilityRegistry
    participant SDK as OpenAI Agents SDK

    API->>Runtime: run_stream(session, user_input)
    Runtime->>Registry: dispatch(BEFORE_RUN)
    Registry-->>Runtime: 注入上下文和元数据
    Runtime->>SDK: Runner.run_streamed(agent, enriched_input)
    SDK-->>Runtime: stream events / interruptions
    alt 无审批中断
        Runtime->>Registry: dispatch(AFTER_RUN)
        Registry-->>Runtime: 写入记忆/检查点等结果
        Runtime-->>API: NDJSON done event
    else 工具调用需要审批
        Runtime-->>API: interruptions + run_state
        API->>Runtime: POST /chat/resume/stream + 审批决策
        Runtime->>SDK: Runner.run_streamed(agent, RunState)
        SDK-->>Runtime: 恢复后 stream events
        Runtime->>Registry: dispatch(AFTER_RUN)
    end
```

## 🧬 能力依赖图

```mermaid
flowchart TD
    Tool["tool_registry"]
    Model["model_router"]
    Resilience["model_resilience"]
    MemorySession["memory_session"]
    LongMemory["long_term_memory"]
    Vector["vector_search"]
    Prompt["prompt"]
    Compression["context_compression"]
    Auth["auth"]
    Rate["rate_limit"]
    Obs["observability"]
    Handoff["handoff"]

    Model --> Resilience
    MemorySession --> Compression
    Model --> Compression
    LongMemory --> Vector
    Prompt --> Compression
    Auth --> Rate
    Model --> Handoff
```

说明：

- `model_router` 是模型选择和弹性运行的基础。
- `memory_session` 提供对话上下文，`context_compression` 在其后运行。
- `prompt` 可以为主 Agent 和摘要策略提供模板，但关闭时使用内置兜底文本。
- `auth` 和 `rate_limit` 属于协议层能力，不进入 Agent `RunContext` 主链路。
- `observability` 管理 Langfuse/OpenTelemetry 生命周期，并向 API 接入层提供 HTTP interceptor；它不属于鉴权或流量治理。

## 🧱 HarnessBuilder 装配策略

`HarnessBuilder` 是当前架构中最关键的组合点。

它负责：

- 创建 `ToolRegistry` 并注册默认工具。
- 读取 HITL 配置并将待审批工具映射为 SDK 原生审批工具。
- 读取 Checkpoint 配置并按需注册进程内执行快照能力。
- 读取 Handoff 专家配置并将目标 Agent 挂载到 SDK 主 Agent。
- 创建 `ModelRouter` 和模型弹性配置。
- 创建兼容旧构造参数的空 `MemoryStore`；实际记忆读写由 `Mem0MemoryManager`、Redis 和 MySQL 承担。
- 按需创建一套共享 `DatabaseResource`，避免能力各自创建连接池。
- 按需创建 `Mem0MemoryManager`。
- 按需创建 `PromptManager`。
- 注册 capability marker。
- 创建 `AgentOrchestrator` 并注入依赖。
- 校验能力依赖。

这种方式让 `Runtime` 不再依赖全局单例，也让业务方 fork 后可以围绕 `Builder` 替换或扩展装配逻辑。

HTTP 接入部分由 `src/api/app.py` 和 `ProtocolRequestChain` 负责装配。Chain 直接声明从外到内的请求执行顺序，例如 `RequestContext -> Observability -> Auth -> RateLimit`；FastAPI 中间件的 LIFO 注册适配被封装在 `install_on()` 内部。`src/main.py` 仅保留 ASGI 导出，避免随着协议能力增多而不断承载配置判断。RequestContext 始终位于请求链最外层，独占 `X-Request-ID`；Observability 读取该 ID 并输出 `X-Trace-ID`。

当前 `CapabilityManifest` 是能力目录和依赖说明的元数据来源，不是动态装配解释器。`HarnessBuilder` 与 `AgentOrchestrator` 显式创建或注册 Memory、Prompt、Compression、HITL、Checkpoint 与 Handoff。

## 🧰 OpenAI Agents SDK 适配

当前主路径：

- 工具通过 `ToolRegistry.list_agent_tools()` 转为 SDK 可消费工具。
- 标记为需要审批的工具映射为 SDK `needs_approval=True` 工具。
- `Runtime` 创建 `Agent`。
- `Runtime` 使用 `OpenAIChatCompletionsModel` 注入模型。
- `Runtime` 通过 `Runner.run_streamed()` 执行。
- SDK 返回 `interruptions` 时，`Runtime` 返回序列化 `RunState`，由 `POST /chat/resume/stream` 接收人工决策。
- 恢复请求通过 `RunState.approve()` / `RunState.reject()` 处理决策，再将状态交还 `Runner.run_streamed()`。
- 启用 handoff 时，Runtime 将配置生成的专家 Agent 交给 SDK 原生 `Agent.handoffs` 执行转交。
- 模型降级、重试、超时由 `ModelRouter.run_with_resilience()` 包裹。

原则：

- 不重新实现 Agent 执行引擎。
- Harness 只负责企业工程能力和上下文装配。
- SDK 的 Agent、Runner、Tool 仍是核心抽象。

当前 HTTP 恢复接口采用轻量无状态方式：调用方暂存中断响应里的 `run_state` 并在审批时回传。生产化阶段应将运行状态和审批记录迁移到服务端存储，并补充查询、审计和幂等控制。

当 `HITL_ENABLED=true` 时，`HarnessBuilder` 会装配 `ApprovalManager`，并将 `HITL_REQUIRE_APPROVAL_TOOLS` 列出的工具策略注入 `ToolRegistry`。恢复请求必须回传中断响应中的原始输入、实际模型和运行状态，以保持能力生命周期和 fallback 模型一致；此模式下还必须携带审批请求标识，Runtime 会校验审批请求、会话、中断序号和运行状态的一致性，再将决定应用到 SDK `RunState`。

`Checkpoint` 与 HITL 状态存储保持分离。当前 `CHECKPOINT_ENABLED=true` 只装配进程内 `CheckpointManager`；`CHECKPOINT_AUTO_SAVE=true` 时记录运行前/后的 `AgentState` 摘要。该能力用于运行回看与业务状态检查，不包含 SDK 序列化 `RunState`，因此不能替代 HITL 的持久化状态仓库。

当 `HANDOFF_ENABLED=true` 时，`HANDOFF_AGENTS_JSON` 描述静态专家 Agent 的名称、描述与指令。`HarnessBuilder` 装配 `HandoffManager`，Runtime 使用与主 Agent 相同的当前模型构造专家目标并传入 SDK 原生 `handoffs`。本阶段不扩展专家专属工具和动态路由，以保持配置契约轻量。

Memory 当前包含四层存储语义：MySQL `session_store` 保存会话列表和完整消息流水，也是短期原文记忆的权威兜底；`memory_session` 保存当前会话最近上下文，启用 `MEMORY_SHORT_TERM_ENABLED=true` 且 `REDIS_ENABLED=true` 时由 Redis 承载，读取时 Redis 优先、miss 后读 MySQL 近 N 轮，不使用进程内兜底；`session_summary` 使用 LLM 生成会话滚动摘要，MySQL 持久化、Redis 缓存，作为短期原文过期后的连续性兜底；`long_term_memory` 由 `MEMORY_LONG_TERM_ENABLED=true` 启用，通过 Mem0 负责用户偏好、长期记忆抽取和搜索。业务层不在写入阶段预判长期记忆类型，只在读取和上下文注入阶段对偏好类结果做冲突消解，同一偏好维度只保留最新生效项。

## 🧭 能力目录与运行态检查

`CapabilityManifest` 描述当前 Harness 内置能力的名称、类型、配置域、依赖、产物和装配顺序。它用于文档化能力边界和运行态检查，不用于生成业务代码。

当前工程通过 `/health/capability-catalog` 输出机器可读目录。它与 `/health/capabilities` 的区别是：

| 接口 | 用途 |
| --- | --- |
| `/health/capabilities` | 查看当前运行实例实际装配的能力图 |
| `/health/capability-catalog` | 查看 Harness 支持的能力目录、当前启用状态与依赖矩阵 |

目录中的 `provider_capabilities` 用于说明能力间依赖；`external_resource=true` 表示该能力依赖数据库、Redis、模型服务等外部资源配置。

`memory_manager` 与 `tool_registry` 在目录中标记为 `builder_resource`，表示它们由 `HarnessBuilder` 统一装配，不是业务方需要直接实现的业务能力。

## ✅ 当前已解决的问题

- `Runtime` 不再在 API 路由中全局实例化。
- Memory、Prompt、Observability 已迁移到 Harness 或插件装配。
- 当前装配能力图已可通过 `/health/capabilities` 查看。
- 能力目录和依赖矩阵已可通过 `/health/capability-catalog` 读取。
- Memory 长期层统一使用 Mem0；原有 SQLAlchemy / ES / pgvector 模块保留为内部历史实现，不作为平台配置主路径。
- Database 已收敛为 Harness 持有的共享连接池，并开放 pool 配置参数。
- HTTP Client 支持可配置超时/连接限制并采用懒加载。
- 协议插件 setup 失败会阻止启动；Redis 限流默认 fail-closed。
- 测试已拆分为 `unit`、`integration`、`e2e`。
- README 和文档索引已按当前实现更新。

## ⚠️ 后续演进重点

- 为 `/chat` 会话标识与 `/memory/*` 管理接口补充认证主体/租户级资源授权，避免调用方仅凭 `session_id` 或 `user_id` 访问记忆。
- 为 Mem0 接入增加成本观测、失败重试、租户隔离和生产环境索引/存储参数验证。
- 为 HITL 增加服务端状态持久化、审批查询、审计和幂等控制。
- 继续清理历史方案文档中与当前实现不一致的表述。
