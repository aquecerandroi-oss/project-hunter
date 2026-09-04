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

Close codes: ``4401`` unauthenticated (bad, missing or late token), ``4400``
protocol error (unparseable frame, unknown message type), ``4408`` no pong.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
from typing import TYPE_CHECKING, Any, cast

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from hunter_api.auth.clerk import InvalidTokenError
from hunter_api.auth.principal import ProvisioningError, principal_from_token
from hunter_api.realtime.channels import (
    MAX_CHANNELS_PER_CONNECTION,
    is_authorized,
    throttle_class,
)
from hunter_api.realtime.redis_bridge import RedisBridge, RedisClientLike
from hunter_api.realtime.throttle import DEFAULT_INTERVALS_MS, Throttle
from hunter_api.realtime.ws_manager import ConnectionManager
from hunter_core.logging import get_logger

if TYPE_CHECKING:
    from hunter_api.auth.principal import Principal

router = APIRouter()
logger = get_logger(__name__)

AUTH_TIMEOUT_SECONDS = 5
PING_INTERVAL_SECONDS = 25
MAX_FRAME_BYTES = 16 * 1024

WS_AUTH_REQUIRED_CODE = 4401
WS_PROTOCOL_ERROR_CODE = 4400
WS_PONG_TIMEOUT_CODE = 4408


class RealtimeHub:
    """Owns the process-wide fan-out: Redis pub/sub in, WebSockets out.

    One bridge and one connection manager per process. A channel is subscribed
    in Redis when its first client asks for it and dropped when its last one
    leaves, so an idle deployment holds no subscriptions at all.
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

    async def detach(self, connection: WebSocket) -> None:
        channels = [
            channel
            for channel in self.manager.channels()
            if self.manager.subscriber_count(channel) > 0
        ]
        self.manager.unsubscribe_all(connection)
        for channel in channels:
            if self.manager.subscriber_count(channel) == 0:
                await self._bridge.unsubscribe(channel)

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
    await websocket.accept()
    principal = await _authenticate(websocket)
    if principal is None:
        return
    hub: RealtimeHub = websocket.app.state.realtime
    await websocket.send_text(json.dumps({"type": "authenticated"}))
    heartbeat = asyncio.ensure_future(_heartbeat(websocket))
    try:
        await _serve(websocket, principal, hub)
    finally:
        heartbeat.cancel()
        with contextlib.suppress(asyncio.CancelledError, Exception):
            await heartbeat
        await hub.detach(websocket)


async def _authenticate(websocket: WebSocket) -> Principal | None:
    """The first frame, or 4401. Never logs the token."""
    try:
        raw = await asyncio.wait_for(websocket.receive_text(), timeout=AUTH_TIMEOUT_SECONDS)
    except TimeoutError:
        await _close(websocket, WS_AUTH_REQUIRED_CODE, "authentication timeout")
        return None
    except WebSocketDisconnect:
        return None

    message = _parse(raw)
    if message is None or message.get("type") != "auth":
        await _close(websocket, WS_AUTH_REQUIRED_CODE, "authentication required")
        return None
    token = message.get("token")
    if not isinstance(token, str):
        await _close(websocket, WS_AUTH_REQUIRED_CODE, "authentication required")
        return None
    try:
        return await principal_from_token(
            token,
            provider=websocket.app.state.auth_provider,
            resolver=websocket.app.state.principal_resolver,
        )
    except (InvalidTokenError, ProvisioningError):
        logger.info("ws_auth_rejected")
        await _close(websocket, WS_AUTH_REQUIRED_CODE, "authentication failed")
        return None


async def _serve(websocket: WebSocket, principal: Principal, hub: RealtimeHub) -> None:
    subscribed: set[str] = set()
    while True:
        try:
            raw = await websocket.receive_text()
        except WebSocketDisconnect:
            return
        message = _parse(raw)
        if message is None:
            await _close(websocket, WS_PROTOCOL_ERROR_CODE, "malformed frame")
            return
        kind = message.get("type")
        if kind == "pong":
            _mark_pong(websocket)
        elif kind == "ping":
            await websocket.send_text(json.dumps({"type": "pong"}))
        elif kind == "subscribe":
            await _subscribe(websocket, principal, hub, message, subscribed)
        elif kind == "unsubscribe":
            for channel in _channels(message):
                subscribed.discard(channel)
                await hub.unsubscribe(websocket, channel)
        else:
            await _close(websocket, WS_PROTOCOL_ERROR_CODE, "unknown message type")
            return


async def _subscribe(
    websocket: WebSocket,
    principal: Principal,
    hub: RealtimeHub,
    message: dict[str, Any],
    subscribed: set[str],
) -> None:
    accepted: list[str] = []
    for channel in _channels(message):
        if len(subscribed) >= MAX_CHANNELS_PER_CONNECTION:
            await _error(websocket, "too_many_channels", channel)
            break
        if not is_authorized(channel, principal):
            logger.info("ws_channel_denied", principal_id=str(principal.user_id))
            await _error(websocket, "forbidden_channel", channel)
            continue
        await hub.subscribe(websocket, channel)
        subscribed.add(channel)
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
    with contextlib.suppress(Exception):
        await websocket.close(code=code, reason=reason)
