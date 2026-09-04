"""A ``Content-Length`` cap on ``/api/*``, checked before the body is read.

Every other guard in the stack — authentication, RBAC, Pydantic validation —
runs *after* the framework has pulled the request body into memory. So an
unauthenticated POST announcing a 100 MB body costs 100 MB of RAM before the
first check refuses it, and a handful of concurrent ones is an out-of-memory
kill on a container sized for JSON payloads.

This middleware reads one header and answers 413 without touching the receive
channel. It is deliberately the *outer* of the two size checks: the Clerk
webhook applies its own, much smaller cap (``services.clerk_webhook``), and
routes that will one day accept an upload can raise theirs — but nothing gets
past this one.

Only ``/api/*``: ``/metrics`` and ``/health`` carry no body, and a limit there
would be a limit on the orchestrator rather than on a caller.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

from hunter_api.errors import CONTENT_TYPE, PROBLEM_BASE

if TYPE_CHECKING:
    from starlette.middleware.base import RequestResponseEndpoint
    from starlette.types import ASGIApp

    from hunter_api.settings import ApiSettings

GUARDED_PREFIX = "/api/"
BODY_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})


class BodySizeLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app: ASGIApp, settings: ApiSettings) -> None:
        super().__init__(app)
        self._limit = settings.max_request_body_bytes

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Any:
        if request.method in BODY_METHODS and request.url.path.startswith(GUARDED_PREFIX):
            declared = content_length(request)
            if declared is not None and declared > self._limit:
                return payload_too_large(request, self._limit)
        return await call_next(request)


def content_length(request: Request) -> int | None:
    """The declared body size, or ``None`` when there is no usable header.

    ``None`` covers both "absent" and "not a number": a chunked upload sends
    no ``Content-Length`` at all, and callers that need the header to exist
    (the Clerk webhook) check for ``None`` themselves rather than having this
    function invent a size.
    """
    raw = request.headers.get("content-length")
    if raw is None:
        return None
    try:
        value = int(raw)
    except ValueError:
        return None
    return value if value >= 0 else None


def payload_too_large(request: Request, limit: int) -> JSONResponse:
    body: dict[str, Any] = {
        "type": f"{PROBLEM_BASE}/payload-too-large",
        "title": "Content Too Large",
        "status": 413,
        "detail": f"The request body must not exceed {limit} bytes.",
        "instance": request.url.path,
    }
    request_id = getattr(request.state, "request_id", None)
    if request_id is not None:
        body["request_id"] = request_id
    return JSONResponse(body, status_code=413, media_type=CONTENT_TYPE)
