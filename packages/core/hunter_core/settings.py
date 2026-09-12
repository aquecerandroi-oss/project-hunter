"""Application settings, read from environment variables.

Every field mirrors a variable in ``.env.example`` (ARCHITECTURE.md §10: "Uma classe
Settings ... carregada de variaveis de ambiente. Nenhum arquivo .env e lido em
producao."). ``pydantic-settings`` matches env vars to field names case-insensitively.

Fields that hold credentials or connection strings with embedded credentials are
``SecretStr`` so they never render in plain text (``repr``, logs, ``str``);
``dump_safe()`` returns a dict with those masked for diagnostics endpoints. Fields
meant to reach the browser (``NEXT_PUBLIC_*``) stay plain ``str`` (SECURITY.md §4).
"""

from __future__ import annotations

from functools import lru_cache
from typing import Any, Literal

from pydantic import SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from hunter_core.domain.enums import KillSwitchState
from hunter_core.sharding import parse_shard_spec

Environment = Literal["development", "test", "staging", "production"]
Role = Literal[
    "api", "market", "scanner", "strategy", "execution", "analytics", "meme", "meme_executor", "all"
]
MarketRole = Literal["perpetual", "spot", "both"]


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
    database_url_migrations: SecretStr | None = SecretStr("")
    """Schema owner's DSN, ``migrate``/``ops`` only (DEPLOYMENT.md §3.4); no
    ``localhost`` default — ``migration_url()`` already refuses an empty one."""
    redis_url: SecretStr | None = SecretStr("redis://localhost:6379/0")
    db_pool_size: int = 5
    db_max_overflow: int = 5
    db_statement_timeout_app_s: int = 10
    """Server-side ``SET LOCAL statement_timeout`` (seconds) applied to every
    ``hunter_app`` transaction (``hunter_core.db.session.role_session``). The
    API previously ran with the server default (``0`` — no deadline; D3's
    ``command_timeout=30`` bounds only the driver, not the server), so an
    authenticated caller hitting an unindexed/expensive query repeatedly could
    saturate Postgres with nothing ever cutting a single query short. Lower
    than ``db_statement_timeout_worker_s`` on purpose: request/response work is
    expected to be short; a worker job legitimately needs more room."""
    db_statement_timeout_worker_s: int = 15
    """Server-side ``SET LOCAL statement_timeout`` (seconds) for ``hunter_worker``
    transactions — unchanged from the value this module already enforced."""

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
    enable_paper_autonomy: bool = False
    """T3.14: whether the execution-worker consumes ``shadow.signals.emitted`` and
    submits eligible signals to admission on its own.

    Default ``false``, and it stays ``false`` in production until the nine
    verifications of T3.9 are accepted (``docs/plans/M3.md``, joint decision item
    9). This field is the **single** source: ``hunter_execution_worker.config``
    reads it off a plain ``Settings()`` (T3.14b review item 5) rather than
    parsing ``ENABLE_PAPER_AUTONOMY`` a second time, so this class and the
    worker cannot disagree about which mode a deployment is in.
    """
    system_kill_switch: KillSwitchState = KillSwitchState.ACTIVE

    # ---- Dimensionamento ----
    market_universe_size: int = 200
    book_depth: int = 25
    tick_coalesce_ms: int = 250
    feature_throttle_ms: int = 1000
    radar_push_ms: int = 1000
    retention_candles_1m_days: int = 90
    retention_feature_snapshots_days: int = 14
    meme_retention_days: int = 90  # T4.2, a MESMA para graduado e nao (DATABASE.md §33.4)

    # ---- market-worker (docs/plans/M1.md T1.3) ----
    market_universe_allowlist: list[str] = []
    market_universe_blocklist: list[str] = []
    market_stale_after_s: int = 10
    market_universe_refresh_s: int = 900
    market_oi_poll_s: int = 300
    market_snapshot_interval_s: int = 60

    # ---- market-worker SPOT collection (docs/plans/M3.md T3.0c) ----
    market_spot_enabled: bool = False
    """Collect the tradable SPOT universe alongside the perpetual one.

    D1 makes spot the venue the wallet executes on, so this has to be *on* before
    the paper portfolio can run for real — and it is nonetheless **off by
    default**, because the spot path is a second WebSocket connection, a second
    REST budget and a second parse loop **inside the perpetual collector's own
    event loop**.

    Measured, not assumed (``.claude/state/t30-proof.md``): on the local stack,
    with ``MARKET_SHARD=0/1`` and 200 perpetuals — a topology T2.5g already
    showed saturates one core — turning this on made the *perpetual* socket miss
    its keepalive (``sent 1011 keepalive ping timeout``), reconnect 8 times in 6
    minutes and persist zero candles, while with it off the same process stayed
    connected and wrote 600. A default that changes the behaviour of a running,
    already-saturated collector on its next restart is not a default.

    Turning it on is one variable, and the thing to check first is event-loop
    headroom on the shard that will carry it (only shard 0 does —
    ``hunter_market_worker.spot.collects_spot``): a shard whose process already
    sits at ~100% CPU has none."""

    # ---- Runtime (nao documentado em .env.example; ver CONCERNS do T03) ----
    health_port: int = 8001

    # ---- market-worker sharding (T1.6b-C) ----
    market_shard: str = "0/1"
    """``"<index>/<total>"`` — which stable hash slice of the monitored
    universe this process owns (:func:`hunter_market_worker.universe.shard_symbols`).
    Default ``"0/1"`` is exactly today's behaviour: one process, the whole
    universe, no coordination. Parsed eagerly by
    :func:`hunter_core.sharding.parse_shard_spec` so a malformed value fails
    at construction, never silently at the first symbol-assignment call."""

    @model_validator(mode="after")
    def _validate_market_shard(self) -> Settings:
        parse_shard_spec("MARKET_SHARD", self.market_shard)
        return self

    @property
    def shard_index(self) -> int:
        """This process's shard index, ``0 <= shard_index < shard_total``."""
        return parse_shard_spec("MARKET_SHARD", self.market_shard)[0]

    @property
    def shard_total(self) -> int:
        """Total number of shards (``>= 1``)."""
        return parse_shard_spec("MARKET_SHARD", self.market_shard)[1]

    # ---- strategy-worker sharding (T3.74f, mirrors market_shard above) ----
    strategy_shard: str = "0/1"
    """Which crc32 slice (:func:`hunter_core.sharding.owns`, same formula
    ``market_shard`` uses) of the monitored universe this strategy-worker
    process decides on. ``"0/1"``: today's behaviour, one process. T3.74f
    measured one process pinned at ~99% of one core for a whole burst while
    Postgres stayed at 20-25% of its cores -- CPU, not the pool, is why."""

    @model_validator(mode="after")
    def _validate_strategy_shard(self) -> Settings:
        parse_shard_spec("STRATEGY_SHARD", self.strategy_shard)
        return self

    @property
    def strategy_shard_index(self) -> int:
        return parse_shard_spec("STRATEGY_SHARD", self.strategy_shard)[0]

    @property
    def strategy_shard_total(self) -> int:
        return parse_shard_spec("STRATEGY_SHARD", self.strategy_shard)[1]

    # ---- market-worker data-path role (T3.0f) ------------------------------
    market_role: MarketRole | None = None
    """Which data path(s) this market-worker process runs: ``"perpetual"``
    (today's shard behaviour, never spot -- ``MARKET_SPOT_ENABLED`` has no
    effect here regardless of its value), ``"spot"`` (the dedicated spot
    collector only -- no perpetual universe, ingest, heartbeat or backfill at
    all), or ``"both"`` (one process runs the perpetual pipeline and, on
    shard 0 with ``MARKET_SPOT_ENABLED=true``, the spot one too -- today's
    single-process local-stack behaviour).

    ``None`` (unset, the default) resolves via :attr:`market_role_effective`
    instead of hardcoding one value: ``"perpetual"`` when this process is
    part of a shard topology (``shard_total > 1``), ``"both"`` otherwise. The
    reason is exactly what ``.claude/state/t30-proof.md`` measured -- turning
    on the spot collector inside an already-saturated ``MARKET_SHARD=0/N``
    process (``N > 1``) made the *perpetual* WebSocket miss its keepalive and
    reconnect 8 times in 6 minutes. A sharded deployment should run spot as
    its own process (``infra/docker/docker-compose.yml``'s
    ``market-worker-spot``, profile ``spot``) with ``MARKET_ROLE=spot`` set
    explicitly there -- never implied by a shard happening to be index 0.
    """

    @property
    def market_role_effective(self) -> MarketRole:
        """:attr:`market_role`, or the shard-aware default when unset."""
        if self.market_role is not None:
            return self.market_role
        return "perpetual" if self.shard_total > 1 else "both"

    @model_validator(mode="after")
    def _validate_market_role(self) -> Settings:
        """Refuse two ambiguous combinations at startup, loudly, rather than
        let either silently run something nobody asked for.

        ``"spot"`` is a dedicated, whole-universe collector (never sharded --
        ``hunter_market_worker.spot`` module docstring): a ``MARKET_ROLE=spot``
        process declaring ``MARKET_SHARD`` with more than one total shard
        cannot mean "shard N of the spot universe" (spot never shards) nor
        "shard N of the perpetual universe" (this role never touches
        perpetual) -- there is no reading of that combination that is not a
        misconfiguration, so it is refused rather than silently running as a
        very confusing solo collector.

        ``"both"`` mixes spot and 200 perpetuals in one event loop -- exactly
        the combination ``t30-proof.md`` §1 measured breaking the perpetual
        socket's keepalive. It is fine, and kept, for the single-process local
        stack (``shard_total == 1``); explicitly requesting it under a shard
        topology (``shard_total > 1``) is refused rather than silently
        reproducing that outage on whichever shard happens to be index 0.

        Deliberately **not** refused here: ``MARKET_ROLE=spot`` with
        ``MARKET_SPOT_ENABLED=false``. That is a legitimate, if inert,
        configuration -- the dedicated process logs it and idles forever
        rather than crash-looping (``hunter_market_worker.spot.run_spot``).
        """
        role = self.market_role
        if role is None:
            return self
        shard_total = parse_shard_spec("MARKET_SHARD", self.market_shard)[1]
        if role == "spot" and shard_total > 1:
            raise ValueError(
                "MARKET_ROLE=spot cannot be combined with a sharded MARKET_SHARD "
                f"({self.market_shard!r}, shard_total={shard_total}): the spot "
                "collector owns the whole spot universe as one solo process, "
                "never a shard of one -- use MARKET_SHARD=0/1 (the default) for "
                "the dedicated spot process."
            )
        if role == "both" and shard_total > 1:
            raise ValueError(
                "MARKET_ROLE=both cannot be combined with a sharded MARKET_SHARD "
                f"({self.market_shard!r}, shard_total={shard_total}): mixing spot "
                "and a perpetual shard in one event loop is exactly the "
                "keepalive-starving combination t30-proof.md measured breaking "
                "the perpetual socket -- use MARKET_ROLE=perpetual on every "
                "shard and a dedicated MARKET_ROLE=spot process instead."
            )
        return self

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
