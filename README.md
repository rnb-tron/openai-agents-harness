# OpenAI Agent SDK Engineering Scaffold

一个基于 OpenAI Agents SDK 的可扩展工程底座，已移除原 `ai_chat_butler` 中所有业务逻辑，只保留通用能力并按分层重组，便于后续持续叠加业务功能。

## 分层结构（对应能力分层图）

```text
app/
├── main.py                         # FastAPI 入口与生命周期
├── api/                            # 对外接口层（HTTP/SSE/gRPC adapter）
│   └── routers/
├── application/                    # 应用编排层（workflow/orchestration）
│   └── orchestration/
├── capabilities/                   # 原子能力层（可插拔）
│   ├── tools/
│   ├── memory/
│   └── model_routing/
├── core/                           # 基础设施层（logging/http/redis/kafka/db 等）
├── shared/                         # 共享配置、schema、通用 helper
│   ├── config/
│   ├── schemas/
│   └── utils/
├── routers/                        # 兼容导入（逐步移除）
├── models/                         # 兼容导入（逐步移除）
├── utils/                          # 兼容导入（逐步移除）
└── layers/                         # 兼容导入（逐步移除）
```

## 已迁移并去业务化的能力

- 配置管理与环境变量加载
- 结构化日志（RID 上下文 + 文件轮转）
- 全局异步 HTTP 客户端
- Redis 客户端（支持主从读写分离）
- Kafka 异步生产者（通用消息发送）
- SQLAlchemy 异步数据库连接管理
- Redis 限流器与装饰器
- 轻量事件总线
- 时间工具、签名工具、雪花 ID
- 统一响应模型与响应构造工具

## 快速启动

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp config/test.env.example config/test.env
ENVTYPE=test uvicorn app.main:app --reload --port 8080
curl http://localhost:8080/health/ok

# minimal chat endpoint
curl -X POST http://localhost:8080/chat \
  -H "Content-Type: application/json" \
  -d '{"message":"what is weather in beijing and 3+5?","session_id":"demo-session"}'
```

## 后续扩展建议

- 在 `app/layers/layer_3_orchestration` 中增加 Agent workflow/graph。
- 在 `app/layers/layer_5_core_capability` 中扩展 Tool Registry、Model Router、Memory。
- 在 `app/layers/layer_8_governance` 中追加 Eval、审计、成本、策略模块。
