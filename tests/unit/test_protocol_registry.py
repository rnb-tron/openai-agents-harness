from unittest.mock import AsyncMock

import pytest

from src.api.middleware.registry import ProtocolPluginRegistry


class _FailingPlugin:
    name = "failure"

    def is_enabled(self):
        return True

    def install(self, app):
        return None

    async def setup(self):
        raise RuntimeError("setup unavailable")

    async def teardown(self):
        return None


@pytest.mark.asyncio
async def test_protocol_registry_raises_enabled_plugin_setup_failure():
    registry = ProtocolPluginRegistry()
    registry.register(_FailingPlugin())

    with pytest.raises(RuntimeError, match="setup unavailable"):
        await registry.setup_all()
