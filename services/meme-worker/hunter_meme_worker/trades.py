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

**Cursor**: the API lists newest first with a cursor towards *older* trades.
The puller keeps, per mint, the newest ``slotIndexId`` it has stored (the
high-water mark) and follows the cursor only while the page did not reach it —
bounded by ``max_pages`` per pull, so one very active mint cannot spend the
cycle. Dedupe is the schema's ``(block_time, signature, event_index)``; the mark
only saves requests.

**Coverage** is what makes a zero honest: ``covered_since[mint]`` is the
receive time of the first successful pull, and the fold writes a tape number
for a minute only when the mint was covered by that minute's close
(``features_tape.tape_for``). A refused pull is an error on the source, a
``rate_limited`` reason on the minute, never a silent empty tape.
"""

from __future__ import annotations

from collections.abc import Mapping
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


class TradeSource(Protocol):
    async def get_trades(
        self, mint: str, *, limit: int = 100, cursor: str | None = None
    ) -> TradesPage: ...


@dataclass
class TapeCoverage:
    covered_since: datetime | None = None
    last_pull_at: datetime | None = None
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


class TradesPuller:
    def __init__(
        self,
        client: TradeSource,
        *,
        budget_60s: int,
        cycle_s: float,
        max_pages: int = 3,
        sources: SourcesState | None = None,
    ) -> None:
        self._client = client
        self._budget_per_cycle = max(1, int(budget_60s * cycle_s / 60))
        self._max_pages = max(1, max_pages)
        self._sources = sources
        self.coverage: dict[str, TapeCoverage] = {}

    def covered_since(self, mint: str) -> datetime | None:
        state = self.coverage.get(mint)
        return None if state is None else state.covered_since

    def absence_reason(self, mint: str) -> str:
        state = self.coverage.get(mint)
        if state is not None and state.covered_since is None and state.last_error == "rate_limited":
            return "rate_limited"
        return "no_trade_feed"

    def plan(self, tiers: Mapping[str, int], now: datetime) -> list[str]:
        """Which mints to pull this cycle: due by their tier's interval, ordered
        by tier then by staleness, capped by the cycle's share of the budget."""
        due: list[tuple[int, datetime, str]] = []
        for mint, tier in tiers.items():
            state = self.coverage.get(mint)
            last = None if state is None else state.last_pull_at
            interval = MIN_INTERVAL_S.get(tier, DEFAULT_INTERVAL_S)
            if last is not None and (now - last) < timedelta(seconds=interval):
                continue
            due.append((tier, last or datetime.min.replace(tzinfo=now.tzinfo), mint))
        due.sort()
        return [mint for _, _, mint in due[: self._budget_per_cycle]]

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
        while pages < self._max_pages and not reached:
            try:
                page = await self._client.get_trades(mint, cursor=cursor)
            except RateLimited as exc:
                state.last_error = "rate_limited"
                self._error(now, f"rate_limited:{exc.retry_after_s:.0f}s")
                return PullReport(pulled=0, rows=rows_written, pages=pages, errors=1)
            except Exception as exc:  # one mint's failure is not the cycle's
                state.last_error = type(exc).__name__
                self._error(now, type(exc).__name__)
                logger.warning("meme_tape_pull_failed", mint=mint, error=str(exc))
                return PullReport(pulled=0, rows=rows_written, pages=pages, errors=1)
            pages += 1
            state.pulls += 1
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
        state.covered_since = state.covered_since or now
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
) -> PullReport:
    """One cycle over the planned mints, sequential (the bucket paces it)."""
    pulled = rows = pages = errors = 0
    skipped: dict[str, int] = {}
    for mint in puller.plan(tiers, now):
        report = await puller.pull(session_factory, mint, now=now)
        pulled += report.pulled
        rows += report.rows
        pages += report.pages
        errors += report.errors
        for reason, count in report.skipped.items():
            skipped[reason] = skipped.get(reason, 0) + count
    return PullReport(pulled=pulled, rows=rows, pages=pages, errors=errors, skipped=skipped)
