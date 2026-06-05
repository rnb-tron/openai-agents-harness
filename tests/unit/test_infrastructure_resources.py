from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from src.infrastructure.database import DatabaseConfig, DatabaseResource
from src.infrastructure.http_client import HttpClientConfig


def test_database_config_exposes_connection_pool_settings():
    config = DatabaseConfig.from_settings(
        SimpleNamespace(
            database_url="postgresql+asyncpg://agent:secret@localhost/app",
            debug=True,
            database_pool_size=7,
            database_max_overflow=11,
            database_pool_timeout_seconds=12.5,
            database_pool_recycle_seconds=900,
            database_pool_pre_ping=False,
        )
    )

    assert config.pool_size == 7
    assert config.max_overflow == 11
    assert config.pool_timeout_seconds == 12.5
    assert config.pool_recycle_seconds == 900
    assert config.pool_pre_ping is False


def test_database_resource_passes_configured_pool_values_to_engine():
    fake_engine = MagicMock()
    with patch(
        "src.infrastructure.database.create_async_engine",
        return_value=fake_engine,
    ) as create_engine:
        DatabaseResource(
            DatabaseConfig(
                url="postgresql+asyncpg://agent:secret@localhost/app",
                pool_size=7,
                max_overflow=11,
                pool_timeout_seconds=12.5,
                pool_recycle_seconds=900,
                pool_pre_ping=False,
            )
        )

    assert create_engine.call_args.kwargs["pool_size"] == 7
    assert create_engine.call_args.kwargs["max_overflow"] == 11
    assert create_engine.call_args.kwargs["pool_timeout"] == 12.5
    assert create_engine.call_args.kwargs["pool_recycle"] == 900
    assert create_engine.call_args.kwargs["pool_pre_ping"] is False


def test_http_client_config_exposes_timeouts_and_limits_with_defaults():
    config = HttpClientConfig.from_settings(SimpleNamespace())

    assert config.timeout_seconds == 30.0
    assert config.connect_timeout_seconds == 10.0
    assert config.max_connections == 100
    assert config.max_keepalive_connections == 20
