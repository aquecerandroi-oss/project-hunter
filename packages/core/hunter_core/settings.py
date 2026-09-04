"""Application settings, read from environment variables.

Every field mirrors a variable in ``.env.example`` (ARCHITECTURE.md §10: "Uma
classe Settings ... carregada de variaveis de ambiente. Nenhum arquivo .env e
lido em producao."). ``pydantic-settings`` matches env vars to field names
case-insensitively, so no aliases are needed.

Fields that hold credentials or connection strings with embedded credentials
are ``SecretStr`` so they never render in plain text (``repr``, logs, ``str``);
``dump_safe()`` returns a dict with those masked for diagnostics endpoints.
Fields explicitly meant to reach the browser (``NEXT_PUBLIC_*``) stay plain
``str`` — they are public by design (see SECURITY.md §4).
"""

from __future__ import annotations

from functools import lru_cache
from typing import Any, Literal

from pydantic import SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from hunter_core.domain.enums import KillSwitchState

Environment = Literal["dev", "test", "prod"]
Role = Literal["api", "market", "scanner", "strategy", "execution", "analytics", "all"]


class Settings(BaseSettings):
    """Process-wide configuration. Construct via :func:`get_settings`."""

    model_config = SettingsConfigDict(case_sensitive=False, extra="ignore")

    # ---- Ambiente ----
    hunter_env: Environment = "dev"
    hunter_role: Role = "all"
    log_level: str = "INFO"
    web_origin: str = "http://localhost:3000"
    api_url: str = "http://localhost:8000"
    next_public_api_url: str = "http://localhost:8000"
    next_public_ws_url: str = "ws://localhost:8000/ws"

    # ---- Banco e cache ----
    database_url: SecretStr | None = SecretStr(
        "postgresql+asyncpg://hunter:hunter@localhost:5432/hunter"
    )
    database_url_migrations: SecretStr | None = SecretStr(
        "postgresql://hunter:hunter@localhost:5432/hunter"
    )
    redis_url: SecretStr | None = SecretStr("redis://localhost:6379/0")
    db_pool_size: int = 5
    db_max_overflow: int = 5

    # ---- Auth (Clerk) ----
    next_public_clerk_publishable_key: str = ""
    clerk_secret_key: SecretStr = SecretStr("")
    clerk_webhook_secret: SecretStr = SecretStr("")
    clerk_jwks_url: SecretStr = SecretStr("")
    clerk_issuer: str = ""

    # ---- Segredos de aplicacao ----
    auth_secret: SecretStr = SecretStr("")
    hunter_master_key: SecretStr = SecretStr("")
    kms_key_id: SecretStr = SecretStr("")

    # ---- Observabilidade e produto ----
    sentry_dsn: SecretStr = SecretStr("")
    sentry_environment: str = "development"
    next_public_posthog_key: str = ""
    next_public_posthog_host: str = "https://us.i.posthog.com"

    # ---- LLM (Fase 2) ----
    anthropic_api_key: SecretStr = SecretStr("")
    anthropic_model: str = "claude-opus-5"

    # ---- Exchanges (opcionais) ----
    binance_api_key: SecretStr = SecretStr("")
    binance_api_secret: SecretStr = SecretStr("")
    bybit_api_key: SecretStr = SecretStr("")
    bybit_api_secret: SecretStr = SecretStr("")

    # ---- Feature flags de sistema ----
    enable_live_trading: bool = False
    enable_social_intelligence: bool = False
    enable_onchain: bool = False
    enable_stripe: bool = False
    enable_llm_analysis: bool = False
    enable_arena: bool = False
    enable_backtests: bool = False
    system_kill_switch: KillSwitchState = KillSwitchState.ACTIVE

    # ---- Dimensionamento ----
    market_universe_size: int = 200
    book_depth: int = 25
    tick_coalesce_ms: int = 250
    feature_throttle_ms: int = 1000
    radar_push_ms: int = 1000
    retention_candles_1m_days: int = 90
    retention_feature_snapshots_days: int = 14

    # ---- Runtime (nao documentado em .env.example; ver CONCERNS do T03) ----
    health_port: int = 8000

    @model_validator(mode="after")
    def _require_urls_in_prod(self) -> Settings:
        if self.hunter_env != "prod":
            return self
        missing = [
            name
            for name, value in (("DATABASE_URL", self.database_url), ("REDIS_URL", self.redis_url))
            if value is None or not value.get_secret_value()
        ]
        if missing:
            raise ValueError(f"missing required settings in prod: {', '.join(missing)}")
        return self

    def cors_origins(self) -> list[str]:
        """``WEB_ORIGIN`` as a list — one or more origins, comma separated."""
        return [origin.strip() for origin in self.web_origin.split(",") if origin.strip()]

    def dump_safe(self) -> dict[str, Any]:
        """``model_dump`` with every secret masked — safe for logs or a debug endpoint.

        JSON-mode serialization of a ``SecretStr`` already yields the masked
        placeholder (or ``""`` for an unset secret) instead of the real value;
        this just names that behavior for callers.
        """
        return self.model_dump(mode="json")


@lru_cache
def get_settings() -> Settings:
    """Cached process-wide settings. Call ``get_settings.cache_clear()`` in tests."""
    return Settings()
