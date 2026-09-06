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

**T2.5-adapter** (full account: ``.claude/state/astra-review-T2.5-adapter-diff.md``)
closed two gaps the 0.5s margin alone cannot see through, both read at
**stamp time** (every housekeeping tick, ~250ms), never per event:

- **an internal reconnect.** ``ConnectionRunner.run`` (``binance/connection.py``)
  retries a dropped socket without ever ending :meth:`stream`'s generator, so
  a session that only broke when that generator ended could keep publishing
  "continuous" straight through a real gap. Two signals catch it: ``ws_state``
  (the adapter's own ``connection_state()``, mandatory, set to
  ``"reconnecting"`` *before* the close awaits, worst state across every
  connection key) and ``connection_generation`` (a monotonic counter, bumped
  on every reconnect — catches a full connect→disconnect→reconnect cycle that
  completes *between* two stamps, which ``ws_state`` alone would read as
  "connected" throughout). Either changing forces ``reason="reconnect"``;
  once both agree healthy again, a *fresh* session starts at the resumption
  instant rather than stretching the old one across a gap this process could
  not see through;
- **a backlogged queue without drops.** ``_in_flight == 0`` means no write
  *this process* started is unfinished, never that the adapter's own inbound
  queue was empty — an item its reader task already popped is not delivered
  until actually yielded. ``queue_progress`` (``enqueued``, ``delivered``,
  ``evicted``) fixes that: an eviction counts on its own side of the ledger
  so the one break it already causes (``dropped_events``) does not read as
  permanent backlog afterwards. Unlike a reconnect, this kind of backlog
  clearing without ever losing ``ws_state`` never invalidates the session —
  nothing was lost, only delayed.

**T2.5e** (``.claude/state/brief-T2.5e-coverage-caught-up.md``, full account
in ``.claude/state/notes-T2.5.md`` T2.5e section) found the ledger above
right but the bar wrong: at ~150 msg/s across 200 markets there is almost
always one item between an ``append`` and the matching ``get``, so
``enqueued == delivered + evicted`` was true only in the instant the queue
was fully empty — nearly never, and once broken the interval stayed
``reason="queue_backlog"`` forever (the warning only fires on *entering* the
break, measured on the local stack and the VPS). "Caught up" is now a
**bounded delay**: a nonzero backlog only breaks the interval if the oldest
pending event's own timestamp (:func:`hunter_exchanges.binance.event_queue._effective_ts`,
wall clock — ``queue_oldest_pending_ts()``) has itself reached the window
this stamp is about to claim covered (``moment - COVERAGE_SAFETY_S``); ahead
of that cut, the event's absence from ``delivered`` costs nothing the claim
depends on, and the 0.5s margin is doing exactly the job declared for it
above. A plain count threshold was rejected in design review (magnitude
decides nothing a timestamp does not already decide correctly), and so was a
*locally measured* age: an event can sit longer than the margin upstream of
this queue, invisibly, before ever being ``put``, so its own ``ts`` — not
how long *this* queue has known about it — is what must be checked, taken as
the *minimum* over every still-pending event (arrival order across several
reader tasks is not timestamp order) including one already popped from the
queue but not yet delivered (``queue_oldest_pending_ts()`` covers both; see
that module's docstring for how).

All four signals are read in the same housekeeping task that already calls
:meth:`writing`/:meth:`written`. ``connection_generation``/``queue_progress``/
``queue_oldest_pending_ts`` are read defensively (``getattr``, additive
capability, same pattern as ``rest_gate_status``); ``ws_state`` is not, since
``connection_state()`` is mandatory. An adapter implementing none of the
additive methods behaves exactly as before this module existed: ``ws_state``
defaults to ``"connected"``, the other three to ``None``.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from time import monotonic
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
        # T2.5-adapter: the last ``covered_until`` computed while genuinely
        # caught up (already margin-adjusted) — frozen, not the raw clock,
        # while ``ws_state``/``queue_progress`` say otherwise (Astra review:
        # freezing on the raw clock would let the very first backlogged tick
        # unduly regain the 0.5s the margin had been holding back).
        self._last_safe_covered_until: datetime | None = None
        #: ``None`` while caught up; otherwise the reason the *last* stamp
        #: was not — ``"reconnect"`` (ws_state or connection_generation) vs
        #: ``"queue_backlog"`` decide whether resuming starts a fresh session
        #: or simply un-freezes the current one (see module docstring).
        self._break_reason: str | None = None
        #: Monotonic reading when the current break started (T2.5e resumption
        #: log; monotonic so a wall-clock adjustment cannot go negative).
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
