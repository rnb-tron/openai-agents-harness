"""基于现有 Settings 的 Harness 结构化配置外观。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class RuntimeConfig:
    """运行时通用开关。"""

    tracing_disabled: bool = False


@dataclass(frozen=True)
class CapabilitySwitches:
    memory: bool
    context_compression: bool
    prompt: bool
    hitl: bool
    checkpoint: bool
    handoff: bool
    observability: bool
    auth: bool
    rate_limit: bool


@dataclass(frozen=True)
class HarnessConfig:
    """基于 Settings 的轻量应用配置视图。"""

    settings: Any
    runtime: RuntimeConfig
    capabilities: CapabilitySwitches

    @classmethod
    def from_settings(cls, settings: Any) -> "HarnessConfig":
        memory_capability_enabled = (
            settings.memory_short_term_enabled
            or settings.memory_session_summary_enabled
            or settings.memory_long_term_enabled
        )
        return cls(
            settings=settings,
            runtime=RuntimeConfig(
                tracing_disabled=not settings.observability_enabled,
            ),
            capabilities=CapabilitySwitches(
                memory=memory_capability_enabled,
                context_compression=settings.compression_enabled,
                prompt=settings.prompt_enabled,
                hitl=getattr(settings, "hitl_enabled", False),
                checkpoint=getattr(settings, "checkpoint_enabled", False),
                handoff=getattr(settings, "handoff_enabled", False),
                observability=settings.observability_enabled,
                auth=settings.auth_enabled,
                rate_limit=settings.rate_limit_enabled,
            ),
        )
