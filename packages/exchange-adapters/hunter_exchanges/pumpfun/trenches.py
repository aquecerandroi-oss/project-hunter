"""``wss://advanced-indexer.pump.fun/ws/trenches`` — one board, one connection.

The site's own push feed (``docs/PUMPFUN.md`` §3.1): the subscription rides in
the URL (``?subscription=<url-encoded {board, tier, filterKey}>``) **and** in a
``subscribe`` event sent right after the handshake; the server answers with a
snapshot and then a delta per change. No key, no login, no cookie — measured
live on 2026-09-12 with exactly the two messages below.

Reconnect discipline follows the site's client, ``min(1000·2^n, 30000)`` ms
(:func:`backoff_delay_s`), plus jitter, and it is **unbounded**: a board that
cannot be reached is a degraded source the worker reports
(``state.ws_state``, ``state.consecutive_failures``), never a reason to take the
curve poller down with it — the opposite of the PumpPortal client, whose loss
means the radar discovers nothing. Liveness is an idle timeout: the boards
patch every second when anything moves, and ``graduating`` was measured going
quiet for tens of seconds, so the timeout is generous and reconnecting is cheap
(a fresh snapshot).

Sequence discipline (``docs/EXCHANGE_INTEGRATION.md`` §4's "checar sequência;
ressincronizar ao detectar salto"): a delta the mirror cannot follow — a
``baseVersion`` behind the version held, a version that does not advance, a
patch for a mint we were never sent — is an :class:`OutOfOrderDelta`; the
client closes the socket and resubscribes, which yields a fresh snapshot.
Counted in ``state.resyncs``. A *forward* gap is not a jump to resync on: the
per-board counter moves on changes outside the shown top-N (measured on
``graduating``), so it is applied and counted in ``state.version_gaps``.
Malformed frames are counted in ``state.malformed`` and skipped; the worker
turns the counter into a per-minute heartbeat field.
"""

from __future__ import annotations

import asyncio
import json
import random
from collections.abc import AsyncIterator, Callable
from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any, cast
from urllib.parse import quote

from hunter_core.domain.types import utcnow
from hunter_core.logging import get_logger
from hunter_exchanges.base import MalformedMessage
from hunter_exchanges.pumpfun.board_models import BOARDS
from hunter_exchanges.pumpfun.trenches_state import BoardEvent, BoardState, OutOfOrderDelta
from hunter_exchanges.pumpfun.ws import WsConnection

logger = get_logger(__name__)

INDEXER_WS_URL = "wss://advanced-indexer.pump.fun/ws/trenches"
SUBSCRIPTION_TIER = "web"
SUBSCRIPTION_FILTER_KEY = "default"
"""The variant that answered with a snapshot in the live capture; the site
builds the key from its filter form, and ``default`` is the unfiltered board."""

BACKOFF_BASE_MS = 1000
BACKOFF_MAX_MS = 30_000
IDLE_TIMEOUT_S = 90.0
CONNECT_TIMEOUT_S = 15.0
MAX_MESSAGE_BYTES = 8_000_000
"""A ``graduated`` snapshot measured ~300 KB; the default 1 MiB would be a
ceiling nobody declared."""


def subscription_url(board: str, *, base_url: str = INDEXER_WS_URL) -> str:
    payload = {"board": board, "tier": SUBSCRIPTION_TIER, "filterKey": SUBSCRIPTION_FILTER_KEY}
    return base_url + "?subscription=" + quote(json.dumps(payload, separators=(",", ":")), safe="")


def subscribe_message(board: str) -> str:
    return json.dumps(
        {
            "event": "subscribe",
            "data": {
                "board": board,
                "tier": SUBSCRIPTION_TIER,
                "platform": "WEB",
                "surface": "WEB",
            },
        }
    )


def backoff_delay_s(attempt: int, rand: Callable[[], float] = random.random) -> float:
    """``min(1000·2^n, 30000)`` ms as the site does, plus up to 10 % of jitter."""
    base_ms = min(BACKOFF_BASE_MS * (2**attempt), BACKOFF_MAX_MS)
    return base_ms / 1000 * (1 + 0.1 * rand())


def default_connect(url: str) -> AbstractAsyncContextManager[WsConnection]:
    import websockets

    return websockets.connect(  # type: ignore[return-value]
        url,
        additional_headers={"Origin": "https://pump.fun"},
        ping_interval=20,
        ping_timeout=20,
        max_size=MAX_MESSAGE_BYTES,
    )


@dataclass
class TrenchesState:
    """Counters the worker reads; every one answers an operator question."""

    board: str
    ws_state: str = "disconnected"
    reconnects: int = 0
    resyncs: int = 0
    consecutive_failures: int = 0
    snapshots: int = 0
    deltas: int = 0
    patches: int = 0
    version_gaps: int = 0
    """Deltas that skipped versions we were not sent (``trenches_state.py``)."""
    malformed: int = 0
    last_observed_at: datetime | None = None
    last_received_at: datetime | None = None


class TrenchesWsClient:
    """One board's stream of :class:`BoardEvent`, reconnecting forever."""

    def __init__(
        self,
        board: str,
        *,
        base_url: str = INDEXER_WS_URL,
        connect_fn: Any = None,
        sleep: Any = asyncio.sleep,
        rand: Callable[[], float] = random.random,
        clock: Callable[[], datetime] = utcnow,
        idle_timeout_s: float = IDLE_TIMEOUT_S,
        connect_timeout_s: float = CONNECT_TIMEOUT_S,
    ) -> None:
        if board not in BOARDS:
            raise ValueError(f"unknown board {board!r}; boards are {BOARDS}")
        self.board = board
        self._url = subscription_url(board, base_url=base_url)
        self._connect_fn = connect_fn or default_connect
        self._sleep = sleep
        self._rand = rand
        self._clock = clock
        self._idle_timeout_s = idle_timeout_s
        self._connect_timeout_s = connect_timeout_s
        self.state = TrenchesState(board=board)
        self.board_state = BoardState(board)
        self._closed = False
        self._connection: WsConnection | None = None

    def connection_state(self) -> str:
        return self.state.ws_state

    async def aclose(self) -> None:
        self._closed = True
        if self._connection is not None:
            await self._connection.close()

    def _decode(self, raw: str | bytes) -> dict[str, Any]:
        try:
            text = raw if isinstance(raw, str) else raw.decode("utf-8")
            payload = json.loads(text, parse_float=Decimal)
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise MalformedMessage(
                f"trenches frame is not JSON: {exc}", exchange="pumpfun"
            ) from exc
        if not isinstance(payload, dict):
            raise MalformedMessage("trenches frame is not a JSON object", exchange="pumpfun")
        return cast(dict[str, Any], payload)

    def _apply(self, raw: str | bytes) -> BoardEvent:
        """Decode and apply; raises :class:`MalformedMessage` or :class:`OutOfOrderDelta`."""
        event = self.board_state.apply(self._decode(raw), received_at=self._clock())
        if event.kind == "snapshot":
            self.state.snapshots += 1
        else:
            self.state.deltas += 1
            self.state.patches += sum(event.patch_ops.values())
            self.state.version_gaps += event.version_gap > 0
        self.state.last_observed_at = event.observed_at
        self.state.last_received_at = event.received_at
        return event

    async def _backoff(self, exc: Exception, verb: str) -> None:
        delay = backoff_delay_s(self.state.consecutive_failures, self._rand)
        self.state.consecutive_failures += 1
        logger.warning(
            "trenches_ws_backoff",
            board=self.board,
            verb=verb,
            error=str(exc),
            delay_s=round(delay, 3),
            failures=self.state.consecutive_failures,
        )
        await self._sleep(delay)

    async def stream(self) -> AsyncIterator[BoardEvent]:
        """Yield board events forever; reconnects, resubscribes and resyncs internally."""
        first = True
        while not self._closed:
            self.state.ws_state = "connecting" if first else "reconnecting"
            if not first:
                self.state.reconnects += 1
            first = False
            self.board_state = BoardState(self.board)
            try:
                cm = self._connect_fn(self._url)
                connection = await asyncio.wait_for(
                    cm.__aenter__(), timeout=self._connect_timeout_s
                )
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                await self._backoff(exc, "connect")
                continue
            self.state.ws_state = "connected"
            self._connection = connection
            failure: Exception | None = None
            try:
                await connection.send(subscribe_message(self.board))
                async for event in self._consume(connection):
                    yield event
            except asyncio.CancelledError:
                raise
            except OutOfOrderDelta as exc:
                self.state.resyncs += 1
                logger.warning("trenches_ws_resync", board=self.board, error=str(exc))
            except Exception as exc:
                failure = exc
            finally:
                await self._close_quietly(cm)
                self._connection = None
                self.state.ws_state = "disconnected"
            if failure is not None and not self._closed:
                await self._backoff(failure, "stream")
        self.state.ws_state = "disconnected"

    async def _consume(self, connection: WsConnection) -> AsyncIterator[BoardEvent]:
        while not self._closed:
            try:
                raw = await asyncio.wait_for(connection.recv(), timeout=self._idle_timeout_s)
            except TimeoutError:
                raise ConnectionError(
                    f"trenches board {self.board!r} idle for {self._idle_timeout_s:.0f}s"
                ) from None
            try:
                event = self._apply(raw)
            except MalformedMessage as exc:
                self.state.malformed += 1
                logger.warning("trenches_ws_malformed_message", board=self.board, error=str(exc))
                continue
            self.state.consecutive_failures = 0
            yield event

    async def _close_quietly(self, cm: AbstractAsyncContextManager[WsConnection]) -> None:
        try:
            await cm.__aexit__(None, None, None)
        except Exception as exc:  # closing must never raise past this point
            logger.warning("trenches_ws_close_error", board=self.board, error=str(exc))


__all__ = [
    "BACKOFF_MAX_MS",
    "IDLE_TIMEOUT_S",
    "INDEXER_WS_URL",
    "TrenchesState",
    "TrenchesWsClient",
    "backoff_delay_s",
    "default_connect",
    "subscribe_message",
    "subscription_url",
]
