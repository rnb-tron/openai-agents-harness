# Agent Harness 项目文档索引

欢迎查阅 **Agent Harness** 的完整文档!

---

## 📚 文档导航

### 🚀 入门文档

| 文档 | 说明 | 适合人群 |
|------|------|----------|
| [快速入门指南](./QUICKSTART.md) | 从 0 到 1 开始使用 Agent Harness | 所有用户 |
| [架构设计](./ARCHITECTURE_DESIGN.md) | 六层架构设计详解 | 开发者、架构师 |

---

### 🔧 核心功能

| 文档 | 说明 | 关键内容 |
|------|------|----------|
| [AgentOrchestrator 使用指南](./AGENT_ORCHESTRATOR_USAGE.md) | 三种使用模式详解 | 简单/中等/完整模式 |
| [高级能力指南](./ADVANCED_AGENTS_GUIDE.md) | HITL/Checkpoint/Handoff | 高级功能使用 |
| [记忆系统](./MEMORY_SYSTEM.md) | 短期/长期记忆管理 | 记忆存储与检索 |
| [模型弹性指南](./MODEL_RESILIENCE_GUIDE.md) | 降级/重试/超时控制 | 弹性设计 |

---

### 📊 可观测性与运维

| 文档 | 说明 | 关键内容 |
|------|------|----------|
| [可观测性指南](./OBSERVABILITY_GUIDE.md) | Langfuse 集成 | Trace/Span/Metrics |
| [Langfuse 集成计划](./LANGFUSE_INTEGRATION_PLAN.md) | 可观测性技术方案 | 架构设计 |

---

### 🏗️ 工程实践

| 文档 | 说明 | 关键内容 |
|------|------|----------|
| [目录结构迁移报告](./MIGRATION_REPORT.md) | 目录重构记录 | 迁移过程 |
| [安全审计报告](./SECURITY_AUDIT_REPORT.md) | 代码安全扫描 | 安全最佳实践 |
| [Git 提交指南](./GIT_SUBMIT_GUIDE.md) | 版本控制规范 | Git Workflow |

---

### 🔬 技术方案

| 文档 | 说明 | 关键内容 |
|------|------|----------|
| [模型降级重试超时方案](./MODEL_FALLBACK_RETRY_TIMEOUT_PLAN.md) | 模型弹性技术方案 | 技术设计 |
| [高级能力集成指南](./ADVANCED_AGENTS_INTEGRATION.md) | 如何集成高级能力 | 集成方案 |

---

## 🎯 按场景查找文档

### 场景 1: 我是新用户,想快速上手

👉 阅读顺序:
1. [快速入门指南](./QUICKSTART.md) - 5 分钟了解项目
2. 运行测试验证环境
3. 启动服务体验 API

### 场景 2: 我想了解架构设计

👉 阅读顺序:
1. [架构设计](./ARCHITECTURE_DESIGN.md) - 理解六层架构
2. [目录结构迁移报告](./MIGRATION_REPORT.md) - 了解目录组织
3. [AgentOrchestrator 使用指南](./AGENT_ORCHESTRATOR_USAGE.md) - 核心组件

### 场景 3: 我想启用高级能力

👉 阅读顺序:
1. [高级能力指南](./ADVANCED_AGENTS_GUIDE.md) - 了解能力列表
2. [AgentOrchestrator 使用指南](./AGENT_ORCHESTRATOR_USAGE.md) - 配置方法
3. [高级能力集成指南](./ADVANCED_AGENTS_INTEGRATION.md) - 集成步骤

### 场景 4: 我想优化稳定性和性能

👉 阅读顺序:
1. [模型弹性指南](./MODEL_RESILIENCE_GUIDE.md) - 降级/重试/超时
2. [记忆系统](./MEMORY_SYSTEM.md) - 记忆优化
3. [可观测性指南](./OBSERVABILITY_GUIDE.md) - 监控和追踪

### 场景 5: 我想部署到生产环境

👉 阅读顺序:
1. [安全审计报告](./SECURITY_AUDIT_REPORT.md) - 安全检查
2. [可观测性指南](./OBSERVABILITY_GUIDE.md) - 监控配置
3. [Git 提交指南](./GIT_SUBMIT_GUIDE.md) - 版本管理

---

## 📖 文档结构

```
docs/
├── QUICKSTART.md                          # 快速入门 (新!)
├── PROJECT_DOCUMENTATION.md               # 本文档 (新!)
├── AGENT_ORCHESTRATOR_USAGE.md            # Orchestrator 使用 (新!)
├── ADVANCED_AGENTS_GUIDE.md               # 高级能力指南
├── ADVANCED_AGENTS_INTEGRATION.md         # 高级能力集成
├── ARCHITECTURE_DESIGN.md                 # 架构设计
├── MEMORY_SYSTEM.md                       # 记忆系统
├── MODEL_RESILIENCE_GUIDE.md              # 模型弹性
├── OBSERVABILITY_GUIDE.md                 # 可观测性
├── LANGFUSE_INTEGRATION_PLAN.md           # Langfuse 集成
├── MODEL_FALLBACK_RETRY_TIMEOUT_PLAN.md   # 模型弹性方案
├── MIGRATION_REPORT.md                    # 迁移报告
├── SECURITY_AUDIT_REPORT.md               # 安全审计
└── GIT_SUBMIT_GUIDE.md                    # Git 指南
```

---

## 🔗 外部资源

- **GitHub 仓库**: https://github.com/rnb-tron/openai-agent-sdk
- **OpenAI Agents SDK**: https://github.com/openai/openai-agents-python
- **Langfuse**: https://langfuse.com/

---

## 📝 文档更新记录

| 日期 | 文档 | 更新内容 |
|------|------|----------|
| 2026-05-20 | 快速入门指南 | 新增完整入门指南 |
| 2026-05-20 | 项目文档索引 | 新增本文档 |
| 2026-05-20 | AgentOrchestrator 使用指南 | 新增三种模式详解 |
| 2026-05-20 | 高级能力指南 | 完善 HITL/Checkpoint/Handoff |
| 2026-05-19 | 模型弹性指南 | 完善降级/重试/超时 |

---

## 💡 如何贡献文档

1. Fork 项目
2. 创建分支 (`git checkout -b docs/your-feature`)
3. 修改文档
4. 提交 PR (`git commit -m "docs: improve XXX"`)
5. 等待审核

---

## ❓ 常见问题

### Q: 我应该从哪个文档开始?

A: 推荐从 [快速入门指南](./QUICKSTART.md) 开始,5 分钟即可上手!

### Q: 文档有中文版吗?

A: 所有文档都是中文! 🎉

### Q: 如何找到特定功能的文档?

A: 查看上面的 "按场景找文档" 部分,或直接搜索关键词。

### Q: 文档有错误怎么办?

A: 欢迎提交 Issue 或 PR 帮助修正!

---

## 📞 联系我们

- **Issue**: https://github.com/rnb-tron/openai-agent-sdk/issues
- **Email**: your-email@example.com
- **Discussion**: https://github.com/rnb-tron/openai-agent-sdk/discussions

---

**祝你阅读愉快!** 📚
