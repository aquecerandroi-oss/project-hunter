"""PumpPortal WebSocket client — ``subscribeNewToken`` + ``subscribeMigration``.

One connection, two free subscriptions (T4.0 §3: the two paid ones,
``subscribeTokenTrade``/``subscribeAccountTrade``, are out of scope — see
``models.py``'s ``NormalizedMemeTrade`` docstring). Mirrors the reconnect
discipline of ``hunter_exchanges.binance.connection.ConnectionRunner``
(backoff with jitter, an idle timeout standing in for heartbeat, a
reconnect counter a caller can use as an ingestion-gap signal) without
importing it: that module is built around N symbol-group connections
multiplexed by stream name, which does not apply to this single, symbol-less
subscription.

No timestamp in the frame: neither ``create`` nor ``migrate`` messages carry
an on-chain block time (confirmed live —
``tests/fixtures/pumpfun/pumpportal_ws_capture_raw.jsonl`` has none across 19
non-ack messages). ``normalize.py`` sets ``created_at``/``migrated_at`` equal
to ``received_at`` and documents why on the models themselves; this client
never invents a better one.

Dedupe: PumpPortal does not document at-most-once delivery, and a
reconnect's own catch-up could plausibly re-deliver a frame the previous
connection already handled. Every accepted ``(mint, signature)`` pair is
remembered in a bounded FIFO set (``_DEDUPE_MAX_SIZE``) so a repeat is
dropped, counted, and never yielded twice.
"""

from __future__ import annotations

import asyncio
import json
import random
from collections import OrderedDict
from collections.abc import AsyncIterator
from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Protocol, cast

from hunter_core.logging import get_logger
from hunter_exchanges.base import ExchangeUnavailable, MalformedMessage
from hunter_exchanges.pumpfun import normalize
from hunter_exchanges.pumpfun.models import NormalizedMemeMigration, NormalizedMemeTokenCreated

logger = get_logger(__name__)

WS_URL = "wss://pumpportal.fun/api/data"
BACKOFF_BASE_S = 1.0
BACKOFF_MAX_S = 60.0
#: No documented server heartbeat; this is the liveness check (Binance calls
#: the same idea F7's idle timeout) that stands in for one — a socket that
#: goes silent this long is treated as dead and reconnected.
IDLE_TIMEOUT_S = 60.0
CONNECT_TIMEOUT_S = 15.0
MAX_RECONNECT_FAILURES = 5
#: Bounded so a long-lived process's dedupe set cannot grow without limit;
#: at ~20 creates/55s observed live, 10k entries is comfortably hours deep.
DEDUPE_MAX_SIZE = 10_000

MemeEvent = NormalizedMemeTokenCreated | NormalizedMemeMigration


class WsConnection(Protocol):
    async def recv(self) -> str | bytes: ...
    async def send(self, message: str) -> None: ...
    async def close(self) -> None: ...


def default_connect(url: str) -> AbstractAsyncContextManager[WsConnection]:
    import websockets

    return websockets.connect(url, ping_interval=20, ping_timeout=20)  # type: ignore[return-value]


@dataclass
class ConnectionState:
    """This client's single-connection analogue of
    ``hunter_exchanges.binance.connection.ConnectionState`` — one connection,
    no per-symbol-group map, so the richer dataclass would carry unused
    fields. ``reconnects`` is the hook a future T4.2 consumer reads to decide
    whether an ``ingestion_gaps`` row is warranted."""

    ws_state: str = "disconnected"
    reconnects: int = 0
    dropped_duplicates: int = 0
    skipped_out_of_scope: int = 0


def _sync_monotonic() -> float:
    return asyncio.get_running_loop().time()


class PumpPortalWsClient:
    def __init__(
        self,
        *,
        url: str = WS_URL,
        connect_fn: Any = None,
        clock: Any = None,
        sleep: Any = asyncio.sleep,
        rand: Any = random.random,
        idle_timeout_s: float = IDLE_TIMEOUT_S,
        connect_timeout_s: float = CONNECT_TIMEOUT_S,
        max_reconnect_failures: int = MAX_RECONNECT_FAILURES,
        dedupe_max_size: int = DEDUPE_MAX_SIZE,
    ) -> None:
        self._url = url
        self._connect_fn = connect_fn or default_connect
        self._clock = clock or _sync_monotonic
        self._sleep = sleep
        self._rand = rand
        self._idle_timeout_s = idle_timeout_s
        self._connect_timeout_s = connect_timeout_s
        self._max_reconnect_failures = max_reconnect_failures
        self._dedupe_max_size = dedupe_max_size
        self._seen: OrderedDict[tuple[str, str], None] = OrderedDict()
        self.state = ConnectionState()
        self._closed = False
        self._connection: WsConnection | None = None

    def connection_state(self) -> str:
        return self.state.ws_state

    async def aclose(self) -> None:
        self._closed = True
        if self._connection is not None:
            await self._connection.close()

    def _is_duplicate(self, mint: str, signature: str) -> bool:
        key = (mint, signature)
        if key in self._seen:
            return True
        self._seen[key] = None
        if len(self._seen) > self._dedupe_max_size:
            self._seen.popitem(last=False)
        return False

    def _parse_frame(self, raw: str | bytes) -> MemeEvent | None:
        """Return a normalized event, or ``None`` for anything to skip
        (ack message, out-of-scope pool, duplicate) — never raises for those,
        only for a genuinely malformed frame, which is logged and skipped by
        the caller, exactly like ``EXCHANGE_INTEGRATION.md`` §6's contract."""
        try:
            text = raw if isinstance(raw, str) else raw.decode("utf-8")
            payload = json.loads(text, parse_float=Decimal)
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise MalformedMessage(
                f"pumpportal frame is not JSON: {exc}", exchange="pumpfun"
            ) from exc
        if not isinstance(payload, dict):
            raise MalformedMessage(
                f"pumpportal frame is not a JSON object: {text[:200]}", exchange="pumpfun"
            )
        payload = cast(dict[str, Any], payload)
        if "message" in payload and "txType" not in payload:
            return None  # subscribe ack, e.g. {"message": "Successfully subscribed..."}
        if normalize.is_new_token_message(payload):
            pool = payload.get("pool")
            if not isinstance(pool, str) or not normalize.is_in_scope_pool(pool):
                self.state.skipped_out_of_scope += 1
                return None
            event: MemeEvent = normalize.parse_new_token(payload)
        elif normalize.is_migration_message(payload):
            if payload.get("pool") != normalize.PUMPSWAP_POOL:
                self.state.skipped_out_of_scope += 1
                return None
            event = normalize.parse_migration(payload)
        else:
            raise MalformedMessage(
                f"pumpportal frame has unknown txType: {text[:200]}", exchange="pumpfun"
            )
        if self._is_duplicate(event.mint, event.signature):
            self.state.dropped_duplicates += 1
            return None
        return event

    async def _subscribe(self, connection: WsConnection) -> None:
        await connection.send(json.dumps({"method": "subscribeNewToken"}))
        await connection.send(json.dumps({"method": "subscribeMigration"}))

    async def _backoff_or_raise(self, attempt: int, exc: Exception, verb: str) -> int:
        delay = min(BACKOFF_MAX_S, BACKOFF_BASE_S * (2**attempt)) + self._rand()
        attempt += 1
        if attempt >= self._max_reconnect_failures:
            self.state.ws_state = "disconnected"
            raise ExchangeUnavailable(
                f"pumpportal ws {verb} {attempt} times in a row: {exc}", exchange="pumpfun"
            ) from exc
        await self._sleep(delay)
        return attempt

    async def stream(self) -> AsyncIterator[MemeEvent]:
        """Yield normalized events forever; reconnects and resubscribes internally."""
        attempt = 0
        first_iteration = True
        while not self._closed:
            self.state.ws_state = "connecting" if first_iteration else "reconnecting"
            if not first_iteration:
                self.state.reconnects += 1
            first_iteration = False
            try:
                cm = self._connect_fn(self._url)
                connection = await asyncio.wait_for(
                    cm.__aenter__(), timeout=self._connect_timeout_s
                )
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # any connect failure backs off the same way
                logger.warning("pumpportal_ws_connect_error", error=str(exc))
                attempt = await self._backoff_or_raise(attempt, exc, "failed to connect")
                continue

            self.state.ws_state = "connected"
            self._connection = connection
            failure: Exception | None = None
            try:
                await self._subscribe(connection)
                while not self._closed:
                    try:
                        raw = await asyncio.wait_for(
                            connection.recv(), timeout=self._idle_timeout_s
                        )
                    except TimeoutError:
                        raise ConnectionError(
                            f"pumpportal ws idle for {self._idle_timeout_s:.1f}s, no frames received"
                        ) from None
                    try:
                        event = self._parse_frame(raw)
                    except MalformedMessage as exc:
                        logger.warning("pumpportal_ws_malformed_message", error=str(exc))
                        continue
                    if event is not None:
                        attempt = 0
                        yield event
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # connection-level failure, backed off below
                logger.warning("pumpportal_ws_connection_error", error=str(exc))
                self.state.ws_state = "reconnecting"
                failure = exc
            finally:
                await self._close_quietly(cm, connection)
                self._connection = None
                self.state.ws_state = "disconnected"
            if failure is not None and not self._closed:
                attempt = await self._backoff_or_raise(attempt, failure, "failed")
        self.state.ws_state = "disconnected"

    async def _close_quietly(
        self, cm: AbstractAsyncContextManager[WsConnection], connection: WsConnection
    ) -> None:
        try:
            await cm.__aexit__(None, None, None)
        except Exception as exc:  # closing must never raise past this point
            logger.warning("pumpportal_ws_close_error", error=str(exc))


__all__ = [
    "IDLE_TIMEOUT_S",
    "MAX_RECONNECT_FAILURES",
    "WS_URL",
    "ConnectionState",
    "MemeEvent",
    "PumpPortalWsClient",
    "WsConnection",
    "default_connect",
]
