"""Redis sliding-window rate limiting, per client key.

The key is the authenticated principal id when one is present on
``request.state`` (set by T06's auth), else the client IP — plus, on the Clerk
webhook, a second bucket for the ``svix-id`` (see :func:`_client_keys`).
SECURITY.md §5: "token bucket em Redis por usuario e por IP" — implemented here
as a sliding window over a Redis sorted set
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
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING, Any, Protocol

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from hunter_api.errors import CONTENT_TYPE, PROBLEM_BASE
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
                    redis_client, client_keys, self._settings.rate_limit_per_minute
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

    An authenticated caller is one bucket: the principal. The Clerk webhook is
    two, and that is the whole point. ``svix-id`` alone is a bucket the sender
    picks, so a fresh id per request is a fresh empty bucket; the client
    address alone puts every customer's deliveries in one bucket, because they
    all arrive from Svix. Counting both bounds a retry storm for one delivery
    *and* a flood from one source.
    """
    principal_id = getattr(request.state, "principal_id", None)
    if principal_id:
        return [f"hunter:rl:principal:{principal_id}"]
    client = request.client
    ip = client.host if client is not None else "unknown"
    keys = [f"hunter:rl:ip:{ip}"]
    delivery_key = getattr(request.state, "delivery_key", None)
    if delivery_key:
        keys.append(f"hunter:rl:delivery:{delivery_key}")
    return keys


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
    body = {
        "type": f"{PROBLEM_BASE}/rate-limit-exceeded",
        "title": "Too Many Requests",
        "status": 429,
        "detail": "Rate limit exceeded.",
        "instance": request.url.path,
    }
    return JSONResponse(
        body,
        status_code=429,
        media_type=CONTENT_TYPE,
        headers={"Retry-After": str(WINDOW_SECONDS)},
    )
