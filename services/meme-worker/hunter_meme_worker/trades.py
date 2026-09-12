"""The tape puller: ``swap-api`` trades into ``meme_trades``, inside a global
budget and in a declared priority — pure planning, IO in :func:`pull_once`.

**Budget**: ``MEME_SWAP_API_BUDGET_60S`` (900 = the measured 1000 minus 10 %)
is the adapter's token bucket; this module spends at most its share of it per
cycle (``budget_60s × cycle_s / 60``) so a 10 s cycle never bursts the minute.

**Priority** (the brief's, and the adendo's): mints with an **open paper bet**
first, then the ``graduating`` board, then ``new``, then the rest — and each
tier has its own minimum interval between pulls (10 s, 10 s, 20 s, 60 s), so
the tape of the mints the Lab is deciding on is at most seconds old while a
quiet mint is read once a minute. Inside a tier the least recently pulled goes
first.

**Concurrency, and why it is the T4.2e fix.** T4.2c pulled sequentially: with
~250 tracked mints at 250–450 ms a request the "10 s" cycle took ~90 s, the
10 s tiers were pulled every ~90 s, one round of the rest tier took more than
a minute, and ``swap_api_used_60s`` sat at ~170 of 900 — which is what
08:35 BRT on 12/09 measured as 109 of 250 gate rows without tape, three
minutes after a deploy had reset the in-memory coverage. Pulls now run
``concurrency`` at a time (``MEME_TRADES_CONCURRENCY``, 8) behind the adapter's
bucket, which is what paces them: a 250-mint round takes ~10 s, the tiers mean
what they say, and every tracked mint is pulled at least once a minute inside
the budget. What the cap still cannot reach is **named**: a mint due this cycle
but cut by ``budget_per_cycle`` is remembered, and the minute's ``tape_reason``
for it is ``not_polled`` — the curve's word for the same fact.

**Cursor**: the API lists newest first with a cursor towards *older* trades.
The puller keeps, per mint, the newest ``slotIndexId`` it has stored (the
high-water mark) and follows the cursor only while the page did not reach it —
bounded by ``max_pages`` per pull, so one very active mint cannot spend the
cycle. Dedupe is the schema's ``(block_time, signature, event_index)``; the mark
only saves requests.

**Coverage** is what makes a zero honest: ``covered_since[mint]`` is the
receive time of the first successful pull, and the fold writes a tape number
for a minute only when the mint was covered by that minute's close
(``features_tape.tape_for``) **and** its newest successful pull at that close is
younger than ``stale_s`` (180 s = three rest intervals): a tape the source
stopped answering for is not a zero, it is ``rate_limited`` or ``no_trade_feed``
again. A refused pull is an error on the source, never a silent empty tape.
"""

from __future__ import annotations

import asyncio
import time
from collections import deque
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Protocol

from hunter_core.db.session import role_session
from hunter_core.logging import get_logger
from hunter_exchanges.base import RateLimited
from hunter_meme_worker.repo_tape import insert_trades, trade_rows
from hunter_meme_worker.sources import SWAP_API, SourcesState
from hunter_meme_worker.tracker import TIER_GRADUATING, TIER_NEW, TIER_OPEN_BET

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    from hunter_exchanges.pumpfun.swap_api import TradesPage

logger = get_logger(__name__)

WORKER_ROLE = "hunter_worker"
MIN_INTERVAL_S: Mapping[int, float] = {
    TIER_OPEN_BET: 10.0,
    TIER_GRADUATING: 10.0,
    TIER_NEW: 20.0,
}
DEFAULT_INTERVAL_S = 60.0
DEFAULT_CONCURRENCY = 8
DEFAULT_STALE_S = 180.0
RATE_LIMITED = "rate_limited"
NO_TRADE_FEED = "no_trade_feed"
NOT_POLLED = "not_polled"


class TradeSource(Protocol):
    async def get_trades(
        self, mint: str, *, limit: int = 100, cursor: str | None = None
    ) -> TradesPage: ...


@dataclass
class TapeCoverage:
    covered_since: datetime | None = None
    last_pull_at: datetime | None = None
    ok_times: deque[datetime] = field(default_factory=lambda: deque(maxlen=8))
    """Receive times of the newest successful pulls — the fold asks for the
    newest one at or before a minute's close (non-anticipation)."""
    high_water: str | None = None
    """The newest ``slotIndexId`` stored for the mint."""
    last_error: str | None = None
    pulls: int = 0
    rows: int = 0


@dataclass(frozen=True, slots=True)
class PullReport:
    pulled: int
    rows: int
    pages: int
    errors: int
    skipped: dict[str, int] = field(default_factory=dict[str, int])
    planned: int = 0
    deferred: int = 0
    """Due this cycle, cut by the cap — each remembered as ``not_polled``."""
    duration_s: float = 0.0


@dataclass(frozen=True, slots=True)
class TapeStats:
    """How much of the tracked set the tape covers right now."""

    tracked: int
    covered: int
    never_pulled: int
    failing: int
    """Never covered and the last pull failed (the source's problem, named)."""


class TradesPuller:
    def __init__(
        self,
        client: TradeSource,
        *,
        budget_60s: int,
        cycle_s: float,
        max_pages: int = 3,
        sources: SourcesState | None = None,
        concurrency: int = DEFAULT_CONCURRENCY,
        stale_s: float = DEFAULT_STALE_S,
    ) -> None:
        self._client = client
        self._budget_per_cycle = max(1, int(budget_60s * cycle_s / 60))
        self._max_pages = max(1, max_pages)
        self._sources = sources
        self.concurrency = max(1, concurrency)
        self._stale = timedelta(seconds=stale_s)
        self.coverage: dict[str, TapeCoverage] = {}
        self.not_planned: dict[str, datetime] = {}
        """Mints the last plan left out for the cap, with when — the
        ``not_polled`` of the tape."""
        self.last_deferred = 0

    @property
    def budget_per_cycle(self) -> int:
        return self._budget_per_cycle

    def covered_since(self, mint: str) -> datetime | None:
        state = self.coverage.get(mint)
        return None if state is None else state.covered_since

    def coverage_for(self, mint: str, end_time: datetime) -> datetime | None:
        """``covered_since`` if the mint's tape is usable at ``end_time``: covered,
        and the newest successful pull at or before ``end_time`` younger than
        ``stale_s``. ``None`` otherwise — :meth:`absence_reason` says why."""
        state = self.coverage.get(mint)
        if state is None or state.covered_since is None:
            return None
        # The first successful pull is a successful pull: ``covered_since`` stands
        # in for an empty ``ok_times`` (a coverage restored without its history).
        oks = list(state.ok_times) or [state.covered_since]
        fresh = [at for at in oks if at <= end_time]
        if not fresh or end_time - max(fresh) > self._stale:
            return None
        return state.covered_since

    def absence_reason(self, mint: str) -> str:
        """Why a minute has no tape for ``mint`` — asked only when it has none."""
        state = self.coverage.get(mint)
        if state is not None and state.last_error == RATE_LIMITED:
            return RATE_LIMITED
        if (state is None or state.covered_since is None) and mint in self.not_planned:
            return NOT_POLLED
        return NO_TRADE_FEED

    def plan(self, tiers: Mapping[str, int], now: datetime) -> list[str]:
        """Which mints to pull this cycle: due by their tier's interval, ordered
        by tier then by staleness, capped by the cycle's share of the budget.
        The mints the cap leaves out are remembered as ``not_planned``."""
        due: list[tuple[int, datetime, str]] = []
        for mint, tier in tiers.items():
            state = self.coverage.get(mint)
            last = None if state is None else state.last_pull_at
            interval = MIN_INTERVAL_S.get(tier, DEFAULT_INTERVAL_S)
            if last is not None and (now - last) < timedelta(seconds=interval):
                continue
            due.append((tier, last or datetime.min.replace(tzinfo=now.tzinfo), mint))
        due.sort()
        planned = [mint for _, _, mint in due[: self._budget_per_cycle]]
        deferred = [mint for _, _, mint in due[self._budget_per_cycle :]]
        for mint in planned:
            self.not_planned.pop(mint, None)
        for mint in deferred:
            self.not_planned[mint] = now
        self.last_deferred = len(deferred)
        return planned

    def stats(self, tiers: Mapping[str, int]) -> TapeStats:
        covered = never = failing = 0
        for mint in tiers:
            state = self.coverage.get(mint)
            if state is not None and state.covered_since is not None:
                covered += 1
            elif state is not None and state.last_error is not None:
                failing += 1
            else:
                never += 1
        return TapeStats(tracked=len(tiers), covered=covered, never_pulled=never, failing=failing)

    async def pull(
        self, session_factory: async_sessionmaker[AsyncSession], mint: str, *, now: datetime
    ) -> PullReport:
        """One mint: page 1, then older pages until the high-water mark or the cap."""
        state = self.coverage.setdefault(mint, TapeCoverage())
        state.last_pull_at = now
        cursor: str | None = None
        pages = 0
        rows_written = 0
        skipped: dict[str, int] = {}
        newest: str | None = None
        seen: set[str] = set()
        reached = False
        received: datetime | None = None
        while pages < self._max_pages and not reached:
            try:
                page = await self._client.get_trades(mint, cursor=cursor)
            except RateLimited as exc:
                state.last_error = RATE_LIMITED
                self._error(now, f"{RATE_LIMITED}:{exc.retry_after_s:.0f}s")
                return PullReport(pulled=0, rows=rows_written, pages=pages, errors=1)
            except Exception as exc:  # one mint's failure is not the cycle's
                state.last_error = type(exc).__name__
                self._error(now, type(exc).__name__)
                logger.warning("meme_tape_pull_failed", mint=mint, error=str(exc))
                return PullReport(pulled=0, rows=rows_written, pages=pages, errors=1)
            pages += 1
            state.pulls += 1
            received = received or page.received_at
            if self._sources is not None:
                observed = page.trades[0].observed_at if page.trades else page.received_at
                self._sources[SWAP_API].record_ok(
                    observed_at=observed, received_at=page.received_at
                )
            if newest is None and page.trades:
                newest = page.trades[0].slot_index_id
            fresh = [
                t
                for t in page.trades
                if (state.high_water is None or t.slot_index_id > state.high_water)
                and t.slot_index_id not in seen
            ]
            seen.update(t.slot_index_id for t in fresh)
            # Stop at the mark, at the end of the tape, or on a page that adds
            # nothing (a cursor that stopped moving must not spend the cap).
            reached = len(fresh) < len(page.trades) or not page.has_more or not fresh
            rows, page_skipped = trade_rows(fresh)
            for reason, count in page_skipped.items():
                skipped[reason] = skipped.get(reason, 0) + count
            if rows:
                async with role_session(session_factory, db_role=WORKER_ROLE) as session:
                    rows_written += await insert_trades(session, rows)
            cursor = page.next_cursor
            if cursor is None:
                reached = True
        # Coverage is stamped with the *receive* time of the first page: a pull
        # that straddles a minute's close covers the next minute, not this one.
        received = received or now
        state.covered_since = state.covered_since or received
        state.ok_times.append(received)
        state.last_error = None
        state.rows += rows_written
        if newest is not None and (state.high_water is None or newest > state.high_water):
            state.high_water = newest
        return PullReport(pulled=1, rows=rows_written, pages=pages, errors=0, skipped=skipped)

    def _error(self, at: datetime, error: str) -> None:
        if self._sources is not None:
            self._sources[SWAP_API].record_spent(at)
            self._sources[SWAP_API].record_error(at, error)


async def pull_once(
    puller: TradesPuller,
    session_factory: async_sessionmaker[AsyncSession],
    *,
    tiers: Mapping[str, int],
    now: datetime,
    clock: Callable[[], datetime] | None = None,
) -> PullReport:
    """One cycle over the planned mints, ``concurrency`` at a time (the bucket
    paces them). ``clock`` stamps each pull with its own start time; without it
    every pull carries ``now`` (the tests' fixed clock)."""
    started = time.monotonic()
    planned = puller.plan(tiers, now)
    gate = asyncio.Semaphore(puller.concurrency)

    async def one(mint: str) -> PullReport:
        async with gate:
            return await puller.pull(session_factory, mint, now=clock() if clock else now)

    reports = await asyncio.gather(*(one(mint) for mint in planned))
    pulled = rows = pages = errors = 0
    skipped: dict[str, int] = {}
    for report in reports:
        pulled += report.pulled
        rows += report.rows
        pages += report.pages
        errors += report.errors
        for reason, count in report.skipped.items():
            skipped[reason] = skipped.get(reason, 0) + count
    return PullReport(
        pulled=pulled,
        rows=rows,
        pages=pages,
        errors=errors,
        skipped=skipped,
        planned=len(planned),
        deferred=puller.last_deferred,
        duration_s=round(time.monotonic() - started, 3),
    )
