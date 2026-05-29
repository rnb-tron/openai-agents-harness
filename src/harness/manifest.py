"""Harness builder 使用的能力元数据。

Manifest 刻意保持很小：它给未来脚手架生成器足够的信息来推导能力组合，
同时不强迫每个能力立即接入沉重的插件框架。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class CapabilityKind(str, Enum):
    RUNTIME = "runtime"
    PROTOCOL = "protocol"
    GOVERNANCE = "governance"


@dataclass(frozen=True)
class CapabilityManifest:
    name: str
    kind: CapabilityKind
    config_section: str = ""
    depends_on: tuple[str, ...] = ()
    provides: tuple[str, ...] = ()
    install_order: int = 100
    tags: tuple[str, ...] = field(default_factory=tuple)
