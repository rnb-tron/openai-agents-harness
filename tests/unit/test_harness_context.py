from types import SimpleNamespace

import pytest

from src.capabilities.plugin import Capability, CapabilityRegistry
from src.capabilities.tools import ToolRegistry
from src.capabilities.model_routing.router import ModelRouter
from src.harness.config import HarnessConfig
from src.harness.context import HarnessContext
from src.harness.manifest import CapabilityKind, CapabilityManifest


class _ManifestCapability(Capability):
    def __init__(
        self,
        name: str,
        *,
        depends_on: tuple[str, ...] = (),
        provides: tuple[str, ...] = (),
        enabled: bool = True,
    ):
        self.name = name
        self.manifest = CapabilityManifest(
            name=name,
            kind=CapabilityKind.RUNTIME,
            depends_on=depends_on,
            provides=provides,
        )
        self._enabled = enabled

    def is_enabled(self) -> bool:
        return self._enabled


def _settings():
    return SimpleNamespace(
        observability_enabled=False,
        memory_short_term_enabled=False,
        memory_session_summary_enabled=False,
        memory_long_term_enabled=False,
        compression_enabled=False,
        prompt_enabled=False,
        auth_enabled=False,
        rate_limit_enabled=False,
    )


def _context(registry: CapabilityRegistry) -> HarnessContext:
    settings = _settings()
    return HarnessContext(
        config=HarnessConfig.from_settings(settings),
        settings=settings,
        tool_registry=ToolRegistry(),
        model_router=ModelRouter(),
        capability_registry=registry,
    )


def test_context_collects_provided_names_from_resources_and_capabilities():
    registry = CapabilityRegistry()
    registry.register(
        _ManifestCapability(
            "memory",
            depends_on=("tool_registry",),
            provides=("conversation_context",),
        )
    )
    ctx = _context(registry)
    ctx.add_provides("tool_registry")

    assert ctx.provided_names() == {
        "tool_registry",
        "memory",
        "conversation_context",
    }
    assert ctx.missing_dependencies() == {}


def test_context_reports_missing_dependencies():
    registry = CapabilityRegistry()
    registry.register(_ManifestCapability("rag", depends_on=("vector_search",)))
    ctx = _context(registry)

    assert ctx.missing_dependencies() == {"rag": ["vector_search"]}
    with pytest.raises(ValueError, match="rag"):
        ctx.validate_dependencies()


def test_context_ignores_disabled_capabilities_by_default():
    registry = CapabilityRegistry()
    registry.register(
        _ManifestCapability(
            "disabled_rag",
            depends_on=("vector_search",),
            enabled=False,
        )
    )
    ctx = _context(registry)

    assert ctx.missing_dependencies() == {}
    assert ctx.missing_dependencies(enabled_only=False) == {"disabled_rag": ["vector_search"]}
