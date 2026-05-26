"""Machine-readable capability catalog for scaffold planning."""

from __future__ import annotations

from src.api.middleware.capabilities import AuthCapability, RateLimitCapability
from src.capabilities.advanced_agents import (
    CheckpointCapability,
    HandoffCapability,
    HITLCapability,
)
from src.capabilities.context_compression import ContextCompressionCapability
from src.capabilities.memory.capability import (
    LongTermMemoryCapability,
    MemoryCapability,
    VectorSearchCapability,
)
from src.capabilities.model_routing.capabilities import (
    ModelResilienceCapability,
    ModelRouterCapability,
)
from src.capabilities.observability import ObservabilityCapability
from src.capabilities.prompt import PromptCapability
from src.harness.manifest import CapabilityKind, CapabilityManifest


TOOL_REGISTRY_MANIFEST = CapabilityManifest(
    name="tool_registry",
    kind=CapabilityKind.RUNTIME,
    config_section="tools",
    provides=("tool_registry",),
    install_order=4,
    tags=("required", "builder_resource"),
)

MEMORY_MANAGER_MANIFEST = CapabilityManifest(
    name="memory_manager",
    kind=CapabilityKind.RESOURCE,
    config_section="memory",
    depends_on=("database",),
    provides=("memory_manager",),
    install_order=19,
    tags=("builder_resource",),
)

EMBEDDING_PROVIDER_MANIFEST = CapabilityManifest(
    name="embedding_provider",
    kind=CapabilityKind.RESOURCE,
    config_section="memory",
    depends_on=("embedding_api",),
    provides=("embedding_provider",),
    install_order=20,
    tags=("builder_resource",),
)


def available_capability_manifests() -> list[CapabilityManifest]:
    """Return manifests for capabilities the current Harness can assemble."""
    manifests = [
        TOOL_REGISTRY_MANIFEST,
        AuthCapability.manifest,
        RateLimitCapability.manifest,
        ObservabilityCapability.manifest,
        ModelRouterCapability.manifest,
        ModelResilienceCapability.manifest,
        PromptCapability.manifest,
        MEMORY_MANAGER_MANIFEST,
        EMBEDDING_PROVIDER_MANIFEST,
        MemoryCapability.manifest,
        LongTermMemoryCapability.manifest,
        VectorSearchCapability.manifest,
        ContextCompressionCapability.manifest,
        CheckpointCapability.manifest,
        HandoffCapability.manifest,
        HITLCapability.manifest,
    ]
    return sorted(manifests, key=lambda item: (item.install_order, item.name))


def validate_capability_selection(selected: list[str]) -> dict[str, object]:
    """Resolve a platform capability selection without assembling a runtime."""
    manifests = available_capability_manifests()
    by_name = {manifest.name: manifest for manifest in manifests}
    requested = set(selected)
    unknown = sorted(name for name in requested if name not in by_name)
    resolved = {name for name in requested if name in by_name}
    required = {
        manifest.name for manifest in manifests if "required" in manifest.tags
    }
    resolved.update(required)

    providers: dict[str, list[str]] = {}
    for manifest in manifests:
        for provided in {manifest.name, *manifest.provides}:
            providers.setdefault(provided, []).append(manifest.name)

    external_by_resource: dict[str, set[str]] = {}
    unresolved: dict[tuple[str, str], dict[str, object]] = {}
    changed = True
    while changed:
        changed = False
        provided = {
            provided
            for name in resolved
            for provided in (name, *by_name[name].provides)
        }
        for name in list(resolved):
            for dependency in by_name[name].depends_on:
                if dependency in provided:
                    continue
                provider_names = sorted(set(providers.get(dependency, [])))
                if len(provider_names) == 1:
                    provider = provider_names[0]
                    if provider not in resolved:
                        resolved.add(provider)
                        changed = True
                    continue
                if not provider_names:
                    external_by_resource.setdefault(dependency, set()).add(name)
                    continue
                unresolved[(name, dependency)] = {
                    "capability": name,
                    "requires": dependency,
                    "provider_capabilities": provider_names,
                }

    ordered_resolved = [
        manifest.name for manifest in manifests if manifest.name in resolved
    ]
    requested_known = {name for name in requested if name in by_name}
    auto_included = [
        name for name in ordered_resolved if name not in requested_known
    ]
    external_requirements = [
        {
            "resource": resource,
            "required_by": sorted(required_by),
        }
        for resource, required_by in sorted(external_by_resource.items())
    ]
    return {
        "version": 1,
        "requested_selection": sorted(requested),
        "resolved_selection": ordered_resolved,
        "auto_included": auto_included,
        "unknown_capabilities": unknown,
        "unresolved_dependencies": [
            unresolved[key] for key in sorted(unresolved)
        ],
        "external_requirements": external_requirements,
        "valid": not unknown and not unresolved,
    }
