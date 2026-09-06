"""The collector's proof that it was still listening — ``covered_until``.

``hunter_indicators.features.windows.trades_between`` refuses a trade window
unless the collector proves it stayed connected through it: the tape alone
cannot tell a quiet market from a dropped connection, and a trade right before
the cut only says the collector came back (T2.2 notes §12.3/§13). Until that
proof exists, ``trade_velocity_1m``, ``buy_pressure_5m`` and ``sell_pressure_5m``
are ``insufficient_coverage`` and no EARLY stage is ever confirmed.

Only this process can produce the proof, and only about the interval it can
actually stand behind:

- **the session**, not the socket. ``ws_state = connected`` next to a
  *cumulative* ``dropped_events`` (``heartbeat.py``) would let a connection that
  lost a trade read as covered. A drop can have been a trade on any symbol, so
  it ends the interval and a new one starts at that instant;
- **per symbol**, because a market subscribed mid-session is only covered from
  its own subscription, and an unsubscribed one stops claiming coverage at once;
- **short of the clock**. An event the adapter already received may not have
  reached the tape yet, so a stamp claims ``now - COVERAGE_SAFETY_S`` and never
  ``now``. :meth:`CoverageTracker.writing`/:meth:`written` additionally hold the
  stamp back while a hot-state write is in flight, so the margin covers the
  adapter's own queue rather than a write this process knows is unfinished.

The scanner then evaluates each market at ``as_of = covered_until`` instead of
at its own clock: "as it was observable at ``as_of``" is what ``MarketContext``
means, and moving the cut is the only honest way to satisfy a proof that is,
by construction, always slightly behind.

**What this does NOT yet prove** (Astra, T2.5 diff review, accepted as a stated
limit rather than argued away). Two gaps remain, and both need the *adapter* to
participate, which is why the margin is a complement and not the proof:

- **an internal reconnect.** The tracker opens a session in ``consume_once`` and
  only breaks it when that loop ends. An adapter that handles a dropped socket
  and reconnects without ending its generator would leave the gap inside an
  interval this module still calls continuous. Closing it needs a connection
  *generation* from the adapter, bumped on every reconnect;
- **a backlogged queue without drops.** ``_in_flight == 0`` means no write this
  process started is unfinished; it does not mean the adapter's own inbound
  queue is empty. If that backlog ever exceeds ``COVERAGE_SAFETY_S`` the stamp
  runs past events that have not reached the tape. Closing it needs a delivered
  *progress marker* from the adapter, confirmed after the write -- queue depth
  alone is not enough, because an item already popped by the reader task has
  left the queue and not yet reached the consumer.

Both live in ``packages/exchange-adapters/**`` and are filed in
``.claude/state/notes-T2.5.md`` section 10.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Any, cast

from hunter_core.domain.types import utcnow
from hunter_core.logging import get_logger
from hunter_core.redis import keys

if TYPE_CHECKING:
    from collections.abc import Iterable

    import redis.asyncio as redis_asyncio

logger = get_logger(__name__)

COVERAGE_SAFETY_S = 0.5
"""How far short of the clock a stamp stops. Covers the adapter's own inbound
queue, which this process cannot inspect: an event received 100 ms ago may not
have been yielded to the ingest loop yet, and claiming it as tape would be
exactly the fabricated coverage this module exists to avoid."""

COVERAGE_STAMP_S = 0.25
"""Cadence of the stamp. Bounds how far behind the scanner's cut runs, and with
it the tick->opportunity latency the cut is measured against (p99 <= 3 s)."""

COVERAGE_TTL_S = 60
"""A dead collector's proof must expire on its own: a scanner that kept reading
a stale hash would keep publishing windows nobody is collecting."""

_SESSION_SINCE = "session_since"
_COVERED_UNTIL = "covered_until"
_SYMBOL_PREFIX = "sym:"

__all__ = [
    "COVERAGE_SAFETY_S",
    "COVERAGE_STAMP_S",
    "COVERAGE_TTL_S",
    "CoverageTracker",
]


class CoverageTracker:
    """The coverage interval of one exchange's stream, and how it is published."""

    def __init__(self, exchange: str) -> None:
        self.exchange = exchange
        self._session_since: datetime | None = None
        self._symbols: dict[str, datetime] = {}
        self._published: set[str] = set()
        self._dropped: int | None = None
        self._in_flight = 0
        self._last_stamp: float | None = None

    # --- session lifecycle -------------------------------------------------

    def session_started(self, symbols: Iterable[str], *, at: datetime | None = None) -> None:
        """A fresh stream is connected and subscribed to ``symbols``."""
        moment = at or utcnow()
        self._session_since = moment
        self._symbols = {symbol: moment for symbol in symbols}
        self._dropped = None
        self._in_flight = 0

    def session_broken(self) -> None:
        """The stream ended (error, restart, universe reconnect): no coverage."""
        self._session_since = None
        self._symbols = {}

    def subscribed(self, symbols: Iterable[str], *, at: datetime | None = None) -> None:
        """Symbols added mid-session — covered from this instant, not earlier."""
        moment = at or utcnow()
        for symbol in symbols:
            self._symbols.setdefault(symbol, moment)

    def unsubscribed(self, symbols: Iterable[str]) -> None:
        for symbol in symbols:
            self._symbols.pop(symbol, None)

    # --- in-flight writes --------------------------------------------------

    def writing(self) -> None:
        """A hot-state write started; the stamp may not run past it."""
        self._in_flight += 1

    def written(self) -> None:
        self._in_flight = max(0, self._in_flight - 1)

    # --- publication -------------------------------------------------------

    def due(self, monotonic: float, *, interval_s: float = COVERAGE_STAMP_S) -> bool:
        if self._last_stamp is None or monotonic - self._last_stamp >= interval_s:
            self._last_stamp = monotonic
            return True
        return False

    async def stamp(
        self,
        redis: redis_asyncio.Redis,
        *,
        dropped_events: int,
        now: datetime | None = None,
    ) -> bool:
        """Publish the interval this collector can stand behind. ``False`` = nothing claimed."""
        moment = now or utcnow()
        key = keys.tape_coverage(self.exchange)
        if self._session_since is None:
            if self._published:
                await self._clear(redis, key)
            return False
        if self._in_flight:
            return False
        if self._dropped is None:
            self._dropped = dropped_events
        elif dropped_events > self._dropped:
            logger.warning(
                "tape_coverage_interval_broken",
                exchange=self.exchange,
                dropped=dropped_events - self._dropped,
            )
            self._dropped = dropped_events
            self._session_since = moment
        covered_until = moment - timedelta(seconds=COVERAGE_SAFETY_S)
        if covered_until < self._session_since:
            covered_until = self._session_since
        mapping = {
            _SESSION_SINCE: self._session_since.isoformat(),
            _COVERED_UNTIL: covered_until.isoformat(),
        }
        for symbol, since in self._symbols.items():
            mapping[f"{_SYMBOL_PREFIX}{symbol}"] = since.isoformat()
        stale = self._published - {f"{_SYMBOL_PREFIX}{symbol}" for symbol in self._symbols}
        await cast(Any, redis).hset(key, mapping=mapping)
        if stale:
            await cast(Any, redis).hdel(key, *sorted(stale))
        await redis.expire(key, COVERAGE_TTL_S)
        self._published = set(mapping) - {_SESSION_SINCE, _COVERED_UNTIL}
        return True

    async def _clear(self, redis: redis_asyncio.Redis, key: str) -> None:
        """Say the interval ended. Deleting the key would be read as "no
        collector", which is a different fact from "the collector is here and
        stopped being able to prove continuity"."""
        await cast(Any, redis).hset(key, mapping={_SESSION_SINCE: "", _COVERED_UNTIL: ""})
        if self._published:
            await cast(Any, redis).hdel(key, *sorted(self._published))
        await redis.expire(key, COVERAGE_TTL_S)
        self._published = set()
