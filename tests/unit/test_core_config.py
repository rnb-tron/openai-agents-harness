from src.core.config import get_settings


def test_get_settings_builds_database_url_from_pg_env(monkeypatch):
    monkeypatch.setenv("ENVTYPE", "unit")
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("PGHOST", "db.example.com")
    monkeypatch.setenv("PGPORT", "5432")
    monkeypatch.setenv("PGDATABASE", "agent_harness")
    monkeypatch.setenv("PGUSER", "business_pac_admin")
    monkeypatch.setenv("PGPASSWORD", "Grv0nwJEs%BL@Wq!")

    settings = get_settings()

    assert (
        settings.database_url
        == "postgresql+asyncpg://business_pac_admin:Grv0nwJEs%25BL%40Wq%21@db.example.com:5432/agent_harness"
    )


def test_get_settings_loads_memory_pgvector_split_env(monkeypatch):
    monkeypatch.setenv("ENVTYPE", "unit")
    monkeypatch.setenv("MEMORY_PGVECTOR_PGHOST", "10.19.74.82")
    monkeypatch.setenv("MEMORY_PGVECTOR_PGPORT", "5432")
    monkeypatch.setenv("MEMORY_PGVECTOR_PGDATABASE", "agent_memory")
    monkeypatch.setenv("MEMORY_PGVECTOR_PGUSER", "business_pac_admin")
    monkeypatch.setenv("MEMORY_PGVECTOR_PGPASSWORD", "Grv0nwJEs%BL@Wq!")

    settings = get_settings()

    assert settings.memory_pgvector_pg_host == "10.19.74.82"
    assert settings.memory_pgvector_pg_port == "5432"
    assert settings.memory_pgvector_pg_database == "agent_memory"
    assert settings.memory_pgvector_pg_user == "business_pac_admin"
    assert settings.memory_pgvector_pg_password == "Grv0nwJEs%BL@Wq!"


def test_get_settings_loads_short_term_context_max_turns(monkeypatch):
    monkeypatch.setenv("ENVTYPE", "unit")
    monkeypatch.setenv("MEMORY_SHORT_TERM_CONTEXT_MAX_TURNS", "3")

    settings = get_settings()

    assert settings.memory_short_term_context_max_turns == 3


def test_get_settings_loads_split_memory_enable_switches(monkeypatch):
    monkeypatch.setenv("ENVTYPE", "unit")
    monkeypatch.setenv("MEMORY_SHORT_TERM_ENABLED", "true")
    monkeypatch.setenv("MEMORY_SESSION_SUMMARY_ENABLED", "false")
    monkeypatch.setenv("MEMORY_LONG_TERM_ENABLED", "true")

    settings = get_settings()

    assert settings.memory_short_term_enabled is True
    assert settings.memory_session_summary_enabled is False
    assert settings.memory_long_term_enabled is True


def test_get_settings_ignores_old_memory_enabled(monkeypatch):
    monkeypatch.setenv("ENVTYPE", "unit")
    monkeypatch.delenv("MEMORY_SHORT_TERM_ENABLED", raising=False)
    monkeypatch.delenv("MEMORY_LONG_TERM_ENABLED", raising=False)
    monkeypatch.setenv("MEMORY_ENABLED", "true")

    settings = get_settings()

    assert settings.memory_short_term_enabled is False
    assert settings.memory_long_term_enabled is False


def test_get_settings_loads_long_term_memory_names(monkeypatch):
    monkeypatch.setenv("ENVTYPE", "unit")
    monkeypatch.setenv("MEMORY_LONG_TERM_PROVIDER", "mem0")
    monkeypatch.setenv("MEMORY_LONG_TERM_MEM0_MODE", "platform")
    monkeypatch.setenv("MEMORY_LONG_TERM_MEM0_API_KEY", "mem0-key")
    monkeypatch.setenv("MEMORY_LONG_TERM_MEM0_CONFIG_JSON", "{\"x\": {}}")
    monkeypatch.setenv("MEMORY_LONG_TERM_VECTOR_STORE", "pgvector")

    settings = get_settings()

    assert settings.memory_long_term_provider == "mem0"
    assert settings.memory_long_term_mem0_mode == "platform"
    assert settings.memory_long_term_mem0_api_key == "mem0-key"
    assert settings.memory_long_term_mem0_config_json == "{\"x\": {}}"
    assert settings.memory_long_term_vector_store == "pgvector"
