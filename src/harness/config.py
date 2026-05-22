"""Structured harness config facade over the existing Settings object."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class RuntimeConfig:
    """Runtime-level switches derived from capability choices."""

    tracing_disabled: bool = False


@dataclass(frozen=True)
class CapabilitySwitches:
    memory: bool
    context_compression: bool
    prompt: bool
    observability: bool
    auth: bool
    rate_limit: bool


@dataclass(frozen=True)
class HarnessConfig:
    """A lightweight, scaffold-friendly view of application settings."""

    settings: Any
    runtime: RuntimeConfig
    capabilities: CapabilitySwitches

    @classmethod
    def from_settings(cls, settings: Any) -> "HarnessConfig":
        return cls(
            settings=settings,
            runtime=RuntimeConfig(
                tracing_disabled=not settings.observability_enabled,
            ),
            capabilities=CapabilitySwitches(
                memory=settings.memory_enabled,
                context_compression=settings.compression_enabled,
                prompt=settings.prompt_enabled,
                observability=settings.observability_enabled,
                auth=settings.auth_enabled,
                rate_limit=settings.rate_limit_enabled,
            ),
        )
