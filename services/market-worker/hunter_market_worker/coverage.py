"""The collector's proof that it was still listening — ``covered_until``.

``hunter_indicators.features.windows.trades_between`` refuses a trade window
unless the collector proves it stayed connected through it: the tape alone
cannot tell a quiet market from a dropped connection (T2.2 notes §12.3/§13).
Until then, ``trade_velocity_1m``, ``buy_pressure_5m`` and ``sell_pressure_5m``
are ``insufficient_coverage`` and no EARLY is confirmed.

Only this process can produce the proof, and only about the interval it can
actually stand behind: **the session**, not the socket (a *cumulative*
``dropped_events`` next to ``ws_state=connected`` would let a connection that
lost one trade still read as covered — a drop ends the interval and a new one
starts at that instant); **per symbol** (subscribed mid-session = covered
only from then); and **short of the clock** (an event already received may
not have reached the tape yet, so a stamp claims ``now - COVERAGE_SAFETY_S``,
never ``now`` — :meth:`writing`/:meth:`written` hold it back mid-write too).

The scanner then evaluates each market at ``as_of = covered_until`` instead of
at its own clock: "as it was observable at ``as_of``" is what ``MarketContext``
means -- the only honest way to satisfy a proof that is always behind.

**T2.5-adapter** (``.claude/state/astra-review-T2.5-adapter-diff.md``) closed
two gaps the margin alone cannot see through, both read at **stamp time**: an
**internal reconnect** the adapter retries without ending :meth:`stream`'s
generator (``ws_state``/``connection_generation``, the latter also catching a
full cycle *between* two stamps — either forces a *fresh* session on
resumption); and a **backlogged queue without drops** (``_in_flight == 0``
only proves no write *this process* started is unfinished — an eviction never
reads as permanent backlog once it clears, unlike a reconnect).

**T2.5e** (``.claude/state/notes-T2.5.md`` T2.5e) found that ledger right but
its bar wrong: ``enqueued == delivered + evicted`` holds only when the queue
is momentarily empty, so the interval broke on nearly every stamp. "Caught
up" is now a **bounded delay**: a nonzero backlog only breaks the interval if
the oldest pending event's own ``ts`` (``queue_oldest_pending_ts()``) has
itself reached the window this stamp is about to claim.

**T2.5g** made the collector N processes (``MARKET_SHARD=i/N``); what this
shard can stand behind is decided here as before, *publishing* moved to
:mod:`hunter_market_worker.coverage_publish` (one Lua script, conservative
merge). ``connection_generation``/``queue_progress``/``queue_oldest_pending_ts``
are read defensively (additive), ``ws_state`` is not — an adapter
implementing none of them behaves as before this module existed.

**T3.46d — the book stamp race** (``.claude/state/notes-T3.46d.md`` §1-2). The
margin above guards events received but not yet yielded upstream — nothing
about how fresh a live book naturally is, and against this module's own
independently-scheduled housekeeping tick a book was newer than
``covered_until`` in 89% of paired VPS reads (a 500ms tolerance would still
leave ~28% ``after_cut``, rejected). :meth:`observe_proof` closes the race:
every event *already accepted* floors ``stamp``'s claim at its own ``ts`` —
never past it or the stamp's own clock, only while ``caught_up``.

**T3.46g** closes the remaining phase gap: :meth:`stamp` is unchanged, only
called from a second place — after :mod:`hunter_market_worker.coalesce`'s
flush writes a cycle's book/ticker, on top of the periodic housekeeping
fallback. :data:`CoverageStampFn` is the one closure both callers share.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
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

CoverageStampFn = Callable[[], Awaitable[bool]]
"""One session's live :meth:`CoverageTracker.stamp` call, closed over its own
adapter/ledger (T3.46g module docstring) — built once, shared by two callers."""

__all__ = [
    "COVERAGE_SAFETY_S",
    "COVERAGE_STAMP_S",
    "COVERAGE_TTL_S",
    "CoverageStampFn",
    "CoverageTracker",
]


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
        self._observed_proof: datetime | None = None  # T3.46d: newest ts accepted

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
        self._observed_proof = None

    def session_broken(self) -> None:
        """The stream ended (error, restart, universe reconnect): no coverage."""
        self._session_since = None
        self._symbols = {}
        self._last_safe_covered_until = None
        self._break_reason = None
        self._broken_since_monotonic = None
        self._generation = None
        self._observed_proof = None

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

    def observe_proof(self, ts: datetime | None) -> None:
        """``ts`` of an event already accepted this session (T3.46d)."""
        if ts is not None and (self._observed_proof is None or ts > self._observed_proof):
            self._observed_proof = ts

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
            # Confirmed resumption from a real rupture: a fresh, conservative session
            # starts now rather than stretching the old one across an unseen gap.
            self._session_since = moment
            self._symbols = {symbol: moment for symbol in self._symbols}
            self._last_safe_covered_until = None
            self._observed_proof = None  # a proof from before the gap is not a proof
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
            margin_based = moment - timedelta(seconds=COVERAGE_SAFETY_S)
            proof = self._observed_proof
            if proof is not None and proof > margin_based:  # T3.46d floor
                margin_based = proof if proof < moment else moment
            self._last_safe_covered_until = margin_based
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
