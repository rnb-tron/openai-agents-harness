# 模型降级、重试与超时控制技术方案

## 📋 需求分析

### 核心需求
1. **循环模型降级 (Circular Model Fallback)**: 当主模型失败时,自动降级到备选模型
2. **重试机制 (Retries)**: 网络抖动、超时等临时故障时自动重试
3. **总超时预算控制 (Total Timeout Budget)**: 控制整个请求链路的最大耗时

### 使用场景
- 模型服务不稳定或限流
- 多模型优先级调度 (如: qwen3.5-plus → qwen3.0 → gpt-4o-mini)
- SLA 保障 (如: 总耗时不超过 30 秒)
- 成本优化 (优先使用便宜模型,失败后降级)

---

## 🎯 必要性评估

### ✅ 必要性: **高**

| 维度 | 评分 | 说明 |
|------|------|------|
| **稳定性** | ⭐⭐⭐⭐⭐ | 生产环境必备能力,应对模型服务故障 |
| **用户体验** | ⭐⭐⭐⭐⭐ | 避免因单次失败导致用户请求失败 |
| **成本优化** | ⭐⭐⭐⭐ | 可优先使用便宜模型,失败后降级到高质量模型 |
| **可观测性** | ⭐⭐⭐⭐ | 结合 Langfuse 可追踪降级链路和成功率 |
| **通用性** | ⭐⭐⭐⭐⭐ | 所有 Agent 应用都需要的基础能力 |

### 结论
**强烈建议实现**,这是生产级 Agent Harness 的核心能力之一。

---

## 🔍 可行性评估

### ✅ 可行性: **高**

#### 优势
1. **架构支持**: 六层架构中 `capabilities/` 层正是为这类可插拔能力设计
2. **OpenAI SDK 支持**: 原生支持 retry 机制 (`max_retries` 参数)
3. **异步友好**: Python asyncio 提供完善的超时控制机制
4. **已有基础**: 已有 `ModelRouter` 可扩展

#### 挑战
1. **状态管理**: 降级链路的上下文传递
2. **超时预算分配**: 多次重试/降级的超时分配策略
3. **可观测性**: 需要记录完整的降级链路
4. **成本控制**: 避免降级导致成本激增

#### 结论
**完全可行**,利用现有架构可在 1-2 天内完成实现。

---

## 🏗️ 技术方案设计

### 方案 1: 增强 ModelRouter (推荐)

#### 架构设计

```
src/capabilities/model_routing/
├── router.py           # 现有: 简单路由
├── fallback.py         # 新增: 降级策略
├── retry.py            # 新增: 重试策略
├── timeout.py          # 新增: 超时控制
└── config.py           # 新增: 配置管理
```

#### 核心设计

##### 1. 降级策略 (Fallback Strategy)

```python
@dataclass
class FallbackConfig:
    """降级配置"""
    models: list[str]                    # 降级链路: ["qwen3.5-plus", "qwen3.0", "gpt-4o-mini"]
    fallback_on: list[type[Exception]]   # 触发降级的异常类型
    track_metrics: bool = True           # 是否记录降级指标

class ModelFallback:
    """循环模型降级器"""
    
    async def run(self, func, **kwargs):
        """
        执行降级逻辑
        :param func: 执行函数 (接收 model 参数)
        :param kwargs: 传递给 func 的额外参数
        """
        last_error = None
        
        for model in self.config.models:
            try:
                return await func(model=model, **kwargs)
            except tuple(self.config.fallback_on) as e:
                last_error = e
                logger.warning(f"Model {model} failed: {e}")
                
                # 记录降级指标
                if self.config.track_metrics:
                    await self.record_fallback(model, e)
        
        # 所有模型都失败
        raise last_error
```

##### 2. 重试策略 (Retry Strategy)

```python
@dataclass
class RetryConfig:
    """重试配置"""
    max_retries: int = 3                 # 最大重试次数
    initial_delay: float = 1.0           # 初始延迟 (秒)
    max_delay: float = 10.0              # 最大延迟 (秒)
    exponential_base: float = 2.0        # 指数退避基数
    retry_on: list[type[Exception]]      # 触发重试的异常类型

class RetryExecutor:
    """指数退避重试器"""
    
    async def execute(self, func, **kwargs):
        """执行重试逻辑"""
        last_error = None
        delay = self.config.initial_delay
        
        for attempt in range(self.config.max_retries + 1):
            try:
                return await func(**kwargs)
            except tuple(self.config.retry_on) as e:
                last_error = e
                
                if attempt == self.config.max_retries:
                    break
                
                # 指数退避
                await asyncio.sleep(delay)
                delay = min(delay * self.config.exponential_base, self.config.max_delay)
        
        raise last_error
```

##### 3. 超时控制 (Timeout Budget)

```python
@dataclass
class TimeoutBudget:
    """超时预算"""
    total_timeout: float = 30.0          # 总超时 (秒)
    per_request_timeout: float = 10.0    # 单次请求超时 (秒)

class TimeoutController:
    """超时预算控制器"""
    
    async def execute_with_budget(self, func, **kwargs):
        """带超时预算的执行"""
        try:
            return await asyncio.wait_for(
                func(**kwargs),
                timeout=self.config.total_timeout
            )
        except asyncio.TimeoutError:
            raise ModelTimeoutError(f"Total timeout {self.config.total_timeout}s exceeded")
```

##### 4. 组合策略 (Orchestrator)

```python
class ResilientModelRunner:
    """弹性模型运行器 - 组合降级、重试、超时"""
    
    def __init__(
        self,
        fallback: ModelFallback,
        retry: RetryExecutor,
        timeout: TimeoutController
    ):
        self.fallback = fallback
        self.retry = retry
        self.timeout = timeout
    
    async def run(self, agent_factory, **kwargs):
        """
        执行弹性模型调用
        :param agent_factory: 创建 Agent 的工厂函数
        """
        # 外层: 超时控制
        async def with_timeout():
            # 中层: 降级策略
            async def with_fallback(model):
                # 内层: 重试策略
                async def with_retry():
                    agent = await agent_factory(model=model)
                    return await Runner.run(agent, **kwargs)
                
                return await self.retry.execute(with_retry)
            
            return await self.fallback.run(with_fallback)
        
        return await self.timeout.execute_with_budget(with_timeout)
```

#### 使用示例

```python
# 配置
fallback_config = FallbackConfig(
    models=["qwen3.5-plus", "qwen3.0", "gpt-4o-mini"],
    fallback_on=[APIError, TimeoutError, RateLimitError]
)

retry_config = RetryConfig(
    max_retries=2,
    initial_delay=1.0,
    max_delay=5.0,
    retry_on=[ConnectionError, TimeoutError]
)

timeout_config = TimeoutBudget(
    total_timeout=30.0,
    per_request_timeout=10.0
)

# 创建运行器
runner = ResilientModelRunner(
    fallback=ModelFallback(fallback_config),
    retry=RetryExecutor(retry_config),
    timeout=TimeoutController(timeout_config)
)

# 执行
result = await runner.run(
    agent_factory=create_agent,
    input=user_input
)
```

---

### 方案 2: 装饰器模式 (轻量级)

#### 设计思路

使用装饰器组合实现,更简洁但灵活性较低:

```python
@timeout(30.0)
@fallback(models=["qwen3.5-plus", "qwen3.0"])
@retry(max_retries=3, delay=1.0)
async def call_model(model, input):
    agent = Agent(name="Test", model=model)
    return await Runner.run(agent, input)
```

#### 优缺点

| 维度 | 方案 1 (Runner) | 方案 2 (装饰器) |
|------|----------------|----------------|
| **灵活性** | ⭐⭐⭐⭐⭐ 高 | ⭐⭐⭐ 中 |
| **可测试性** | ⭐⭐⭐⭐⭐ 高 | ⭐⭐⭐⭐ 高 |
| **可观测性** | ⭐⭐⭐⭐⭐ 易于埋点 | ⭐⭐⭐ 需额外工作 |
| **配置管理** | ⭐⭐⭐⭐⭐ 集中管理 | ⭐⭐⭐ 分散 |
| **代码复杂度** | ⭐⭐⭐ 中 | ⭐⭐⭐⭐⭐ 简单 |

**推荐**: 方案 1 (Runner 模式),更适合生产环境。

---

## 📊 集成到现有架构

### 修改点

#### 1. `src/capabilities/model_routing/router.py`

```python
class ModelRouter:
    """增强版模型路由器"""
    
    def __init__(self, config: ModelRoutingConfig):
        self.fallback = ModelFallback(config.fallback)
        self.retry = RetryExecutor(config.retry)
        self.timeout = TimeoutController(config.timeout)
        self.resilient_runner = ResilientModelRunner(
            self.fallback, self.retry, self.timeout
        )
    
    async def run_with_resilience(self, agent_factory, **kwargs):
        """弹性执行模型调用"""
        return await self.resilient_runner.run(agent_factory, **kwargs)
```

#### 2. `src/application/orchestration/agent_runtime.py`

```python
class AgentOrchestrator:
    async def run(self, session: AgentSession, user_input: str):
        # 使用弹性运行器
        async def create_agent(model):
            client = AsyncOpenAI(...)
            return Agent(
                name="MinimalChatAgent",
                instructions="...",
                model=OpenAIChatCompletionsModel(model=model, openai_client=client),
                tools=self.tool_registry.list_agent_tools(),
            )
        
        result = await self.model_router.run_with_resilience(
            agent_factory=create_agent,
            input=enriched_input
        )
        
        return parse_result(result)
```

#### 3. 配置管理

```python
# src/core/config.py
class ModelRoutingSettings(BaseSettings):
    # 降级配置
    model_fallback_enabled: bool = True
    model_fallback_chain: str = "qwen3.5-plus,qwen3.0,gpt-4o-mini"
    
    # 重试配置
    model_retry_enabled: bool = True
    model_max_retries: int = 2
    
    # 超时配置
    model_total_timeout: float = 30.0
    model_per_request_timeout: float = 10.0
```

---

## 🔧 实现步骤

### Phase 1: 基础实现 (1-2 天)

1. ✅ 创建 `src/capabilities/model_routing/fallback.py`
2. ✅ 创建 `src/capabilities/model_routing/retry.py`
3. ✅ 创建 `src/capabilities/model_routing/timeout.py`
4. ✅ 创建 `src/capabilities/model_routing/config.py`
5. ✅ 更新 `ModelRouter` 集成弹性运行器
6. ✅ 更新 `AgentOrchestrator` 使用新能力

### Phase 2: 可观测性集成 (0.5 天)

1. ✅ 集成 Langfuse 追踪降级链路
2. ✅ 记录降级指标 (成功率、延迟分布)
3. ✅ 添加告警支持 (降级率超过阈值)

### Phase 3: 测试与文档 (0.5 天)

1. ✅ 单元测试 (降级、重试、超时)
2. ✅ 集成测试 (完整链路)
3. ✅ 使用文档
4. ✅ 配置示例

---

## 📈 可观测性设计

### Langfuse 追踪

```python
with trace("Model Fallback Chain"):
    for model in fallback_chain:
        with span(f"Model: {model}") as s:
            s.set_attribute("model.name", model)
            s.set_attribute("model.attempt", attempt)
            
            try:
                result = await call_model(model)
                s.set_attribute("model.status", "success")
                return result
            except Exception as e:
                s.set_attribute("model.status", "failed")
                s.record_exception(e)
```

### 指标收集

```python
@dataclass
class FallbackMetrics:
    total_requests: int = 0
    fallback_count: int = 0
    retry_count: int = 0
    timeout_count: int = 0
    success_rate: float = 0.0
    avg_latency: float = 0.0
    fallback_chain: dict[str, int] = field(default_factory=dict)
```

---

## 🎯 配置示例

### config/test.env

```bash
# 模型降级配置
MODEL_FALLBACK_ENABLED=true
MODEL_FALLBACK_CHAIN=qwen3.5-plus,qwen3.0,gpt-4o-mini

# 重试配置
MODEL_RETRY_ENABLED=true
MODEL_MAX_RETRIES=2
MODEL_RETRY_DELAY=1.0

# 超时配置
MODEL_TOTAL_TIMEOUT=30.0
MODEL_PER_REQUEST_TIMEOUT=10.0
```

---

## ⚠️ 注意事项

### 1. 成本控制
- 降级可能导致多次调用,增加成本
- 建议设置每日预算上限

### 2. 用户体验
- 降级后的模型质量可能不同
- 可在响应中添加提示 (如: "使用备选模型生成")

### 3. 超时分配
- 总超时需合理分配给每次尝试
- 建议: 总超时 / (降级链长度 × 重试次数)

### 4. 异常分类
- 区分可重试异常 (网络错误) 和不可重试异常 (认证失败)
- 避免无效重试

### 5. 降级链路
- 避免循环依赖
- 确保最终有一个兜底模型

---

## ✅ 总结

### 必要性: ⭐⭐⭐⭐⭐ (高)
- 生产环境必备能力
- 提升稳定性和用户体验

### 可行性: ⭐⭐⭐⭐⭐ (高)
- 现有架构完全支持
- 实现难度低,1-2 天可完成

### 推荐方案: Runner 模式
- 灵活性高
- 可测试性强
- 易于集成可观测性

### 实施建议
1. 先实现基础功能 (降级 + 重试 + 超时)
2. 集成 Langfuse 可观测性
3. 编写完整测试
4. 逐步推广到所有 Agent

---

**结论: 强烈建议实现,这是生产级 Agent Harness 的核心能力!** 🚀
