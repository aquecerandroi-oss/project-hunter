"""Admission control for ``/ws`` — the per-address handshake-rate limit
(checked *before* ``accept()``) and the per-principal live-connection cap
(checked right after authentication).

Split out of ``realtime.endpoint`` (T3.44b): once every gateway close started
logging one structured line, that module crossed the 350-line file-size
budget (``infra/scripts/check_file_size.py``). This module's logic is
unchanged from what used to live there, just relocated by responsibility —
"how many connections is this caller allowed" is its own concern, separate
from serving one already-admitted socket.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from hunter_api.middleware.rate_limit import RateLimitRedis, under_ip_limit
from hunter_core.logging import get_logger

if TYPE_CHECKING:
    from fastapi import WebSocket

logger = get_logger(__name__)

DEFAULT_HANDSHAKES_PER_MINUTE = 30
DEFAULT_MAX_CONNECTIONS_PER_PRINCIPAL = 5
"""Fallbacks for a bare test app with no settings on ``app.state``; a deployed
process always has ``ApiSettings``."""


async def handshake_allowed(websocket: WebSocket) -> bool:
    """The per-address handshake limit, on the same Redis window the HTTP
    middleware uses (its own ``ws`` bucket, so the two budgets are separate).

    Fails open when Redis is unreachable, exactly as the HTTP limiter does:
    losing the cache must not also mean losing realtime.
    """
    redis_client: RateLimitRedis | None = getattr(websocket.app.state, "redis", None)
    if redis_client is None:
        return True
    client = websocket.client
    ip = client.host if client is not None else "unknown"
    limit = int(setting(websocket, "ws_handshakes_per_minute", DEFAULT_HANDSHAKES_PER_MINUTE))
    try:
        return await under_ip_limit(redis_client, ip, limit, scope="ws")
    except Exception:
        logger.warning("ws_handshake_limit_unavailable")
        return True


def connection_cap(websocket: WebSocket) -> int:
    return int(
        setting(
            websocket,
            "ws_max_connections_per_principal",
            DEFAULT_MAX_CONNECTIONS_PER_PRINCIPAL,
        )
    )


def setting(websocket: WebSocket, name: str, default: int) -> int:
    settings = getattr(websocket.app.state, "settings", None)
    value: int = getattr(settings, name, default)
    return value
