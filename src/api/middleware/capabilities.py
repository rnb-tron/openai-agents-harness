"""Protocol-layer capability markers for scaffold generation."""

from __future__ import annotations

from src.capabilities.plugin import Capability
from src.harness.manifest import CapabilityKind, CapabilityManifest


class AuthCapability(Capability):
    name = "auth"
    manifest = CapabilityManifest(
        name="auth",
        kind=CapabilityKind.PROTOCOL,
        config_section="auth",
        provides=("principal", "auth"),
        install_order=1,
    )

    def __init__(self, enabled: bool) -> None:
        self._enabled = enabled

    def is_enabled(self) -> bool:
        return self._enabled


class RateLimitCapability(Capability):
    name = "rate_limit"
    manifest = CapabilityManifest(
        name="rate_limit",
        kind=CapabilityKind.PROTOCOL,
        config_section="rate_limit",
        provides=("rate_limit",),
        install_order=2,
        tags=("uses_principal_when_available",),
    )

    def __init__(self, enabled: bool) -> None:
        self._enabled = enabled

    def is_enabled(self) -> bool:
        return self._enabled
