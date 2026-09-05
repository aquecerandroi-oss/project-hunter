"""Request bodies are bounded twice: on the declared size and on the real one.

The failure this prevents is cheap to cause and expensive to absorb: one POST
announcing a 100 MB body, and the process reads 100 MB into memory before any
handler, any validation or any authentication runs. A few concurrent ones are
an out-of-memory kill on a container sized for JSON payloads.

The first check is on the header, and it happens before the body is ever pulled
off the receive channel — which is what the ``_post`` tests assert, by driving
the app with a ``receive`` that records whether it was called at all. The
second is on the stream itself, because ``Content-Length`` is written by the
client: a chunked upload declares nothing and a lying header is one line to
write. The ``_stream`` tests drive a receive channel that hands out a 60 MB
body one chunk at a time and count how much of it the application was allowed
to pull.
"""

from __future__ import annotations

import json
from collections.abc import MutableMapping
from typing import TYPE_CHECKING, Any

import pytest

from hunter_api.app import create_app

if TYPE_CHECKING:
    from collections.abc import Callable
    from contextlib import AbstractAsyncContextManager

    import httpx
    from fastapi import FastAPI

    from hunter_api.settings import ApiSettings

pytestmark = pytest.mark.unit

WEBHOOK_PATH = "/api/webhooks/clerk"
HUGE = 100 * 1024 * 1024
HUGE_STREAM = 60 * 1024 * 1024
LIMIT = 4096
CHUNK = 64 * 1024


class _Call:
    """One ASGI round trip, with the receive channel under observation."""

    def __init__(self) -> None:
        self.received = False
        self.messages: list[dict[str, Any]] = []

    async def receive(self) -> MutableMapping[str, Any]:
        self.received = True
        return {"type": "http.request", "body": b"{}", "more_body": False}

    async def send(self, message: MutableMapping[str, Any]) -> None:
        self.messages.append(dict(message))

    @property
    def _start(self) -> dict[str, Any]:
        return next(
            message for message in self.messages if message["type"] == "http.response.start"
        )

    @property
    def status(self) -> int:
        return int(self._start["status"])

    @property
    def headers(self) -> dict[str, str]:
        raw: list[tuple[bytes, bytes]] = self._start.get("headers", [])
        return {key.decode().lower(): value.decode() for key, value in raw}


async def _post(app: FastAPI, path: str, headers: list[tuple[bytes, bytes]]) -> _Call:
    call = _Call()
    scope: dict[str, Any] = {
        "type": "http",
        "asgi": {"version": "3.0", "spec_version": "2.3"},
        "http_version": "1.1",
        "method": "POST",
        "scheme": "http",
        "path": path,
        "raw_path": path.encode(),
        "query_string": b"",
        "root_path": "",
        "headers": [(b"host", b"testserver"), *headers],
        "client": ("10.0.0.1", 51234),
        "server": ("testserver", 80),
    }
    await app(scope, call.receive, call.send)
    return call


@pytest.fixture
def app(api_settings: ApiSettings) -> FastAPI:
    return create_app(api_settings.model_copy(update={"max_request_body_bytes": LIMIT}))


async def test_an_oversized_content_length_is_rejected_before_the_body_is_read(
    app: FastAPI,
) -> None:
    call = await _post(app, "/api/v1/orgs", [(b"content-length", str(HUGE).encode())])

    assert call.status == 413
    assert call.headers["content-type"].startswith("application/problem+json")
    assert call.received is False, "the body must never be pulled off the receive channel"


async def test_the_webhook_rejects_an_oversized_delivery_before_reading_it(
    app: FastAPI,
) -> None:
    """Svix's own cap is well under the global one, and the webhook is the
    single unauthenticated POST on the surface — the endpoint anybody who
    learns the URL can aim a large body at.
    """
    call = await _post(
        app,
        WEBHOOK_PATH,
        [(b"svix-id", b"msg_FAKE_1"), (b"content-length", str(HUGE).encode())],
    )

    assert call.status == 413
    assert call.received is False


async def test_the_webhook_refuses_a_delivery_with_no_content_length(app: FastAPI) -> None:
    # Svix always sends one; a delivery without it is either not Svix or a
    # chunked upload of unknown size, and neither can be size-checked
    call = await _post(app, WEBHOOK_PATH, [(b"svix-id", b"msg_FAKE_1")])

    assert call.status == 411
    assert call.received is False


async def test_the_webhook_refuses_an_unparseable_content_length(app: FastAPI) -> None:
    call = await _post(
        app,
        WEBHOOK_PATH,
        [(b"svix-id", b"msg_FAKE_1"), (b"content-length", b"not-a-number")],
    )

    assert call.status in (400, 411)
    assert call.received is False


async def test_a_body_within_the_limit_is_read_normally(
    api_settings: ApiSettings,
    client_factory: Callable[[FastAPI], AbstractAsyncContextManager[httpx.AsyncClient]],
) -> None:
    application = create_app(api_settings)

    async with client_factory(application) as test_client:
        response = await test_client.post("/api/v1/orgs", json={"name": "Under The Limit"})

    # no token, so 401 — the point is that the guard did not get in the way
    assert response.status_code == 401


class _StreamedCall(_Call):
    """A receive channel that hands out a large body one chunk at a time.

    ``consumed`` is the number of bytes the application was actually allowed
    to pull off the channel — the figure the streaming cap has to bound. A
    ``Content-Length`` that lies (or is absent entirely, as on a chunked
    upload) buys nothing if this stays small.
    """

    def __init__(self, total: int, chunk: int = CHUNK, payload: bytes | None = None) -> None:
        super().__init__()
        self.payload = payload
        self.remaining = len(payload) if payload is not None else total
        self.chunk = chunk
        self.consumed = 0

    async def receive(self) -> MutableMapping[str, Any]:
        self.received = True
        if self.remaining <= 0:
            return {"type": "http.disconnect"}
        size = min(self.chunk, self.remaining)
        start, self.consumed = self.consumed, self.consumed + size
        self.remaining -= size
        chunk = self.payload[start : start + size] if self.payload is not None else b"\0" * size
        return {"type": "http.request", "body": chunk, "more_body": self.remaining > 0}


async def _stream(
    app: FastAPI,
    headers: list[tuple[bytes, bytes]],
    total: int,
    payload: bytes | None = None,
) -> _StreamedCall:
    call = _StreamedCall(total, payload=payload)
    scope: dict[str, Any] = {
        "type": "http",
        "asgi": {"version": "3.0", "spec_version": "2.3"},
        "http_version": "1.1",
        "method": "POST",
        "scheme": "http",
        "path": "/api/v1/orgs",
        "raw_path": b"/api/v1/orgs",
        "query_string": b"",
        "root_path": "",
        "headers": [(b"host", b"testserver"), (b"content-type", b"application/json"), *headers],
        "client": ("10.0.0.1", 51234),
        "server": ("testserver", 80),
    }
    # unlike ``_post`` above, these tests reach past routing into the handler,
    # which reads ``app.state`` — populated by the lifespan, not by ``create_app``
    async with app.router.lifespan_context(app):
        await app(scope, call.receive, call.send)
    return call


async def test_a_chunked_upload_with_no_content_length_is_cut_off_at_the_limit(
    app: FastAPI,
) -> None:
    """``Content-Length`` is optional, so a cap that only reads that header is
    a cap a client opts into. A chunked upload announces nothing and streams
    60 MB into a process sized for JSON payloads; the running count is the
    only thing that stops it.
    """
    call = await _stream(app, [(b"transfer-encoding", b"chunked")], HUGE_STREAM)

    assert call.status == 413
    assert call.headers["content-type"].startswith("application/problem+json")
    assert call.consumed <= LIMIT + CHUNK, (
        f"the cap must bite within one chunk of the limit, not after {call.consumed} bytes"
    )
    assert call.headers.get("connection") == "close", (
        "a 413 sent mid-stream leaves unread bytes on the wire; the connection has to go"
    )


async def test_a_content_length_that_lies_about_a_huge_body_is_still_cut_off(
    app: FastAPI,
) -> None:
    """The header is written by the client, so it is a hint, not a fact."""
    call = await _stream(app, [(b"content-length", b"10")], HUGE_STREAM)

    assert call.status == 413
    assert call.consumed <= LIMIT + CHUNK


async def test_a_streamed_body_under_the_limit_reaches_the_application(app: FastAPI) -> None:
    payload = json.dumps({"name": "Under The Limit"}).encode()
    call = await _stream(
        app,
        [(b"content-length", str(len(payload)).encode())],
        0,
        payload=payload,
    )

    # no token, so 401 — the point is that the body arrived whole and the
    # guard neither refused it nor truncated it
    assert call.status == 401
    assert call.consumed == len(payload)
