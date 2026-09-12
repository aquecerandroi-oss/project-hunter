"""API process settings, extending :class:`hunter_core.settings.Settings`.

Every field here mirrors a variable in ``.env.example``'s "Ambiente" section.
``ApiSettings`` is what ``create_app`` (``app.py``) and ``main.py`` build the
FastAPI application from; workers keep using the plain core ``Settings``.
"""

from __future__ import annotations

import ipaddress
from decimal import Decimal
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

    rate_limit_per_minute_internal: int = 6000
    """Requests per minute for a client address listed in ``internal_peer_ips``
    (T3.28a). The web service's own server-side (SSR) fetches to this API all
    arrive from one TCP peer — the ``web`` container's address — no matter how
    many browsers they are actually rendering for; without a separate, wider
    limit for that one known address, ``rate_limit_per_minute`` becomes a
    budget for the whole site's server-rendered traffic instead of a budget
    for one abusive caller."""

    internal_peer_ips: str = ""
    """Comma-separated TCP peer addresses that get ``rate_limit_per_minute_internal``
    instead of ``rate_limit_per_minute`` on the per-address bucket in
    :mod:`hunter_api.middleware.rate_limit`. This is not a header-trust list —
    unlike ``forwarded_allow_ips``, nothing here changes what ``uvicorn``
    trusts or what ``request.client.host`` is rewritten to; it only widens the
    bucket for a peer address the deployment already knows is internal (the
    ``web`` service's fixed compose IP — ``infra/docker/docker-compose.yml`` /
    ``infra/vps/docker-compose.prod.yml``, never ``.env``). Empty by default,
    so a bare ``ApiSettings()`` in tests keeps the narrow limit for every
    address."""

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

    manual_order_max_pending_per_portfolio: int = 20
    """How many manual paper order requests (``trade_proposals``, ``source =
    'manual'``, ``status = 'pending'`` — filed, not yet decided) one wallet may
    have outstanding at once (T3.68c, ``notes-T3.68.md`` §T3.68b finding 8).
    Enforced by :func:`hunter_api.services.admission.file_manual_order`, inside
    the same ``INSERT`` that files the request, against a 409 named
    ``too_many_pending_requests``. A decided request (approved, rejected,
    expired, executed or failed) never counts, no matter how it was decided —
    only a row still awaiting the engine's pass does. Not documented in
    ``.env.example``: this task's dispatch forbids touching any ``.env*``
    file; ``MANUAL_ORDER_MAX_PENDING_PER_PORTFOLIO`` follows the same
    ``UPPER_SNAKE_CASE`` env var name as every other field here and can be set
    the same way once that file is next touched by someone allowed to."""

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

    enable_meme_live_trading: bool = False
    """T4.14 — the API's copy of ``ENABLE_MEME_LIVE_TRADING`` (``docs/RISK_ENGINE_MEME.md``
    §3.4), read for **one** purpose: whether the desk may render "Aprovar (REAL)" and
    file ``meme_proposals.mode = 'live'``. The API never signs and never reads a key;
    the executor (``services/meme-executor``) has its own copy of the flag and refuses
    to boot without the gates. Off by default; only Everton sets it, in the VPS ``.env``."""

    daily_goal_brl: Decimal = Decimal("9000")
    """The minimum daily profit Everton set for the Lab (2026-09-10, T3.78).
    ``GET /api/v1/orgs/{org_id}/lab/daily-goal`` compares the day's unique R
    against this, never a number written into the endpoint itself."""

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
    def _validate_internal_peer_ips(self) -> ApiSettings:
        """Fail the boot on a typo, a CIDR or a hostname in ``INTERNAL_PEER_IPS``
        (T3.28d, security-reviewer finding 2 on T3.28a) rather than silently
        never matching :func:`hunter_api.middleware.rate_limit._ip_rate_limit`
        — a listed peer that never matches leaves the whole site's
        server-rendered traffic back on the narrow address bucket, with
        nothing but a puzzling wall of 429s to point at ``INTERNAL_PEER_IPS``.
        ``ipaddress.ip_address`` accepts a single IPv4/IPv6 address only —
        no ``/24`` (that is a network, not one peer's TCP address) and no
        hostname (this list is compared against ``request.client.host``,
        which is never a hostname).
        """
        for raw in self.internal_peer_ips.split(","):
            candidate = raw.strip()
            if not candidate:
                continue
            try:
                ipaddress.ip_address(candidate)
            except ValueError as exc:
                message = (
                    f"INTERNAL_PEER_IPS entry {candidate!r} is not a single IP address "
                    "(no CIDR, no hostname) -- it would never match "
                    "request.client.host and this peer would silently keep the narrow "
                    "rate limit."
                )
                raise ValueError(message) from exc
        return self

    @model_validator(mode="after")
    def _default_cors_from_web_origin(self) -> ApiSettings:
        """When ``CORS_ALLOWED_ORIGINS`` isn't set, fall back to ``WEB_ORIGIN``
        instead of a second hardcoded dev URL, so the two can't drift apart.
        """
        if not self.cors_allowed_origins:
            self.cors_allowed_origins = self.cors_origins()
        return self

    @property
    def internal_peer_ip_set(self) -> frozenset[str]:
        """``internal_peer_ips`` parsed once, for the middleware's per-request
        membership check."""
        return frozenset(ip.strip() for ip in self.internal_peer_ips.split(",") if ip.strip())

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
