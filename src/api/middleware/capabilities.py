"""Protocol-layer capability markers for scaffold generation."""

from __future__ import annotations

from dataclasses import replace

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
        depends_on=("principal",),
        provides=("rate_limit",),
        install_order=2,
        tags=("user_dimension",),
    )

    def __init__(self, enabled: bool, key_strategy: str = "principal") -> None:
        self._enabled = enabled
        if key_strategy in {"ip", "principal_or_ip"}:
            self.manifest = replace(
                type(self).manifest,
                depends_on=(),
                tags=("compatibility_key_strategy",),
            )

    def is_enabled(self) -> bool:
        return self._enabled
