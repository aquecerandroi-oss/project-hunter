"""API process settings, extending :class:`hunter_core.settings.Settings`.

Every field here mirrors a variable in ``.env.example``'s "Ambiente" section.
``ApiSettings`` is what ``create_app`` (``app.py``) and ``main.py`` build the
FastAPI application from; workers keep using the plain core ``Settings``.
"""

from __future__ import annotations

from functools import lru_cache

from pydantic import SecretStr, field_validator, model_validator
from pydantic_settings import SettingsConfigDict

from hunter_core.settings import Settings


class ApiSettings(Settings):
    """Settings for ``HUNTER_ROLE=api`` — adds HTTP-server-specific fields."""

    model_config = SettingsConfigDict(case_sensitive=False, extra="ignore")

    api_port: int = 8000
    cors_allowed_origins: list[str] = []
    rate_limit_per_minute: int = 120
    """Requests per minute per client address, enforced in the middleware — the
    limit that covers the unauthenticated surface."""

    rate_limit_per_minute_principal: int = 600
    """Requests per minute per authenticated principal, enforced after the
    token is verified. Higher than the address limit on purpose: a legitimate
    browser session is chattier than any single address should be, and this
    exists to bound one account spread over many addresses, not to be the
    tighter of the two."""
    enable_openapi_docs: bool = False
    ready_check_timeout_s: float = 3.0
    forwarded_allow_ips: str = "127.0.0.1"
    metrics_token: SecretStr | None = None
    jwks_refresh_cooldown_s: float = 60.0
    """Minimum gap between two JWKS refetches triggered by an unknown ``kid``,
    and how long that ``kid`` is remembered as unknown. ``kid`` arrives from an
    unauthenticated caller, so this is what keeps a flood of invented ones from
    becoming a flood of requests to Clerk."""

    jwks_max_stale_s: float = 86400.0
    """How long a cached JWKS may keep answering while every refetch fails.
    Past this, authentication answers 503 instead of serving keys nobody has
    been able to confirm — a key Clerk revoked is only ever learned about by
    refetching, so an unbounded cache is an unbounded revocation window."""

    max_request_body_bytes: int = 1024 * 1024
    """Hard cap on the body of an ``/api/*`` request, enforced twice: on
    ``Content-Length`` before the body is read, and on the bytes actually
    streamed — the header is written by the client, and a chunked upload sends
    none at all."""

    webhook_claim_stale_s: float = 300.0
    """How long a ``processed_events`` claim may sit unfinished before a
    redelivery may take it over. This is what turns a process killed between
    claiming a Clerk delivery and applying it into one delayed retry instead of
    a delivery that is answered "duplicate" forever."""

    ws_handshakes_per_minute: int = 30
    """WebSocket handshakes a single address may complete per minute. Checked
    before ``accept()``: opening a socket is cheap for the caller and costs us
    a task, a fan-out slot and five seconds of patience, none of which needs a
    token."""

    ws_max_connections_per_principal: int = 5
    """Live WebSocket connections one principal may hold on this process. Bounds
    the slow leak an address limit cannot see: one account opening a socket per
    tab, per device and per reconnect loop, spread out over hours."""

    ws_revalidate_interval_s: float = 60.0
    """How often a live WebSocket re-checks that its principal is still a member
    of the organizations it is subscribed to. A socket outlives the request that
    authorized it; without this, removing someone from an organization leaves
    their open socket receiving that organization's data."""

    # market_stale_after_s lives on the core hunter_core.Settings (T1.3 added
    # it there first — services/markets.py and routers/markets.py read it off
    # this inherited field, shared verbatim with the market worker's own
    # staleness handling).

    @field_validator("cors_allowed_origins", mode="before")
    @classmethod
    def _split_comma_separated(cls, value: object) -> object:
        """Accept ``CORS_ALLOWED_ORIGINS`` as a plain comma-separated string."""
        if isinstance(value, str):
            return [origin.strip() for origin in value.split(",") if origin.strip()]
        return value

    @model_validator(mode="after")
    def _default_cors_from_web_origin(self) -> ApiSettings:
        """When ``CORS_ALLOWED_ORIGINS`` isn't set, fall back to ``WEB_ORIGIN``
        instead of a second hardcoded dev URL, so the two can't drift apart.
        """
        if not self.cors_allowed_origins:
            self.cors_allowed_origins = self.cors_origins()
        return self

    @property
    def openapi_enabled(self) -> bool:
        """OpenAPI docs (``/docs``, ``/redoc``, ``/openapi.json``) are off in
        production unless explicitly re-enabled with ``ENABLE_OPENAPI_DOCS=true``.
        """
        if self.is_production:
            return self.enable_openapi_docs
        return True


@lru_cache
def get_api_settings() -> ApiSettings:
    """Cached process-wide API settings. Call ``get_api_settings.cache_clear()`` in tests."""
    return ApiSettings()
