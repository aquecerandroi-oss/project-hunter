"""Placeholder tenant-context middleware.

T06 authenticates the request (Clerk JWT → ``Principal``) and, on tenant
routes, resolves ``org_id`` from the route plus membership, applying RBAC and
``SET LOCAL app.current_org`` for RLS (ARCHITECTURE.md §9, SECURITY.md §3).
None of that exists yet. This middleware only guarantees
``request.state.org_id`` is always present (as ``None``) so downstream code
(logging, rate limiting) can read it unconditionally instead of every caller
needing ``getattr(..., None)``. It does not authenticate, authorize, or touch
Postgres — completed in T06.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

if TYPE_CHECKING:
    from starlette.middleware.base import RequestResponseEndpoint
    from starlette.types import ASGIApp


class TenantContextMiddleware(BaseHTTPMiddleware):
    def __init__(self, app: ASGIApp) -> None:
        super().__init__(app)

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Any:
        request.state.org_id = None
        return await call_next(request)
