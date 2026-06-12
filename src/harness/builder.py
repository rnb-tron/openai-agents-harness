"""Harness 装配器和生命周期持有者。"""

from __future__ import annotations

from dataclasses import dataclass
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.middleware.capabilities import AuthCapability, RateLimitCapability
from src.application.orchestration.agent_runtime import AgentOrchestrator
from src.capabilities.advanced_agents import CheckpointConfig, HandoffConfig, HITLConfig
from src.capabilities.memory.mem0_manager import Mem0MemoryManager
from src.capabilities.memory.store import MemoryStore
from src.capabilities.model_routing.capabilities import (
    ModelResilienceCapability,
    ModelRouterCapability,
)
from src.capabilities.model_routing.config import ResilienceConfig
from src.capabilities.model_routing.router import ModelRouter
from src.capabilities.observability.capability import ObservabilityCapability
from src.capabilities.plugin import CapabilityRegistry
from src.capabilities.prompt.factory import build_prompt_manager
from src.capabilities.prompt.manager import PromptManager
from src.capabilities.session_store import SessionStore
from src.capabilities.tools.registry import ToolRegistry
from src.core.config import Settings, current_settings
from src.core.logging import setup_logger
from src.infrastructure.redis_client import close_redis, get_redis_client, init_redis
from src.infrastructure.database import DatabaseConfig, DatabaseResource
from src.harness.config import HarnessConfig
from src.harness.context import HarnessContext

logger = setup_logger("harness.builder")


@dataclass
class Harness:
    """持有装配后的运行时和可选能力资源。

    同一个资源会被有意暴露在三个边界上：

    - ``Harness`` 字段负责生命周期管理，也方便 API 层直接读取资源状态；
    - ``context.resources`` 按名称暴露资源，服务于能力发现和依赖校验；
    - ``runtime`` 持有热路径依赖，避免每次请求再做 service locator 查询。

    这些字段保存的是同一个 Python 对象引用，不会复制 store、manager、session
    或连接池。额外成本只是几个对象引用，换来的是所有权、发现能力和运行时访问
    三个职责清晰分离。
    """

    context: HarnessContext
    runtime: AgentOrchestrator
    # 与 context/runtime 共用的短期会话记忆实例，由 Harness 负责对外暴露。
    memory_store: MemoryStore
    # 与 context/runtime 共用的长期记忆管理器实例，由 Harness 负责生命周期。
    memory_manager: Mem0MemoryManager | None = None
    prompt_manager: PromptManager | None = None
    session_store: SessionStore | None = None
    database_resource: DatabaseResource | None = None
    _memory_session: AsyncSession | None = None
    _setup_done: bool = False
    _redis_initialized: bool = False

    async def setup(self) -> None:
        if self._setup_done:
            return

        if getattr(self.context.settings, "redis_enabled", False) and not self._redis_initialized:
            await init_redis(
                self.context.settings.redis_url,
                self.context.settings.redis_slave_url,
            )
            self._redis_initialized = True
            redis_client = get_redis_client()
            if redis_client is not None:
                self.context.set_resource("redis", redis_client)

        if self.memory_manager is not None:
            await self.memory_manager.init()
            try:
                from src.capabilities.memory.tasks import memory_scheduler

                await memory_scheduler.start(self.memory_manager)
                self.context.set_resource("memory_scheduler", memory_scheduler)
            except Exception as exc:
                logger.warning(
                    "memory_scheduler_start_failed",
                    extra={"error_type": type(exc).__name__, "error": str(exc)},
                )

        if (
            self.session_store is not None
            and self.database_resource is not None
            and getattr(self.context.settings, "session_store_auto_create", True)
        ):
            await self.database_resource.create_all()

        await self.runtime.setup()
        self._setup_done = True

    async def teardown(self) -> None:
        if self._setup_done:
            await self.runtime.teardown()

        scheduler = self.context.get_resource("memory_scheduler")
        if scheduler is not None:
            try:
                await scheduler.stop()
            except Exception as exc:
                logger.warning(
                    "memory_scheduler_stop_failed",
                    extra={"error_type": type(exc).__name__, "error": str(exc)},
                )

        if self.memory_manager is not None:
            try:
                await self.memory_manager.close()
            except Exception as exc:
                logger.warning(
                    "memory_manager_close_failed",
                    extra={"error_type": type(exc).__name__, "error": str(exc)},
                )
        if self._memory_session is not None:
            try:
                await self._memory_session.close()
            except Exception as exc:
                logger.warning(
                    "memory_session_close_failed",
                    extra={"error_type": type(exc).__name__, "error": str(exc)},
                )
            self._memory_session = None
        if self.database_resource is not None:
            try:
                await self.database_resource.close()
            except Exception as exc:
                logger.warning(
                    "database_resource_close_failed",
                    extra={"error_type": type(exc).__name__, "error": str(exc)},
                )
            self.database_resource = None

        if self._redis_initialized:
            try:
                await close_redis()
            except Exception as exc:
                logger.warning(
                    "redis_close_failed",
                    extra={"error_type": type(exc).__name__, "error": str(exc)},
                )
            self._redis_initialized = False

        self._setup_done = False


class HarnessBuilder:
    """根据 Settings 装配一个完整 Harness。"""

    def __init__(self, settings: Settings):
        self.settings = settings
        self.config = HarnessConfig.from_settings(settings)

    def build(self) -> Harness:
        hitl_config = HITLConfig.from_settings(self.settings)
        checkpoint_config = CheckpointConfig.from_settings(self.settings)
        handoff_config = HandoffConfig.from_settings(self.settings)

        tool_registry = self._build_tool_registry(hitl_config)
        resilience_config = ResilienceConfig.from_env()
        model_router = self._build_model_router(resilience_config)
        capability_registry = CapabilityRegistry()
        self._register_platform_capabilities(capability_registry, resilience_config)

        context = HarnessContext(
            config=self.config,
            settings=self.settings,
            tool_registry=tool_registry,
            model_router=model_router,
            capability_registry=capability_registry,
        )
        context.add_provides("tool_registry")

        database_resource = self._build_database_resource()
        if database_resource is not None:
            context.set_resource("database", database_resource)

        session_store = self._build_session_store(database_resource)
        if session_store is not None:
            context.set_resource("session_store", session_store)

        # 一个短期记忆实例贯穿三个边界：Harness 生命周期/API、Context 能力发现、
        # 运行时请求热路径。这里注册的是同一个对象引用，不会带来额外存储成本。
        memory_store = MemoryStore()
        context.set_resource("memory_store", memory_store)
        memory_manager, memory_session = self._build_memory_manager(session_store)
        if memory_manager is not None:
            # 先把同一个 manager 引用注册进 Context，后续依赖校验和 Runtime 注入
            # 都围绕这一个实例展开。
            context.set_resource("memory_manager", memory_manager)
            if getattr(memory_manager, "embedding_provider", None) is not None:
                context.set_resource("embedding_provider", memory_manager.embedding_provider)
        prompt_manager = self._build_prompt_manager()
        if prompt_manager is not None:
            context.set_resource("prompt_manager", prompt_manager)

        runtime = AgentOrchestrator(
            tool_registry=tool_registry,
            memory_store=memory_store,
            model_router=model_router,
            memory_manager=memory_manager,
            prompt_manager=prompt_manager,
            settings=self.settings,
            capability_registry=capability_registry,
            tracing_disabled=self.config.runtime.tracing_disabled,
            hitl_config=hitl_config if hitl_config.enabled else None,
            checkpoint_config=checkpoint_config if checkpoint_config.enabled else None,
            handoff_config=handoff_config if handoff_config.enabled else None,
        )
        context.validate_dependencies()

        return Harness(
            context=context,
            runtime=runtime,
            memory_store=memory_store,
            memory_manager=memory_manager,
            prompt_manager=prompt_manager,
            session_store=session_store,
            database_resource=database_resource,
            _memory_session=memory_session,
        )

    def _build_tool_registry(self, hitl_config: HITLConfig) -> ToolRegistry:
        registry = ToolRegistry()
        # Harness 默认不注册业务工具；业务方 fork 后可在这里注册自己的工具，
        # 或替换 HarnessBuilder / runtime 以接入业务侧 ToolRegistry。
        if hitl_config.enabled:
            registry.configure_approval_policy(
                require_approval=hitl_config.require_approval_tools,
                auto_approve=hitl_config.auto_approve_tools,
            )
        return registry

    def _build_model_router(self, resilience_config: ResilienceConfig) -> ModelRouter:
        return ModelRouter(
            default_model=self.settings.agent_model_default,
            reasoning_model=self.settings.agent_model_reasoning,
            resilience_config=resilience_config,
        )

    def _register_platform_capabilities(
        self,
        registry: CapabilityRegistry,
        resilience_config: ResilienceConfig,
    ) -> None:
        registry.register(ModelRouterCapability())
        registry.register(ModelResilienceCapability(enabled=resilience_config.enabled))
        registry.register(AuthCapability(enabled=self.settings.auth_enabled))
        registry.register(
            RateLimitCapability(
                enabled=self.settings.rate_limit_enabled,
                key_strategy=getattr(self.settings, "rate_limit_key_strategy", "principal"),
            )
        )
        registry.register(ObservabilityCapability.from_settings(self.settings))

    def _build_database_resource(self) -> DatabaseResource | None:
        needs_database = bool(
            getattr(self.settings, "mysql_enabled", False)
            or getattr(self.settings, "session_store_enabled", False)
        )
        if not needs_database:
            return None
        if not self.settings.database_url:
            raise ValueError(
                "MYSQL_ENABLED=true or SESSION_STORE_ENABLED=true requires SESSION_STORE_DATABASE_* settings"
            )
        return DatabaseResource(DatabaseConfig.from_settings(self.settings))

    def _build_session_store(
        self,
        database_resource: DatabaseResource | None,
    ) -> SessionStore | None:
        if not getattr(self.settings, "session_store_enabled", False):
            return None
        if database_resource is None:
            raise ValueError("SESSION_STORE_ENABLED=true requires a configured database resource")
        return SessionStore(database_resource.session)

    def _build_memory_manager(
        self,
        session_store: SessionStore | None = None,
    ) -> tuple[Mem0MemoryManager | None, AsyncSession | None]:
        memory_required = any(
            (
                getattr(self.settings, "memory_short_term_enabled", False),
                getattr(self.settings, "memory_session_summary_enabled", False),
                getattr(self.settings, "memory_long_term_enabled", False),
            )
        )
        if not memory_required:
            return None, None
        if getattr(self.settings, "memory_long_term_enabled", False):
            provider = getattr(self.settings, "memory_long_term_provider", "mem0").strip().lower()
            if provider != "mem0":
                raise ValueError(f"Unsupported MEMORY_LONG_TERM_PROVIDER: {provider}")
        redis_client = get_redis_client() if getattr(self.settings, "redis_enabled", False) else None
        return Mem0MemoryManager(
            self.settings,
            redis_client=redis_client,
            session_store=session_store,
        ), None

    def _build_prompt_manager(self) -> PromptManager | None:
        if not self.settings.prompt_enabled:
            return None
        try:
            return build_prompt_manager(self.settings)
        except Exception as exc:
            logger.error(
                "prompt_manager_build_failed",
                extra={"error_type": type(exc).__name__, "error": str(exc)},
            )
            return None


def build_harness(settings: Settings | None = None) -> Harness:
    return HarnessBuilder(settings or current_settings).build()
