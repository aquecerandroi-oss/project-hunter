"""Unit tests for hunter_core.settings."""

import pytest
from pydantic import SecretStr, ValidationError

from hunter_core.domain.enums import KillSwitchState
from hunter_core.settings import Settings, get_settings

pytestmark = pytest.mark.unit


def test_reads_env_vars_with_correct_types(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HUNTER_ENV", "test")
    monkeypatch.setenv("HUNTER_ROLE", "market")
    monkeypatch.setenv("LOG_LEVEL", "DEBUG")
    monkeypatch.setenv("ENABLE_LIVE_TRADING", "true")
    monkeypatch.setenv("MARKET_UNIVERSE_SIZE", "50")
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://u:p@host/db")
    monkeypatch.setenv("SYSTEM_KILL_SWITCH", "WARNING")

    settings = Settings()

    assert settings.hunter_env == "test"
    assert settings.hunter_role == "market"
    assert settings.log_level == "DEBUG"
    assert settings.enable_live_trading is True
    assert settings.market_universe_size == 50
    assert isinstance(settings.database_url, SecretStr)
    assert settings.database_url.get_secret_value() == "postgresql+asyncpg://u:p@host/db"
    assert settings.system_kill_switch == KillSwitchState.WARNING


def test_rejects_unknown_hunter_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HUNTER_ENV", "staging")
    with pytest.raises(ValidationError):
        Settings()


def test_dev_defaults_do_not_require_urls(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HUNTER_ENV", "dev")
    settings = Settings()
    assert settings.database_url is not None


def test_prod_fails_fast_without_database_and_redis_url(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HUNTER_ENV", "prod")
    monkeypatch.setenv("DATABASE_URL", "")
    monkeypatch.setenv("REDIS_URL", "")
    with pytest.raises(ValidationError, match="DATABASE_URL"):
        Settings()


def test_prod_succeeds_with_urls_present(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HUNTER_ENV", "prod")
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://u:p@host/db")
    monkeypatch.setenv("REDIS_URL", "redis://host:6379/0")
    settings = Settings()
    assert settings.hunter_env == "prod"


def test_dump_safe_masks_secrets_and_keeps_public_fields(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://u:supersecret@host/db")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-real-secret-value")
    monkeypatch.setenv("WEB_ORIGIN", "http://localhost:3000")

    dumped = Settings().dump_safe()

    assert "supersecret" not in str(dumped)
    assert "sk-real-secret-value" not in str(dumped)
    assert dumped["web_origin"] == "http://localhost:3000"


def test_cors_origins_splits_comma_separated_list() -> None:
    settings = Settings(web_origin="http://a.com, http://b.com")
    assert settings.cors_origins() == ["http://a.com", "http://b.com"]


def test_get_settings_is_cached() -> None:
    get_settings.cache_clear()
    first = get_settings()
    second = get_settings()
    assert first is second
    get_settings.cache_clear()
