# AGENTS.md

## 项目定位

本仓库是一个通用 Agent Harness 工程底座，不是具体业务 Agent。

项目目标是提供业务方 fork 后开发 Agent 应用所需的通用工程能力，包括运行时编排、工具注册、会话存储、记忆、Prompt 管理、可观测性、认证、限流、模型弹性、HITL、Checkpoint、Handoff 等。

本仓库不负责：

- 根据能力选择自动生成业务代码。
- 内置具体业务逻辑、业务 Agent、业务工具或业务流程。
- 提供特定业务领域的 Prompt、规则、UI 或 API。

业务方 fork 后可以自行添加业务逻辑，并通过 `config/*.env` 中的能力开关启用所需通用能力。

## 修改原则

- 保持主路径通用，不向 `src/application/orchestration`、`src/api` 或 `src/capabilities` 写入具体业务逻辑。
- 示例只能用于说明 Harness 能力，不应成为运行时主路径依赖。
- 能力应通过 env 开关、`HarnessBuilder`、`CapabilityRegistry` 或协议插件接入，避免在路由或 runtime 中散落硬编码判断。
- 普通 Agent 编排路径应保持轻量；HITL、Handoff、Checkpoint 等增强能力应按需引入，避免污染不启用这些能力的阅读路径。
- 不要重新引入“脚手架生成”“按勾选能力生成代码”等描述或实现。

## 关键目录

- `src/application/orchestration/`：Agent runtime 主流程与旁路组件。
- `src/harness/`：Harness 装配、上下文、能力目录和依赖校验。
- `src/capabilities/`：可插拔能力实现。
- `src/api/`：HTTP 路由、协议插件和本地调试 UI。
- `src/infrastructure/`：数据库、Redis、HTTP client 等基础设施资源。
- `config/`：环境配置示例与本地配置。
- `docs/design/`：架构设计和历史设计记录。
- `docs/usage/`：当前能力使用指南。
- `examples/`：能力演示，不作为测试或业务主路径。

## Runtime 边界

`AgentOrchestrator` 是对外 runtime 门面：

- `run_stream()`：普通流式聊天入口。
- `resume_stream_with_approval()`：HITL / SDK interruption 恢复入口，保留在门面上供路由调用。

复杂职责已拆到旁路组件：

- `agent_factory.py`：OpenAI client、SDK Agent、instructions 构造。
- `agent_observation.py`：Langfuse observation 包装。
- `agent_resume.py`：SDK interruption / HITL 审批恢复。
- `advanced_runtime.py`：HITL / Checkpoint / Handoff 可选装配。
- `stream_events.py`：OpenAI Agents SDK 流事件转换。

如果要自定义业务编排，优先新增或替换 runtime，而不是把业务逻辑写进通用 `AgentOrchestrator`。

## 配置约定

- 用户可见配置应优先放在 `config/test.env.example` 和 `config/prod.env.example`。
- 配置项按能力域组织，中文注释说明用途。
- 空值配置使用 `KEY="" # 中文注释`，避免 dotenv 把注释解析为值。
- 会话存储数据库使用 `SESSION_STORE_DATABASE_*`，不要重新暴露 `DATABASE_URL`。
- pgvector 长期记忆使用 `MEMORY_PGVECTOR_PG*`，不要和会话存储数据库配置混用。

## 验证建议

常用快速验证：

```bash
venv/bin/python -m pytest tests/unit/test_core_config.py
venv/bin/python -m pytest tests/unit/test_agent_runtime_resume.py tests/unit/test_chat_resume_router.py
venv/bin/python -m pytest tests/unit/test_health_router.py tests/unit/test_capability_catalog.py
```

修改 orchestration 相关代码后建议运行：

```bash
venv/bin/python -m pytest tests/unit/test_agent_runtime_resume.py tests/unit/test_chat_resume_router.py tests/unit/test_handoff_native_sdk.py tests/unit/test_memory_capabilities.py
venv/bin/python -m compileall -q src/application/orchestration
```

修改文档链接后建议检查 Markdown 相对链接是否存在。
