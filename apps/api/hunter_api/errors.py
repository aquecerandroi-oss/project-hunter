"""RFC 9457 ``application/problem+json`` error responses.

https://www.rfc-editor.org/rfc/rfc9457 — every error the API returns carries
``type``, ``title``, ``status``, ``detail`` and ``instance``. ``type`` values
are placeholder URIs under ``https://hunter.dev/problems/<slug>``; RFC 9457
only requires ``type`` to identify the problem consistently, not to resolve
as a real page.

``HTTPException`` and ``RequestValidationError`` are registered as ordinary
FastAPI exception handlers (Starlette dispatches them from *inside* the
middleware stack, so security headers / CORS / request-id still apply to
their responses). A bare ``Exception`` is deliberately **not** registered
that way: Starlette treats a handler keyed on ``Exception`` as the
outermost ``ServerErrorMiddleware`` fallback, which sits *outside* every
``add_middleware`` layer — a response built there would be missing the
request-id header and security headers. ``ProblemDetailsMiddleware`` below
catches unexpected exceptions itself, from inside the stack, so those
headers are still applied.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import TYPE_CHECKING, Any

from fastapi import status
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

from hunter_core.logging import get_logger

if TYPE_CHECKING:
    from fastapi import FastAPI
    from starlette.middleware.base import RequestResponseEndpoint
    from starlette.types import ASGIApp

logger = get_logger(__name__)

PROBLEM_BASE = "https://hunter.dev/problems"
CONTENT_TYPE = "application/problem+json"

_STATUS_TITLES: dict[int, str] = {
    400: "Bad Request",
    401: "Unauthorized",
    403: "Forbidden",
    404: "Not Found",
    405: "Method Not Allowed",
    409: "Conflict",
    411: "Length Required",
    413: "Content Too Large",
    429: "Too Many Requests",
    503: "Service Unavailable",
}


class HunterError(Exception):
    """Base for application errors that map directly to a problem+json response.

    ``instance`` is deliberately not a constructor argument: it is always the
    request path, filled in by the handler at response time.
    """

    def __init__(
        self,
        *,
        type_slug: str,
        title: str,
        status_code: int,
        detail: str | None = None,
        headers: Mapping[str, str] | None = None,
    ) -> None:
        self.type = f"{PROBLEM_BASE}/{type_slug}"
        self.title = title
        self.status_code = status_code
        self.detail = detail
        self.headers = dict(headers or {})
        """Response headers the problem needs to be actionable — ``Retry-After``
        on a 503 is the whole difference between "come back in a minute" and a
        client that retries immediately and makes the outage worse."""
        super().__init__(detail or title)


def _title_for_status(status_code: int) -> str:
    return _STATUS_TITLES.get(status_code, "Error")


def _slug_for_status(status_code: int) -> str:
    return _title_for_status(status_code).lower().replace(" ", "-")


def _problem_response(
    request: Request,
    *,
    type_: str,
    title: str,
    status_code: int,
    detail: str | None = None,
    extra: dict[str, Any] | None = None,
    headers: Mapping[str, str] | None = None,
) -> JSONResponse:
    body: dict[str, Any] = {
        "type": type_,
        "title": title,
        "status": status_code,
        "detail": detail,
        "instance": request.url.path,
    }
    request_id = getattr(request.state, "request_id", None)
    if request_id is not None:
        body["request_id"] = request_id
    if extra:
        body.update(extra)
    return JSONResponse(
        body,
        status_code=status_code,
        media_type=CONTENT_TYPE,
        headers=dict(headers) if headers else None,
    )


async def hunter_error_handler(request: Request, exc: Exception) -> JSONResponse:
    """Registered for :class:`HunterError`; typed ``exc: Exception`` because
    Starlette's ``ExceptionHandler`` is contravariant in its exception
    parameter (a handler must accept anything callable-compatible with
    ``Exception``) — the ``assert`` recovers the narrow type FastAPI
    guarantees at runtime for a handler registered under a specific key.
    """
    assert isinstance(exc, HunterError)
    return _problem_response(
        request,
        type_=exc.type,
        title=exc.title,
        status_code=exc.status_code,
        detail=exc.detail,
        headers=exc.headers,
    )


async def http_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, StarletteHTTPException)
    detail = exc.detail
    return _problem_response(
        request,
        type_=f"{PROBLEM_BASE}/{_slug_for_status(exc.status_code)}",
        title=_title_for_status(exc.status_code),
        status_code=exc.status_code,
        detail=detail,
    )


_UNSAFE_ERROR_KEYS = frozenset({"input", "url", "ctx"})


def _sanitize_validation_errors(
    errors: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    """Strip ``input``/``url``/``ctx`` from each ``exc.errors()`` entry.

    Pydantic v2 echoes the raw submitted value back in ``input`` (and
    sometimes structured context in ``ctx``) so callers can build a rich
    error UI — but that means an invalid ``Authorization`` header or a
    sensitive body field would otherwise round-trip verbatim into a 422
    response body. ``loc``/``type``/``msg`` are enough to fix a request
    without ever echoing what was submitted.
    """
    return [
        {key: value for key, value in error.items() if key not in _UNSAFE_ERROR_KEYS}
        for error in errors
    ]


async def validation_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, RequestValidationError)
    return _problem_response(
        request,
        type_=f"{PROBLEM_BASE}/validation-error",
        title="Validation Error",
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        detail="One or more fields failed validation.",
        extra={"errors": _sanitize_validation_errors(exc.errors())},
    )


class ProblemDetailsMiddleware(BaseHTTPMiddleware):
    """Catches any exception that escapes routing/``HTTPException`` handling
    and turns it into a problem+json 500 — no internals leaked, traceback
    logged with the request id for correlation.
    """

    def __init__(self, app: ASGIApp) -> None:
        super().__init__(app)

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Any:
        try:
            return await call_next(request)
        except Exception as exc:
            request_id = getattr(request.state, "request_id", None)
            logger.error("unhandled_exception", exc_info=exc, request_id=request_id)
            return _problem_response(
                request,
                type_=f"{PROBLEM_BASE}/internal-server-error",
                title="Internal Server Error",
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="An unexpected error occurred.",
            )


def register_error_handlers(app: FastAPI) -> None:
    """Wire ``HunterError``/``HTTPException``/``RequestValidationError`` handlers.

    Unexpected exceptions are handled by :class:`ProblemDetailsMiddleware`
    (added separately in ``app.py``), not here — see the module docstring.
    """
    app.add_exception_handler(HunterError, hunter_error_handler)
    app.add_exception_handler(StarletteHTTPException, http_exception_handler)
    app.add_exception_handler(RequestValidationError, validation_exception_handler)
