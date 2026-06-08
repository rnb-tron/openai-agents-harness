# 上下文压缩 Capability 方案

> 文档类型：设计记录。该能力已接入 Harness，本文保留初始方案与决策背景。
>
> 状态: **已接入**（具体行为以 `src/capabilities/context_compression/` 与测试为准）
> 范围: 在 `BEFORE_RUN` 钩子链中,对 `enriched_input` 按模型窗口预算压缩
> 兼容性: 默认关闭、配置即启用(`compression_enabled=False` 时零开销)

---

## 一、问题诊断

### 现状梳理

| 能力 | 实现位置 | 评级 | 备注 |
|---|---|---|---|
| Token 计数 | `token_budget.py` / compression strategy | ✅ 有 | tiktoken `cl100k_base`,失败兜底估算 |
| 阈值触发 | `ContextCompressionCapability.before_run` | ✅ 有 | 在 MemoryCapability 注入上下文后执行 |
| 裁剪策略 | `TokenBudgetTruncate` | ✅ 有 | 按预算保留当前输入和最近上下文 |
| 短期容量上限 | `MemoryStore`(内存模式 100 条) | ⚠️ 弱 | 仅 fallback 路径生效 |
| LLM 摘要 | — | ❌ 无 | |
| 滚动摘要 | — | ❌ 无 | |
| 重要性打分 | — | ❌ 无 | |
| 语义去重 | — | ❌ 无 | |
| 模型窗口自适应 | — | ❌ 无 | `max_tokens=8000` 硬编码 |

### 关键缺陷

> 当前实现的记忆上下文由 `Mem0MemoryManager` 统一提供。
> 上下文压缩通过 `ContextCompressionCapability` 接在 `MemoryCapability` 之后。

参见 [`MemoryCapability.before_run`](../../src/capabilities/memory/capability.py):

```python
if self._long_term_enabled and self._manager is not None:
    memory_context = await self._manager.get_context(...)
```

### 痛点量化

| 痛点 | 影响 | 严重度 |
|---|---|---|
| 长会话 token 爆窗 | 模型 `context_length_exceeded` 直接报错 | 🔴 高 |
| 历史重复发送 | 输入 token 成本随轮次线性膨胀 | 🟠 中 |
| 砍轮数信息丢失 | 关键事实(用户身份/约束/目标)首先丢 | 🟠 中 |
| 窗口与模型脱节 | 降级到小窗口模型(16k)必爆 | 🔴 高 |
| 不可观测 | 不知道压了什么、保了什么 | 🟡 低 |

---

## 二、目标 & 非目标

### ✅ 目标

1. 提供**多策略可插拔**的上下文压缩能力(`Truncate / Summary / Hybrid`)
2. 与**模型窗口自适应**(从 `selected_model` 反查 budget)
3. 失败**自动降级**(LLM 摘要失败 → Truncate 兜底)
4. 完全可观测(`ctx.metadata["compression"]` 注入压缩指标)
5. 默认关闭,生产仅需 env 开关

### ❌ 非目标(本期不做)

- 持久化"摘要替换原文"(信息不可逆,留后期)
- 跨会话的全局记忆压缩(那是 long-term memory 的职责)
- 多模态(图片/音频)上下文压缩
- 用户级压缩偏好(每用户配置)

---

## 三、架构设计

### 3.1 在 Capability 链中的定位

```
BEFORE_RUN 钩子顺序(顺序敏感):
  1. MemoryCapability                  → 拼接 enriched_input(history + user_input)
  2. ContextCompressionCapability      → 按预算压缩 enriched_input  ← 新增
  3. (其他 BEFORE_RUN capability)
  4. Runner.run(ctx.enriched_input)
```

> **关键解耦**: 压缩对 Memory 的实现透明,谁拼上下文都能压。
> 后续即使换 Memory 后端(如 mem0/Zep),压缩逻辑无需改动。

### 3.2 Strategy 抽象

```python
# src/capabilities/context_compression/base.py
@dataclass
class CompressionResult:
    text: str
    input_tokens: int
    output_tokens: int
    compress_ratio: float       # output / input
    strategy: str
    fallback_used: bool
    summary_calls: int
    duration_ms: int

class CompressionStrategy(Protocol):
    name: str
    async def compress(
        self,
        text: str,
        *,
        budget_tokens: int,
        ctx: RunContext,
    ) -> CompressionResult: ...
```

### 3.3 内置策略(三种,按"重→轻")

| 策略类 | 算法 | 何时用 | 外部依赖 |
|---|---|---|---|
| `TokenBudgetTruncate` | 提炼现有 `_truncate_context`,从老到新丢弃直至达预算,保留 system / 当前 user | 默认兜底,**零开销** | 仅 tiktoken |
| `RollingSummary` | 老消息批量调 LLM 压成 summary,近 K 轮原文保留;summary 缓存 Redis | 长会话/成本敏感 | OpenAI 客户端 + Redis |
| `HybridStrategy` | 先 RollingSummary,再 Truncate 兜底保证不超预算 | **生产推荐** | 上面两者 |

### 3.4 模型窗口自适应

ModelRouter 增加薄薄一层 `MODEL_SPECS`:

```python
# src/capabilities/model_routing/specs.py
MODEL_SPECS = {
    "gpt-4o-mini":     {"context_window": 128000, "reserved_for_output": 4096},
    "gpt-4.1-mini":    {"context_window": 128000, "reserved_for_output": 8192},
    "gpt-4":           {"context_window": 8192,   "reserved_for_output": 1024},
    "gpt-3.5-turbo":   {"context_window": 16385,  "reserved_for_output": 1024},
}
DEFAULT_SPEC = {"context_window": 8192, "reserved_for_output": 1024}

def get_input_budget(model: str, safety_ratio: float = 0.9) -> int:
    spec = MODEL_SPECS.get(model, DEFAULT_SPEC)
    return int((spec["context_window"] - spec["reserved_for_output"]) * safety_ratio)
```

`ContextCompressionCapability.before_run` 读取 `ctx.selected_model` 算 budget,触发对应策略。

### 3.5 RollingSummary 详细流程

```
输入: enriched_input (Conversation memory + User: <input>)
        │
        ▼
[1] 解析为 messages: [(role, content), ...]
        │
        ▼
[2] 统计总 tokens,若 ≤ budget 直接返回(no-op)
        │
        ▼
[3] 切分: old_messages(待摘要) + recent_messages(保 K 轮原文)
        │
        ▼
[4] 计算 cache_key = hash(session_id + old_messages 内容 hash)
        │
        ▼
[5] 查 Redis: 命中 → 用缓存 summary;否则 →
    │
    └─→ 调 LLM(summary_model,可独立配置):
        prompt: "总结以下对话历史,保留:用户身份/目标/约束/已确认事实/待办/工具结果。
                不要复述寒暄。输出≤{summary_max_tokens} tokens。"
        │
        └─→ 写回 Redis(TTL=compression_cache_ttl_sec)
        │
        ▼
[6] 拼接: "[Summary of earlier conversation]\n{summary}\n\n" + recent_messages + current_input
        │
        ▼
[7] 再次 token 检查:仍超 budget → Truncate 兜底
```

### 3.6 缓存 key 设计

```
ck:compress:summary:{session_id}:{sha1(old_messages)[:16]}
```

- session_id 隔离会话
- 内容 hash 保证内容变了 cache miss
- TTL=`compression_cache_ttl_sec`(默认 1h)

---

## 四、失败兜底矩阵

| 失败场景 | 处置 | 对主流程影响 |
|---|---|---|
| LLM 摘要超时 / 报错 | 降级到 `TokenBudgetTruncate`,记录 warning | 无影响 |
| tiktoken 算 token 失败 | 用 `len/4` 估算 | 精度下降 |
| Redis 不可用(摘要缓存) | 跳过缓存,直连 LLM(每次重压) | 成本上升 |
| 整个 Capability 抛异常 | catch 兜底,`enriched_input` 保持上一阶段值 | 不阻塞主流程 |
| `selected_model` 不在 MODEL_SPECS | 用 DEFAULT_SPEC(8192) | 偏保守 |

**核心原则**: 压缩失败 ≠ 主流程失败。最差情况退化到不压。

---

## 五、可观测注入

`ctx.metadata["compression"]` 自动注入:

```json
{
  "strategy": "rolling_summary",
  "input_tokens": 12480,
  "budget_tokens": 11520,
  "output_tokens": 3870,
  "compress_ratio": 0.31,
  "summary_calls": 1,
  "cache_hit": false,
  "duration_ms": 412,
  "fallback_used": false,
  "model": "gpt-4o-mini"
}
```

结构化日志同步带这些字段(`bind_log_context`),Langfuse trace 也能看到。

---

## 六、配置项(Settings 新增)

```env
# === Context Compression ===
COMPRESSION_ENABLED=false              # 总开关
COMPRESSION_STRATEGY=token_budget      # token_budget | rolling_summary | hybrid
COMPRESSION_SAFETY_RATIO=0.9           # 实际 budget = window * ratio
COMPRESSION_KEEP_RECENT_TURNS=4        # rolling_summary 保留近 K 轮原文
COMPRESSION_SUMMARY_MODEL=             # 留空=复用 default_model
COMPRESSION_SUMMARY_MAX_TOKENS=512     # 单次摘要输出上限
COMPRESSION_CACHE_TTL_SEC=3600         # summary 缓存 TTL,0=禁用缓存
COMPRESSION_FAIL_OPEN=true             # true=失败放行(不压),false=失败抛错
```

---

## 七、关键决策(已敲定)

| # | 决策点 | 选择 | 理由 |
|---|---|---|---|
| **D1** | 首期范围 | `TokenBudget + RollingSummary` | 完整闭环,Hybrid 由两者组合即可 |
| **D2** | 摘要缓存后端 | Redis(复用现有 client) | 跨进程一致;Redis 不可用降级直连 LLM |
| **D3** | 应用顺序 | MemoryCapability 之后(默认) | 数据依赖顺序天然 |
| **D4** | 摘要持久化 | **不做**(每次 run 重压,Redis 缓存) | 信息不可逆,持久替换风险大 |

---

## 八、文件清单(规划)

### 新增

| 路径 | 预估行数 | 职责 |
|---|---|---|
| `src/capabilities/context_compression/__init__.py` | 15 | 导出 |
| `src/capabilities/context_compression/base.py` | 60 | `CompressionStrategy / Result` |
| `src/capabilities/context_compression/token_budget.py` | 80 | Truncate 策略 |
| `src/capabilities/context_compression/rolling_summary.py` | 180 | LLM 摘要 + Redis 缓存 |
| `src/capabilities/context_compression/hybrid.py` | 50 | 组合策略 |
| `src/capabilities/context_compression/capability.py` | 100 | `ContextCompressionCapability` |
| `src/capabilities/model_routing/specs.py` | 40 | `MODEL_SPECS + get_input_budget` |
| `tests/test_context_compression.py` | ~250 | 单测 + 降级 + 缓存 |

### 修改

- `src/capabilities/model_routing/router.py`: 暴露 `get_input_budget()`
- `src/application/orchestration/agent_runtime.py`: 注册 Capability
- `src/core/config.py`: 新增 8 个配置项
- `config/test.env.example`: 配置示例
- `requirements.txt`: 无新增依赖

**合计** ~775 行(含测试),**无新增三方依赖**,~1 个工作日。

---

## 九、验收清单

- [ ] `compression_enabled=False` 时整链路零变更
- [ ] `TokenBudgetTruncate`: budget=1000 时,把 5000-token 上下文压到 ≤1000
- [ ] `RollingSummary`: 近 K 轮原文保留,老消息出现 `[Summary of earlier conversation]`
- [ ] `HybridStrategy`: 摘要后仍超 budget 时,Truncate 兜底
- [ ] LLM 摘要超时 → 自动降级到 Truncate,日志告警,主流程不挂
- [ ] Redis 不可用 → 跳过缓存,继续直连 LLM
- [ ] 同样 old_messages 第二次进 → cache hit,无 LLM 调用
- [ ] `ctx.metadata["compression"]` 字段完整
- [ ] 模型切换(gpt-4o-mini → gpt-3.5-turbo): budget 自动从 128k×0.9 → 16k×0.9
- [ ] `selected_model` 不在 MODEL_SPECS: 走 DEFAULT_SPEC,不抛错
- [ ] 整 Capability 抛异常: `enriched_input` 保持上一阶段值

---

## 十、未来迭代方向

| 项 | 说明 |
|---|---|
| **重要性打分丢弃** | 给历史消息打 importance 分,优先丢低分(需要 scoring 模型) |
| **语义去重 / 合并** | 余弦相似度合并相似 turn |
| **结构化压缩** | 摘要按 schema 输出(facts / todos / preferences) |
| **持久化摘要替换** | 摘要写回 ShortTermMemory 替换原文(信息不可逆) |
| **流式压缩** | 长流式输出实时压缩 |
| **多模态预算** | 图片 token 计数 + 压缩 |
| **用户级偏好** | 每用户独立 strategy / 预算 |

---

## 十一、参考运行链(规划后)

```
Request
  ↓
[Protocol Layer] AuthPlugin → RateLimitPlugin → RequestId
  ↓
chat() → AgentOrchestrator.run()
  ↓
[Capability Layer]
  • MemoryCapability.before_run        → enriched_input = history + user_input
  • ContextCompressionCapability       → enriched_input = compressed (≤ budget)  ← NEW
  • (其他 before_run)
  ↓
Runner.run(enriched_input)
  ↓
[Capability Layer]
  • MemoryCapability.after_run         → 写入历史
  • (其他 after_run)
  ↓
Response (X-Request-Id, X-RateLimit-*, ctx.metadata["compression"] 进 trace)
```
