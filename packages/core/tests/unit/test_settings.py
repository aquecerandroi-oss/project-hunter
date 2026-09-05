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
    monkeypatch.setenv("HUNTER_ENV", "not-a-real-environment")
    with pytest.raises(ValidationError):
        Settings()


def test_accepts_staging_as_a_valid_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    """``.env.example`` documents ``development | staging | production``."""
    monkeypatch.setenv("HUNTER_ENV", "staging")
    _set_required_production_urls(monkeypatch)
    _set_required_clerk_settings(monkeypatch)
    settings = Settings()
    assert settings.hunter_env == "staging"


def test_development_defaults_do_not_require_urls(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HUNTER_ENV", "development")
    settings = Settings()
    assert settings.database_url is not None


def test_production_fails_fast_without_database_and_redis_url(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("HUNTER_ENV", "production")
    monkeypatch.setenv("DATABASE_URL", "")
    monkeypatch.setenv("REDIS_URL", "")
    with pytest.raises(ValidationError, match="DATABASE_URL"):
        Settings()


def test_production_succeeds_with_urls_present(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HUNTER_ENV", "production")
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://u:p@host/db")
    monkeypatch.setenv("REDIS_URL", "redis://host:6379/0")
    monkeypatch.setenv("WEB_ORIGIN", "https://app.hunter.example")
    monkeypatch.setenv("API_URL", "https://api.hunter.example")
    monkeypatch.setenv("NEXT_PUBLIC_API_URL", "https://api.hunter.example")
    monkeypatch.setenv("NEXT_PUBLIC_WS_URL", "wss://api.hunter.example/ws")
    _set_required_clerk_settings(monkeypatch)
    settings = Settings()
    assert settings.hunter_env == "production"


def _set_required_production_urls(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://u:p@host/db")
    monkeypatch.setenv("REDIS_URL", "redis://host:6379/0")
    monkeypatch.setenv("WEB_ORIGIN", "https://app.hunter.example")
    monkeypatch.setenv("API_URL", "https://api.hunter.example")
    monkeypatch.setenv("NEXT_PUBLIC_API_URL", "https://api.hunter.example")
    monkeypatch.setenv("NEXT_PUBLIC_WS_URL", "wss://api.hunter.example/ws")


@pytest.mark.parametrize("hunter_env", ["production", "staging"])
def test_fails_fast_without_web_origin_in_prod_and_staging(
    monkeypatch: pytest.MonkeyPatch, hunter_env: str
) -> None:
    monkeypatch.setenv("HUNTER_ENV", hunter_env)
    _set_required_production_urls(monkeypatch)
    monkeypatch.setenv("WEB_ORIGIN", "")
    with pytest.raises(ValidationError, match="WEB_ORIGIN"):
        Settings()


def test_fails_fast_naming_every_missing_public_url(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HUNTER_ENV", "production")
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://u:p@host/db")
    monkeypatch.setenv("REDIS_URL", "redis://host:6379/0")
    monkeypatch.setenv("WEB_ORIGIN", "")
    monkeypatch.setenv("API_URL", "")
    monkeypatch.setenv("NEXT_PUBLIC_API_URL", "")
    monkeypatch.setenv("NEXT_PUBLIC_WS_URL", "")
    with pytest.raises(ValidationError) as exc_info:
        Settings()
    message = str(exc_info.value)
    assert "WEB_ORIGIN" in message
    assert "API_URL" in message
    assert "NEXT_PUBLIC_API_URL" in message
    assert "NEXT_PUBLIC_WS_URL" in message


def test_production_succeeds_with_all_urls_set(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HUNTER_ENV", "production")
    _set_required_production_urls(monkeypatch)
    _set_required_clerk_settings(monkeypatch)
    settings = Settings()
    assert settings.hunter_env == "production"


def test_development_without_public_urls_uses_localhost_defaults(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("HUNTER_ENV", "development")
    settings = Settings()
    assert settings.web_origin == "http://localhost:3000"
    assert settings.api_url == "http://localhost:8000"
    assert settings.next_public_api_url == "http://localhost:8000"
    assert settings.next_public_ws_url == "ws://localhost:8000/ws"


def test_is_production_and_is_development_properties(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HUNTER_ENV", "production")
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://u:p@host/db")
    monkeypatch.setenv("REDIS_URL", "redis://host:6379/0")
    _set_required_clerk_settings(monkeypatch)
    prod = Settings()
    assert prod.is_production is True
    assert prod.is_development is False

    monkeypatch.setenv("HUNTER_ENV", "development")
    dev = Settings()
    assert dev.is_production is False
    assert dev.is_development is True

    monkeypatch.setenv("HUNTER_ENV", "staging")
    staging = Settings()
    assert staging.is_production is False
    assert staging.is_development is False

    monkeypatch.setenv("HUNTER_ENV", "test")
    test_env = Settings()
    assert test_env.is_production is False
    assert test_env.is_development is False


def test_dump_safe_masks_secrets_and_keeps_public_fields(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://u:FAKEsupersecret@host/db")
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


def _set_required_clerk_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CLERK_ISSUER", "https://clerk.hunter.example")
    monkeypatch.setenv("CLERK_JWKS_URL", "https://clerk.hunter.example/.well-known/jwks.json")
    monkeypatch.setenv("CLERK_SECRET_KEY", "sk_FAKE_not_a_real_key")
    monkeypatch.setenv("CLERK_WEBHOOK_SECRET", "whsec_FAKE_not_a_real_secret")


@pytest.mark.parametrize("hunter_env", ["production", "staging"])
@pytest.mark.parametrize(
    "missing",
    ["CLERK_ISSUER", "CLERK_JWKS_URL", "CLERK_SECRET_KEY", "CLERK_WEBHOOK_SECRET"],
)
def test_fails_fast_without_the_clerk_credentials(
    monkeypatch: pytest.MonkeyPatch, hunter_env: str, missing: str
) -> None:
    """Each of these has a silent failure mode when empty, which is why the
    process refuses to start instead: no issuer or JWKS URL and every token is
    rejected at runtime; no webhook secret and Clerk's user events return 503
    forever; no secret key and just-in-time provisioning cannot fetch a
    profile, so a new customer's first request fails.
    """
    monkeypatch.setenv("HUNTER_ENV", hunter_env)
    _set_required_production_urls(monkeypatch)
    _set_required_clerk_settings(monkeypatch)
    monkeypatch.setenv(missing, "")

    with pytest.raises(ValidationError, match=missing):
        Settings()


def test_production_succeeds_with_the_clerk_credentials_present(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("HUNTER_ENV", "production")
    _set_required_production_urls(monkeypatch)
    _set_required_clerk_settings(monkeypatch)

    settings = Settings()

    assert settings.clerk_issuer == "https://clerk.hunter.example"


def test_development_does_not_require_the_clerk_credentials(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("HUNTER_ENV", "development")

    settings = Settings()

    assert settings.clerk_issuer == ""


# ---- MARKET_SHARD (T1.6b-C1) -----------------------------------------------


def test_market_shard_defaults_to_single_process_whole_universe() -> None:
    settings = Settings()
    assert settings.market_shard == "0/1"
    assert settings.shard_index == 0
    assert settings.shard_total == 1


def test_market_shard_reads_env_and_exposes_parsed_properties(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("MARKET_SHARD", "2/4")
    settings = Settings()
    assert settings.shard_index == 2
    assert settings.shard_total == 4


@pytest.mark.parametrize(
    "value",
    [
        "not-a-shard",
        "1",
        "1/2/3",
        "a/4",
        "1/a",
        "4/4",  # index must be < total
        "-1/4",  # index must be >= 0
        "0/0",  # total must be >= 1
        "0/-1",
        "1/-4",
    ],
)
def test_market_shard_rejects_invalid_values(monkeypatch: pytest.MonkeyPatch, value: str) -> None:
    monkeypatch.setenv("MARKET_SHARD", value)
    with pytest.raises(ValidationError, match="MARKET_SHARD"):
        Settings()


def test_market_shard_single_index_zero_of_one_is_valid() -> None:
    settings = Settings(market_shard="0/1")
    assert settings.shard_index == 0
    assert settings.shard_total == 1
