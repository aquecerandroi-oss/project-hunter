"""The tape puller: ``swap-api`` trades into ``meme_trades``, inside the budget
the edge actually enforces and in a declared priority — pure planning, IO in
:func:`pull_once`.

**Budget** (T4.2f, ``tape_budget.py``): ``MEME_SWAP_API_BUDGET_60S`` (16 = the
measured Cloudflare ceiling of ~20/60 s per IP minus margin) handed to each
10 s cycle as its exact share, a real 429 shrinking it and blocking the
``retry-after``. Sixteen a minute is the number: what the tape can cover is
bounded by it, and the rows say so.

**One page per mint per minute.** The 100 newest trades are the minute for
every mint the radar tracks; the cursor walk towards older pages
(``max_pages``) is kept only for the mints with an **open paper bet**, whose
whole covered tape the Lab reads for ``creator_sold``. Every tier is due once
a minute; the priority — open bet, ``graduating``, ``new``, young, rest — decides
who gets the 16, least recently pulled first inside a tier.

**Coverage** is what makes a zero honest: ``covered_since[mint]`` is the
receive time of the first successful pull, and the fold writes a tape number
for a minute only when the mint was covered by that minute's close
(``features_tape.tape_for``) **and** its newest successful pull at that close is
younger than ``stale_s`` (180 s): a tape the source stopped answering for is
not a zero. When there is none, :meth:`TradesPuller.absence_reason` says why,
and the words mean what they say: ``rate_limited`` only when the server refused
(a real 429, or the block it imposed — never our own bucket), ``not_polled``
when the budget did not reach the mint, ``no_trade_feed`` when it was never
pulled at all.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Callable, Mapping
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Protocol

from hunter_core.db.session import role_session
from hunter_core.logging import get_logger
from hunter_exchanges.base import RateLimited
from hunter_exchanges.pumpfun.rate_shared import HttpRateLimited
from hunter_meme_worker.repo_tape import insert_trades, trade_rows
from hunter_meme_worker.sources import SWAP_API, SourcesState
from hunter_meme_worker.tape_budget import (
    BUDGET_REFUSED,
    NO_TRADE_FEED,
    NOT_POLLED,
    RATE_LIMITED,
    PullReport,
    TapeBudget,
    TapeCoverage,
    TapeStats,
)
from hunter_meme_worker.tracker import TIER_OPEN_BET

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    from hunter_exchanges.pumpfun.swap_api import TradesPage

logger = get_logger(__name__)

WORKER_ROLE = "hunter_worker"
MIN_INTERVAL_S: Mapping[int, float] = {}
"""Every tier is due once a minute (T4.2f); the priority decides who gets the budget."""
DEFAULT_INTERVAL_S = 60.0
DEFAULT_CONCURRENCY = 2
DEFAULT_STALE_S = 180.0

__all__ = [
    "DEFAULT_INTERVAL_S",
    "MIN_INTERVAL_S",
    "NOT_POLLED",
    "NO_TRADE_FEED",
    "RATE_LIMITED",
    "PullReport",
    "TapeCoverage",
    "TapeStats",
    "TradeSource",
    "TradesPuller",
    "pull_once",
]


class TradeSource(Protocol):
    async def get_trades(
        self, mint: str, *, limit: int = 100, cursor: str | None = None
    ) -> TradesPage: ...


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
        adapt_hold_s: float = 900.0,
    ) -> None:
        self._client = client
        self.budget = TapeBudget(budget_60s=budget_60s, cycle_s=cycle_s, hold_s=adapt_hold_s)
        self._max_pages = max(1, max_pages)
        self._sources = sources
        self.concurrency = max(1, concurrency)
        self._stale = timedelta(seconds=stale_s)
        self.coverage: dict[str, TapeCoverage] = {}
        self.not_planned: dict[str, datetime] = {}
        """Mints the budget left out, with when — the ``not_polled`` of the tape."""
        self.last_deferred = 0

    @property
    def budget_per_cycle(self) -> int:
        return self.budget.per_cycle_nominal

    @property
    def max_pages(self) -> int:
        return self._max_pages

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

    def absence_reason(self, mint: str, at: datetime | None = None) -> str:
        """Why a minute has no tape for ``mint`` — asked only when it has none.
        ``at`` (the minute's close) is what the server's block is judged at."""
        if at is not None and self.budget.blocked_at(at):
            return RATE_LIMITED
        if mint in self.not_planned:
            return NOT_POLLED
        state = self.coverage.get(mint)
        if state is not None and state.last_error == RATE_LIMITED:
            return RATE_LIMITED
        return NO_TRADE_FEED

    def plan(self, tiers: Mapping[str, int], now: datetime) -> list[str]:
        """Which mints to pull this cycle: due by their tier's interval, ordered
        by tier then by staleness, capped by the cycle's share of the budget
        (zero while the server's block lasts). The mints the cap leaves out are
        remembered as ``not_planned``."""
        due: list[tuple[int, datetime, str]] = []
        for mint, tier in tiers.items():
            state = self.coverage.get(mint)
            last = None if state is None else state.last_pull_at
            interval = MIN_INTERVAL_S.get(tier, DEFAULT_INTERVAL_S)
            if last is not None and (now - last) < timedelta(seconds=interval):
                continue
            due.append((tier, last or datetime.min.replace(tzinfo=now.tzinfo), mint))
        due.sort()
        cap = self.budget.per_cycle(now)
        planned = [mint for _, _, mint in due[:cap]]
        deferred = [mint for _, _, mint in due[cap:]]
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
        self,
        session_factory: async_sessionmaker[AsyncSession],
        mint: str,
        *,
        now: datetime,
        max_pages: int | None = None,
    ) -> PullReport:
        """One mint: page 1, then older pages until the high-water mark or the cap."""
        state = self.coverage.setdefault(mint, TapeCoverage())
        state.last_pull_at = now
        limit = self._max_pages if max_pages is None else max(1, max_pages)
        cursor: str | None = None
        pages = rows_written = 0
        skipped: dict[str, int] = {}
        newest: str | None = None
        seen: set[str] = set()
        reached = False
        received: datetime | None = None
        while pages < limit and not reached:
            try:
                page = await self._client.get_trades(mint, cursor=cursor)
            except HttpRateLimited as exc:  # the server's word: measure, shrink, block
                state.last_error = RATE_LIMITED
                effective = self.budget.record_refusal(now, retry_after_s=exc.retry_after_s)
                self._error(now, f"{RATE_LIMITED}:{exc.retry_after_s:.0f}s")
                logger.warning(
                    "meme_tape_rate_limited",
                    mint=mint,
                    retry_after_s=exc.retry_after_s,
                    edge=exc.edge,
                    measured_60s=self.budget.measured,
                    effective_budget_60s=effective,
                )
                return PullReport(pulled=0, rows=rows_written, pages=pages, errors=1, refused_429=1)
            except RateLimited:  # our own bucket: the budget did not reach the mint
                state.last_error = BUDGET_REFUSED
                self.not_planned[mint] = now
                self._error(now, BUDGET_REFUSED)
                return PullReport(pulled=0, rows=rows_written, pages=pages, errors=1)
            except Exception as exc:  # one mint's failure is not the cycle's
                state.last_error = type(exc).__name__
                self._error(now, type(exc).__name__)
                logger.warning("meme_tape_pull_failed", mint=mint, error=str(exc))
                return PullReport(pulled=0, rows=rows_written, pages=pages, errors=1)
            pages += 1
            state.pulls += 1
            received = received or page.received_at
            self.budget.record_ok(page.received_at)
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
    """One cycle over the planned mints, ``concurrency`` at a time. ``clock``
    stamps each pull with its own start time; without it every pull carries
    ``now`` (the tests' fixed clock). Open bets walk ``max_pages``; everyone
    else gets the one page that is the minute."""
    started = time.monotonic()
    planned = puller.plan(tiers, now)
    gate = asyncio.Semaphore(puller.concurrency)

    async def one(mint: str) -> PullReport:
        async with gate:
            pages = puller.max_pages if tiers.get(mint) == TIER_OPEN_BET else 1
            return await puller.pull(
                session_factory, mint, now=clock() if clock else now, max_pages=pages
            )

    reports = await asyncio.gather(*(one(mint) for mint in planned))
    pulled = rows = pages = errors = refused = 0
    skipped: dict[str, int] = {}
    for report in reports:
        pulled += report.pulled
        rows += report.rows
        pages += report.pages
        errors += report.errors
        refused += report.refused_429
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
        refused_429=refused,
    )
