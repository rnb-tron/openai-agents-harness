# 📚 Agent Harness 项目文档导航

本文档是 `openai-agent-sdk` 的完整文档导航，用于帮助研发、架构和平台同学快速找到对应资料。

## 🚀 当前必读

| 文档 | 说明 |
| --- | --- |
| [项目 README](../README.md) | 项目定位、当前架构、能力体系、运行方式 |
| [文档索引](./README.md) | 文档分组和推荐阅读路径 |
| [架构设计](./ARCHITECTURE_DESIGN.md) | 当前 Harness 架构、Capability 抽象、脚手架生成设计 |
| [快速入门](./QUICKSTART.md) | 本地安装、配置、启动和测试 |

## 🏗️ 架构与运行时

| 文档 | 重点内容 |
| --- | --- |
| [架构设计](./ARCHITECTURE_DESIGN.md) | 分层设计、模块边界、运行流程、能力依赖图 |
| [AgentOrchestrator 使用指南](./AGENT_ORCHESTRATOR_USAGE.md) | Agent 运行入口、不同能力组合下的使用方式 |
| [Memory 系统](./MEMORY_SYSTEM.md) | 短期记忆、长期记忆、上下文管理、向量检索 |

## 🧩 能力文档

| 文档 | 能力 | 当前状态 |
| --- | --- | --- |
| [模型弹性指南](./MODEL_RESILIENCE_GUIDE.md) | Model Router / Fallback / Retry / Timeout | 部分生产化 |
| [可观测性指南](./OBSERVABILITY_GUIDE.md) | Langfuse / OpenTelemetry | 已接入 |
| [Prompt 管理方案](./PROMPT_MANAGEMENT_PLAN.md) | PromptManager / YAML / Langfuse | 已接入 |
| [上下文压缩方案](./CONTEXT_COMPRESSION_PLAN.md) | Token Budget / Rolling Summary / Hybrid | 已接入 |
| [Auth 与 RateLimit 方案](./AUTH_RATE_LIMIT_PLAN.md) | JWT / 限流中间件 | 已接入 |
| [高级能力指南](./ADVANCED_AGENTS_GUIDE.md) | HITL / Checkpoint / Handoff | 实验中 |

## 🔬 方案与设计记录

| 文档 | 说明 |
| --- | --- |
| [模型降级重试超时方案](./MODEL_FALLBACK_RETRY_TIMEOUT_PLAN.md) | 模型弹性能力设计过程 |
| [Langfuse 集成方案](./LANGFUSE_INTEGRATION_PLAN.md) | 可观测性设计过程 |
| [结构化日志方案](./STRUCTURED_LOGGING_PLAN.md) | 日志、脱敏、上下文设计 |
| [高级能力集成](./ADVANCED_AGENTS_INTEGRATION.md) | HITL、Checkpoint、Handoff 集成说明 |
| [简单日志指南](./SIMPLE_LOGGING_GUIDE.md) | 基础日志使用说明 |

## 📊 报告类文档

| 文档 | 说明 |
| --- | --- |
| [Memory 系统测试报告](./reports/MEMORY_SYSTEM_TEST_REPORT.md) | Memory 测试记录 |
| [迁移报告](./reports/MIGRATION_REPORT.md) | 历史目录迁移记录 |
| [安全审计报告](./reports/SECURITY_AUDIT_REPORT.md) | 安全审计记录 |
| [文档总结](./DOCUMENTATION_SUMMARY.md) | 历史文档整理记录 |

## 🧭 按角色阅读

### 业务 Agent 研发

1. [项目 README](../README.md)
2. [快速入门](./QUICKSTART.md)
3. [AgentOrchestrator 使用指南](./AGENT_ORCHESTRATOR_USAGE.md)
4. [Prompt 管理方案](./PROMPT_MANAGEMENT_PLAN.md)

### 平台脚手架研发

1. [架构设计](./ARCHITECTURE_DESIGN.md)
2. [项目 README](../README.md)
3. [Auth 与 RateLimit 方案](./AUTH_RATE_LIMIT_PLAN.md)
4. [上下文压缩方案](./CONTEXT_COMPRESSION_PLAN.md)

### 基础设施/稳定性研发

1. [模型弹性指南](./MODEL_RESILIENCE_GUIDE.md)
2. [可观测性指南](./OBSERVABILITY_GUIDE.md)
3. [结构化日志方案](./STRUCTURED_LOGGING_PLAN.md)
4. [安全审计报告](./reports/SECURITY_AUDIT_REPORT.md)

## 🧭 当前文档可信度说明

- README 和 [架构设计](./ARCHITECTURE_DESIGN.md) 已按当前代码实现更新。
- 方案类文档保留了设计演进过程，可能包含早期表述。
- 报告类文档保留历史记录，不一定代表当前最终形态。
- 如文档之间存在差异，以当前代码、README 和架构设计为准。
