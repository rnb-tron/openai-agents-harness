"""Harness builder and lifecycle owner."""

from __future__ import annotations

from dataclasses import dataclass
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.middleware.capabilities import AuthCapability, RateLimitCapability
from src.application.orchestration.agent_runtime import AgentOrchestrator
from src.capabilities.advanced_agents import CheckpointConfig, HandoffConfig, HITLConfig
from src.capabilities.memory.manager import MemoryManager
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
from src.capabilities.tools.registry import ToolRegistry
from src.core.config import Settings, current_settings
from src.core.logging import setup_logger
from src.infrastructure.database import DatabaseConfig, DatabaseResource
from src.harness.config import HarnessConfig
from src.harness.context import HarnessContext

logger = setup_logger("harness.builder")


@dataclass
class Harness:
    """Owns the assembled runtime and optional capability resources."""

    context: HarnessContext
    runtime: AgentOrchestrator
    memory_store: MemoryStore
    memory_manager: MemoryManager | None = None
    prompt_manager: PromptManager | None = None
    database_resource: DatabaseResource | None = None
    _memory_session: AsyncSession | None = None
    _setup_done: bool = False

    async def setup(self) -> None:
        if self._setup_done:
            return

        if self.memory_manager is not None:
            await self.memory_manager.init()
            self.context.set_resource("memory_manager", self.memory_manager)
            try:
                from src.capabilities.memory.tasks import memory_scheduler

                await memory_scheduler.start(self.memory_manager)
                self.context.set_resource("memory_scheduler", memory_scheduler)
            except Exception as exc:
                logger.warning(
                    "memory_scheduler_start_failed",
                    extra={"error_type": type(exc).__name__, "error": str(exc)},
                )

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
            await self.memory_manager.close()
        if self._memory_session is not None:
            await self._memory_session.close()
            self._memory_session = None
        if self.database_resource is not None:
            await self.database_resource.close()
            self.database_resource = None

        self._setup_done = False


class HarnessBuilder:
    """Builds a scaffold-friendly harness from settings."""

    def __init__(self, settings: Settings):
        self.settings = settings
        self.config = HarnessConfig.from_settings(settings)

    def build(self) -> Harness:
        # Tool Registry
        tool_registry = ToolRegistry()
        # Register default tools
        tool_registry.register_defaults()
        # Configure HITL
        hitl_config = HITLConfig.from_settings(self.settings)
        checkpoint_config = CheckpointConfig.from_settings(self.settings)
        handoff_config = HandoffConfig.from_settings(self.settings)
        if hitl_config.enabled:
            tool_registry.configure_approval_policy(
                require_approval=hitl_config.require_approval_tools,
                auto_approve=hitl_config.auto_approve_tools,
            )

        # Resilience Configuration
        resilience_config = ResilienceConfig.from_env()
        # Model Router
        model_router = ModelRouter(
            default_model=self.settings.agent_model_default,
            reasoning_model=self.settings.agent_model_reasoning,
            resilience_config=resilience_config,
        )
        capability_registry = CapabilityRegistry()
        capability_registry.register(ModelRouterCapability())
        capability_registry.register(
            ModelResilienceCapability(enabled=resilience_config.enabled)
        )
        capability_registry.register(AuthCapability(enabled=self.settings.auth_enabled))
        capability_registry.register(
            RateLimitCapability(enabled=self.settings.rate_limit_enabled)
        )
        capability_registry.register(
            ObservabilityCapability(enabled=self.settings.observability_enabled)
        )
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

        memory_store = MemoryStore()
        context.set_resource("memory_store", memory_store)
        memory_manager, memory_session = self._build_memory_manager(database_resource)
        if memory_manager is not None:
            context.set_resource("memory_manager", memory_manager)
            if memory_manager.embedding_provider is not None:
                context.set_resource(
                    "embedding_provider", memory_manager.embedding_provider
                )
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
            database_resource=database_resource,
            _memory_session=memory_session,
        )

    def _build_database_resource(self) -> DatabaseResource | None:
        needs_database = self.settings.database_enabled or self.settings.memory_enabled
        if not needs_database:
            return None
        if not self.settings.database_url:
            if self.settings.database_enabled:
                raise ValueError("DATABASE_ENABLED=true requires DATABASE_URL")
            return None
        return DatabaseResource(DatabaseConfig.from_settings(self.settings))

    def _build_memory_manager(
        self,
        database_resource: DatabaseResource | None,
    ) -> tuple[MemoryManager | None, AsyncSession | None]:
        if not self.settings.memory_enabled:
            return None, None
        if database_resource is None:
            logger.warning("memory_enabled_without_database_url")
            return None, None

        session = database_resource.session()
        return MemoryManager(self.settings, session), session

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
