"""FastAPI plugin for request tracing and observability lifecycle."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Optional

from fastapi import FastAPI

from src.capabilities.observability.config import ObservabilityConfig
from src.capabilities.observability.middleware import observability_middleware
from src.capabilities.observability.tracer import TracerManager
from src.core.logging import setup_logger

logger = setup_logger("observability.plugin")

InitFn = Callable[[Optional[ObservabilityConfig]], Awaitable[TracerManager]]
ShutdownFn = Callable[[], Awaitable[None]]


class ObservabilityPlugin:
    """Protocol/resource plugin for OpenTelemetry/Langfuse observability."""

    name = "observability"

    def __init__(
        self,
        *,
        enabled: bool = False,
        config: ObservabilityConfig | None = None,
        init_fn: InitFn | None = None,
        shutdown_fn: ShutdownFn | None = None,
    ) -> None:
        self._enabled = enabled
        self._config = config
        self._init_fn = init_fn
        self._shutdown_fn = shutdown_fn
        self._initialized = False

    @classmethod
    def from_settings(cls, settings) -> "ObservabilityPlugin":
        enabled = bool(getattr(settings, "observability_enabled", False))
        if not enabled:
            return cls(enabled=False)
        config = ObservabilityConfig.from_env()
        config.enabled = enabled
        config.environment = getattr(settings, "app_profile", config.environment)
        config.application = getattr(settings, "app_name", config.application)
        return cls(enabled=True, config=config)

    def is_enabled(self) -> bool:
        return self._enabled

    def install(self, app: FastAPI) -> None:
        if not self._enabled:
            return
        app.middleware("http")(observability_middleware)
        logger.info("observability_middleware_installed")

    async def setup(self) -> None:
        if not self._enabled:
            return
        init_fn = self._init_fn
        if init_fn is None:
            from src.capabilities.observability import init_observability

            init_fn = init_observability
        await init_fn(self._config)
        self._initialized = True
        logger.info("observability_plugin_initialized")

    async def teardown(self) -> None:
        if not self._enabled or not self._initialized:
            return
        shutdown_fn = self._shutdown_fn
        if shutdown_fn is None:
            from src.capabilities.observability import shutdown_observability

            shutdown_fn = shutdown_observability
        await shutdown_fn()
        self._initialized = False
        logger.info("observability_plugin_shutdown")
