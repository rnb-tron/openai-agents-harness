# Memory 系统指南

> 状态：当前实现指南。本文描述代码现有行为，包括仍需收敛的配置语义和安全边界。

## 组成

```text
Runtime
  -> SessionStore                  # MySQL: 会话列表与完整消息流水
  -> MemoryCapability
     -> MemoryStore                  # 未启用 Mem0 时的进程内降级
     -> Mem0MemoryManager (optional) # MEMORY_ENABLED=true
        -> ShortTermMemory           # Redis: 当前会话最近上下文
        -> Mem0                      # 用户偏好、长期记忆、语义检索
```

`HarnessBuilder` 在 `SESSION_STORE_ENABLED=true` 时装配 MySQL 会话仓储，在 `MEMORY_ENABLED=true` 时统一装配 `Mem0MemoryManager`。Mem0 管理长期记忆、用户偏好和语义检索；短期会话记忆优先使用 Redis，Redis 未启用时降级为进程内存。

## 存储分层

| 层次 | 存储 | 生命周期 | 用途 |
| --- | --- | --- | --- |
| 会话记录 | MySQL | 长期持久化 | 保存会话列表、完整 user/assistant 消息流水，供 UI 回放、审计和后续事件扩展使用 |
| 短期会话记忆 | Redis / 进程内降级 | 会话级 TTL | 保存当前会话最近上下文，参与下一次 `before_run` 上下文拼接 |
| 会话摘要 | MySQL + Redis 缓存 | MySQL 长期持久化，Redis 长 TTL 缓存 | 用 LLM 滚动压缩当前会话状态，作为短期原文过期后的连续性兜底 |
| 长期记忆 | Mem0 + 可选 pgvector / Elasticsearch | 用户级长期持久化 | 抽取用户偏好、长期事实和可语义召回的历史信息 |

会话记录和记忆不是同一个概念：MySQL 消息流水负责“发生过什么”；Redis 原文窗口负责“最近细节”；MySQL 会话摘要负责“会话连续性兜底”；Mem0 负责“用户级稳定记忆”。删除会话时会删除 MySQL 会话消息和摘要，并清理该 session 的短期记忆；用户级长期记忆默认保留。

## 实际开关语义

| 配置 | 当前行为 |
| --- | --- |
| 默认配置 | `MemoryStore` 保存当前进程内的聊天历史并注入下一次运行 |
| `SESSION_STORE_ENABLED=true` | 使用业务数据库持久化 `chat_sessions` / `chat_messages` |
| `MEMORY_ENABLED=true` | 装配 `Mem0MemoryManager`，由 Mem0 管理用户偏好和长期记忆 |
| `MEMORY_MEM0_MODE=local` | 使用 Mem0 OSS 本地模式 |
| `MEMORY_MEM0_MODE=platform` | 使用 Mem0 Platform，需要 `MEMORY_MEM0_API_KEY` |
| `REDIS_ENABLED=true` | `Mem0MemoryManager.short_term` 使用 Redis 保存短期会话记忆 |
| `MEMORY_VECTOR_STORE=pgvector/elasticsearch` | Mem0 本地模式使用指定向量后端 |
| `MEMORY_SESSION_SUMMARY_ENABLED=true` | 启用 LLM 会话摘要；摘要持久化到 MySQL，并缓存到 Redis |

注意：Runtime 仍走 `MemoryCapability.before_run/after_run`，但长期存取由 Mem0 后端完成。`after_run` 会先异步过滤空内容、寒暄、工具失败和拒绝执行等明显噪声；通过过滤的 user/assistant 对话会提交给 Mem0，由 Mem0 判断是否抽取、合并、更新或忽略长期记忆。会话摘要在 `after_run` 后台更新，不阻塞主响应；`before_run` 只读取 Redis/MySQL 中已存在的摘要，不同步重建大摘要。用户偏好检索带用户级 TTL 缓存，长期记忆检索会跳过明显低价值短输入。

## 偏好记忆治理

Mem0 负责抽取、存储和搜索记忆，业务层不在写入阶段预判“这是用户偏好还是其他长期记忆”。但“多个偏好结果如何进入 prompt”属于上下文治理语义，当前实现采用读取阶段治理：

1. 写入时直接把 user/assistant messages 和通用来源 metadata 提交给 Mem0。
2. 由 Mem0 判断是否抽取、合并、更新或忽略长期记忆。
3. 检索和注入上下文时，对偏好类结果按维度只保留最新一条。
4. 不物理删除旧偏好，保留历史可追溯性。

提交给 Mem0 的通用 metadata 类似：

```json
{
  "source": "chat",
  "source_session_id": "session-001",
  "memory_type": "long_term"
}
```

读取阶段用于冲突消解的内置偏好维度：

| `preference_key` | 说明 | 示例 |
| --- | --- | --- |
| `response_language` | 回答语言偏好 | “尽量使用英文”覆盖“尽量使用中文” |
| `answer_order` | 回答顺序偏好 | “先给结论” |
| `answer_detail` | 详略偏好 | “简洁一点” / “详细展开” |
| `answer_format` | 格式偏好 | Markdown、表格、列表、代码块 |
| `tone` | 语气偏好 | 正式、轻松、口语化 |
| `general_preference` | 无法归类的通用偏好 | 其他稳定偏好 |

示例：如果用户先说“以后尽量用中文，先给结论”，后来又说“以后回答先给结论，尽量使用英文”，Mem0 中可能保留两条历史记忆；但 `before_run` 注入上下文和偏好类 `/memory/search` 只会返回最新的 `response_language=English` 与 `answer_order=conclusion first` 生效版本。

## 配置

Mem0 本地模式：

```env
MEMORY_ENABLED=true
REDIS_ENABLED=true
SESSION_STORE_ENABLED=true
DATABASE_URL=mysql+aiomysql://agent:secret@localhost:3306/agent
MEMORY_VECTOR_STORE=none
MEMORY_MEM0_MODE=local
MEMORY_PREFERENCE_CACHE_TTL_SEC=900
MEMORY_SESSION_SUMMARY_ENABLED=true
MEMORY_SESSION_SUMMARY_CACHE_TTL=2592000
MEMORY_SESSION_SUMMARY_INITIAL_MESSAGES=4
MEMORY_SESSION_SUMMARY_UPDATE_MESSAGES=6
MEMORY_SESSION_SUMMARY_MODEL=
MEMORY_SESSION_SUMMARY_MAX_TOKENS=512
# 可选：需要完全自定义 Mem0 OSS 配置时再设置 MEMORY_MEM0_CONFIG_JSON
```

Mem0 local 模式默认复用主模型网关配置：`llm.config` 自动使用 `OPENAI_API_KEY`、`OPENAI_BASE_URL` 和 `AGENT_MODEL_DEFAULT`；`embedder.config` 自动使用 `OPENAI_API_KEY`、`OPENAI_BASE_URL` 和 `MEMORY_EMBEDDING_MODEL`。传给 Mem0 SDK 时，网关地址字段使用 Mem0 兼容的 `openai_base_url`。显式设置 `MEMORY_MEM0_CONFIG_JSON` 时，会完全使用该 JSON，不再自动注入这些字段。

Mem0 Platform 模式：

```env
MEMORY_ENABLED=true
MEMORY_MEM0_MODE=platform
MEMORY_MEM0_API_KEY=your-mem0-api-key
```

## Runtime 数据流

### 不装配 `MemoryManager`

```text
before_run: MemoryStore.render_context(session_id) -> ctx.enriched_input
after_run:  user/output -> MemoryStore
```

### 装配 `MemoryManager`

```text
before_run: MemoryManager.get_context() -> preference cache + optional long-term retrieval
                                      -> session summary cache/store
                                      -> recent short-term messages
after_run:  user/output -> MemoryStore
            user/output -> Mem0MemoryManager.add_memory()
                       -> Redis short-term raw messages
                       -> async noise filter
                       -> Mem0.add()
                       -> background LLM session summary update
```

Mem0 写入或搜索失败时默认 fail-open：记录 warning，不阻止主聊天结果返回。

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

当查询包含“偏好 / preference / communication style”等信号时，`/memory/search` 会按偏好维度做冲突消解；普通长期记忆查询仍按 Mem0 语义搜索结果返回。

安全提示：这些 Memory API 当前直接使用请求提供的 `user_id` / `session_id`，尚未对认证主体执行对象级授权校验。对外部署前必须补充租户隔离、会话所有权和管理接口权限控制。

## UI 验证

启动本地服务后访问 `http://localhost:8080/ui`：

1. 发送“请记住我的偏好：以后回答先给结论，尽量使用中文”。
2. 再发送“请记住我的偏好：以后回答先给结论，尽量使用英文”。
3. 点击“搜索长期记忆”，查询“用户偏好”。
4. 预期只展示当前生效的英文偏好；旧中文偏好不会进入当前生效偏好列表。
5. 右侧“Redis 短期记忆 / Mem0 状态”会展示当前 session 的短期会话记忆内容和 Mem0 状态。

## 组件调用

```python
from src.capabilities.memory.mem0_manager import Mem0MemoryManager

manager = Mem0MemoryManager(settings)
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

测试中可以注入一个符合 Mem0 `add/search` 形态的 client，避免访问真实外部服务：

```python
manager = Mem0MemoryManager(settings, client=fake_mem0_client)
```

## 待完善事项

- 为 Mem0 接入补充成本观测、失败重试和生产配置模板。
- 加入 memory API 的主体授权与租户隔离。
- 验证 Mem0 本地模式与 Platform 模式在真实数据规模下的检索质量。
