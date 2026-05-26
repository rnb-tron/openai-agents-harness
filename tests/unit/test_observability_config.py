from unittest.mock import MagicMock, patch

import pytest

from src.capabilities.observability.config import (
    DEFAULT_LANGFUSE_BASE_URL,
    ObservabilityConfig,
)
from src.capabilities.observability.tracer import TracerManager


def test_observability_config_defaults_to_internal_langfuse_platform(monkeypatch):
    monkeypatch.delenv("LANGFUSE_BASE_URL", raising=False)

    assert ObservabilityConfig().base_url == DEFAULT_LANGFUSE_BASE_URL
    assert ObservabilityConfig.from_env().base_url == DEFAULT_LANGFUSE_BASE_URL


@pytest.mark.asyncio
async def test_tracer_passes_configured_langfuse_endpoint_to_sdk():
    client = MagicMock()
    client.auth_check.return_value = True
    config = ObservabilityConfig(
        public_key="pk-test",
        secret_key="sk-test",
        base_url="http://agent-otel-test.ke.com",
        enabled=True,
        tracing_enabled=False,
    )

    with patch(
        "src.capabilities.observability.tracer.Langfuse",
        return_value=client,
    ) as langfuse:
        await TracerManager(config).initialize()

    langfuse.assert_called_once_with(
        public_key="pk-test",
        secret_key="sk-test",
        base_url="http://agent-otel-test.ke.com",
        tracing_enabled=False,
    )
