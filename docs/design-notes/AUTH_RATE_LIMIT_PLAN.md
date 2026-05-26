# 协议层 Auth 与限流 可插拔方案

> 文档类型：设计记录。当前能力开关与装配状态以代码及架构设计文档为准。
>
> 更新说明：当前实现已将抽象名称收敛为 `ProtocolPlugin` / `ProtocolPluginRegistry`，由 `src/api/app.py` 装配；Redis 限流默认 fail-closed，以下早期 fail-open 描述仅保留决策演进背景。
>
> 状态: **已实施**(分支 `refactor/arch-cleanup-p0-p1-p2` 之上的协议层增强)
> 范围: 仅"消费方 JWT 认证 + Token-Bucket 限流",不含登录会话/Token 颁发
> 兼容性: 默认关闭、配置即启用(零开销 + 向后兼容)

---

## 一、问题诊断

### 现状(立项前)
- ❌ 无任何 AuthN/AuthZ:`/chat` 完全裸奔,任何调用方都能消费 OpenAI 配额
- ❌ 无限流:`/chat` 无频次/并发控制,配额可被打爆
- ❌ 无登录/会话:user_id 由请求体自报,无法证伪
- ✅ 唯一中间件: `request_id_middleware`(可观测用)
- ✅ 底座具备: Redis(限流原子操作) + 结构化日志 + Settings 配置

### 目标
1. 提供**消费方 JWT 认证**:在 API Gateway 之后承接已签发的 token
2. 提供**多维度 Token-Bucket 限流**:principal / IP / route 维度可插拔
3. 形态**可插拔**:默认关闭,生产仅需 env 切开关
4. **不污染 Capability 层**:这两件事属于 HTTP 协议生命周期,不应混入 Agent run 周期

---

## 二、核心架构决策

### 2.1 引入新抽象:`MiddlewarePlugin`(协议层)

与应用层 `Capability` 抽象**正交不耦合**,形成"双层可插拔":

```
┌─────────────────────────────────────────────────────────┐
│ HTTP Request                                            │
│   │                                                     │
│   ▼  ┌──────────────────────────────────────────────┐   │
│      │ MiddlewarePlugin 链 (协议层周期)             │   │
│      │   • AuthPlugin       → request.state.principal│   │
│      │   • RateLimitPlugin  → 429 / X-RateLimit-*  │   │
│      └──────────────────────────────────────────────┘   │
│   │                                                     │
│   ▼  ┌──────────────────────────────────────────────┐   │
│      │ Capability 链 (Agent run 周期)               │   │
│      │   • MemoryCapability                         │   │
│      │   • ContextCompressionCapability(规划中)     │   │
│      │   • HITLCapability / CheckpointCapability    │   │
│      └──────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────┘
```

### 2.2 协议层抽象三件套

```python
# src/api/middleware/base.py
@runtime_checkable
class MiddlewarePlugin(Protocol):
    name: str
    def is_enabled(self) -> bool: ...
    def install(self, app: FastAPI) -> None: ...
    async def setup(self) -> None: ...
    async def teardown(self) -> None: ...

# src/api/middleware/registry.py
class MiddlewareRegistry:
    def register(self, plugin: MiddlewarePlugin) -> None: ...
    def install_all(self, app: FastAPI) -> None:
        # 反向 install,使注册顺序 = 运行顺序
        for plugin in reversed(self.enabled):
            plugin.install(app)
    async def setup_all(self) -> None: ...
    async def teardown_all(self) -> None: ...

middleware_registry = MiddlewareRegistry()  # 全局单例
```

> ⚠️ FastAPI middleware 是 LIFO 的(后注册先运行),Registry 内部反向 install,
> 让用户视角的"先注册 Auth、再注册 RateLimit"在运行时=`Auth → RateLimit → Router`。

---

## 三、Auth 子系统

### 3.1 Principal 模型(贯穿运行时)

```python
@dataclass
class Principal:
    user_id: str
    scopes: list[str] = field(default_factory=list)
    claims: dict[str, Any] = field(default_factory=dict)
    is_anonymous: bool = False
```

通过 `request.state.principal` 注入,业务代码用 `Depends(get_current_principal)` 取。

### 3.2 JWT Backend 设计要点

- **Token 来源优先级**: `Authorization: Bearer <token>` 主,`X-Api-Token` 备
- **算法**: 默认 HS256(对称),可选 RS256(非对称,key 走 `auth_jwt_public_key`)
- **校验项**: 签名 / `exp`(带 `leeway_sec`) / `iss` / `aud`
- **Claims 映射**: `sub` → `user_id`,`scope` 或 `scopes` → `list[str]`
- **错误细分**: `token_expired / invalid_signature / invalid_issuer / invalid_audience / invalid_token / missing_sub`

### 3.3 Strict / 非 Strict 双模式

| 模式 | 未带 token | 用处 |
|---|---|---|
| `auth_strict=False`(默认) | 注入匿名 Principal,放行 | 灰度阶段、内部联调 |
| `auth_strict=True` | 直接 401 | 生产 |

### 3.4 Skip Paths

健康检查、文档(`/health`, `/docs`, `/openapi.json`)默认绕过,可配置追加。

### 3.5 FastAPI Depends 集成

```python
# 业务路由仅一行集成
@router.post("")
async def chat(
    request: ChatRequest,
    principal: Principal = Depends(get_current_principal),
):
    user_id = request.user_id if principal.is_anonymous else principal.user_id
    ...

# 需要权限的接口
@router.delete("/admin/sessions")
async def delete_all(
    principal: Principal = Depends(require_scope("admin")),
):
    ...
```

### 3.6 与结构化日志联动

Auth middleware 在 `principal` 解析后,通过 `bind_log_context(principal_id=...)` 注入,
日志和 trace 自动带 `principal_id` 字段。

---

## 四、RateLimit 子系统

### 4.1 算法选型: Token Bucket

三参数: `limit`(令牌总量) / `window_sec`(窗口) / `burst`(突发上限)

> 与 Sliding Window 比:支持突发更友好;与 Fixed Window 比:无窗口边界尖峰。

### 4.2 后端可插拔

| 后端 | 适用 | 一致性 |
|---|---|---|
| `RedisRateLimiter`(默认生产) | 多实例 | Lua 脚本原子 EVALSHA + NOSCRIPT 重试 |
| `MemoryRateLimiter` | 单机/测试 | 仅本进程 |

### 4.3 Lua 脚本(Redis 后端核心)

```lua
-- KEYS[1]=bucket key; ARGV: limit, window_sec, burst, now_ms
-- 状态: tokens(浮点) + last_refill_ms
-- 流程: HMGET → 按时间差补令牌 → 扣减/拒绝 → HSET + EXPIRE
-- 返回: [allowed(0/1), remaining, retry_after_sec]
```

失败 fail-open(降级放行,日志 warning),保证限流不背锅故障。

### 4.4 维度策略 (`rate_limit_key_strategy`)

| 策略 | key 模板 | 用处 |
|---|---|---|
| `principal` | `rl:{route}:principal:{user_id}` | 已认证用户限流 |
| `ip` | `rl:{route}:ip:{client_ip}` | 防爬虫/匿名滥用 |
| `principal_or_ip`(默认) | 有 principal 用 principal,否则 IP | 兼容性最好 |

### 4.5 路由级覆写 (`rate_limit_routes`)

JSON 字符串(便于 env var):

```json
{
  "POST /v1/chat":   {"limit": 30, "window_sec": 60, "burst": 5},
  "POST /v1/admin/*":{"limit": 10, "window_sec": 60, "burst": 2}
}
```

未匹配的路由用 `rate_limit_default_*` 三元组。

### 4.6 响应规范

#### 触发限流(429)

```http
HTTP/1.1 429 Too Many Requests
Retry-After: 12
X-RateLimit-Limit: 30
X-RateLimit-Remaining: 0
X-RateLimit-Reset: 12

{"error": "rate_limited", "retry_after": 12, "message": "Too many requests"}
```

#### 正常请求

每次响应都附带 `X-RateLimit-*` 头,前端可做客户端预判。

---

## 五、配置项总览(env)

```env
# === Auth ===
AUTH_ENABLED=false               # 总开关
AUTH_STRICT=false                # true=未带 token 直接 401
AUTH_JWT_ALGORITHM=HS256         # HS256 | RS256
AUTH_JWT_SECRET=<at-least-32B>   # HS256 时必填
AUTH_JWT_PUBLIC_KEY=             # RS256 时必填(PEM)
AUTH_JWT_ISSUER=                 # 可选 iss 校验
AUTH_JWT_AUDIENCE=               # 可选 aud 校验
AUTH_JWT_LEEWAY_SEC=30           # exp 容差
AUTH_SKIP_PATHS=/health,/docs,/openapi.json

# === RateLimit ===
RATE_LIMIT_ENABLED=false
RATE_LIMIT_BACKEND=redis         # redis | memory
RATE_LIMIT_DEFAULT_LIMIT=60
RATE_LIMIT_DEFAULT_WINDOW_SEC=60
RATE_LIMIT_DEFAULT_BURST=10
RATE_LIMIT_KEY_STRATEGY=principal_or_ip
RATE_LIMIT_ROUTES=               # JSON 字符串,空=不覆写
RATE_LIMIT_SKIP_PATHS=/health,/docs,/openapi.json
```

---

## 六、文件清单

### 新增 13 个

| 路径 | 行数 | 职责 |
|---|---|---|
| `src/api/middleware/__init__.py` | 11 | 导出 |
| `src/api/middleware/base.py` | 39 | `MiddlewarePlugin` Protocol |
| `src/api/middleware/registry.py` | 92 | 注册中心 + 反向 install |
| `src/api/middleware/auth/__init__.py` | 17 | 导出 |
| `src/api/middleware/auth/base.py` | 56 | `Principal / AuthError / AuthBackend` |
| `src/api/middleware/auth/jwt_backend.py` | 128 | PyJWT 验签 |
| `src/api/middleware/auth/plugin.py` | 129 | HTTP middleware 安装 |
| `src/api/middleware/auth/deps.py` | 43 | `Depends(get_current_principal)` |
| `src/api/middleware/rate_limit/__init__.py` | 22 | 导出 |
| `src/api/middleware/rate_limit/base.py` | 58 | `RateLimitKey / Decision / Limiter` |
| `src/api/middleware/rate_limit/redis_backend.py` | 155 | Lua + EVALSHA 重试 + fail-open |
| `src/api/middleware/rate_limit/memory_backend.py` | 69 | 进程内 Token Bucket |
| `src/api/middleware/rate_limit/plugin.py` | 195 | 限流 middleware + 路由覆写 |

### 修改 5 个

- `src/main.py`: 注册插件 + lifespan setup/teardown
- `src/core/config.py`: 新增 18 个配置项
- `src/api/routers/chat.py`: `Depends(get_current_principal)`,principal 优先取 `user_id`
- `requirements.txt`: 新增 `PyJWT >= 2.8.0`
- `config/test.env.example`: 新增 22 行配置示例

### 新增测试 2 个文件 / 15 用例

- `tests/test_middleware_auth.py`(8 用例): strict/expired/tampered/skip/scope/fallback header
- `tests/test_middleware_rate_limit.py`(7 用例): burst/路由隔离/路由覆写/skip/header/disabled/direct

---

## 七、验收清单

- [x] `auth_enabled=False` 时整链路零变更(向后兼容)
- [x] HS256 / RS256 双算法验签
- [x] strict 模式下未带 token → 401
- [x] 非 strict 模式下匿名 Principal 注入
- [x] expired / tampered / wrong issuer / wrong audience 错误码细分
- [x] `require_scope("admin")` 缺权限 → 403,匿名 → 401
- [x] `X-Api-Token` 头 fallback
- [x] Redis Lua 原子限流,NOSCRIPT 重试一次后 fail-open
- [x] 三种 key 策略(principal / ip / principal_or_ip)
- [x] 路由覆写 + skip 路径
- [x] `Retry-After` + `X-RateLimit-*` 响应头
- [x] 15/15 测试通过,15 模块导入 OK

---

## 八、已知约束 & 后期可迭代

| 项 | 现状 | 后期 |
|---|---|---|
| Token 颁发 | 不做(假设由 IDP / Gateway 出) | 视需求引入 `/auth/login` |
| 登录会话 | 不做 | 引入 SessionStore(Redis) + cookie |
| OAuth2 | 不做 | 加 `OAuth2Backend` 实现 `AuthBackend` 协议 |
| 限流后端 | Redis / Memory | 可加 `Sentinel/Cluster` 支持 |
| 限流维度 | 三选一 | 可加 `composite`(principal × route × tenant) |
| 限流算法 | Token Bucket | 可加 `SlidingWindow / LeakyBucket` 策略类 |
| 审计日志 | 复用结构化日志 | 可加专用 `audit.log` channel |

---

## 九、参考调用链(运行时)

```
Request
  ↓
RateLimitPlugin.middleware    ← LIFO: 后注册先跑
  ↓ (decision.allowed)
AuthPlugin.middleware
  ↓ (request.state.principal)
request_id_middleware
  ↓
FastAPI Router  (Depends(get_current_principal))
  ↓
chat() → AgentOrchestrator.run() → Capability 链 → Runner
  ↓
Response (X-RateLimit-* headers, X-Request-Id)
```
