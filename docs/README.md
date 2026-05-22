# 📚 Agent Harness 文档索引

这里是 `openai-agent-sdk` 的文档入口。建议优先阅读“当前状态文档”，历史方案类文档用于理解演进过程，不代表全部都是最终实现。

## 🚀 快速入口

| 文档 | 用途 | 建议阅读对象 |
| --- | --- | --- |
| [README](../README.md) | 项目总览、架构、运行和测试 | 所有人 |
| [项目文档导航](./PROJECT_DOCUMENTATION.md) | 全部文档分组索引 | 所有人 |
| [快速入门](./QUICKSTART.md) | 本地启动和基本使用 | 新接入同学 |
| [架构设计](./ARCHITECTURE_DESIGN.md) | 当前 Harness 架构和能力边界 | 架构、平台、核心研发 |

## 🏗️ 当前架构与核心模块

| 文档 | 内容 |
| --- | --- |
| [架构设计](./ARCHITECTURE_DESIGN.md) | 分层设计、Harness 装配、Capability 抽象、脚手架生成适配 |
| [AgentOrchestrator 使用指南](./AGENT_ORCHESTRATOR_USAGE.md) | Agent 运行时入口和使用方式 |
| [Memory 系统](./MEMORY_SYSTEM.md) | 短期记忆、长期记忆、向量检索相关说明 |
| [模型弹性指南](./MODEL_RESILIENCE_GUIDE.md) | 模型降级、重试、超时 |
| [可观测性指南](./OBSERVABILITY_GUIDE.md) | Langfuse / OpenTelemetry 接入 |

## 🧩 能力方案文档

| 文档 | 内容 | 状态 |
| --- | --- | --- |
| [Prompt 管理方案](./PROMPT_MANAGEMENT_PLAN.md) | PromptManager、Store、缓存和兜底策略 | 方案 + 部分实现 |
| [上下文压缩方案](./CONTEXT_COMPRESSION_PLAN.md) | token budget、rolling summary、hybrid 策略 | 方案 + 已接入 |
| [Auth / RateLimit 方案](./AUTH_RATE_LIMIT_PLAN.md) | 协议层插件和安全控制 | 方案 + 已接入 |
| [Langfuse 集成方案](./LANGFUSE_INTEGRATION_PLAN.md) | 可观测性方案设计 | 方案 + 已接入 |
| [模型降级重试超时方案](./MODEL_FALLBACK_RETRY_TIMEOUT_PLAN.md) | 模型弹性设计 | 方案 + 部分实现 |
| [结构化日志方案](./STRUCTURED_LOGGING_PLAN.md) | 日志结构、脱敏、上下文关联 | 方案 + 已接入 |

## 🧪 高级 Agent 能力

| 文档 | 内容 | 状态 |
| --- | --- | --- |
| [高级能力指南](./ADVANCED_AGENTS_GUIDE.md) | HITL、Checkpoint、Handoff 使用说明 | 实验中 |
| [高级能力集成](./ADVANCED_AGENTS_INTEGRATION.md) | 高级能力接入细节 | 实验中 |

## 📊 报告与历史记录

| 文档 | 内容 |
| --- | --- |
| [Memory 系统测试报告](./reports/MEMORY_SYSTEM_TEST_REPORT.md) | Memory 测试记录 |
| [迁移报告](./reports/MIGRATION_REPORT.md) | 历史目录迁移记录 |
| [安全审计报告](./reports/SECURITY_AUDIT_REPORT.md) | 安全检查记录 |
| [文档总结](./DOCUMENTATION_SUMMARY.md) | 历史文档整理记录 |

## 🧭 推荐阅读路径

### 新接入研发

1. [README](../README.md)
2. [快速入门](./QUICKSTART.md)
3. [AgentOrchestrator 使用指南](./AGENT_ORCHESTRATOR_USAGE.md)

### 平台/脚手架研发

1. [架构设计](./ARCHITECTURE_DESIGN.md)
2. [项目文档导航](./PROJECT_DOCUMENTATION.md)
3. [Prompt 管理方案](./PROMPT_MANAGEMENT_PLAN.md)
4. [Auth / RateLimit 方案](./AUTH_RATE_LIMIT_PLAN.md)

### 生产化能力研发

1. [Memory 系统](./MEMORY_SYSTEM.md)
2. [模型弹性指南](./MODEL_RESILIENCE_GUIDE.md)
3. [可观测性指南](./OBSERVABILITY_GUIDE.md)
4. [结构化日志方案](./STRUCTURED_LOGGING_PLAN.md)

## ⚠️ 文档状态说明

- “指南”类文档用于使用当前实现。
- “方案”类文档包含设计过程，部分内容可能早于当前实现。
- “报告”类文档用于保留历史测试、审计和迁移记录。
- 如 README 与历史方案文档不一致，以 README 和当前代码为准。
