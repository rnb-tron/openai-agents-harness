"""Harness-owned observability runtime capability."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Optional

from src.capabilities.plugin import Capability
from src.harness.manifest import CapabilityKind, CapabilityManifest

from .config import ObservabilityConfig
from .tracer import TracerManager

InitFn = Callable[[Optional[ObservabilityConfig]], Awaitable[TracerManager]]
ShutdownFn = Callable[[], Awaitable[None]]


class ObservabilityCapability(Capability):
    """Own Langfuse/OpenTelemetry lifecycle for runtime execution."""

    name = "observability"
    manifest = CapabilityManifest(
        name="observability",
        kind=CapabilityKind.RUNTIME,
        config_section="observability",
        provides=("langfuse",),
        install_order=3,
        tags=("langfuse", "opentelemetry"),
    )

    def __init__(
        self,
        enabled: bool,
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
    def from_settings(cls, settings) -> "ObservabilityCapability":
        enabled = bool(getattr(settings, "observability_enabled", False))
        if not enabled:
            return cls(enabled=False)
        config = ObservabilityConfig.from_env()
        config.enabled = True
        config.environment = getattr(settings, "app_profile", config.environment)
        config.application = getattr(settings, "app_name", config.application)
        return cls(enabled=True, config=config)

    def is_enabled(self) -> bool:
        return self._enabled

    async def setup(self) -> None:
        if not self._enabled:
            return
        init_fn = self._init_fn
        if init_fn is None:
            from src.capabilities.observability import init_observability

            init_fn = init_observability
        await init_fn(self._config)
        self._initialized = True

    async def teardown(self) -> None:
        if not self._enabled or not self._initialized:
            return
        shutdown_fn = self._shutdown_fn
        if shutdown_fn is None:
            from src.capabilities.observability import shutdown_observability

            shutdown_fn = shutdown_observability
        await shutdown_fn()
        self._initialized = False
