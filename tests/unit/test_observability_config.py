from unittest.mock import ANY, MagicMock, patch

import pytest

from src.capabilities.observability.config import (
    DEFAULT_LANGFUSE_BASE_URL,
    ObservabilityConfig,
)
from src.capabilities.observability.tracer import TracerManager
from src.capabilities.observability.tracer import _mask_pii


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
        timeout=30,
        tracing_enabled=False,
        flush_at=100,
        flush_interval=5.0,
        environment="development",
        release="0.1.0",
        sample_rate=1.0,
        mask=ANY,
    )


def test_langfuse_mask_redacts_common_sensitive_values():
    masked = _mask_pii(
        data={
            "email": "alice@example.com",
            "authorization": "Bearer abc.def.ghi",
            "nested": ["phone +86 138 0013 8000", "sk_test_123456789"],
        }
    )

    assert masked["email"] != "alice@example.com"
    assert masked["authorization"] == "[redacted]"
    assert masked["nested"][0] == "phone [phone]"
    assert masked["nested"][1] == "[secret]"
