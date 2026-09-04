"""Redis sliding-window rate limiting, per client key.

The key is the authenticated principal id when one is present on
``request.state`` (set by T06's auth), else the client IP. SECURITY.md §5:
"token bucket em Redis por usuario e por IP" — implemented here as a sliding
window over a Redis sorted set (``ZADD``/``ZREMRANGEBYSCORE``/``ZCARD``),
which is simple, exact, and needs no Lua script.

Fails open (allows the request, logs a warning) if Redis is unreachable:
ARCHITECTURE.md's "degradacao segura" principle prioritizes availability on
read paths over strict enforcement of a rate limit — unlike the Risk Engine,
which never fails open. ``/health``, ``/ready`` and ``/metrics`` are exempt
so orchestrators/monitoring are never rate limited.
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING, Any, Protocol

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from hunter_api.errors import CONTENT_TYPE, PROBLEM_BASE
from hunter_core.logging import get_logger

if TYPE_CHECKING:
    from starlette.middleware.base import RequestResponseEndpoint
    from starlette.types import ASGIApp

    from hunter_api.settings import ApiSettings

logger = get_logger(__name__)

WINDOW_SECONDS = 60
EXEMPT_PATHS = frozenset({"/health", "/ready", "/metrics"})


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

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        if request.url.path in EXEMPT_PATHS:
            return await call_next(request)

        redis_client: RateLimitRedis | None = getattr(request.app.state, "redis", None)
        client_key = _client_key(request)
        allowed = True
        if redis_client is not None:
            try:
                allowed = await _under_limit(
                    redis_client, client_key, self._settings.rate_limit_per_minute
                )
            except Exception:
                logger.warning("rate_limit_redis_unavailable", client_key=client_key)
                allowed = True

        if not allowed:
            return _too_many_requests(request)
        return await call_next(request)


def _client_key(request: Request) -> str:
    principal_id = getattr(request.state, "principal_id", None)
    if principal_id:
        return f"hunter:rl:principal:{principal_id}"
    client = request.client
    ip = client.host if client is not None else "unknown"
    return f"hunter:rl:ip:{ip}"


async def _under_limit(redis_client: RateLimitRedis, key: str, limit: int) -> bool:
    now = time.time()
    await redis_client.zremrangebyscore(key, 0, now - WINDOW_SECONDS)
    await redis_client.zadd(key, {str(now): now})
    count = await redis_client.zcard(key)
    await redis_client.expire(key, WINDOW_SECONDS)
    return count <= limit


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
