from types import SimpleNamespace

from src import cli


def test_doctor_reports_missing_openai_key(monkeypatch, capsys):
    monkeypatch.setattr(
        cli,
        "get_settings",
        lambda: SimpleNamespace(
            openai_api_key="",
            session_store_enabled=False,
            database_url="",
            rate_limit_enabled=False,
            rate_limit_backend="memory",
            redis_enabled=False,
        ),
    )

    assert cli.main(["doctor"]) == 1
    assert "OPENAI_API_KEY is empty" in capsys.readouterr().out


def test_doctor_accepts_minimal_valid_settings(monkeypatch, capsys):
    monkeypatch.setattr(
        cli,
        "get_settings",
        lambda: SimpleNamespace(
            openai_api_key="sk-test",
            session_store_enabled=False,
            database_url="",
            rate_limit_enabled=False,
            rate_limit_backend="memory",
            redis_enabled=False,
        ),
    )

    assert cli.main(["doctor"]) == 0
    assert "Configuration looks OK." in capsys.readouterr().out
