# 📚 Agent Harness 文档索引

本文档是 `openai-agent-sdk` 的唯一文档入口。请优先阅读“当前实现”类文档；`design-notes/` 与 `archive/` 用于保留决策背景和阶段记录，不作为当前行为依据。

## 🚀 快速入口

| 文档 | 用途 | 读者 |
| --- | --- | --- |
| [项目 README](../README.md) | 项目定位、能力概览、运行命令 | 所有人 |
| [快速入门](./getting-started/QUICKSTART.md) | 安装、启动与基本调用 | 业务研发 |
| [架构设计](./architecture/ARCHITECTURE_DESIGN.md) | Harness 分层、能力目录、组合校验与脚手架适配 | 架构与平台研发 |
| [示例索引](../examples/README.md) | 示例运行条件与推荐接入路径 | 业务研发 |

## 🏗️ 当前实现文档

| 文档 | 内容 |
| --- | --- |
| [架构设计](./architecture/ARCHITECTURE_DESIGN.md) | Runtime、Capability、OpenAI Agents SDK 接入、脚手架生成前校验 |
| [AgentOrchestrator 使用指南](./guides/AGENT_ORCHESTRATOR_USAGE.md) | 运行时入口与能力装配 |
| [高级 Agent 能力指南](./guides/ADVANCED_AGENTS_GUIDE.md) | HITL、Checkpoint、Handoff 能力说明 |
| [Memory 系统](./guides/MEMORY_SYSTEM.md) | 会话记忆、长期记忆与向量检索现状 |
| [模型弹性指南](./guides/MODEL_RESILIENCE_GUIDE.md) | 路由、降级、重试、超时 |
| [可观测性指南](./guides/OBSERVABILITY_GUIDE.md) | Langfuse 与 OpenTelemetry |
| [结构化日志指南](./guides/SIMPLE_LOGGING_GUIDE.md) | 日志字段与使用方式 |

## 🧩 设计记录

以下文件记录能力演进过程，可能包含早于当前实现的方案细节。

| 文档 | 主题 |
| --- | --- |
| [高级能力集成记录](./design-notes/ADVANCED_AGENTS_INTEGRATION.md) | HITL、Checkpoint、Handoff 早期接入设计 |
| [Auth 与 RateLimit 方案](./design-notes/AUTH_RATE_LIMIT_PLAN.md) | 协议层安全和限流 |
| [上下文压缩方案](./design-notes/CONTEXT_COMPRESSION_PLAN.md) | 压缩策略设计 |
| [Prompt 管理方案](./design-notes/PROMPT_MANAGEMENT_PLAN.md) | Prompt Store 与缓存策略 |
| [Langfuse 集成方案](./design-notes/LANGFUSE_INTEGRATION_PLAN.md) | 可观测方案设计 |
| [模型弹性方案](./design-notes/MODEL_FALLBACK_RETRY_TIMEOUT_PLAN.md) | fallback、retry、timeout 设计 |
| [结构化日志方案](./design-notes/STRUCTURED_LOGGING_PLAN.md) | 日志与脱敏设计 |

## 🗄️ 归档记录

| 文档 | 说明 |
| --- | --- |
| [Memory 系统测试报告](./archive/reports/MEMORY_SYSTEM_TEST_REPORT.md) | 阶段性测试记录 |
| [目录迁移报告](./archive/reports/MIGRATION_REPORT.md) | `app/` 迁移至 `src/` 的历史记录 |
| [安全审查报告](./archive/reports/SECURITY_AUDIT_REPORT.md) | 阶段性审查记录 |

## 🧭 推荐阅读路径

### 业务 Agent 研发

1. [项目 README](../README.md)
2. [快速入门](./getting-started/QUICKSTART.md)
3. [示例索引](../examples/README.md)
4. [AgentOrchestrator 使用指南](./guides/AGENT_ORCHESTRATOR_USAGE.md)

### 平台与脚手架研发

1. [架构设计](./architecture/ARCHITECTURE_DESIGN.md)
2. [高级 Agent 能力指南](./guides/ADVANCED_AGENTS_GUIDE.md)
3. 相关 [设计记录](./design-notes/)

### 能力维护研发

1. 对应 `guides/` 使用指南
2. 对应 `design-notes/` 设计记录
3. `src/capabilities/` 与 `tests/` 中的实际实现和验证

## ⚠️ 状态约定

- `architecture/`、`getting-started/`、`guides/` 描述当前可使用能力，仍以代码和测试为最终依据。
- `design-notes/` 保存设计过程，不保证示例与当前 API 完全一致。
- `archive/` 保存历史记录，不应作为当前测试结论或发布审查结论。
