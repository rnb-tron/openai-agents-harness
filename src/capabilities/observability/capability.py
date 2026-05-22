"""Observability capability marker."""

from __future__ import annotations

from src.capabilities.plugin import Capability
from src.harness.manifest import CapabilityKind, CapabilityManifest


class ObservabilityCapability(Capability):
    name = "observability"
    manifest = CapabilityManifest(
        name="observability",
        kind=CapabilityKind.RESOURCE,
        config_section="observability",
        provides=("observability", "tracing", "log_correlation"),
        install_order=3,
        tags=("langfuse", "opentelemetry"),
    )

    def __init__(self, enabled: bool) -> None:
        self._enabled = enabled

    def is_enabled(self) -> bool:
        return self._enabled
