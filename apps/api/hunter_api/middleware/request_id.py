"""``X-Request-ID``: read the inbound header or mint a uuid7, bind it to the
structlog context for the duration of the request, and echo it back.

ARCHITECTURE.md §11: "Logs JSON com request_id, org_id, role, event_id." An
inbound value is only trusted if it's a short, plain token (``MAX_LENGTH``
chars of ``[A-Za-z0-9._-]``) — it ends up in log lines and response headers
unescaped, so anything else (oversized, or carrying header-injection /
markup characters) is discarded in favor of a minted id instead.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

from hunter_core.domain.types import uuid7
from hunter_core.logging import bind_context, clear_context

if TYPE_CHECKING:
    from starlette.middleware.base import RequestResponseEndpoint
    from starlette.types import ASGIApp

REQUEST_ID_HEADER = "X-Request-ID"
MAX_LENGTH = 128
_VALID_REQUEST_ID_RE = re.compile(rf"^[A-Za-z0-9._-]{{1,{MAX_LENGTH}}}$")


def _clean_inbound_request_id(value: str | None) -> str | None:
    if value is not None and _VALID_REQUEST_ID_RE.match(value):
        return value
    return None


class RequestIdMiddleware(BaseHTTPMiddleware):
    """Outermost middleware: every response, including error responses
    produced deeper in the stack, gets ``request.state.request_id`` set
    before anything else runs and the header echoed back last.
    """

    def __init__(self, app: ASGIApp) -> None:
        super().__init__(app)

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Any:
        inbound = _clean_inbound_request_id(request.headers.get(REQUEST_ID_HEADER))
        request_id = inbound or str(uuid7())
        request.state.request_id = request_id
        bind_context(request_id=request_id)
        try:
            response = await call_next(request)
        finally:
            clear_context()
        response.headers[REQUEST_ID_HEADER] = request_id
        return response
