"""``/ws`` — the WebSocket gateway.

Protocol (ARCHITECTURE.md §5.2, SECURITY.md §1):

1. the client connects and sends ``{"type":"auth","token":"<jwt>"}`` within
   5 seconds. The token travels in the first *message*, never in the query
   string: a URL lands in proxy logs, browser history and ``Referer`` headers,
   and a session token that leaks there is a session anybody can resume.
2. the server answers ``{"type":"authenticated"}``, and from then on the
   client may ``subscribe``/``unsubscribe``. Every channel is authorized
   against the principal's memberships (``channels.is_authorized``); an
   unauthorized one is refused individually with ``forbidden_channel`` rather
   than closing the socket, so one bad name in a batch does not drop a working
   connection.
3. the server sends ``{"type":"ping"}`` every 25 s and expects ``pong``. A
   client that misses one is closed with 4408 — TCP alone will happily hold a
   dead connection open for minutes, which shows up as a browser that has
   silently stopped receiving prices.
4. membership is re-checked every ``ws_revalidate_interval_s`` for as long as
   the socket lives (``realtime.session``), because a subscription authorized
   an hour ago is not evidence of anything now.

Two limits bound what a caller can hold here, because a socket is cheap to
open and expensive to keep: an address may only complete
``ws_handshakes_per_minute`` handshakes (checked *before* ``accept()``, so a
refused one costs a header parse), and a principal may only hold
``ws_max_connections_per_principal`` live connections on this process. Both
answer ``4429``.

Close codes: ``4401`` unauthenticated (bad, missing or late token), ``4400``
protocol error (unparseable frame, unknown message type), ``4403`` membership
revoked while connected, ``4408`` no pong, ``4409`` idle, ``4429`` too many
handshakes or too many connections for this principal, ``4503``
authentication temporarily unavailable (the JWKS could not be fetched — the
credential was never judged, so this is not a 4401). ``44xx`` codes are
application-defined (RFC 6455 §7.4.2); the client maps them in
``apps/web``'s realtime hook.

Every close this gateway performs, or merely observes (a client hanging up
while a caller here is still waiting on a frame), logs one ``ws_closed`` line
(``code``, ``reason``, ``client``, ``authenticated``, ``duration_ms``) and
increments ``hunter_ws_closed_total{code}`` — see
``realtime.session.log_ws_closed``. T3.44b: a 4401 used to close in silence
whenever the auth frame's token was missing or not a string, which hid a
race in the browser's own auth flow for days.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
from typing import TYPE_CHECKING, Any, cast

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from hunter_api.auth.clerk import AuthUnavailableError, InvalidTokenError
from hunter_api.auth.principal import ProvisioningError
from hunter_api.realtime.admission import connection_cap, handshake_allowed
from hunter_api.realtime.channels import (
    MAX_CHANNELS_PER_CONNECTION,
    is_authorized,
    throttle_class,
)
from hunter_api.realtime.redis_bridge import RedisBridge, RedisClientLike
from hunter_api.realtime.session import (
    WsSession,
    close_socket,
    log_ws_closed,
    mark_connected,
    watch_session,
)
from hunter_api.realtime.throttle import DEFAULT_INTERVALS_MS, Throttle
from hunter_api.realtime.ws_manager import ConnectionManager
from hunter_core.logging import get_logger

if TYPE_CHECKING:
    from hunter_api.auth.clerk import AuthProvider

router = APIRouter()
logger = get_logger(__name__)

AUTH_TIMEOUT_SECONDS = 5
PING_INTERVAL_SECONDS = 25
MAX_FRAME_BYTES = 16 * 1024

WS_AUTH_REQUIRED_CODE = 4401
WS_PROTOCOL_ERROR_CODE = 4400
WS_PONG_TIMEOUT_CODE = 4408
WS_TOO_MANY_CODE = 4429
WS_AUTH_UNAVAILABLE_CODE = 4503


class RealtimeHub:
    """Owns the process-wide fan-out: Redis pub/sub in, WebSockets out.

    One bridge and one connection manager per process. A channel is subscribed
    in Redis when its first client asks for it and dropped -- with all of its
    per-channel state, see :meth:`_forget` -- when its last one leaves, so an
    idle deployment holds no subscriptions at all.
    """

    def __init__(self, redis_client: RedisClientLike) -> None:
        self.manager = ConnectionManager()
        self._intervals: dict[str, int] = {}
        self._throttle = Throttle(self._intervals, default_ms=0)
        self._bridge = RedisBridge(redis_client, self.dispatch)

    async def subscribe(self, connection: WebSocket, channel: str) -> None:
        self._intervals.setdefault(channel, DEFAULT_INTERVALS_MS[throttle_class(channel)])
        self.manager.subscribe(connection, channel)
        await self._bridge.ensure_subscribed(channel)

    async def unsubscribe(self, connection: WebSocket, channel: str) -> None:
        self.manager.unsubscribe(connection, channel)
        if self.manager.subscriber_count(channel) == 0:
            await self._bridge.unsubscribe(channel)
            self._forget(channel)

    def _forget(self, channel: str) -> None:
        """Per-channel state dies with its last subscriber: names are client-
        supplied and a live socket has no per-message rate limit, so a
        subscribe/unsubscribe loop grew these dicts until the process ran out
        of memory (T1.6b security review, 2026-09-05)."""
        self._intervals.pop(channel, None)
        self._throttle.forget(channel)

    async def detach(self, connection: WebSocket) -> None:
        self.manager.release(connection)
        channels = [c for c in self.manager.channels() if self.manager.subscriber_count(c) > 0]
        self.manager.unsubscribe_all(connection)
        for channel in channels:
            if self.manager.subscriber_count(channel) == 0:
                await self._bridge.unsubscribe(channel)
                self._forget(channel)

    async def close(self) -> None:
        await self._bridge.close()

    async def dispatch(self, channel: str, payload: bytes) -> None:
        """One Redis message out to every subscriber, throttled per channel.

        ``create_redis`` builds the client with ``decode_responses=False``
        (payloads are orjson bytes), so this decodes once here rather than
        letting every consumer guess.
        """
        if not self._throttle.should_emit(channel):
            return
        body = payload.decode(errors="replace")
        await self.manager.broadcast(channel, json.dumps({"channel": channel, "data": body}))


@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket) -> None:
    if not await handshake_allowed(websocket):
        # before accept(): Starlette turns this into a rejected handshake, so
        # nothing is spent on a connection we are not going to keep
        await _close(websocket, WS_TOO_MANY_CODE, "too many handshakes")
        return
    await websocket.accept()
    mark_connected(websocket)
    session = await _authenticate(websocket)
    if session is None:
        return
    hub: RealtimeHub = websocket.app.state.realtime
    principal_id = str(session.principal.user_id)
    if not hub.manager.try_register(websocket, principal_id, connection_cap(websocket)):
        logger.info("ws_connection_cap_reached", principal_id=principal_id)
        await _close(websocket, WS_TOO_MANY_CODE, "too many connections")
        return
    await websocket.send_text(json.dumps({"type": "authenticated"}))
    heartbeat = asyncio.ensure_future(_heartbeat(websocket))
    watchdog = asyncio.ensure_future(watch_session(websocket, session, hub))
    try:
        await _serve(websocket, session, hub)
    finally:
        for task in (heartbeat, watchdog):
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await task
        await hub.detach(websocket)


async def _authenticate(websocket: WebSocket) -> WsSession | None:
    """The first frame, or a close. Never logs the token.

    The verified claims are kept on the session, not the token: revalidation
    needs to re-resolve the same identity later, and a live credential is not
    something to hold for the lifetime of a connection.
    """
    try:
        raw = await asyncio.wait_for(websocket.receive_text(), timeout=AUTH_TIMEOUT_SECONDS)
    except TimeoutError:
        await _close(websocket, WS_AUTH_REQUIRED_CODE, "authentication timeout")
        return None
    except WebSocketDisconnect as exc:
        # the client hung up on its own before sending an auth frame at all —
        # never went through close_socket(), so it never got a ws_closed line
        log_ws_closed(websocket, exc.code, exc.reason or "client disconnected")
        return None

    message = _parse(raw)
    if message is None or message.get("type") != "auth":
        await _close(websocket, WS_AUTH_REQUIRED_CODE, "authentication required")
        return None
    token = message.get("token")
    if not isinstance(token, str) or not token:
        await _close(websocket, WS_AUTH_REQUIRED_CODE, "authentication required")
        return None
    provider: AuthProvider = websocket.app.state.auth_provider
    try:
        claims = await provider.verify(token)
        principal = await websocket.app.state.principal_resolver.resolve(claims)
    except AuthUnavailableError:
        # the token was never judged — telling the client its credential is
        # bad would send it to re-authenticate through the provider that is
        # the thing currently unavailable
        logger.warning("ws_auth_unavailable")
        await _close(websocket, WS_AUTH_UNAVAILABLE_CODE, "authentication unavailable")
        return None
    except (InvalidTokenError, ProvisioningError):
        logger.info("ws_auth_rejected")
        await _close(websocket, WS_AUTH_REQUIRED_CODE, "authentication failed")
        return None
    websocket.state.authenticated = True
    return WsSession(principal, claims)


async def _serve(websocket: WebSocket, session: WsSession, hub: RealtimeHub) -> None:
    while True:
        try:
            raw = await websocket.receive_text()
        except WebSocketDisconnect as exc:
            log_ws_closed(websocket, exc.code, exc.reason or "client disconnected")
            return
        message = _parse(raw)
        if message is None:
            await _close(websocket, WS_PROTOCOL_ERROR_CODE, "malformed frame")
            return
        kind = message.get("type")
        if kind == "pong":
            # deliberately *not* mark_frame(): a pong is our own heartbeat
            # coming back, which a browser answers whether or not anybody is
            # using the tab. Counting it as activity would leave the idle
            # timeout unable to fire for exactly the connections it exists for
            _mark_pong(websocket)
            continue
        session.mark_frame()
        if kind == "ping":
            await websocket.send_text(json.dumps({"type": "pong"}))
        elif kind == "subscribe":
            await _subscribe(websocket, session, hub, message)
        elif kind == "unsubscribe":
            for channel in _channels(message):
                session.subscribed.discard(channel)
                await hub.unsubscribe(websocket, channel)
        else:
            await _close(websocket, WS_PROTOCOL_ERROR_CODE, "unknown message type")
            return


async def _subscribe(
    websocket: WebSocket,
    session: WsSession,
    hub: RealtimeHub,
    message: dict[str, Any],
) -> None:
    accepted: list[str] = []
    for channel in _channels(message):
        if len(session.subscribed) >= MAX_CHANNELS_PER_CONNECTION:
            await _error(websocket, "too_many_channels", channel)
            break
        if not is_authorized(channel, session.principal):
            logger.info("ws_channel_denied", principal_id=str(session.principal.user_id))
            await _error(websocket, "forbidden_channel", channel)
            continue
        await hub.subscribe(websocket, channel)
        session.subscribed.add(channel)
        accepted.append(channel)
    await websocket.send_text(json.dumps({"type": "subscribed", "channels": accepted}))


async def _heartbeat(websocket: WebSocket) -> None:
    """Ping every ``PING_INTERVAL_SECONDS``; close 4408 if the last one went
    unanswered. The pong flag is stamped on the socket by the receive loop,
    which is the only place frames are read.
    """
    websocket.state.pong_pending = False
    while True:
        await asyncio.sleep(PING_INTERVAL_SECONDS)
        if getattr(websocket.state, "pong_pending", False):
            await _close(websocket, WS_PONG_TIMEOUT_CODE, "pong timeout")
            return
        websocket.state.pong_pending = True
        try:
            await websocket.send_text(json.dumps({"type": "ping"}))
        except Exception:
            return


def _mark_pong(websocket: WebSocket) -> None:
    websocket.state.pong_pending = False


def _channels(message: dict[str, Any]) -> list[str]:
    raw = message.get("channels")
    if not isinstance(raw, list):
        return []
    values = cast("list[object]", raw)
    return [value for value in values if isinstance(value, str)][:MAX_CHANNELS_PER_CONNECTION]


def _parse(raw: str) -> dict[str, Any] | None:
    if len(raw) > MAX_FRAME_BYTES:
        return None
    try:
        data: object = json.loads(raw)
    except ValueError:
        return None
    return cast("dict[str, Any]", data) if isinstance(data, dict) else None


async def _error(websocket: WebSocket, code: str, channel: str) -> None:
    await websocket.send_text(json.dumps({"type": "error", "code": code, "channel": channel}))


async def _close(websocket: WebSocket, code: int, reason: str) -> None:
    await close_socket(websocket, code, reason)
