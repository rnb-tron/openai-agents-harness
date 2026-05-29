import asyncio

from src.capabilities.plugin import Capability, CapabilityRegistry, RunContext, RunPhase
from src.harness.manifest import CapabilityKind, CapabilityManifest


def test_capability_kind_uses_lifecycle_responsibility_only():
    assert {kind.value for kind in CapabilityKind} == {
        "runtime",
        "protocol",
        "governance",
    }


class _RecorderCapability(Capability):
    def __init__(self, name: str, order: int, calls: list[str]):
        self.name = name
        self.manifest = CapabilityManifest(
            name=name,
            kind=CapabilityKind.RUNTIME,
            install_order=order,
        )
        self._calls = calls

    async def before_run(self, ctx: RunContext) -> None:
        self._calls.append(self.name)


def test_capability_registry_dispatches_by_manifest_order():
    calls: list[str] = []
    registry = CapabilityRegistry()
    registry.register(_RecorderCapability("late", 90, calls))
    registry.register(_RecorderCapability("early", 10, calls))

    asyncio.run(
        registry.dispatch(
            RunPhase.BEFORE_RUN,
            RunContext(session_id="s1", user_input="hello", enriched_input="hello"),
        )
    )

    assert calls == ["early", "late"]
