"""Solana RPC WebSocket client — ``logsSubscribe``/``accountSubscribe``/
``slotSubscribe`` multiplexed on one connection (T4.52b-1, plan-T4.52b.md §1
item 8). ``ws.py`` speaks PumpPortal's fixed two-subscription protocol;
``rpc.py``/``rpc_curves.py`` are HTTP-only. Transport-level and
pump.fun-agnostic: returns ``rpc_ws_models.Notification`` values, never
``Normalized*`` models (``trade_event.normalized_curve_trade``/
``decode.decode_bonding_curve_account`` build those from the notifications).

Reconnect discipline mirrors ``ws.py`` (modelled on
``hunter_exchanges.binance.connection.ConnectionRunner``): backoff with
jitter, an idle timeout standing in for a heartbeat, a ``reconnects`` counter.
Every ``subscribe_*`` call is remembered as a ``SubscriptionSpec`` keyed by a
*logical* id the caller keeps forever; a reconnect silently resubscribes the
whole set — the server's own ``subscription`` number is reassigned every
connection and never leaks out. Request/response matching: every request
carries a locally unique ``id``, resolving an ``asyncio.Future``; a
notification instead carries ``{"method": "...Notification"}`` with no
top-level ``id`` — presence of ``id`` tells the two shapes apart.

**F2 (T4.52b-4).** :meth:`SolanaWsClient.listen` never raises: a connect or
read failure backs off (capped, jittered) and retries forever, never as
``ExchangeUnavailable``; the idle timeout only arms once something is
subscribed (no subscriptions yet is not a failure); ``attempt`` resets on
connect, not only on a delivered notification.
"""

from __future__ import annotations

import asyncio
import json
import random
from collections.abc import AsyncIterator, Sequence
from contextlib import AbstractAsyncContextManager
from itertools import count
from typing import Any, Protocol, cast

from hunter_core.domain.types import utcnow
from hunter_core.logging import get_logger
from hunter_exchanges.base import ExchangeUnavailable, MalformedMessage
from hunter_exchanges.pumpfun.rpc_ws_models import (
    ConnectionState,
    Notification,
    SubscriptionSpec,
    parse_account_result,
    parse_logs_result,
    parse_notification_envelope,
    parse_slot_result,
    store_subscription,
)

logger = get_logger(__name__)

_NOTIFICATION_PARSERS = {
    "logsNotification": parse_logs_result,
    "accountNotification": parse_account_result,
    "slotNotification": parse_slot_result,
}

PUBLIC_WS_URL = "wss://api.mainnet-beta.solana.com"
BACKOFF_BASE_S = 1.0
BACKOFF_MAX_S = 30.0
"""F2: capped at 30 s (down from 60 s) — ``listen()`` never gives up, so the
cap alone bounds how long a caller waits between attempts, forever."""
IDLE_TIMEOUT_S = 60.0
CONNECT_TIMEOUT_S = 15.0
REQUEST_TIMEOUT_S = 15.0

__all__ = [
    "CONNECT_TIMEOUT_S",
    "IDLE_TIMEOUT_S",
    "PUBLIC_WS_URL",
    "REQUEST_TIMEOUT_S",
    "SolanaWsClient",
    "WsConnection",
]


class WsConnection(Protocol):
    async def recv(self) -> str | bytes: ...
    async def send(self, message: str) -> None: ...
    async def close(self) -> None: ...


def default_connect(url: str) -> AbstractAsyncContextManager[WsConnection]:
    import websockets

    return websockets.connect(url, ping_interval=20, ping_timeout=20)  # type: ignore[return-value]


class SolanaWsClient:
    """One connection, N caller-managed subscriptions, typed notifications."""

    def __init__(
        self,
        *,
        url: str = PUBLIC_WS_URL,
        connect_fn: Any = None,
        sleep: Any = asyncio.sleep,
        rand: Any = random.random,
        idle_timeout_s: float = IDLE_TIMEOUT_S,
        connect_timeout_s: float = CONNECT_TIMEOUT_S,
        request_timeout_s: float = REQUEST_TIMEOUT_S,
    ) -> None:
        self._url = url
        self._connect_fn = connect_fn or default_connect
        self._sleep = sleep
        self._rand = rand
        self._idle_timeout_s = idle_timeout_s
        self._connect_timeout_s = connect_timeout_s
        self._request_timeout_s = request_timeout_s
        self.state = ConnectionState()
        self._closed = False
        self._connection: WsConnection | None = None
        self._connected = asyncio.Event()
        self._specs: dict[int, SubscriptionSpec] = {}
        self._server_id_of: dict[int, int] = {}
        self._logical_of_server: dict[int, int] = {}
        self._pending: dict[int, tuple[SubscriptionSpec | None, asyncio.Future[Any]]] = {}
        self._next_logical_id = count(1)
        self._next_request_id = count(1)

    def connection_state(self) -> str:
        return self.state.ws_state

    async def aclose(self) -> None:
        self._closed = True
        self._connected.clear()
        if self._connection is not None:
            await self._connection.close()

    async def subscribe_logs(
        self, *, mentions: Sequence[str], commitment: str = "confirmed"
    ) -> int:
        return await self._activate(
            "logsSubscribe",
            "logsUnsubscribe",
            [{"mentions": list(mentions)}, {"commitment": commitment}],
            "logs",
        )

    async def subscribe_account(
        self, pubkey: str, *, commitment: str = "confirmed", encoding: str = "base64"
    ) -> int:
        return await self._activate(
            "accountSubscribe",
            "accountUnsubscribe",
            [pubkey, {"encoding": encoding, "commitment": commitment}],
            "account",
        )

    async def subscribe_slot(self) -> int:
        return await self._activate("slotSubscribe", "slotUnsubscribe", [], "slot")

    async def unsubscribe(self, logical_id: int) -> bool:
        spec = self._specs.pop(logical_id, None)
        server_id = self._server_id_of.pop(logical_id, None)
        if server_id is not None:
            self._logical_of_server.pop(server_id, None)
        if spec is None or server_id is None:
            return False
        if self._connection is None:
            return True  # the connection that knew this subscription is already gone
        result = await self._send_request(spec.unsubscribe_method, [server_id])
        return bool(result)

    async def _activate(
        self, method: str, unsubscribe_method: str, params: list[object], kind: Any
    ) -> int:
        logical_id = next(self._next_logical_id)
        spec = SubscriptionSpec(logical_id, method, unsubscribe_method, params, kind)
        await asyncio.wait_for(self._connected.wait(), timeout=self._connect_timeout_s)
        await self._send_request(method, params, spec=spec)
        return logical_id

    async def _resubscribe_all(self) -> None:
        self._server_id_of.clear()
        self._logical_of_server.clear()
        for spec in list(self._specs.values()):
            await self._send_request(spec.method, spec.params, spec=spec)

    async def _send_request(
        self, method: str, params: list[object], *, spec: SubscriptionSpec | None = None
    ) -> Any:
        """``spec`` set means this is a subscribe; ``_resolve_response`` stores
        its mapping (never here) so a notification can't race ahead of it."""
        if self._connection is None:
            raise ExchangeUnavailable("solana ws has no live connection", exchange="solana")
        request_id = next(self._next_request_id)
        future: asyncio.Future[Any] = asyncio.get_running_loop().create_future()
        self._pending[request_id] = (spec, future)
        payload = json.dumps(
            {"jsonrpc": "2.0", "id": request_id, "method": method, "params": params}
        )
        try:
            await self._connection.send(payload)
            return await asyncio.wait_for(future, timeout=self._request_timeout_s)
        finally:
            self._pending.pop(request_id, None)

    def _resolve_response(self, payload: dict[str, Any]) -> None:
        request_id = payload.get("id")
        if not isinstance(request_id, int) or isinstance(request_id, bool):
            return
        pending = self._pending.get(request_id)
        if pending is None or pending[1].done():
            return
        spec, future = pending
        error = payload.get("error")
        if error is not None:
            future.set_exception(
                ExchangeUnavailable(f"solana ws error: {error}", exchange="solana")
            )
            return
        result = payload.get("result")
        if spec is not None:
            try:
                self._store(spec, result)
            except MalformedMessage as exc:
                future.set_exception(exc)
                return
        future.set_result(result)

    def _store(self, spec: SubscriptionSpec, server_id: Any) -> None:
        store_subscription(
            spec, server_id, self._specs, self._server_id_of, self._logical_of_server
        )

    def _fail_pending(self, exc: Exception) -> None:
        for _spec, future in self._pending.values():
            if not future.done():
                future.set_exception(exc)
        self._pending.clear()

    def _parse_frame(self, raw: str | bytes) -> Notification | None:
        try:
            text = raw if isinstance(raw, str) else raw.decode("utf-8")
            payload = json.loads(text)
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise MalformedMessage(
                f"solana ws frame is not JSON: {exc}", exchange="solana"
            ) from exc
        if not isinstance(payload, dict):
            raise MalformedMessage("solana ws frame is not a JSON object", exchange="solana")
        payload = cast(dict[str, Any], payload)
        if payload.get("id") is not None:
            self._resolve_response(payload)
            return None
        try:
            method, result, server_id = parse_notification_envelope(payload)
        except MalformedMessage as exc:
            raise MalformedMessage(f"{exc} ({text[:200]})", exchange="solana") from exc
        logical_id = self._logical_of_server.get(server_id)
        if logical_id is None:
            self.state.dropped += 1  # a notification for a subscription we no longer track
            return None
        parser = _NOTIFICATION_PARSERS.get(method)
        if parser is None:
            raise MalformedMessage(
                f"solana ws unknown notification method: {method}", exchange="solana"
            )
        return parser(logical_id, result, utcnow())

    async def _backoff(self, attempt: int) -> int:
        """F2: always sleeps, never raises — capped, jittered, and the only
        thing that stands between a dead provider and a tight retry loop."""
        delay = min(BACKOFF_MAX_S, BACKOFF_BASE_S * (2**attempt)) + self._rand()
        await self._sleep(delay)
        return attempt + 1

    async def listen(self) -> AsyncIterator[Notification]:
        """Yield notifications forever; connects, resubscribes and reconnects
        with backoff internally — never raises (F2). A caller registers
        subscriptions with ``subscribe_*`` before or concurrently with this."""
        attempt = 0
        first = True
        while not self._closed:
            self.state.ws_state = "connecting" if first else "reconnecting"
            if not first:
                self.state.reconnects += 1
            first = False
            try:
                cm = self._connect_fn(self._url)
                connection = await asyncio.wait_for(
                    cm.__aenter__(), timeout=self._connect_timeout_s
                )
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.warning("solana_ws_connect_error", error=str(exc))
                attempt = await self._backoff(attempt)
                continue

            self.state.ws_state = "connected"
            self._connection = connection
            self._connected.set()
            attempt = 0  # F2: reset on a successful (re)connect, not only on delivery
            # Concurrent, not awaited: awaiting it here would deadlock a
            # reconnect (its responses resolve through the read loop below).
            resubscribe_task = asyncio.create_task(self._resubscribe_all())
            failure: Exception | None = None
            try:
                while not self._closed:
                    # F2: idle timeout only means anything once something is
                    # subscribed — a fresh or fully-aged-out connection has
                    # nothing due to arrive and must not be timed out for it.
                    timeout = self._idle_timeout_s if self._specs else None
                    try:
                        raw = await asyncio.wait_for(connection.recv(), timeout=timeout)
                    except TimeoutError:
                        raise ConnectionError(
                            f"solana ws idle for {self._idle_timeout_s:.1f}s, no frames received"
                        ) from None
                    self.state.messages += 1
                    try:
                        item = self._parse_frame(raw)
                    except MalformedMessage as exc:
                        self.state.malformed += 1
                        logger.warning("solana_ws_malformed_message", error=str(exc))
                        continue
                    if item is not None:
                        yield item
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.warning("solana_ws_connection_error", error=str(exc))
                self.state.ws_state = "reconnecting"
                failure = exc
            finally:
                if not resubscribe_task.done():
                    resubscribe_task.cancel()
                try:
                    await resubscribe_task
                except asyncio.CancelledError:
                    pass
                except Exception as exc:
                    logger.warning("solana_ws_resubscribe_error", error=str(exc))
                self._connected.clear()
                self._fail_pending(ConnectionError("solana ws connection closed"))
                await self._close_quietly(cm)
                self._connection = None
                self.state.ws_state = "disconnected"
            if failure is not None and not self._closed:
                attempt = await self._backoff(attempt)
        self.state.ws_state = "disconnected"

    async def _close_quietly(self, cm: AbstractAsyncContextManager[WsConnection]) -> None:
        try:
            await cm.__aexit__(None, None, None)
        except Exception as exc:
            logger.warning("solana_ws_close_error", error=str(exc))
