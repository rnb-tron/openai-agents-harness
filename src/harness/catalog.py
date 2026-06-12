"""Harness 支持的机器可读能力目录。"""

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
    kind=CapabilityKind.RUNTIME,
    config_section="memory",
    provides=("memory_manager",),
    install_order=19,
    tags=("builder_resource", "mem0"),
)

DATABASE_MANIFEST = CapabilityManifest(
    name="database",
    kind=CapabilityKind.RUNTIME,
    config_section="mysql",
    provides=("database",),
    install_order=17,
    tags=("builder_resource", "mysql"),
)

SESSION_STORE_MANIFEST = CapabilityManifest(
    name="session_store",
    kind=CapabilityKind.RUNTIME,
    config_section="session_store",
    provides=("session_store", "chat_transcripts"),
    install_order=18,
    tags=("builder_resource", "mysql"),
)


def available_capability_manifests() -> list[CapabilityManifest]:
    """返回当前 Harness 能装配的能力清单。"""
    manifests = [
        TOOL_REGISTRY_MANIFEST,
        AuthCapability.manifest,
        RateLimitCapability.manifest,
        ObservabilityCapability.manifest,
        ModelRouterCapability.manifest,
        ModelResilienceCapability.manifest,
        PromptCapability.manifest,
        DATABASE_MANIFEST,
        SESSION_STORE_MANIFEST,
        MEMORY_MANAGER_MANIFEST,
        MemoryCapability.manifest,
        LongTermMemoryCapability.manifest,
        VectorSearchCapability.manifest,
        ContextCompressionCapability.manifest,
        CheckpointCapability.manifest,
        HandoffCapability.manifest,
        HITLCapability.manifest,
    ]
    return sorted(manifests, key=lambda item: (item.install_order, item.name))
