"""Clears the per-request tenant slots, and keys the webhook's rate limit.

``request.state.org_id`` and ``request.state.principal_id`` are read by the
rate limiter and by log context, and are *written* by the RBAC dependencies
(``hunter_api.auth.rbac``) once the caller is known. This middleware exists so
they are always present — ``None`` — before anything reads them, instead of
every reader defending with ``getattr(..., None)``.

The one thing it fills in is the Clerk webhook's rate-limit key. That endpoint
has no principal and no useful client IP (every delivery for every customer
arrives from Svix's egress addresses, so an IP key puts them all in one bucket
and starts dropping real events under load). ``svix-id`` identifies the
delivery, so keying on it bounds a retry storm for one event without touching
any other. It is set here because the limiter runs *inside* this middleware —
see the ordering note in ``app.py`` — and reads the key before the route is
ever reached.

``svix-id`` is attacker-controllable, so it is length-capped and namespaced
into its own key space before it becomes a Redis key; it grants nothing on its
own (the Svix signature is what authenticates the request, in the handler).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

if TYPE_CHECKING:
    from starlette.middleware.base import RequestResponseEndpoint
    from starlette.types import ASGIApp

WEBHOOK_PATH_PREFIX = "/api/webhooks/"
MAX_DELIVERY_ID_LENGTH = 128


class TenantContextMiddleware(BaseHTTPMiddleware):
    def __init__(self, app: ASGIApp) -> None:
        super().__init__(app)

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Any:
        request.state.org_id = None
        request.state.principal_id = webhook_rate_limit_key(request)
        return await call_next(request)


def webhook_rate_limit_key(request: Request) -> str | None:
    if not request.url.path.startswith(WEBHOOK_PATH_PREFIX):
        return None
    delivery_id = request.headers.get("svix-id")
    if not delivery_id or len(delivery_id) > MAX_DELIVERY_ID_LENGTH:
        return None
    return f"svix:{delivery_id}"
