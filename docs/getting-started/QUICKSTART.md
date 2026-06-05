# Agent Harness 快速入门

本项目是基于 OpenAI Agents SDK 的可组合 Agent 工程底座，用于验证运行时装配、能力目录和脚手架生成路径。

> 状态：当前实现入门指南。生产化限制请同时阅读 [架构设计](../architecture/ARCHITECTURE_DESIGN.md)。

## 当前主路径

```text
src.main:app
  -> src.api.app.create_app(settings)
     -> build_harness(settings)
     -> build_protocol_chain(settings)
     -> /chat, /chat/stream, /chat/resume, /memory/*, /health/*
```

- `src/main.py` 仅导出 ASGI `app`。
- `HarnessBuilder` 创建 Runtime、工具注册表、模型路由和可选资源。
- `ProtocolRequestChain` 以请求执行顺序显式装配 `RequestContext -> Observability -> Auth -> RateLimit`；观测资源生命周期由 Harness 管理。
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

浏览器手工验证 `/chat` 时，打开：

```text
http://localhost:8080/ui
```

页面默认调用 `POST /chat/stream` 实时展示文本增量，并复用同一 `session_id`、显示原始事件；启用 HITL 时也可在页面批准或拒绝中断的工具调用。启用 Auth 时，可在页面请求设置中填写 Bearer Token。

## 聊天 API

```bash
curl -X POST http://localhost:8080/chat \
  -H 'Content-Type: application/json' \
  -d '{"message":"北京天气如何？","session_id":"demo-session","user_id":"demo-user"}'
```

`/chat` 会返回 `session_id`、`output`、实际使用的 `model`、工具调用以及当前内存会话消息数量。

需要流式显示时，提交相同请求体到 `POST /chat/stream`。该接口以
`application/x-ndjson` 依次发送 `start`、`delta` 和 `done` 事件；失败时发送
`error` 事件。由于已发送的文本增量不可透明撤回，模型失败重试与 fallback 仍由完整响应接口 `/chat` 承载。

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
MEMORY_SHORT_TERM_ENABLED=true
MEMORY_SESSION_SUMMARY_ENABLED=true
MEMORY_LONG_TERM_ENABLED=true
REDIS_ENABLED=true
SESSION_STORE_ENABLED=true
DATABASE_URL=mysql+aiomysql://agent:secret@localhost:3306/agent
MEMORY_LONG_TERM_PROVIDER=mem0
MEMORY_LONG_TERM_MEM0_MODE=local
MEMORY_LONG_TERM_VECTOR_STORE=none
MEMORY_PREFERENCE_CACHE_TTL_SEC=900
MEMORY_SESSION_SUMMARY_CACHE_TTL=2592000
MEMORY_SESSION_SUMMARY_INITIAL_MESSAGES=4
MEMORY_SESSION_SUMMARY_UPDATE_MESSAGES=6
MEMORY_SESSION_SUMMARY_MAX_SOURCE_MESSAGES=20
```

说明：

- `SESSION_STORE_ENABLED=true` 时使用 MySQL 持久化会话列表和完整消息流水。
- `REDIS_ENABLED=true` 且 `MEMORY_SHORT_TERM_ENABLED=true` 时，短期会话记忆写入 Redis；读取时 Redis miss 会回退到 MySQL 近 N 轮消息。
- 不启用 Redis 时，短期原文记忆直接从 MySQL 会话消息读取。
- `MEMORY_SESSION_SUMMARY_ENABLED=true` 时，`after_run` 后台使用 LLM 更新会话摘要，摘要持久化到 MySQL 并缓存到 Redis；无 Redis 时只读写 MySQL，不使用进程内兜底。
- `MEMORY_LONG_TERM_ENABLED=true` 时由 Mem0 管理用户偏好、长期记忆和语义检索。
- Mem0 local 模式默认继承 `OPENAI_API_KEY`、`OPENAI_BASE_URL`、`AGENT_MODEL_DEFAULT` 和 `MEMORY_EMBEDDING_MODEL`。
- 偏好记忆采用“保留历史、注入生效版本”：同一偏好维度只把最新一条注入上下文，避免语言、格式等偏好冲突。
- `MEMORY_LONG_TERM_MEM0_MODE=platform` 时需要配置 `MEMORY_LONG_TERM_MEM0_API_KEY`。
- `MEMORY_LONG_TERM_VECTOR_STORE=pgvector` 时配置 `MEMORY_PGVECTOR_PGHOST`、`MEMORY_PGVECTOR_PGPORT`、`MEMORY_PGVECTOR_PGDATABASE`、`MEMORY_PGVECTOR_PGUSER` 和 `MEMORY_PGVECTOR_PGPASSWORD`；`MEMORY_LONG_TERM_VECTOR_STORE=elasticsearch` 时配置 `MEMORY_ES_HOSTS` 和 `MEMORY_ES_INDEX`。

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
LANGFUSE_BASE_URL=http://agent-otel-test.ke.com
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

选择 `vector_search` 会自动解析 `long_term_memory` 与 `memory_manager` 等内部要求；Mem0 管理长期检索所需的 embedding 与存储配置。

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
