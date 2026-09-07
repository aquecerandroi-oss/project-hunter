"""The collector's proof that it was still listening — ``covered_until``.

``hunter_indicators.features.windows.trades_between`` refuses a trade window
unless the collector proves it stayed connected through it: the tape alone
cannot tell a quiet market from a dropped connection (T2.2 notes §12.3/§13).
Until that proof exists, ``trade_velocity_1m``, ``buy_pressure_5m`` and
``sell_pressure_5m`` are ``insufficient_coverage`` and no EARLY is confirmed.

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
means, and moving the cut is the only honest way to satisfy a proof that is
always slightly behind.

**T2.5-adapter** (full account: ``.claude/state/astra-review-T2.5-adapter-diff.md``)
closed two gaps the 0.5s margin alone cannot see through, both read at
**stamp time** (every housekeeping tick, ~250ms), never per event:

- **an internal reconnect.** ``ConnectionRunner.run`` (``binance/connection.py``)
  retries a dropped socket without ever ending :meth:`stream`'s generator, so a
  session that only broke when that generator ended could publish "continuous"
  straight through a real gap. Two signals catch it: ``ws_state`` (mandatory,
  worst across connection keys, set to ``"reconnecting"`` *before* the close
  awaits) and ``connection_generation`` (bumped on every reconnect — catches a
  full cycle completing *between* two stamps). Either changing forces
  ``reason="reconnect"``, and resumption starts a *fresh* session rather than
  stretching the old one across a gap this process could not see through;
- **a backlogged queue without drops.** ``_in_flight == 0`` says no write *this
  process* started is unfinished, never that the adapter's inbound queue was
  empty. ``queue_progress`` (``enqueued``, ``delivered``, ``evicted``) fixes
  that; an eviction counts on its own side of the ledger, so the break it
  already causes (``dropped_events``) does not read as permanent backlog
  afterwards. Unlike a reconnect, backlog clearing never invalidates the
  session: nothing was lost, only delayed.

**T2.5e** (``.claude/state/brief-T2.5e-coverage-caught-up.md``, full account
in ``.claude/state/notes-T2.5.md`` T2.5e section) found that ledger right but
its bar wrong: under continuous flow ``enqueued == delivered + evicted`` holds
only in the instant the queue is fully empty, so the interval broke on nearly
every stamp and stayed broken. "Caught up" is now a **bounded delay**: a
nonzero backlog only breaks the interval if the oldest pending event's own
timestamp (``queue_oldest_pending_ts()``, which covers both the deque and an
item already popped but not yet delivered) has itself reached the window this
stamp is about to claim (``moment - COVERAGE_SAFETY_S``). Its *own* ``ts``,
never how long this queue has known about it — an event can sit upstream of
here invisibly; and the minimum over pending events, since arrival order
across reader tasks is not timestamp order. A plain count threshold was
rejected in design review: magnitude decides nothing a timestamp does not
already decide correctly.

**T2.5g** made the collector N processes (``MARKET_SHARD=i/N``) while the
scanner still reads one hash per exchange. What this shard can stand behind is
decided here as before; *publishing* it moved to
:mod:`hunter_market_worker.coverage_publish` (one Lua script, conservative
merge — its module docstring has the aggregate's rules). Fixed on the way:
``dropped_events`` arrived here as a constant ``0``, because ``streaming.py``
read it off the adapter instead of its connections, so the break below never
fired on the VPS while 1.2M events were dropped (``DroppedEventsLedger``).

All four signals are read in the same housekeeping task that already calls
:meth:`writing`/:meth:`written`. ``connection_generation``/``queue_progress``/
``queue_oldest_pending_ts`` are read defensively (``getattr``, additive
capability, like ``rest_gate_status``); ``ws_state`` is not, since
``connection_state()`` is mandatory. An adapter implementing none of them
behaves as before this module existed: ``ws_state`` ``"connected"``, the rest
``None``.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from time import monotonic
from typing import TYPE_CHECKING

from hunter_core.domain.enums import MarketType
from hunter_core.domain.types import utcnow
from hunter_core.logging import get_logger
from hunter_market_worker import coverage_publish
from hunter_market_worker.coverage_limits import (
    COVERAGE_SAFETY_S,
    COVERAGE_STAMP_S,
    COVERAGE_TTL_S,
)

if TYPE_CHECKING:
    from collections.abc import Iterable

    import redis.asyncio as redis_asyncio

logger = get_logger(__name__)

__all__ = ["COVERAGE_SAFETY_S", "COVERAGE_STAMP_S", "COVERAGE_TTL_S", "CoverageTracker"]


class CoverageTracker:
    """The coverage interval of one exchange's stream, and how it is published."""

    def __init__(
        self,
        exchange: str,
        shard_index: int = 0,
        shard_total: int = 1,
        *,
        market_type: MarketType = MarketType.PERPETUAL,
    ) -> None:
        self.exchange = exchange
        #: T3.0c: one proof per venue **and product** — the spot tape and the
        #: perpetual tape break independently, so one hash would always be
        #: wrong about one of them.
        self.market_type = market_type
        #: T2.5g: which slice of the universe this process proves. N shards
        #: write one shared hash, so the aggregate is computed by the Lua
        #: script in ``coverage_publish`` and never by whoever wrote last.
        self.shard = coverage_publish.shard_id(shard_index, shard_total)
        self._session_since: datetime | None = None
        self._symbols: dict[str, datetime] = {}
        self._claiming = False
        self._dropped: int | None = None
        self._in_flight = 0
        self._last_stamp: float | None = None
        # T2.5-adapter: the last ``covered_until`` computed while genuinely
        # caught up (already margin-adjusted) — frozen, not the raw clock,
        # while ``ws_state``/``queue_progress`` say otherwise (freezing on the
        # raw clock would regain the 0.5s the margin was holding back).
        self._last_safe_covered_until: datetime | None = None
        #: ``None`` while caught up; otherwise why the *last* stamp was not —
        #: ``"reconnect"`` (ws_state/connection_generation) vs
        #: ``"queue_backlog"`` decide whether resuming starts a fresh session
        #: or merely un-freezes this one (see module docstring).
        self._break_reason: str | None = None
        #: Monotonic reading when the break started (T2.5e resumption log).
        self._broken_since_monotonic: float | None = None
        #: Last ``connection_generation`` observed, baselined fresh each
        #: session so a number that does not reset across sessions never
        #: reads as a break at the next ``session_started``.
        self._generation: int | None = None

    # --- session lifecycle -------------------------------------------------

    def session_started(self, symbols: Iterable[str], *, at: datetime | None = None) -> None:
        """A fresh stream is connected and subscribed to ``symbols``."""
        moment = at or utcnow()
        self._session_since = moment
        self._symbols = {symbol: moment for symbol in symbols}
        self._dropped = None
        self._in_flight = 0
        self._last_safe_covered_until = None
        self._break_reason = None
        self._broken_since_monotonic = None
        self._generation = None

    def session_broken(self) -> None:
        """The stream ended (error, restart, universe reconnect): no coverage."""
        self._session_since = None
        self._symbols = {}
        self._last_safe_covered_until = None
        self._break_reason = None
        self._broken_since_monotonic = None
        self._generation = None

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
        ws_state: str = "connected",
        queue_progress: tuple[int, int, int] | None = None,
        connection_generation: int | None = None,
        oldest_pending_ts: datetime | None = None,
    ) -> bool:
        """Publish the interval this collector can stand behind. ``False`` = nothing claimed.

        Three more reasons ``covered_until`` may hold back, on top of the
        ``dropped_events`` break below (module docstring): ``ws_state`` not
        ``"connected"``, or ``connection_generation`` changed, are each a
        ``reason="reconnect"`` break; a nonzero backlog in ``queue_progress``
        is ``reason="queue_backlog"`` *unless* ``oldest_pending_ts`` proves it
        bounded (still ahead of the window this stamp is about to claim) —
        unknown counts as unbounded. A ``"reconnect"`` break, once resumed,
        starts a fresh session at the resumption instant; a
        ``"queue_backlog"`` break simply un-freezes the existing one. Neither
        ever moves the claim forward faster than the existing rules allow.
        """
        moment = now or utcnow()
        if self._session_since is None:
            if self._claiming:
                await self._clear(redis, moment)
            return False
        if self._in_flight:
            return False
        if self._dropped is None:
            self._dropped = dropped_events
        elif dropped_events > self._dropped:
            logger.warning(
                "tape_coverage_interval_broken",
                exchange=self.exchange,
                reason="dropped_events",
                dropped=dropped_events - self._dropped,
            )
            self._dropped = dropped_events
            self._session_since = moment
            self._last_safe_covered_until = None

        caught_up = ws_state == "connected"
        reason = "reconnect" if not caught_up else None
        if connection_generation is not None:
            if self._generation is None:
                self._generation = connection_generation
            elif connection_generation != self._generation:
                # Survives a full reconnect cycle completed between stamps.
                self._generation = connection_generation
                caught_up = False
                reason = "reconnect"
        backlog = 0
        if caught_up and queue_progress is not None:
            enqueued, delivered, evicted = queue_progress
            backlog = enqueued - delivered - evicted
            if backlog != 0:
                # Bounded delay, not empty queue (T2.5e, module docstring):
                # still a break unless the oldest pending event's own
                # timestamp proves it has not reached the claimed window.
                candidate_cut = moment - timedelta(seconds=COVERAGE_SAFETY_S)
                if oldest_pending_ts is None or oldest_pending_ts <= candidate_cut:
                    caught_up = False
                    reason = "queue_backlog"

        was_broken = self._break_reason is not None
        if caught_up and was_broken and self._break_reason == "queue_backlog":
            assert self._broken_since_monotonic is not None
            logger.info(
                "tape_coverage_interval_resumed",
                exchange=self.exchange,
                reason="queue_backlog",
                frozen_for_s=monotonic() - self._broken_since_monotonic,
            )
        if caught_up and was_broken and self._break_reason == "reconnect":
            # Confirmed resumption from a real rupture: a fresh, conservative
            # session starts now rather than stretching the old one across a
            # gap this process could not see through.
            self._session_since = moment
            self._symbols = {symbol: moment for symbol in self._symbols}
            self._last_safe_covered_until = None
        if not caught_up:
            if reason != "reconnect" and self._break_reason == "reconnect":
                # "reconnect" outranks and survives a backlog observed before
                # resumption is confirmed (else the next caught-up tick would
                # merely un-freeze instead of starting the fresh session the
                # rupture still requires).
                reason = "reconnect"
            if reason is not None and not was_broken:
                logger.warning(
                    "tape_coverage_interval_broken",
                    exchange=self.exchange,
                    reason=reason,
                    backlog=backlog,
                )
                self._broken_since_monotonic = monotonic()
            self._break_reason = reason
        else:
            self._break_reason = None
            self._broken_since_monotonic = None

        if caught_up:
            self._last_safe_covered_until = moment - timedelta(seconds=COVERAGE_SAFETY_S)
        covered_until = (
            self._last_safe_covered_until
            if self._last_safe_covered_until is not None
            else self._session_since
        )
        if covered_until < self._session_since:
            covered_until = self._session_since
        # Per symbol, the truth is ``max(this session, that symbol's own
        # subscription)``: the aggregate ``session_since`` published by
        # ``coverage_publish`` is the MIN across shards, a lower bound that
        # must never lift a symbol's own start (the reader takes the max of
        # the two).
        symbols = {
            symbol: max(since, self._session_since) for symbol, since in self._symbols.items()
        }
        await coverage_publish.publish(
            redis,
            self.exchange,
            shard=self.shard,
            session_since=self._session_since,
            covered_until=covered_until,
            symbols=symbols,
            now=moment,
            key_ttl_s=COVERAGE_TTL_S,
            market_type=self.market_type,
        )
        self._claiming = True
        return True

    async def _clear(self, redis: redis_asyncio.Redis, moment: datetime) -> None:
        """This shard's interval ended — an empty record, not a deleted key
        (``coverage_publish.publish``)."""
        await coverage_publish.publish(
            redis,
            self.exchange,
            shard=self.shard,
            session_since=None,
            covered_until=None,
            symbols={},
            now=moment,
            key_ttl_s=COVERAGE_TTL_S,
            market_type=self.market_type,
        )
        self._claiming = False
