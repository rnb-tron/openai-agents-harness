# Memory System 集成指南

## 概述

基于 mem0 架构思想,结合 MySQL + Elasticsearch 实现的混合记忆管理系统,支持短期记忆、长期记忆、向量检索和记忆生命周期管理。

## 架构

```
Memory Capability Layer
├── MemoryManager (统一入口)
│   ├── ShortTermMemory (短期记忆 - Redis/内存)
│   ├── LongTermMemory (长期记忆 - MySQL + ES)
│   │   ├── MemoryRepository (MySQL CRUD)
│   │   ├── VectorStore (ES向量检索)
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
- `tiktoken>=0.7.0` - Token计数
- `apscheduler>=3.10.0` - 定时任务

### 2. 配置环境变量

在 `config/test.env` 中添加:

```env
# Memory System Configuration
MEMORY_ENABLED=true
MEMORY_SHORT_TERM_TTL=3600
MEMORY_LONG_TERM_ENABLED=true
MEMORY_ES_HOSTS=http://localhost:9200
MEMORY_ES_INDEX=agent_memories
MEMORY_VECTOR_DIMENSION=1536
MEMORY_MAX_CONTEXT_TURNS=6
MEMORY_RETRIEVAL_TOP_K=3
MEMORY_IMPORTANCE_THRESHOLD=0.3
MEMORY_FORGETTING_ENABLED=true
```

### 3. 数据库初始化

执行SQL迁移脚本:

```bash
mysql -u root -p your_database < config/memory_migration.sql
```

### 4. 启动服务

```bash
uvicorn app.main:app --reload
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
from app.capabilities.memory.manager import MemoryManager

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

### ShortTermMemory

短期记忆 (Redis/内存):

```python
from app.capabilities.memory.store import ShortTermMemory

short_term = ShortTermMemory(redis_client=redis, ttl=3600)

# 添加记忆
await short_term.append("session123", "user", "Hello")

# 获取最近记忆
memories = await short_term.get_recent("session123", max_turns=6)

# 清空记忆
await short_term.clear("session123")
```

### MemoryRepository

MySQL数据仓库:

```python
from app.capabilities.memory.repository import MemoryRepository

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
from app.capabilities.memory.vector_store import ElasticsearchVectorStore

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

### MemoryLifecycleManager

记忆生命周期管理:

```python
from app.capabilities.memory.lifecycle import MemoryLifecycleManager

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
User Input → MemoryManager → ShortTerm (Redis) → 异步 → LongTerm (MySQL + ES)
```

### 读取流程
```
Query → ContextManager → ShortTerm (最近N轮) + LongTerm (ES向量检索) → 合并 → Token裁剪
```

### 检索流程
```
Query → ES向量检索 → 返回Top-K相关记忆 → MySQL补充元数据
```

## 性能优化

1. **批量写入**: ES使用bulk API批量插入
2. **Redis Pipeline**: 批量操作Redis
3. **异步IO**: 所有操作使用async/await
4. **连接池**: MySQL/ES/Redis连接池复用
5. **索引优化**: 合理的数据库索引设计

## 可插拔设计

- 短期/长期记忆可独立启用/禁用
- 向量存储可切换 (ES/Milvus/Qdrant)
- 支持降级方案 (无Redis时使用内存存储)

## 注意事项

1. **ES向量生成**: 当前版本需要手动集成嵌入模型 (如OpenAI text-embedding-3-small)
2. **数据库会话**: Memory系统使用独立的数据库连接池
3. **容错设计**: Memory系统失败不影响主聊天流程
4. **TTL管理**: 短期记忆通过Redis TTL自动过期

## 故障排查

### ES连接失败
```bash
curl http://localhost:9200/_cluster/health
```

### MySQL表不存在
```bash
mysql -u root -p your_database < config/memory_migration.sql
```

### 查看日志
```bash
tail -f app/logs/default.log
```

## 后续优化

- [ ] 集成嵌入模型 (OpenAI/Sentence-Transformers)
- [ ] 实现混合检索 (向量 + BM25)
- [ ] 添加记忆缓存层 (Redis)
- [ ] 支持多租户隔离
- [ ] 记忆可视化界面
