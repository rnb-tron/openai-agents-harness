"""Shared harness context for resources, registries, and runtime state."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from src.capabilities.model_routing.router import ModelRouter
from src.capabilities.plugin import CapabilityRegistry
from src.capabilities.tools.registry import ToolRegistry
from src.core.config import Settings
from src.harness.config import HarnessConfig
from src.harness.manifest import CapabilityManifest


@dataclass
class HarnessContext:
    config: HarnessConfig
    settings: Settings
    tool_registry: ToolRegistry
    model_router: ModelRouter
    capability_registry: CapabilityRegistry
    resources: dict[str, Any] = field(default_factory=dict)
    provides: set[str] = field(default_factory=set)

    def set_resource(self, name: str, value: Any) -> None:
        self.resources[name] = value
        self.provides.add(name)

    def get_resource(self, name: str, default: Any = None) -> Any:
        return self.resources.get(name, default)

    def add_provides(self, *names: str) -> None:
        self.provides.update(name for name in names if name)

    def capability_manifests(self, *, enabled_only: bool = True) -> list[CapabilityManifest]:
        capabilities = (
            self.capability_registry.enabled
            if enabled_only
            else self.capability_registry.all
        )
        return [cap.manifest for cap in capabilities]

    def capability_snapshot(self, *, enabled_only: bool = False) -> dict[str, Any]:
        """Return a scaffold-generator friendly view of registered capabilities."""
        capabilities = (
            self.capability_registry.enabled
            if enabled_only
            else self.capability_registry.all
        )
        items = []
        for cap in capabilities:
            manifest = cap.manifest
            items.append(
                {
                    "name": manifest.name,
                    "kind": manifest.kind.value,
                    "enabled": cap.is_enabled(),
                    "config_section": manifest.config_section,
                    "depends_on": list(manifest.depends_on),
                    "provides": list(manifest.provides),
                    "install_order": manifest.install_order,
                    "tags": list(manifest.tags),
                }
            )

        items.sort(key=lambda item: (item["install_order"], item["name"]))
        return {
            "capabilities": items,
            "provided": sorted(self.provided_names(enabled_only=True)),
            "missing_dependencies": self.missing_dependencies(enabled_only=True),
        }

    def provided_names(self, *, enabled_only: bool = True) -> set[str]:
        provided = set(self.provides)
        for manifest in self.capability_manifests(enabled_only=enabled_only):
            provided.add(manifest.name)
            provided.update(manifest.provides)
        return provided

    def missing_dependencies(self, *, enabled_only: bool = True) -> dict[str, list[str]]:
        provided = self.provided_names(enabled_only=enabled_only)
        missing: dict[str, list[str]] = {}
        for manifest in self.capability_manifests(enabled_only=enabled_only):
            deps = [name for name in manifest.depends_on if name not in provided]
            if deps:
                missing[manifest.name] = deps
        return missing

    def validate_dependencies(self, *, enabled_only: bool = True) -> None:
        missing = self.missing_dependencies(enabled_only=enabled_only)
        if missing:
            detail = ", ".join(
                f"{cap}: {deps}" for cap, deps in sorted(missing.items())
            )
            raise ValueError(f"Missing capability dependencies: {detail}")
