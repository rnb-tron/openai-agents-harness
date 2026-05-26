# Memory System 集成指南

> 状态：使用指南。短期会话记忆已接入 Runtime；长期记忆依赖数据库资源；`vector_search` 可由配置启用完整写入与检索链路。

## 概述

基于 mem0 架构思想实现混合记忆管理系统，短期记忆使用内存/Redis，长期关系记录可使用 MySQL 或 PostgreSQL，向量存储可选择 Elasticsearch 或 PostgreSQL + pgvector。

## 架构

```
Memory Capability Layer
├── MemoryManager (统一入口)
│   ├── ShortTermMemory (短期记忆 - Redis/内存)
│   ├── LongTermMemory (长期记忆)
│   │   ├── MemoryRepository (SQLAlchemy: MySQL / PostgreSQL)
│   │   ├── EmbeddingProvider (OpenAI Embeddings API / 可替换实现)
│   │   ├── VectorStore Protocol (Elasticsearch / pgvector)
│   │   └── MemoryLifecycle (记忆生命周期管理)
│   └── ContextManager (上下文管理 - 压缩/裁剪)
```

## 快速开始

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

新增依赖:
- `elasticsearch>=8.0.0` - ES客户端
- `asyncpg>=0.29.0` - PostgreSQL 异步驱动
- `tiktoken>=0.7.0` - Token计数
- `apscheduler>=3.10.0` - 定时任务

### 2. 配置环境变量

在 `config/test.env` 中添加:

```env
# Memory System Configuration
MEMORY_ENABLED=true
MEMORY_SHORT_TERM_TTL=3600
MEMORY_LONG_TERM_ENABLED=true
MEMORY_VECTOR_BACKEND=none  # none | elasticsearch | pgvector；按需开启向量检索
MEMORY_ES_HOSTS=http://localhost:9200
MEMORY_ES_INDEX=agent_memories
MEMORY_PGVECTOR_TABLE=memory_vectors
MEMORY_EMBEDDING_PROVIDER=openai  # openai | none
MEMORY_EMBEDDING_MODEL=text-embedding-3-small
MEMORY_VECTOR_DIMENSION=1536
MEMORY_MAX_CONTEXT_TURNS=6
MEMORY_RETRIEVAL_TOP_K=3
MEMORY_IMPORTANCE_THRESHOLD=0.3
MEMORY_FORGETTING_ENABLED=true
```

### 3. 存储组合

| 组合 | `DATABASE_URL` | `MEMORY_VECTOR_BACKEND` | 适用场景 |
| --- | --- | --- | --- |
| MySQL + Elasticsearch | `mysql+aiomysql://...` | `elasticsearch` | 已有 ES 集群 |
| PostgreSQL + Elasticsearch | `postgresql+asyncpg://...` | `elasticsearch` | 仅迁移关系存储 |
| PostgreSQL + pgvector | `postgresql+asyncpg://...` | `pgvector` | 单数据库轻量部署 |
| 仅关系长期记忆 | MySQL 或 PostgreSQL | `none` | 暂不启用向量检索 |

`MEMORY_VECTOR_BACKEND=pgvector` 时必须使用 PostgreSQL `DATABASE_URL`，否则 Harness 会在装配阶段拒绝启动。
需要自动向量写入和语义检索时，将 `MEMORY_EMBEDDING_PROVIDER` 配置为 `openai` 并提供 `OPENAI_API_KEY`；设置为 `none` 时只使用关系长期记忆。

### 4. 数据库初始化

MySQL + Elasticsearch：

```bash
mysql -u root -p your_database < config/memory_migration.sql
```

PostgreSQL + pgvector：

```bash
psql "$DATABASE_URL" -f config/memory_postgres_pgvector_migration.sql
```

迁移脚本默认创建 `vector(1536)` 字段；调整 `MEMORY_VECTOR_DIMENSION` 时需要同步修改脚本中的维度。

### 5. 启动服务

```bash
venv/bin/python -m uvicorn src.main:app --reload
```

## API 接口

### 1. 搜索记忆

```bash
POST /memory/search
Content-Type: application/json

{
  "query": "Python编程",
  "user_id": "user123",
  "top_k": 5
}
```

### 2. 清空会话记忆

```bash
POST /memory/clear
Content-Type: application/json

{
  "session_id": "session456"
}
```

### 3. 获取记忆统计

```bash
GET /memory/stats?user_id=user123
```

### 4. 清理旧记忆

```bash
POST /memory/cleanup
```

## 核心组件

### MemoryManager

统一记忆管理入口:

```python
from src.capabilities.memory.manager import MemoryManager

# 初始化
memory_manager = MemoryManager(settings, db_session)
await memory_manager.init()

# 添加记忆
await memory_manager.add_memory(
    session_id="session123",
    user_id="user456",
    role="user",
    content="Hello, how are you?",
)

# 获取上下文
context = await memory_manager.get_context(
    session_id="session123",
    user_id="user456",
    user_input="What did we discuss?",
)

# 搜索记忆
results = await memory_manager.search_memories(
    user_id="user456",
    query="programming",
    top_k=5,
)
```

`MemoryManager` 将关系记录作为有效状态的事实源：向量检索结果会再次校验对应记录是否仍有效，清空会话后不会返回已软删除记忆。

### EmbeddingProvider

向量生成与向量存储相互独立；默认 OpenAI 实现也可以由符合协议的业务实现注入：

```python
from src.capabilities.memory.embeddings import OpenAIEmbeddingProvider

provider = OpenAIEmbeddingProvider(
    api_key="...",
    model="text-embedding-3-small",
    dimension=1536,
)
memory_manager = MemoryManager(settings, db_session, embedding_provider=provider)
```

OpenAI Agents SDK 负责 Agent 执行；embedding 使用 OpenAI Python SDK 的 Embeddings API，这是独立于 `Runner` 的数据准备能力。

### ShortTermMemory

短期记忆 (Redis/内存):

```python
from src.capabilities.memory.store import MemoryStore

short_term = ShortTermMemory(redis_client=redis, ttl=3600)

# 添加记忆
await short_term.append("session123", "user", "Hello")

# 获取最近记忆
memories = await short_term.get_recent("session123", max_turns=6)

# 清空记忆
await short_term.clear("session123")
```

### MemoryRepository

关系数据仓库（MySQL / PostgreSQL）:

```python
from src.capabilities.memory.repository import MemoryRepository

repo = MemoryRepository(db_session)

# 创建记忆
record = await repo.create(
    user_id="user123",
    session_id="session456",
    role="user",
    content="Hello",
)

# 查询会话记忆
memories = await repo.query_by_session("session456", limit=10)

# 软删除
await repo.soft_delete(record.id)
```

### ElasticsearchVectorStore

向量存储:

```python
from src.capabilities.memory.vector_store import ElasticsearchVectorStore

vector_store = ElasticsearchVectorStore(
    hosts="http://localhost:9200",
    index_name="agent_memories",
    dimension=1536,
)

# 创建索引
await vector_store.create_index()

# 插入向量
await vector_store.upsert(
    memory_id="12345",
    embedding=[0.1, 0.2, ...],  # 1536维向量
    user_id="user123",
    session_id="session456",
    memory_type="long_term",
    role="user",
    content="Hello",
)

# 向量检索
results = await vector_store.search(
    query_embedding=[0.1, 0.2, ...],
    top_k=5,
    user_id="user123",
)
```

### PostgresVectorStore

使用 PostgreSQL `vector` 扩展保存和查询向量：

```python
from src.capabilities.memory.postgres_vector_store import PostgresVectorStore

vector_store = PostgresVectorStore(
    session=db_session,
    table_name="memory_vectors",
    dimension=1536,
)

await vector_store.create_index()
await vector_store.upsert(
    memory_id="12345",
    embedding=[0.1, 0.2, ...],
    user_id="user123",
    session_id="session456",
    memory_type="long_term",
    role="user",
    content="Hello",
)
results = await vector_store.search(
    query_embedding=[0.1, 0.2, ...],
    user_id="user123",
)
```

该适配器复用 SQLAlchemy 异步会话并直接使用 PostgreSQL `vector` 类型与余弦距离运算，不要求额外的 Python pgvector ORM 包。

### MemoryLifecycleManager

记忆生命周期管理:

```python
from src.capabilities.memory.lifecycle import MemoryLifecycleManager

lifecycle = MemoryLifecycleManager(repository)

# 计算重要性评分
importance = await lifecycle.calculate_importance(memory_record)

# 应用遗忘策略
await lifecycle.apply_forgetting_policy("user123")

# 去重
await lifecycle.deduplicate_similar_memories("user123")

# 归档
await lifecycle.archive_old_memories("user123", days_threshold=90)

# 运行维护任务
result = await lifecycle.run_maintenance()
```

## 定时任务

系统自动运行以下定时任务:

1. **每日凌晨2点**: 执行记忆维护 (遗忘策略、去重、归档)
2. **每小时**: 检查记忆系统健康状态

## 数据流转

### 写入流程
```
User Input → MemoryManager → ShortTerm → LongTerm Repository (MySQL/PostgreSQL)
                                    └→ EmbeddingProvider → VectorStore (ES/pgvector)
```

### 读取流程
```
Query → ContextManager → ShortTerm (最近N轮) + LongTerm (ES/pgvector 向量检索) → 合并 → Token裁剪
```

### 检索流程
```
Query → EmbeddingProvider → VectorStore 向量检索 → Repository 有效性校验/访问统计 → 返回 Top-K
```

## 性能优化

1. **批量写入**: 后续可分别为 ES 与 pgvector 增加批量写入策略
2. **Redis Pipeline**: 批量操作Redis
3. **异步IO**: 所有操作使用async/await
4. **连接池**: 关系数据库、ES 和 Redis 连接池复用
5. **索引优化**: 合理的数据库索引设计

## 可插拔设计

- 短期/长期记忆可独立启用/禁用
- 向量存储可配置切换（`elasticsearch` / `pgvector` / `none`）
- 向量后端默认为 `none`，只启用关系长期记忆时不会连接 ES 或 embedding 服务
- 嵌入生成器通过 `EmbeddingProvider` 注入，默认可配置为 `openai` 或 `none`
- 支持降级方案 (无Redis时使用内存存储)

## 注意事项

1. **向量生成**: `MEMORY_EMBEDDING_PROVIDER=openai` 会调用外部 Embeddings API；测试或仅关系存储场景可设为 `none`
2. **数据库会话**: Memory系统使用独立的数据库连接池
3. **容错设计**: Memory系统失败不影响主聊天流程
4. **TTL管理**: 短期记忆通过Redis TTL自动过期

## 故障排查

### ES连接失败
```bash
curl http://localhost:9200/_cluster/health
```

### PostgreSQL / pgvector 初始化失败

```bash
psql "$DATABASE_URL" -c "CREATE EXTENSION IF NOT EXISTS vector;"
psql "$DATABASE_URL" -f config/memory_postgres_pgvector_migration.sql
```

### MySQL 表不存在
```bash
mysql -u root -p your_database < config/memory_migration.sql
```

### 查看日志
```bash
tail -f data/logs/default.log
```

## 后续优化

- [ ] 在真实 PostgreSQL / pgvector 与 Embeddings API 环境验证索引性能和迁移策略
- [ ] 评估批量 embedding、重试与成本观测
- [ ] 实现混合检索 (向量 + BM25)
- [ ] 添加记忆缓存层 (Redis)
- [ ] 支持多租户隔离
- [ ] 记忆可视化界面
