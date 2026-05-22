"""Capability markers for model selection and resilience."""

from __future__ import annotations

from src.capabilities.plugin import Capability
from src.harness.manifest import CapabilityKind, CapabilityManifest


class ModelRouterCapability(Capability):
    """Marker for model selection capability."""

    name = "model_router"
    manifest = CapabilityManifest(
        name="model_router",
        kind=CapabilityKind.RUNTIME,
        config_section="model_routing",
        provides=("model_router", "model_selection"),
        install_order=5,
        tags=("required",),
    )


class ModelResilienceCapability(Capability):
    """Marker for retry/fallback/timeout execution policy."""

    name = "model_resilience"
    manifest = CapabilityManifest(
        name="model_resilience",
        kind=CapabilityKind.RUNTIME,
        config_section="model_routing",
        depends_on=("model_router",),
        provides=("model_resilience",),
        install_order=6,
    )

    def __init__(self, enabled: bool) -> None:
        self._enabled = enabled

    def is_enabled(self) -> bool:
        return self._enabled
