"""FastAPI adapter for request tracing middleware."""

from __future__ import annotations

from fastapi import FastAPI

from src.capabilities.observability.middleware import observability_middleware
from src.core.logging import setup_logger

logger = setup_logger("observability.plugin")


class ObservabilityPlugin:
    """Protocol adapter only; Harness owns tracing resource lifecycle."""

    name = "observability"

    def __init__(
        self,
        *,
        enabled: bool = False,
    ) -> None:
        self._enabled = enabled

    @classmethod
    def from_settings(cls, settings) -> "ObservabilityPlugin":
        enabled = bool(getattr(settings, "observability_enabled", False))
        return cls(enabled=enabled)

    def is_enabled(self) -> bool:
        return self._enabled

    def install(self, app: FastAPI) -> None:
        if not self._enabled:
            return
        app.middleware("http")(observability_middleware)
        logger.info("observability_middleware_installed")

    async def setup(self) -> None:
        return None

    async def teardown(self) -> None:
        return None
