# Memory 系统指南

> 状态：当前实现指南。本文描述代码现有行为，包括仍需收敛的配置语义和安全边界。

## 组成

```text
Runtime
  -> MemoryCapability
     -> MemoryStore                  # 基础会话历史，进程内，始终启用
     -> MemoryManager (optional)     # MEMORY_ENABLED + DATABASE_URL
        -> MemoryRepository          # SQLAlchemy 关系记录
        -> ShortTermMemory           # 当前 manager 内为内存后备实现
        -> VectorStore (optional)    # Elasticsearch / PostgreSQL pgvector
        -> EmbeddingProvider         # 当前内置 OpenAI provider
        -> MemoryLifecycleManager
```

`HarnessBuilder` 创建共享 `DatabaseResource` 并向 `MemoryManager` 提供 session；Memory 不再自行创建独立连接池。

## 实际开关语义

| 配置 | 当前行为 |
| --- | --- |
| 默认配置 | `MemoryStore` 保存当前进程内的聊天历史并注入下一次运行 |
| `MEMORY_ENABLED=true` 且有 `DATABASE_URL` | 装配 `MemoryManager`，完成运行后向关系仓库写入记录 |
| `MEMORY_LONG_TERM_ENABLED=true` | 允许构造可选向量后端和 embedding provider，并在读取上下文时开启语义检索 |
| `MEMORY_VECTOR_BACKEND=none` | 不创建向量存储 |
| `MEMORY_EMBEDDING_PROVIDER=none` | 即使配置了向量后端，也不生成向量或执行语义搜索 |

注意：当前实现中，`MEMORY_ENABLED=true` 即会使 Runtime 走 `MemoryManager.add_memory()` 的关系记录写入路径；`MEMORY_LONG_TERM_ENABLED` 主要门控向量增强与检索，不是“禁止持久化写入”的总开关。

另一个当前边界是：虽然仓库存在 Redis 基础设施，Runtime 的 `MemoryStore` 与 `MemoryManager.short_term` 尚未注入 Redis client，因此会话短期历史目前不是跨实例持久状态。

## 配置

仅启用关系记录：

```env
MEMORY_ENABLED=true
DATABASE_URL=mysql+aiomysql://agent:password@localhost:3306/agent_harness
MEMORY_LONG_TERM_ENABLED=false
```

Elasticsearch 语义检索：

```env
MEMORY_ENABLED=true
DATABASE_URL=mysql+aiomysql://agent:password@localhost:3306/agent_harness
MEMORY_LONG_TERM_ENABLED=true
MEMORY_VECTOR_BACKEND=elasticsearch
MEMORY_ES_HOSTS=http://localhost:9200
MEMORY_ES_INDEX=agent_memories
MEMORY_EMBEDDING_PROVIDER=openai
MEMORY_EMBEDDING_MODEL=text-embedding-3-small
MEMORY_VECTOR_DIMENSION=1536
OPENAI_API_KEY=your-api-key
```

PostgreSQL + pgvector：

```env
MEMORY_ENABLED=true
DATABASE_URL=postgresql+asyncpg://agent:password@localhost:5432/agent_harness
MEMORY_LONG_TERM_ENABLED=true
MEMORY_VECTOR_BACKEND=pgvector
MEMORY_PGVECTOR_TABLE=memory_vectors
MEMORY_EMBEDDING_PROVIDER=openai
MEMORY_VECTOR_DIMENSION=1536
OPENAI_API_KEY=your-api-key
```

初始化脚本：

```bash
# MySQL 关系记录
mysql -u root -p your_database < config/memory_migration.sql

# PostgreSQL + pgvector
psql "$DATABASE_URL" -f config/memory_postgres_pgvector_migration.sql
```

`MEMORY_VECTOR_BACKEND=pgvector` 要求 PostgreSQL `DATABASE_URL`；迁移脚本默认向量维度为 `1536`，调整维度时需同步调整 schema。

## Runtime 数据流

### 不装配 `MemoryManager`

```text
before_run: MemoryStore.render_context(session_id) -> ctx.enriched_input
after_run:  user/output -> MemoryStore
```

### 装配 `MemoryManager`

```text
before_run: MemoryManager.get_context() -> manager short term + optional vector retrieval
after_run:  user/output -> MemoryStore
            user/output -> MemoryManager.add_memory() -> repository
                                               -> optional embedding/vector upsert
```

向量写入发生失败时，代码保留关系记录并记录 warning；Memory hook 异常不会阻止主聊天结果返回。

## HTTP API

```bash
curl -X POST http://localhost:8080/memory/search \
  -H 'Content-Type: application/json' \
  -d '{"query":"项目偏好","user_id":"user-123","top_k":5}'

curl -X POST http://localhost:8080/memory/clear \
  -H 'Content-Type: application/json' \
  -d '{"session_id":"session-001"}'

curl 'http://localhost:8080/memory/stats?user_id=user-123'
curl -X POST http://localhost:8080/memory/cleanup
```

安全提示：这些 Memory API 当前直接使用请求提供的 `user_id` / `session_id`，尚未对认证主体执行对象级授权校验。对外部署前必须补充租户隔离、会话所有权和管理接口权限控制。

## 组件调用

```python
from src.capabilities.memory.manager import MemoryManager

manager = MemoryManager(settings, db_session)
await manager.init()
await manager.add_memory(
    session_id="session-001",
    user_id="user-001",
    role="user",
    content="我喜欢简洁的技术总结。",
)
context = await manager.get_context(
    session_id="session-001",
    user_id="user-001",
    user_input="我的偏好是什么？",
)
results = await manager.search_memories(
    user_id="user-001",
    query="技术总结",
    top_k=3,
)
```

也可以为测试或业务后端注入符合协议的 embedding provider：

```python
manager = MemoryManager(settings, db_session, embedding_provider=my_provider)
```

## 定时任务

当 `Harness` 成功装配 `MemoryManager` 并执行 `setup()` 后，会启动 `MemoryTaskScheduler`：

| 计划 | 行为 |
| --- | --- |
| 每日 02:00 | 执行遗忘、去重、归档维护 |
| 每小时整点 | 检查向量后端健康并记录统计 |

## 待完善事项

- 将会话短期存储明确接入 Redis 或服务端 session store。
- 将“关系持久化”与“向量检索”开关语义进一步拆分并固化为生成器契约。
- 加入 memory API 的主体授权与租户隔离。
- 验证真实 ES/pgvector 索引、embedding 成本和失败重试策略。
