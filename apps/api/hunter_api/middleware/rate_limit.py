"""Redis sliding-window rate limiting — SECURITY.md §5, "por usuario e por IP".

Two limits, in two places, because one place cannot do both:

- **Per address**, in :class:`RateLimitMiddleware`. It runs before routing, so
  the only thing it can key on is ``request.client.host`` (plus, on the Clerk
  webhook, a second bucket for the ``svix-id`` — see :func:`_client_keys`).
  This is the limit that covers the unauthenticated surface: sign-up, the
  webhook, anything reachable without a token.
- **Per principal**, in :func:`enforce_principal_limit`, called by
  ``auth.rbac.get_principal`` once the token has actually been verified. An
  address limit alone is defeated by anyone with a proxy pool: one account
  behind a phone network or a VPN is many addresses and one identity. Both
  apply to an authenticated request, and whichever runs out first answers 429.

A third limit, on the ``/ws`` handshake, lives in ``realtime.endpoint`` and
calls :func:`under_ip_limit` here, so all three share one window
implementation.

The window is a Redis sorted set
(``ZADD``/``ZREMRANGEBYSCORE``/``ZCARD``), which is simple, exact, and needs no
Lua script.

Fails open (allows the request, logs a warning at most once per
``WARNING_LOG_INTERVAL_S``) if Redis is unreachable: ARCHITECTURE.md's
"degradacao segura" principle prioritizes availability on read paths over
strict enforcement of a rate limit — unlike the Risk Engine, which never
fails open. ``/health``, ``/ready`` and ``/metrics`` are exempt so
orchestrators/monitoring are never rate limited.

IP trust model: ``_client_key`` keys on ``request.client.host``, never on an
``X-Forwarded-For`` header — a client fully controls its own request
headers, so trusting a self-reported IP would let anyone bypass their limit
by sending a different value on every request. ``request.client.host`` is
itself only as trustworthy as the ASGI server's proxy configuration: uvicorn
is started (``main.py``) with ``proxy_headers=True`` and
``forwarded_allow_ips=ApiSettings.forwarded_allow_ips``, so it only rewrites
``request.client`` from a proxy's forwarding headers when the *direct* TCP
peer is that trusted address (the platform ingress in production) — from
any other peer, including one presenting a forged ``X-Forwarded-For``, the
real TCP peer address is what lands in ``request.client.host``.

Trust chain, end to end: browser -> Caddy (sets ``X-Forwarded-For`` to the
browser's address) -> ``api`` (uvicorn rewrites ``request.client`` from it,
because Caddy's fixed compose IP is in ``forwarded_allow_ips``). A server
component's own fetch (Next.js SSR) never goes through Caddy — ``web`` calls
``api`` directly over the compose network (``API_URL=http://api:8000``) — so
its peer is the ``web`` container, an address that is *not* in
``forwarded_allow_ips`` and never should be: ``web`` does not currently
propagate the browser's address on that call (it would need ``Headers()``
inside the Server Component and a header the API trusts only from that one
peer — out of this module's scope, since it lives in ``apps/web``), so the
real TCP peer — ``web``'s own address — is what lands in
``request.client.host`` for every SSR request, correctly rejecting a forged
header but also making one shared address of the entire site's
server-rendered traffic (T3.28a).

``_ip_rate_limit`` is the fix that does not require ``apps/web`` to change:
a peer address the deployment lists in ``ApiSettings.internal_peer_ips`` (the
``web`` service's own fixed compose IP, set directly in the compose files —
see ``ApiSettings.internal_peer_ips``) gets ``rate_limit_per_minute_internal``
instead of ``rate_limit_per_minute`` for the address bucket. This is a
peer-address lookup, not a second header to trust: nothing an actual client
sends can move a request into the wider bucket, since ``request.client.host``
already went through the rewrite rules above before this check ever runs. The
principal bucket (``enforce_principal_limit``, 600/min) is untouched by this —
an authenticated request behind the ``web`` peer is still bound by its own
account's limit, same as one behind any other address.
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING, Any, Protocol

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from hunter_api.errors import CONTENT_TYPE, HunterError
from hunter_api.metrics import rate_limit_internal_peer_total
from hunter_core.domain.types import uuid7
from hunter_core.logging import get_logger

if TYPE_CHECKING:
    from starlette.middleware.base import RequestResponseEndpoint
    from starlette.types import ASGIApp

    from hunter_api.settings import ApiSettings

logger = get_logger(__name__)

WINDOW_SECONDS = 60
EXEMPT_PATHS = frozenset({"/health", "/ready", "/metrics"})
WARNING_LOG_INTERVAL_S = 60.0

DEFAULT_PRINCIPAL_LIMIT = 600
"""Fallback for ``rate_limit_per_minute_principal`` when the application has no
settings on ``app.state`` — a bare test app, never a deployed process."""

_last_principal_fail_open_warning_at: float = float("-inf")
"""Module level, unlike the middleware's: the principal check is a function
called from a dependency, so there is no instance to hang it off."""


class RateLimitExceededError(HunterError):
    """429 for either limit, so a client sees one shape whichever bit first."""

    def __init__(self) -> None:
        super().__init__(
            type_slug="rate-limit-exceeded",
            title="Too Many Requests",
            status_code=429,
            detail="Rate limit exceeded.",
            headers={"Retry-After": str(WINDOW_SECONDS)},
        )


class RateLimitRedis(Protocol):
    """The handful of Redis commands the sliding window needs."""

    async def zremrangebyscore(self, name: str, min_: float, max_: float) -> Any: ...
    async def zadd(self, name: str, mapping: dict[str, float]) -> Any: ...
    async def zcard(self, name: str) -> int: ...
    async def expire(self, name: str, seconds: int) -> Any: ...


class RateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app: ASGIApp, settings: ApiSettings) -> None:
        super().__init__(app)
        self._settings = settings
        self._last_fail_open_warning_at: float = float("-inf")

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        if request.url.path in EXEMPT_PATHS:
            return await call_next(request)

        redis_client: RateLimitRedis | None = getattr(request.app.state, "redis", None)
        client_keys = _client_keys(request)
        allowed = True
        if redis_client is not None:
            try:
                allowed = await _under_limit(
                    redis_client, client_keys[:1], _ip_rate_limit(request, self._settings)
                )
                if allowed and len(client_keys) > 1:
                    allowed = await _under_limit(
                        redis_client, client_keys[1:], self._settings.rate_limit_per_minute
                    )
            except Exception:
                self._log_fail_open(client_keys[0])
                allowed = True

        if not allowed:
            return _too_many_requests(request)
        return await call_next(request)

    def _log_fail_open(self, client_key: str) -> None:
        """At most one ``rate_limit_redis_unavailable`` warning per
        ``WARNING_LOG_INTERVAL_S`` — an unreachable Redis fails open on
        every single request, so without this guard a sustained outage
        would emit one warning per request and flood the logs.
        """
        now = time.monotonic()
        if now - self._last_fail_open_warning_at < WARNING_LOG_INTERVAL_S:
            return
        self._last_fail_open_warning_at = now
        logger.warning("rate_limit_redis_unavailable", client_key=client_key)


def _client_keys(request: Request) -> list[str]:
    """Every bucket this request counts against — all of them must be under
    the limit for it to pass.

    Always the client address, never a principal: this runs before routing, so
    no token has been verified yet and ``request.state.principal_id`` is
    whatever an earlier version of this function hoped would be there. The
    identity limit is :func:`enforce_principal_limit`, after auth.

    The Clerk webhook adds a second bucket, and that is the whole point.
    ``svix-id`` alone is a bucket the sender picks, so a fresh id per request
    is a fresh empty bucket; the client address alone puts every customer's
    deliveries in one bucket, because they all arrive from Svix. Counting both
    bounds a retry storm for one delivery *and* a flood from one source.
    """
    client = request.client
    ip = client.host if client is not None else "unknown"
    keys = [f"hunter:rl:ip:{ip}"]
    delivery_key = getattr(request.state, "delivery_key", None)
    if delivery_key:
        keys.append(f"hunter:rl:delivery:{delivery_key}")
    return keys


def _ip_rate_limit(request: Request, settings: ApiSettings) -> int:
    """The per-address limit for this request's TCP peer (T3.28a).

    ``rate_limit_per_minute`` ordinarily, or ``rate_limit_per_minute_internal``
    when that peer is listed in ``settings.internal_peer_ips`` — the ``web``
    service's own fixed address, whose SSR fetches to this API all land on one
    peer no matter how many browsers they are serving. This is a lookup
    against the address that already survived the proxy-trust rewrite in
    ``main.py``/uvicorn, not a second thing to trust: nothing a caller sends
    on the wire moves its own request into the wider bucket.
    """
    client = request.client
    ip = client.host if client is not None else "unknown"
    if ip in settings.internal_peer_ip_set:
        rate_limit_internal_peer_total.inc()
        return settings.rate_limit_per_minute_internal
    return settings.rate_limit_per_minute


async def enforce_principal_limit(request: Request, principal_id: str) -> None:
    """The second limit, keyed on the verified identity. Raises 429 or returns.

    Called from ``auth.rbac.get_principal``, so every authenticated route —
    tenant-scoped or not — passes through it exactly once per request, and no
    route added later can quietly miss it.

    Deliberately *after* verification: a limit keyed on an unverified claim is
    a limit anyone can charge to somebody else's account. Fails open on a Redis
    error, like the middleware — an unreachable cache must not take the API
    down with it.
    """
    global _last_principal_fail_open_warning_at

    redis_client: RateLimitRedis | None = getattr(request.app.state, "redis", None)
    if redis_client is None:
        return
    settings = getattr(request.app.state, "settings", None)
    limit = int(getattr(settings, "rate_limit_per_minute_principal", DEFAULT_PRINCIPAL_LIMIT))
    key = f"hunter:rl:principal:{principal_id}"
    try:
        allowed = await _under_limit(redis_client, [key], limit)
    except Exception:
        now = time.monotonic()
        if now - _last_principal_fail_open_warning_at >= WARNING_LOG_INTERVAL_S:
            _last_principal_fail_open_warning_at = now
            logger.warning("rate_limit_redis_unavailable", client_key=key)
        return
    if not allowed:
        logger.info("rate_limit_principal_exceeded", principal_id=principal_id)
        raise RateLimitExceededError


async def under_ip_limit(redis_client: RateLimitRedis, ip: str, limit: int, *, scope: str) -> bool:
    """One window count for an address, for callers outside the HTTP stack.

    ``scope`` names the bucket family (``ws`` for the WebSocket handshake) so a
    budget on one surface is never spent by traffic on another.
    """
    return await _under_limit(redis_client, [f"hunter:rl:{scope}:{ip}"], limit)


async def _under_limit(redis_client: RateLimitRedis, keys: list[str], limit: int) -> bool:
    results = [await _window_count(redis_client, key) <= limit for key in keys]
    return all(results)


async def _window_count(redis_client: RateLimitRedis, key: str) -> int:
    """Add this request to ``key``'s window and return the window's size.

    The member is ``<timestamp>:<uuid7>``, never the timestamp alone: a sorted
    set collapses equal members, so two requests landing on the same
    ``time.time()`` value would be stored once and counted once — and on a
    coarse clock (Windows ticks at ~15 ms) that is most of a burst.
    """
    now = time.time()
    await redis_client.zremrangebyscore(key, 0, now - WINDOW_SECONDS)
    await redis_client.zadd(key, {f"{now}:{uuid7()}": now})
    count = await redis_client.zcard(key)
    await redis_client.expire(key, WINDOW_SECONDS)
    return count


def _too_many_requests(request: Request) -> JSONResponse:
    """The middleware's own 429, built from :class:`RateLimitExceededError` so
    the two limits cannot drift into two different response shapes. The
    middleware cannot simply raise it: an exception here escapes past the
    handler that would render it.
    """
    error = RateLimitExceededError()
    body: dict[str, Any] = {
        "type": error.type,
        "title": error.title,
        "status": error.status_code,
        "detail": error.detail,
        "instance": request.url.path,
    }
    request_id = getattr(request.state, "request_id", None)
    if request_id is not None:
        body["request_id"] = request_id
    return JSONResponse(
        body, status_code=error.status_code, media_type=CONTENT_TYPE, headers=error.headers
    )
