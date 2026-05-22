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
| `long_term_memory` | runtime | 🟡 部分实现 | DB 记忆 manager 已接入，仍需继续产品化 |
| `vector_search` | runtime | 🟡 部分实现 | ES wrapper 已有，embedding 生成仍待完善 |
| `prompt` | runtime | ✅ 已实现 | Harness 构建 PromptManager，并注入 Runtime |
| `context_compression` | runtime | ✅ 已实现 | 支持 token budget、rolling summary、hybrid |
| `auth` | protocol | ✅ 已实现 | JWT 中间件插件 |
| `rate_limit` | protocol | ✅ 已实现 | Redis/内存限流中间件插件 |
| `observability` | resource | ✅ 已实现 | Langfuse/OpenTelemetry 生命周期和 HTTP Trace |
| `hitl` | runtime | 🧪 实验中 | 需要继续对齐 OpenAI Agents SDK 原生中断/恢复 |
| `checkpoint` | runtime | 🧪 实验中 | 已有基础 manager 和能力钩子 |
| `handoff` | runtime | 🧪 实验中 | 已有 manager，尚未进入主运行链路 |

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
├── README.md                # 文档索引
├── PROJECT_DOCUMENTATION.md # 文档导航
└── reports/                 # 报告类文档
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
    SDK-->>R: RunResult
    R->>C: AFTER_RUN
    C-->>R: 持久化 memory / checkpoint 等结果
    R-->>API: 标准响应
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

未来脚手架生成器可以按以下流程工作：

```mermaid
flowchart LR
    A["平台勾选能力"] --> B["读取 CapabilityManifest"]
    B --> C["解析 depends_on / provides"]
    C --> D["生成配置与依赖列表"]
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
make test      -> 33 passed
make test-all  -> 100 passed, 10 skipped
```

外部模型和 Langfuse 相关测试默认跳过。如需显式运行：

```bash
RUN_EXTERNAL_TESTS=true make test-all
```

## ⚙️ 常用配置开关

```bash
MEMORY_ENABLED=false
MEMORY_LONG_TERM_ENABLED=false
COMPRESSION_ENABLED=false
PROMPT_ENABLED=false
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
- [项目文档导航](docs/PROJECT_DOCUMENTATION.md)
- [架构设计](docs/ARCHITECTURE_DESIGN.md)
- [快速入门](docs/QUICKSTART.md)
- [AgentOrchestrator 使用指南](docs/AGENT_ORCHESTRATOR_USAGE.md)
- [Memory 系统](docs/MEMORY_SYSTEM.md)
- [模型弹性指南](docs/MODEL_RESILIENCE_GUIDE.md)
- [可观测性指南](docs/OBSERVABILITY_GUIDE.md)

## ⚠️ 当前限制

- `vector_search` 仍是部分实现，ES wrapper 已有，embedding 生成仍需补齐。
- HITL/Handoff 仍处于实验阶段，还需要继续对齐 OpenAI Agents SDK 原生中断、恢复和 handoff 方式。
- 部分历史文档仍记录旧阶段设计，已通过文档索引标注用途，后续会逐步收敛。
- 外部模型和 Langfuse 测试默认跳过，需要显式开启。

## 🧭 下一步建议

1. 建立脚手架生成器原型，基于 `CapabilityManifest` 生成能力组合工程。
2. 继续完善 long-term memory 和 vector search 的生产级实现。
3. 将 HITL 对齐 OpenAI Agents SDK 原生 interrupt/resume 模式。
4. 输出能力依赖图和配置矩阵，作为平台勾选能力的元数据来源。

## 📄 许可证

MIT
