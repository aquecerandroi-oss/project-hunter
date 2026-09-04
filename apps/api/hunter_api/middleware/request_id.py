"""``X-Request-ID``: read the inbound header or mint a uuid7, bind it to the
structlog context for the duration of the request, and echo it back.

ARCHITECTURE.md §11: "Logs JSON com request_id, org_id, role, event_id."
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

from hunter_core.domain.types import uuid7
from hunter_core.logging import bind_context, clear_context

if TYPE_CHECKING:
    from starlette.middleware.base import RequestResponseEndpoint
    from starlette.types import ASGIApp

REQUEST_ID_HEADER = "X-Request-ID"


class RequestIdMiddleware(BaseHTTPMiddleware):
    """Outermost middleware: every response, including error responses
    produced deeper in the stack, gets ``request.state.request_id`` set
    before anything else runs and the header echoed back last.
    """

    def __init__(self, app: ASGIApp) -> None:
        super().__init__(app)

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Any:
        request_id = request.headers.get(REQUEST_ID_HEADER) or str(uuid7())
        request.state.request_id = request_id
        bind_context(request_id=request_id)
        try:
            response = await call_next(request)
        finally:
            clear_context()
        response.headers[REQUEST_ID_HEADER] = request_id
        return response
