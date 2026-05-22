"""Capability metadata used by the harness builder.

The manifest is intentionally small. It gives the future scaffold generator
enough structure to reason about capability composition without forcing every
capability to adopt a heavy plugin framework immediately.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class CapabilityKind(str, Enum):
    RUNTIME = "runtime"
    PROTOCOL = "protocol"
    RESOURCE = "resource"


@dataclass(frozen=True)
class CapabilityManifest:
    name: str
    kind: CapabilityKind
    config_section: str = ""
    depends_on: tuple[str, ...] = ()
    provides: tuple[str, ...] = ()
    install_order: int = 100
    tags: tuple[str, ...] = field(default_factory=tuple)
