"""A size cap on ``/api/*`` request bodies — the declared one *and* the real one.

Every other guard in the stack — authentication, RBAC, Pydantic validation —
runs *after* the framework has pulled the request body into memory. So an
unauthenticated POST announcing a 100 MB body costs 100 MB of RAM before the
first check refuses it, and a handful of concurrent ones is an out-of-memory
kill on a container sized for JSON payloads.

Two checks, because one is not enough:

- **The header.** ``Content-Length`` over the limit is answered 413 without
  touching the receive channel at all — the cheapest possible refusal.
- **The stream.** ``Content-Length`` is written by the client, so it is a hint,
  not a fact: HTTP/1.1 chunked transfer sends no length at all, and a lying
  header is one line to write. This middleware therefore also counts the bytes
  it lets through and aborts the moment the running total passes the limit, so
  the most an oversized upload can cost is one chunk more than the cap.

A 413 raised mid-stream leaves unread bytes on the wire that no longer line up
with any framing the client expects, so the response carries ``Connection:
close`` and the server drops the connection after sending it. The application's
own response is suppressed from that point on: it is about to fail on a body it
will never finish reading, and one response per request is the contract.

This is deliberately the *outer* of the two size checks: the Clerk webhook
applies its own, much smaller cap (``services.webhook_delivery``), and routes
that will one day accept an upload can raise theirs — but nothing gets past
this one.

Only ``/api/*``: ``/metrics`` and ``/health`` carry no body, and a limit there
would be a limit on the orchestrator rather than on a caller.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

from starlette.requests import Request
from starlette.responses import JSONResponse

from hunter_api.errors import CONTENT_TYPE, PROBLEM_BASE

if TYPE_CHECKING:
    from starlette.types import ASGIApp, Message, Receive, Scope, Send

    from hunter_api.settings import ApiSettings

GUARDED_PREFIX = "/api/"
BODY_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})

_DISCONNECT: dict[str, str] = {"type": "http.disconnect"}


class BodySizeLimitMiddleware:
    """Pure ASGI, not ``BaseHTTPMiddleware``: the cap has to wrap ``receive``.

    ``BaseHTTPMiddleware`` hands its ``dispatch`` a ``Request`` whose body is
    already someone else's to read; only a middleware that sits on the raw
    three-argument ASGI signature can put a counter between the server and the
    application.
    """

    def __init__(self, app: ASGIApp, settings: ApiSettings) -> None:
        self._app = app
        self._limit = settings.max_request_body_bytes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or not _guarded(scope):
            await self._app(scope, receive, send)
            return

        request = Request(scope)
        declared = content_length(request)
        if declared is not None and declared > self._limit:
            await payload_too_large(request, self._limit)(scope, receive, send)
            return

        guard = _StreamGuard(request, self._limit, receive, send)
        try:
            await self._app(scope, guard.receive, guard.send)
        except Exception:
            # a body that stops mid-read is a disconnect as far as the
            # application is concerned, and it says so by raising. Once our own
            # 413 is on the wire that exception has already been answered
            if not guard.tripped:
                raise


class _StreamGuard:
    """One request's byte counter, sitting on both channels.

    On ``receive`` it adds up what it hands over; on ``send`` it drops whatever
    the application produces after the abort, so the 413 is the only response.
    """

    def __init__(self, request: Request, limit: int, receive: Receive, send: Send) -> None:
        self._request = request
        self._limit = limit
        self._receive = receive
        self._send = send
        self._seen = 0
        self._response_started = False
        self.tripped = False

    async def receive(self) -> Message:
        if self.tripped:
            return _DISCONNECT
        message = await self._receive()
        if message["type"] != "http.request":
            return message
        self._seen += len(cast("bytes", message.get("body", b"")))
        if self._seen <= self._limit:
            return message
        if await self._abort():
            return _DISCONNECT
        return message

    async def send(self, message: Message) -> None:
        if self.tripped:
            return
        if message["type"] == "http.response.start":
            self._response_started = True
        await self._send(message)

    async def _abort(self) -> bool:
        """Answer 413 and take over the response. ``False`` when it is too late.

        An application that has already started its response owns the wire, and
        a second ``http.response.start`` is a protocol violation — so in that
        (unreachable in practice: nothing answers before it has read the body)
        case the oversized body is simply passed through.
        """
        if self._response_started:
            return False
        response = payload_too_large(self._request, self._limit, close_connection=True)
        await response(self._request.scope, self._receive, self._send)
        self.tripped = True
        return True


def _guarded(scope: Scope) -> bool:
    path = scope.get("path", "")
    return scope.get("method") in BODY_METHODS and cast("str", path).startswith(GUARDED_PREFIX)


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


def payload_too_large(
    request: Request, limit: int, *, close_connection: bool = False
) -> JSONResponse:
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
    headers = {"Connection": "close"} if close_connection else None
    return JSONResponse(body, status_code=413, media_type=CONTENT_TYPE, headers=headers)
