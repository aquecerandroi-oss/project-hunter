"""Gates the mounted ``/metrics`` Prometheus endpoint (``app.py``).

Three regimes, controlled by ``ApiSettings.metrics_token`` and
``hunter_env``:

* ``METRICS_TOKEN`` set — every request needs
  ``Authorization: Bearer <token>``, compared with ``hmac.compare_digest``
  to avoid a timing side-channel; anything else is a 401 problem+json.
* ``METRICS_TOKEN`` unset in ``staging``/``production`` — ``/metrics`` is
  hidden (404 problem+json) rather than served unauthenticated to whatever
  can reach the ingress; ``app.py``'s startup also logs a warning so this
  is never silent.
* ``METRICS_TOKEN`` unset in ``development``/``test`` — open, matching the
  rest of the api's unauthenticated local-dev posture.
"""

from __future__ import annotations

import hmac
from typing import TYPE_CHECKING, Any

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

from hunter_api.errors import CONTENT_TYPE, PROBLEM_BASE

if TYPE_CHECKING:
    from starlette.middleware.base import RequestResponseEndpoint
    from starlette.types import ASGIApp

    from hunter_api.settings import ApiSettings

METRICS_PATH = "/metrics"
_GATED_ENVIRONMENTS = frozenset({"staging", "production"})


class MetricsAuthMiddleware(BaseHTTPMiddleware):
    def __init__(self, app: ASGIApp, settings: ApiSettings) -> None:
        super().__init__(app)
        self._settings = settings

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Any:
        if not request.url.path.startswith(METRICS_PATH):
            return await call_next(request)

        token = self._settings.metrics_token
        if token is not None and token.get_secret_value():
            expected = f"Bearer {token.get_secret_value()}"
            provided = request.headers.get("authorization", "")
            if not hmac.compare_digest(provided, expected):
                return _unauthorized(request)
        elif self._settings.hunter_env in _GATED_ENVIRONMENTS:
            return _not_found(request)

        return await call_next(request)


def _unauthorized(request: Request) -> JSONResponse:
    return JSONResponse(
        {
            "type": f"{PROBLEM_BASE}/unauthorized",
            "title": "Unauthorized",
            "status": 401,
            "detail": "Missing or invalid metrics token.",
            "instance": request.url.path,
        },
        status_code=401,
        media_type=CONTENT_TYPE,
    )


def _not_found(request: Request) -> JSONResponse:
    return JSONResponse(
        {
            "type": f"{PROBLEM_BASE}/not-found",
            "title": "Not Found",
            "status": 404,
            "detail": "Not Found",
            "instance": request.url.path,
        },
        status_code=404,
        media_type=CONTENT_TYPE,
    )
