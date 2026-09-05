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

Environment = Literal["development", "test", "staging", "production"]
Role = Literal["api", "market", "scanner", "strategy", "execution", "analytics", "all"]


def _parse_market_shard(value: str) -> tuple[int, int]:
    """``"<index>/<total>"`` -> ``(index, total)``, validated (T1.6b-C1).

    Fails loudly and immediately -- a market-worker that silently fell back
    to "the whole universe" on a typo'd ``MARKET_SHARD`` would duplicate
    every other shard's REST/WS load instead of refusing to start.
    """
    parts = value.split("/")
    if len(parts) != 2:
        raise ValueError(f"MARKET_SHARD must be '<index>/<total>', got {value!r}")
    try:
        index, total = int(parts[0]), int(parts[1])
    except ValueError as exc:
        raise ValueError(
            f"MARKET_SHARD must be '<index>/<total>' with integers, got {value!r}"
        ) from exc
    if total < 1:
        raise ValueError(f"MARKET_SHARD total must be >= 1, got {value!r}")
    if not (0 <= index < total):
        raise ValueError(f"MARKET_SHARD index must satisfy 0 <= index < total, got {value!r}")
    return index, total


class Settings(BaseSettings):
    """Process-wide configuration. Construct via :func:`get_settings`."""

    model_config = SettingsConfigDict(case_sensitive=False, extra="ignore")

    # ---- Ambiente ----
    hunter_env: Environment = "development"
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

    # ---- market-worker (docs/plans/M1.md T1.3) ----
    market_universe_allowlist: list[str] = []
    market_universe_blocklist: list[str] = []
    market_stale_after_s: int = 10
    market_universe_refresh_s: int = 900
    market_oi_poll_s: int = 300
    market_snapshot_interval_s: int = 60

    # ---- Runtime (nao documentado em .env.example; ver CONCERNS do T03) ----
    health_port: int = 8001

    # ---- market-worker sharding (T1.6b-C) ----
    market_shard: str = "0/1"
    """``"<index>/<total>"`` — which stable hash slice of the monitored
    universe this process owns (:func:`hunter_market_worker.universe.shard_symbols`).
    Default ``"0/1"`` is exactly today's behaviour: one process, the whole
    universe, no coordination. Parsed eagerly by :func:`_parse_market_shard`
    so a malformed value fails at construction, never silently at the first
    symbol-assignment call."""

    @model_validator(mode="after")
    def _validate_market_shard(self) -> Settings:
        _parse_market_shard(self.market_shard)
        return self

    @property
    def shard_index(self) -> int:
        """This process's shard index, ``0 <= shard_index < shard_total``."""
        return _parse_market_shard(self.market_shard)[0]

    @property
    def shard_total(self) -> int:
        """Total number of shards (``>= 1``)."""
        return _parse_market_shard(self.market_shard)[1]

    @model_validator(mode="after")
    def _require_settings_in_prod(self) -> Settings:
        """Refuse to start a deployed process with an empty required setting.

        Every one of these fails *silently and later* when unset, at the worst
        possible moment: no ``CLERK_ISSUER`` or ``CLERK_JWKS_URL`` and every
        token is rejected once real users arrive; no ``CLERK_WEBHOOK_SECRET``
        and Clerk's deliveries get 503 until they stop retrying, so the local
        mirror silently drifts; no ``CLERK_SECRET_KEY`` and just-in-time
        provisioning cannot fetch a profile, so a new customer's very first
        request fails. Failing at construction turns all of them into a
        deployment that does not roll out.
        """
        if self.hunter_env not in ("production", "staging"):
            return self
        secret_checks: list[tuple[str, SecretStr | None]] = [
            ("DATABASE_URL", self.database_url),
            ("REDIS_URL", self.redis_url),
            ("CLERK_SECRET_KEY", self.clerk_secret_key),
            ("CLERK_WEBHOOK_SECRET", self.clerk_webhook_secret),
            ("CLERK_JWKS_URL", self.clerk_jwks_url),
        ]
        plain_checks: list[tuple[str, str]] = [
            ("WEB_ORIGIN", self.web_origin),
            ("API_URL", self.api_url),
            ("NEXT_PUBLIC_API_URL", self.next_public_api_url),
            ("NEXT_PUBLIC_WS_URL", self.next_public_ws_url),
            ("CLERK_ISSUER", self.clerk_issuer),
        ]
        missing = [
            name for name, value in secret_checks if value is None or not value.get_secret_value()
        ]
        missing += [name for name, value in plain_checks if not value]
        if missing:
            raise ValueError(
                f"missing required settings in {self.hunter_env}: {', '.join(missing)}"
            )
        return self

    @property
    def is_production(self) -> bool:
        """``True`` only for ``HUNTER_ENV=production`` (never for ``staging``)."""
        return self.hunter_env == "production"

    @property
    def is_development(self) -> bool:
        """``True`` only for ``HUNTER_ENV=development`` (never for ``test``)."""
        return self.hunter_env == "development"

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
