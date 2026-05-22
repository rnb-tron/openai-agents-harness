from types import SimpleNamespace

from src.harness.config import HarnessConfig


def test_harness_config_projects_capability_switches():
    settings = SimpleNamespace(
        observability_enabled=True,
        memory_enabled=True,
        compression_enabled=False,
        prompt_enabled=True,
        auth_enabled=False,
        rate_limit_enabled=True,
    )

    config = HarnessConfig.from_settings(settings)

    assert config.runtime.tracing_disabled is False
    assert config.capabilities.memory is True
    assert config.capabilities.context_compression is False
    assert config.capabilities.prompt is True
    assert config.capabilities.auth is False
    assert config.capabilities.rate_limit is True
