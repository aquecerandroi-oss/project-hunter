"""Static security response headers — SECURITY.md §5.

HSTS is skipped in development (plain HTTP locally would otherwise get the
browser to force HTTPS on ``localhost``, which is not served over TLS).
``Cache-Control: no-store`` applies only to ``/api/*`` so `/health`,
``/metrics`` and static docs are unaffected.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

if TYPE_CHECKING:
    from starlette.middleware.base import RequestResponseEndpoint
    from starlette.types import ASGIApp

    from hunter_api.settings import ApiSettings

_PERMISSIONS_POLICY = "camera=(), microphone=(), geolocation=(), payment=()"
_HSTS = "max-age=63072000; includeSubDomains"


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    def __init__(self, app: ASGIApp, settings: ApiSettings) -> None:
        super().__init__(app)
        self._settings = settings

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Any:
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = _PERMISSIONS_POLICY
        if not self._settings.is_development:
            response.headers["Strict-Transport-Security"] = _HSTS
        if request.url.path.startswith("/api/"):
            response.headers["Cache-Control"] = "no-store"
        return response
