from agno_app.settings import Settings


def test_development_settings_are_valid(monkeypatch):
    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.setenv("AUTHORIZATION_ENABLED", "false")
    settings = Settings.from_env()
    assert settings.port == 7777
    assert not settings.is_production


def test_production_requires_authorization(monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("AUTHORIZATION_ENABLED", "false")

    try:
        Settings.from_env()
    except ValueError as exc:
        assert "AUTHORIZATION_ENABLED" in str(exc)
    else:
        raise AssertionError("production must reject disabled authorization")
