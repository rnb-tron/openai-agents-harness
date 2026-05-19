# Memory 系统集成技术方案

## 架构设计

### 整体架构
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

### 数据流转
1. **写入**: User Input → MemoryManager → ShortTerm (Redis) → 异步 → LongTerm (MySQL + ES)
2. **读取**: Query → ContextManager → ShortTerm (最近N轮) + LongTerm (ES向量检索相关记忆) → 合并
3. **检索**: Query → ES向量检索 → 返回Top-K相关记忆 → MySQL补充元数据

---

## 开发步骤

### 步骤 1: 依赖安装与配置扩展

**文件**: `requirements.txt`
- 添加 `mem0ai` (mem0核心库)
- 添加 `elasticsearch` (ES客户端)
- 添加 `asyncpg` 或保持 `aiomysql`

**文件**: `app/shared/config/settings.py`
- 扩展 `Settings` 数据类,添加:
  - `memory_enabled: bool`
  - `memory_short_term_ttl: int` (短期记忆TTL,默认3600秒)
  - `memory_long_term_enabled: bool`
  - `memory_es_hosts: str`
  - `memory_es_index: str`
  - `memory_vector_dimension: int` (向量维度,默认1536)
  - `memory_max_context_turns: int` (最大上下文轮数)
  - `memory_retrieval_top_k: int` (检索Top-K)

**文件**: `config/test.env.example`
- 添加 memory 相关环境变量示例

---

### 步骤 2: MySQL 数据模型设计

**新文件**: `app/capabilities/memory/models.py`

创建 SQLAlchemy 异步模型:
```python
class MemoryRecord(Base):
    __tablename__ = "memory_records"
    
    id: BIGINT (主键,雪花ID)
    user_id: VARCHAR(64) (用户ID,索引)
    session_id: VARCHAR(64) (会话ID,索引)
    memory_type: VARCHAR(32) (short_term/long_term/episodic/semantic)
    role: VARCHAR(16) (user/assistant/system)
    content: TEXT (记忆内容)
    embedding_id: VARCHAR(64) (ES向量ID)
    metadata: JSON (扩展元数据: tokens, timestamp, tags等)
    importance_score: FLOAT (重要性评分,用于遗忘策略)
    access_count: INT (访问次数)
    last_accessed_at: DATETIME (最后访问时间)
    created_at: DATETIME
    updated_at: DATETIME
    is_deleted: TINYINT (软删除)
```

**索引设计**:
- `(user_id, session_id, created_at)` 联合索引
- `(user_id, memory_type)` 联合索引
- `importance_score` 单列索引 (用于遗忘策略)

---

### 步骤 3: Elasticsearch 向量存储

**新文件**: `app/capabilities/memory/vector_store.py`

实现 `ElasticsearchVectorStore` 类:
- `__init__(hosts, index_name, dimension)`: 初始化ES客户端和索引
- `async create_index()`: 创建索引 (dense_vector类型 + keyword字段)
- `async upsert(memory_id, embedding, metadata)`: 插入/更新向量
- `async search(query_embedding, top_k, filters)`: 向量相似度检索
- `async delete(memory_ids)`: 批量删除
- `async health_check()`: 健康检查

**索引映射设计**:
```json
{
  "mappings": {
    "properties": {
      "memory_id": {"type": "keyword"},
      "embedding": {"type": "dense_vector", "dims": 1536, "index": true, "similarity": "cosine"},
      "user_id": {"type": "keyword"},
      "session_id": {"type": "keyword"},
      "memory_type": {"type": "keyword"},
      "content_hash": {"type": "keyword"},
      "metadata": {"type": "object"}
    }
  }
}
```

---

### 步骤 4: MySQL Memory Repository

**新文件**: `app/capabilities/memory/repository.py`

实现 `MemoryRepository` 类 (异步):
- `async create(record: MemoryRecord)`: 创建记忆
- `async get_by_id(memory_id)`: 根据ID查询
- `async query_by_session(session_id, limit, offset)`: 按会话查询
- `async query_by_user(user_id, memory_type, limit)`: 按用户和类型查询
- `async update_importance(memory_id, score)`: 更新重要性评分
- `async increment_access(memory_id)`: 增加访问计数
- `async soft_delete(memory_id)`: 软删除
- `async batch_delete_by_session(session_id)`: 批量删除会话记忆
- `async get_important_memories(user_id, top_n)`: 获取高重要性记忆

---

### 步骤 5: Memory Lifecycle Manager

**新文件**: `app/capabilities/memory/lifecycle.py`

实现记忆生命周期管理:
- **重要性评分**: 基于访问频率、内容长度、用户反馈
- **遗忘策略**: 定期清理低重要性记忆 (TTL + LRU)
- **记忆合并**: 相似记忆去重和合并
- **记忆归档**: 过期记忆迁移到冷存储

核心方法:
```python
class MemoryLifecycleManager:
    async def calculate_importance(memory: MemoryRecord) -> float
    async def apply_forgetting_policy(user_id, max_memories)
    async def deduplicate_similar_memories(user_id, threshold)
    async def archive_old_memories(user_id, days_threshold)
```

---

### 步骤 6: Short-Term Memory (Redis增强)

**重构文件**: `app/capabilities/memory/store.py`

增强现有 `MemoryStore`,支持 Redis:
```python
class ShortTermMemory:
    def __init__(self, redis_client, ttl=3600)
    async def append(session_id, role, content, metadata)
    async def get_recent(session_id, max_turns)
    async def clear(session_id)
    async def get_ttl(session_id)
```

使用 Redis List 或 Sorted Set 存储,支持TTL自动过期。

---

### 步骤 7: Context Manager

**新文件**: `app/capabilities/memory/context_manager.py`

实现上下文管理:
```python
class ContextManager:
    def __init__(self, short_term, long_term, vector_store, max_tokens)
    
    async def build_context(
        session_id, 
        user_input, 
        max_turns=6,
        enable_retrieval=True
    ) -> str:
        # 1. 获取短期记忆 (最近N轮)
        short_memories = await short_term.get_recent(session_id, max_turns)
        
        # 2. 向量检索相关长期记忆
        if enable_retrieval:
            query_embedding = await self._embed(user_input)
            long_memories = await vector_store.search(
                query_embedding, top_k=3, filters={"user_id": user_id}
            )
        
        # 3. 合并并格式化
        context = self._format_context(short_memories, long_memories)
        
        # 4. Token计数和裁剪
        if self._count_tokens(context) > max_tokens:
            context = self._truncate_context(context, max_tokens)
        
        return context
```

---

### 步骤 8: Memory Manager (统一入口)

**重构文件**: `app/capabilities/memory/manager.py` (新建)

统一 Memory 管理入口,替换原有 `MemoryStore`:
```python
class MemoryManager:
    def __init__(self, config):
        self.short_term = ShortTermMemory(...)
        self.long_term_repo = MemoryRepository(...)
        self.vector_store = ElasticsearchVectorStore(...)
        self.context_manager = ContextManager(...)
        self.lifecycle = MemoryLifecycleManager(...)
    
    async def add_memory(session_id, user_id, role, content, metadata)
    async def get_context(session_id, user_id, user_input, **kwargs)
    async def search_memories(user_id, query, top_k)
    async def clear_session(session_id)
    async def cleanup_old_memories()  # 定时任务
```

---

### 步骤 9: 集成到 Agent Runtime

**修改文件**: `app/application/orchestration/agent_runtime.py`

在 `AgentOrchestrator` 中集成 MemoryManager:
```python
class AgentOrchestrator:
    def __init__(self, memory_manager: MemoryManager, ...):
        self.memory_manager = memory_manager
    
    async def run(self, session, user_input):
        # 1. 构建上下文 (短期 + 长期检索)
        context = await self.memory_manager.get_context(
            session.session_id,
            session.user_id,
            user_input
        )
        
        # 2. 添加用户输入到记忆
        await self.memory_manager.add_memory(
            session.session_id, session.user_id, "user", user_input
        )
        
        # 3. 调用 Agent (带上下文)
        agent = Agent(
            instructions=context,  # 注入记忆上下文
            tools=self.tool_registry.list_agent_tools()
        )
        result = await Runner.run(agent, user_input)
        
        # 4. 存储助手响应到记忆
        await self.memory_manager.add_memory(
            session.session_id, session.user_id, "assistant", result.final_output
        )
        
        return {"response": result.final_output, "context_used": context}
```

---

### 步骤 10: API 接口扩展

**修改文件**: `app/api/routers/chat.py`

增强 Chat API,支持记忆检索:
- 添加 `/memory/search` 端点 (搜索长期记忆)
- 添加 `/memory/clear` 端点 (清空会话记忆)
- 添加 `/memory/stats` 端点 (记忆统计信息)

---

### 步骤 11: 初始化与依赖注入

**修改文件**: `app/main.py`

在应用启动时初始化 Memory 系统:
```python
@app.on_event("startup")
async def startup():
    # 初始化 MemoryManager
    memory_manager = MemoryManager(current_settings)
    await memory_manager.vector_store.create_index()
    
    # 注册到全局
    app.state.memory_manager = memory_manager
```

---

### 步骤 12: 定时任务 (记忆清理)

**新文件**: `app/capabilities/memory/tasks.py`

使用 APScheduler 或 Celery 实现定时任务:
- 每日执行遗忘策略 (清理低重要性记忆)
- 每周执行记忆去重
- 每月执行记忆归档

---

## 技术要点

### 1. 嵌入模型选择
- 使用 OpenAI `text-embedding-3-small` (1536维) 或 `text-embedding-3-large` (3072维)
- 或使用本地模型 (sentence-transformers)

### 2. 向量检索优化
- ES cosine similarity
- 过滤条件: `user_id`, `memory_type`, `created_at`
- 混合检索: 向量 + BM25 (可选)

### 3. 性能优化
- 批量写入 ES (bulk API)
- Redis Pipeline 操作
- 异步IO (async/await)
- 连接池复用

### 4. 可插拔设计
- 定义 `MemoryStorage` 抽象接口
- 短期/长期记忆可独立启用/禁用
- 向量存储可切换 (ES/Milvus/Qdrant)

---

## 配置示例

```env
# Memory Configuration
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

---

## 数据库迁移

使用 Alembic 管理 MySQL 表结构:
```bash
alembic revision --autogenerate -m "add memory_records table"
alembic upgrade head
```

---

## 测试策略

1. **单元测试**: Repository、VectorStore、Lifecycle 独立测试
2. **集成测试**: MemoryManager 端到端测试
3. **性能测试**: 向量检索延迟、并发写入测试
4. **Mock**: 使用 `elasticsearch-py` mock 和 Redis faker
