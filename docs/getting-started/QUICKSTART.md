# Agent Harness 快速入门

本项目是基于 OpenAI Agents SDK 的可组合 Agent 工程底座，用于验证运行时装配、能力目录和脚手架生成路径。

> 状态：当前实现入门指南。生产化限制请同时阅读 [架构设计](../architecture/ARCHITECTURE_DESIGN.md)。

## 当前主路径

```text
src.main:app
  -> src.api.app.create_app(settings)
     -> build_harness(settings)
     -> build_protocol_registry(settings)
     -> /chat, /chat/resume, /memory/*, /health/*
```

- `src/main.py` 仅导出 ASGI `app`。
- `HarnessBuilder` 创建 Runtime、工具注册表、模型路由和可选资源。
- `ProtocolPluginRegistry` 装配 Auth、RateLimit 与 Observability 的 HTTP 入口。
- `AgentOrchestrator` 使用 SDK `Agent`、`Runner`、原生 handoff 和审批恢复。

## 准备环境

要求 Python 3.11+。最小聊天调用需要可访问的模型服务和 API key。

```bash
python3.11 -m venv venv
source venv/bin/activate
make install
cp config/test.env.example config/test.env
```

最小配置：

```env
OPENAI_API_KEY=your-api-key
AGENT_MODEL_DEFAULT=gpt-4o-mini
```

如使用兼容端点，可额外设置：

```env
OPENAI_BASE_URL=https://your-api-endpoint.example/v1
```

启动与验证：

```bash
make run
curl http://localhost:8080/health/ok
curl http://localhost:8080/health/capabilities
```

## 聊天 API

```bash
curl -X POST http://localhost:8080/chat \
  -H 'Content-Type: application/json' \
  -d '{"message":"北京天气如何？","session_id":"demo-session","user_id":"demo-user"}'
```

`/chat` 会返回 `session_id`、`output`、实际使用的 `model`、工具调用以及当前内存会话消息数量。

当前安全边界：

- 未启用 Auth 时，`user_id` 与 `session_id` 来自请求体。
- 启用 Auth 时，`/chat` 会优先使用认证主体的 `user_id`。
- 当前尚未实现 session / memory 的资源归属授权校验；对外部署前应补充租户和会话隔离。

## 通过配置启用能力

推荐修改环境变量后重新构建应用，而不是在 router 中手动创建 `AgentOrchestrator`。

### Prompt 与上下文压缩

```env
PROMPT_ENABLED=true
PROMPT_BACKEND=yaml
COMPRESSION_ENABLED=true
COMPRESSION_STRATEGY=token_budget
```

### 长期 Memory 与向量检索

```env
MEMORY_ENABLED=true
DATABASE_URL=postgresql+asyncpg://agent:password@localhost:5432/agent_harness

# 可选语义检索
MEMORY_LONG_TERM_ENABLED=true
MEMORY_VECTOR_BACKEND=pgvector
MEMORY_PGVECTOR_TABLE=memory_vectors
MEMORY_EMBEDDING_PROVIDER=openai
MEMORY_EMBEDDING_MODEL=text-embedding-3-small
MEMORY_VECTOR_DIMENSION=1536
```

使用 `pgvector` 前先执行：

```bash
psql "$DATABASE_URL" -f config/memory_postgres_pgvector_migration.sql
```

说明：

- 基础 `memory_session` 使用进程内 `MemoryStore`，始终参与 Runtime。
- `MEMORY_ENABLED=true` 且提供 `DATABASE_URL` 时装配 `MemoryManager` 和关系长期记录。
- `MEMORY_LONG_TERM_ENABLED=true`、向量后端和 embedding provider 都配置后，才会执行语义写入与检索。
- 当前 Runtime 尚未把 Redis 注入短期会话存储；`REDIS_ENABLED` 主要供基础设施与 Redis 限流使用。

### HITL 审批恢复

```env
HITL_ENABLED=true
HITL_REQUIRE_APPROVAL_TOOLS=get_weather
HITL_APPROVAL_TIMEOUT=300
```

当受控工具被调用时，`POST /chat` 返回 `interruptions` 与 `run_state`。调用方随后将原始 `message`、实际 `model`、`run_state` 和审批决定提交到：

```bash
POST /chat/resume
```

可运行演示：

```bash
venv/bin/python examples/hitl_resume.py --approve --message "请查询北京天气。"
```

当前 `ApprovalManager` 与 `run_state` 持久化仍为轻量实现，不适合作为跨实例、可审计的生产审批仓库。

### Checkpoint 与 Handoff

```env
CHECKPOINT_ENABLED=true
CHECKPOINT_AUTO_SAVE=true
CHECKPOINT_MAX_CHECKPOINTS=10

HANDOFF_ENABLED=true
HANDOFF_AGENTS_JSON={"billing":{"description":"处理账单问题","instructions":"只处理账单问题。"}}
```

- Checkpoint 当前仅保存进程内运行前/后摘要，不保存 SDK `RunState`，不能恢复中断任务。
- Handoff 将静态配置的目标 Agent 传给 SDK 原生 `Agent.handoffs`；当前不配置专家专属工具。

## 协议与观测能力

```env
AUTH_ENABLED=true
AUTH_STRICT=true
AUTH_JWT_SECRET=replace-with-long-secret

RATE_LIMIT_ENABLED=true
RATE_LIMIT_BACKEND=redis
REDIS_ENABLED=true
RATE_LIMIT_FAIL_OPEN=false

LANGFUSE_ENABLED=true
LANGFUSE_PUBLIC_KEY=pk-xxx
LANGFUSE_SECRET_KEY=sk-xxx
LANGFUSE_BASE_URL=https://cloud.langfuse.com
```

- Redis 限流后端要求 `REDIS_ENABLED=true`；后端失败默认返回 `503`，显式设置 `RATE_LIMIT_FAIL_OPEN=true` 才放行。
- 所有 HTTP 请求都有 `X-Request-ID`；启用 Observability 后响应额外包含 `X-Trace-ID`。

## 能力目录与生成前校验

```bash
curl http://localhost:8080/health/capability-catalog
curl -X POST http://localhost:8080/health/capability-selection/validate \
  -H 'Content-Type: application/json' \
  -d '{"selected":["vector_search","hitl"]}'
```

选择 `vector_search` 会自动解析 `long_term_memory`、`memory_manager` 与 `embedding_provider` 等内部要求，并报告 `database` 与 `embedding_api` 等外部资源。

## 测试

```bash
make test
make test-all
```

外部模型相关测试默认跳过；显式验证外部服务时设置 `RUN_EXTERNAL_TESTS=true`。

## 继续阅读

- [架构设计](../architecture/ARCHITECTURE_DESIGN.md)
- [AgentOrchestrator 使用指南](../guides/AGENT_ORCHESTRATOR_USAGE.md)
- [高级 Agent 能力](../guides/ADVANCED_AGENTS_GUIDE.md)
- [Memory 系统](../guides/MEMORY_SYSTEM.md)
- [模型弹性](../guides/MODEL_RESILIENCE_GUIDE.md)
- [可观测性](../guides/OBSERVABILITY_GUIDE.md)
