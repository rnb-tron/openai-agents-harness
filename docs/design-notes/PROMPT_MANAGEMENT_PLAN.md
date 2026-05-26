# Prompt 管理 Capability 方案

> 文档类型：设计记录。该能力已接入 Harness，本文保留初始方案与决策背景。
>
> 状态: **已接入**（具体行为以 `src/capabilities/prompt/` 与测试为准）
> 范围: 中央化 prompt 模板渲染 + Langfuse 远端存储 + 本地 YAML 兜底
> 兼容性: 默认关闭、配置即启用(`prompt_enabled=False` 时零开销)

---

## 一、问题诊断

### 现状梳理

工程内**完全没有** prompt 管理能力,全部 prompt 都是硬编码字符串:

| 位置 | 形式 | 示例 |
|---|---|---|
| [`agent_runtime.py`](../../src/application/orchestration/agent_runtime.py) | `Agent(..., instructions="...")` 硬编码 | `"You are a concise assistant. Use tools when useful..."` |
| [`rolling_summary.py`](../../src/capabilities/context_compression/rolling_summary.py) | 模块级常量 `_SYSTEM_PROMPT` | 摘要 prompt |
| [`advanced_agents/handoff.py`](../../src/capabilities/advanced_agents/handoff.py) | `instructions: str` 由调用方传入 | 各调用方自带 |

### 缺失能力清单

| 能力 | 是否支持 | 影响 |
|---|---|---|
| 模板系统(变量插值) | ❌ | 没有 `{user_name}` 这种渲染机制 |
| 版本管理 | ❌ | 改 prompt = 改代码 = 发版 |
| 标签/灰度(prod/staging/A-B) | ❌ | 无法做实验对比 |
| 中央存储(远端/文件) | ❌ | 全在源码字符串里 |
| 多语言/多场景路由 | ❌ | 不能按 task_type/locale 切换 |
| 热更新(不重启服务) | ❌ | 改一个字要发版 |
| 可观测(prompt_id 追踪) | ❌ | 日志/trace 看不出用了哪版 prompt |

### 痛点量化

| 痛点 | 严重度 |
|---|---|
| 改 prompt 必发版 | 🔴 高(迭代速度被卡死) |
| 没有 prompt 调优闭环 | 🟠 中(无法 A-B 验证效果) |
| 多 Agent 场景 prompt 散落 | 🟠 中(后续 handoff/reasoning 各一套,管理混乱) |
| Langfuse Prompt 已就位却没用 | 🟡 低(资源浪费) |

### 现有可借力点

工程已经依赖 Langfuse 4.x,且已在 [`observability/tracer.py`](../../src/capabilities/observability/tracer.py) 初始化 client (`get_client()`):

- **Langfuse Prompt API**: `langfuse.get_prompt(name, label=...)` 自带版本/标签/缓存
- **Web UI**: 编辑/版本对比/灰度 全套就绪
- **Trace 联动**: prompt_id 自动出现在 trace,无需额外接线

> 用 Langfuse 做 prompt 后端,**几乎不用自建任何东西**,且与 observability 天然打通。

---

## 二、目标 & 非目标

### ✅ 目标

1. 提供**多后端可插拔**的 prompt 管理(`Langfuse / LocalYAML / Composite`)
2. **变量插值**: `{user_name}` `{tools}` 等占位符渲染
3. **本地 YAML 兜底**: Langfuse 不可达时降级到本地文件,保证不挂
4. **缓存层**: 远端 prompt 本地缓存(TTL 配置),减少调用与延迟
5. **可观测**: `ctx.metadata["prompt"]` 注入(name / version / source),Langfuse trace 关联
6. 完全可插拔: 默认关闭、配置即启用

### ❌ 非目标(本期不做)

- 自建 prompt 编辑器 / Web UI(直接用 Langfuse Web)
- 自建 DB 持久化后端(LocalYAML 已够本期)
- Prompt A-B 评分回收(留 C 档)
- Prompt 安全审计 / 注入检测
- 多模态 prompt(图片/音频)

---

## 三、架构设计

### 3.1 双层抽象

```
┌────────────────────────────────────────────────────────┐
│ PromptManager (高层入口)                              │
│   .get(name, version=None, **vars) -> RenderedPrompt   │
└────────────────────────────────────────────────────────┘
              │
              ▼ (delegates to)
┌────────────────────────────────────────────────────────┐
│ PromptStore (Protocol, 多后端可插拔)                  │
│   • LangfuseStore   (远端, 主用)                        │
│   • LocalYamlStore  (本地兜底)                          │
│   • CompositeStore  (Langfuse + Yaml fallback)          │
└────────────────────────────────────────────────────────┘
```

### 3.2 接口约定

```python
# src/capabilities/prompt/base.py
@dataclass
class PromptTemplate:
    name: str
    template: str          # 含 {var} 占位符
    version: str | int | None = None
    label: str | None = None  # prod / staging / experiment
    source: str = "unknown"   # langfuse / yaml / composite
    metadata: dict = field(default_factory=dict)

@dataclass
class RenderedPrompt:
    name: str
    text: str
    version: str | int | None
    source: str
    rendered_vars: dict
    cache_hit: bool = False
    duration_ms: int = 0

class PromptStore(Protocol):
    name: str
    async def fetch(self, name: str, *, version=None, label=None) -> PromptTemplate: ...
```

### 3.3 内置后端(三个)

| 后端 | 数据源 | 用途 | 失败兜底 |
|---|---|---|---|
| `LocalYamlStore` | `prompts/*.yaml` | 离线/默认/兜底 | 找不到文件 → 抛 PromptNotFoundError |
| `LangfuseStore` | Langfuse SaaS | 主用,远端 | 调用失败 → 抛 PromptFetchError |
| `CompositeStore` | 上述两者 | **生产推荐** | Langfuse miss/error → 走 Yaml |

### 3.4 LocalYamlStore 文件结构

```
prompts/
  agents/
    main_chat.yaml           # 主 chat agent system prompt
    handoff_router.yaml
  capabilities/
    summary.yaml             # rolling_summary 摘要 prompt
  defaults.yaml              # 共享变量默认值
```

**单个文件示例** (`prompts/agents/main_chat.yaml`):

```yaml
name: agents.main_chat
version: "1.0.0"
label: prod
template: |
  You are a concise assistant. Use tools when useful.
  If a tool is used, include the final user-facing conclusion in plain text.
  {extra_instructions}
metadata:
  description: "Main chat agent system prompt"
  variables:
    - name: extra_instructions
      default: ""
```

### 3.5 LangfuseStore 实现

复用 [`observability/tracer.py`](../../src/capabilities/observability/tracer.py) 已初始化的 client:

```python
from langfuse import get_client

class LangfuseStore:
    name = "langfuse"
    async def fetch(self, name, *, version=None, label="prod"):
        client = get_client()
        # Langfuse SDK 是同步, 用 run_in_executor 包一下
        prompt = await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: client.get_prompt(name, version=version, label=label)
        )
        return PromptTemplate(
            name=name,
            template=prompt.prompt,
            version=prompt.version,
            label=label,
            source="langfuse",
        )
```

### 3.6 PromptManager(渲染层)

```python
class PromptManager:
    def __init__(self, store: PromptStore, *, cache_ttl_sec: int = 300):
        self._store = store
        self._cache: dict[str, tuple[float, PromptTemplate]] = {}
        self._cache_ttl = cache_ttl_sec

    async def get(
        self, name: str, *,
        version=None, label="prod", **vars,
    ) -> RenderedPrompt:
        tpl = await self._fetch_with_cache(name, version, label)
        text = tpl.template.format_map(_DefaultDict(vars))  # 缺变量保留 {var} 不抛错
        return RenderedPrompt(
            name=tpl.name, text=text, version=tpl.version,
            source=tpl.source, rendered_vars=vars,
        )
```

**变量缺失策略**:用 `_DefaultDict` 把缺失的 `{var}` 保留原样(而非 KeyError),允许多层渲染。

### 3.7 PromptCapability(可观测注入)

```python
class PromptCapability(Capability):
    name = "prompt"

    async def before_run(self, ctx: RunContext) -> None:
        if not self._enabled: return
        # 不改 enriched_input(那是 Memory/Compression 职责),
        # 只是把当前 run 用到的 prompt 元信息预先注入 metadata
        # 实际渲染由各调用方主动调 PromptManager.get()
        ctx.metadata["prompt_manager_ready"] = True
```

> 注: `PromptCapability` 主要做生命周期管理(setup 拉缓存预热 / teardown 释放),
> 实际 prompt 渲染由 **调用方主动调 `PromptManager.get(...)`** 触发,
> 这与 Memory/Compression 自动改 enriched_input 不同 — prompt 是"哪里需要哪里取"。

---

## 四、改造现有硬编码点

### 4.1 主 chat agent

```python
# agent_runtime.py 现状
agent = Agent(
    name="MinimalChatAgent",
    instructions="You are a concise assistant...",  # 硬编码
    ...
)

# 改造后
rendered = await self._prompt_mgr.get("agents.main_chat", task_type=task_type)
agent = Agent(
    name="MinimalChatAgent",
    instructions=rendered.text,
    ...
)
ctx.metadata["prompt"] = {
    "name": rendered.name,
    "version": rendered.version,
    "source": rendered.source,
}
```

### 4.2 RollingSummary 摘要 prompt

```python
# rolling_summary.py 现状
_SYSTEM_PROMPT = "You are a precise conversation summarizer..."

# 改造后(注入 PromptManager)
rendered = await self._prompt_mgr.get("capabilities.summary")
messages = [{"role": "system", "content": rendered.text}, ...]
```

### 4.3 Handoff/HITL 等高级能力

`instructions` 参数改为接收"prompt name"而非裸字符串,内部统一查 PromptManager。

---

## 五、缓存与并发

| 项 | 设计 |
|---|---|
| 缓存层级 | 进程内 LRU + TTL(默认 5min);进一步用 Redis 跨进程一致(可选) |
| 并发预热 | `setup()` 时按 `prompt_warmup_names` 列表批量拉,失败仅 warning |
| 失效策略 | TTL 到期被动刷新;Langfuse Webhook 主动失效(本期不做) |
| 缺省回退 | LangfuseStore 失败 → CompositeStore 自动走 LocalYamlStore |

---

## 六、失败兜底矩阵

| 失败场景 | 处置 | 影响 |
|---|---|---|
| Langfuse 不可达 | 降级 LocalYamlStore | 内容可能滞后 |
| YAML 也找不到 | 抛 `PromptNotFoundError` | 调用方 catch 决定是否降级到内置 string |
| 变量缺失 | 占位符保留原样,warning | 不抛错 |
| `prompt_enabled=False` | PromptManager 不构造,调用方走 fallback string | 主流程不挂 |
| 缓存读写失败 | 跳过缓存直连后端 | 性能下降 |

**核心原则**: prompt 失败不阻塞主流程,Capability 整体加 try/except 兜底。

---

## 七、可观测注入

`ctx.metadata["prompt"]` 自动注入(由调用方 `PromptManager.get()` 触发):

```json
{
  "name": "agents.main_chat",
  "version": "1.0.0",
  "source": "langfuse",
  "label": "prod",
  "rendered_vars": {"task_type": "reasoning"},
  "cache_hit": true,
  "duration_ms": 3
}
```

结构化日志同步带这些字段,Langfuse trace 自动关联(prompt_id 出现在 generation span)。

---

## 八、配置项(Settings 新增)

```env
# === Prompt Management ===
PROMPT_ENABLED=false                   # 总开关
PROMPT_BACKEND=composite               # composite | langfuse | yaml
PROMPT_LOCAL_DIR=prompts               # 本地 yaml 目录(相对项目根)
PROMPT_DEFAULT_LABEL=prod              # Langfuse 默认 label
PROMPT_CACHE_TTL_SEC=300               # 进程内缓存 TTL
PROMPT_WARMUP_NAMES=                   # 启动期预热的 prompt name CSV
PROMPT_FAIL_OPEN=true                  # 失败放行(调用方走兜底 string)
```

---

## 九、关键决策(本方案敲定)

| # | 决策 | 选择 | 理由 |
|---|---|---|---|
| **D1** | 主存储后端 | **Langfuse** | 已就位,免自建,功能完整 |
| **D2** | 兜底后端 | **LocalYamlStore** | 离线可用,可读,Git 可追 |
| **D3** | 渲染时机 | **调用方主动 get** (非自动改 enriched_input) | prompt 用途多样,不该一刀切 |
| **D4** | 变量缺失 | **保留原样 + warning** | 不抛错,允许多层渲染 |
| **D5** | 缓存 | **进程内 LRU + TTL** (本期不做 Redis) | 简单优先,后期再升 |
| **D6** | 改造范围 | **本期 3 处**: main_chat / summary / handoff | 范围可控,验证闭环 |

---

## 十、文件清单(规划)

### 新增

| 路径 | 预估行数 | 职责 |
|---|---|---|
| `src/capabilities/prompt/__init__.py` | 20 | 导出 |
| `src/capabilities/prompt/base.py` | 70 | `PromptStore / PromptTemplate / RenderedPrompt` |
| `src/capabilities/prompt/manager.py` | 120 | `PromptManager` + LRU 缓存 + 渲染 |
| `src/capabilities/prompt/local_yaml_store.py` | 80 | 本地 YAML 加载 |
| `src/capabilities/prompt/langfuse_store.py` | 70 | Langfuse 后端 |
| `src/capabilities/prompt/composite_store.py` | 60 | 主备组合 |
| `src/capabilities/prompt/capability.py` | 80 | `PromptCapability`(预热/释放) |
| `src/capabilities/prompt/errors.py` | 20 | 异常类 |
| `prompts/agents/main_chat.yaml` | - | 主 chat prompt |
| `prompts/capabilities/summary.yaml` | - | 摘要 prompt |
| `tests/test_prompt_management.py` | ~250 | 单测 |

### 修改

- `src/application/orchestration/agent_runtime.py`: 接入 PromptManager,改造 `instructions=...`
- `src/capabilities/context_compression/rolling_summary.py`: `_SYSTEM_PROMPT` 改为 PromptManager 取
- `src/core/config.py`: 新增 7 个配置项
- `src/main.py`: lifespan 期间初始化 PromptManager
- `config/test.env.example`: 配置示例段
- `requirements.txt`: 新增 `PyYAML >= 6.0` (LocalYamlStore 用)

**合计** ~770 行(含测试),~1 工作日,**新增依赖仅 PyYAML**。

---

## 十一、验收清单

- [ ] `prompt_enabled=False` 时整链路零变更(主 agent 仍用硬编码 fallback)
- [ ] `LocalYamlStore.fetch("agents.main_chat")` 正确加载并渲染变量
- [ ] `LangfuseStore.fetch` 调用 `get_prompt`,version/label 透传
- [ ] `CompositeStore`: Langfuse 失败时自动走 Yaml,日志告警
- [ ] PromptManager 缓存: 二次 get 同 name 不重新拉,`cache_hit=True`
- [ ] 变量缺失时 `{var}` 保留原样,warning
- [ ] `prompt_warmup_names` 启动期预热,失败不阻塞 lifespan
- [ ] `ctx.metadata["prompt"]` 字段完整(含 source / version / cache_hit)
- [ ] 主 chat agent 改造后,响应不变(用 main_chat.yaml 内容与原硬编码一致)
- [ ] 测试 ≥ 8 用例全绿,模块导入 OK

---

## 十二、未来迭代方向

| 项 | 说明 |
|---|---|
| **DB 持久化后端** | 自建 prompt 仓库,不依赖 Langfuse |
| **Web 编辑器** | 提供本地编辑界面(替代 Langfuse Web) |
| **A-B 灰度路由** | 按 user_id hash 分流到不同 prompt |
| **评分回收** | prompt → 实际效果回流,自动选优 |
| **Redis 跨进程缓存** | 多实例下一致性 |
| **多语言路由** | 按 locale 自动选 prompt 变体 |
| **Prompt 注入检测** | 防 prompt injection 攻击 |
| **Webhook 主动失效** | Langfuse 改 prompt 即时通知本地 cache invalidate |

---

## 十三、参考运行链(规划后)

```
Request
  ↓
[Protocol Layer] AuthPlugin → RateLimitPlugin → RequestId
  ↓
chat() → AgentOrchestrator.run()
  ↓
[Capability Layer]
  • MemoryCapability.before_run        → enriched_input = history + user_input
  • ContextCompressionCapability       → enriched_input = compressed (≤ budget)
  • PromptCapability.before_run        → ctx.metadata["prompt_manager_ready"] = True
  ↓
agent_runtime.run() 主动:
  • PromptManager.get("agents.main_chat", task_type=...)  ← NEW
  • Agent(instructions=rendered.text)
  ↓
Runner.run(enriched_input)
  ↓
[Capability Layer]
  • MemoryCapability.after_run         → 写入历史
  ↓
Response (X-Request-Id, ctx.metadata["compression"]+["prompt"] 进 trace)
```
