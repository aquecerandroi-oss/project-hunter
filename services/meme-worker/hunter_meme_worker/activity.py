"""The tape by batch (T4.2g): once a minute, the activity of **every** tracked
coin from ``POST /v1/coins/market-activity/batch`` — 50 coins a request, the
same Cloudflare budget as the per-mint tape (``trades.py``), the response's
own stamp as the instant the windows end — into ``meme_market_activity_1m``
and, through :func:`batch_minute`, into the tape columns of the minute and
of the 15-second row when the per-mint tape did not cover them.

**Why.** T4.2f measured the per-mint tape's ceiling from one IP at ~40 % of
the gate's rows a minute (16 pulls/min × 180 s of freshness ÷ ~130 coins),
and the flow gate (``flow_v2/1``) refused ~100 of ~110 young coins a tick for
want of a tape. Three batch requests a minute count buys, sells, distinct
buyers and USD volumes for all of them.

**Budget, declared.** The batch's calls are *reserved* off the top of the
tape's ``TapeBudget`` (``budget.reserve``): with 16/60 s and ~130 tracked
coins the batch takes 3 and the per-mint tape keeps 13 — for the open bets
and the ``graduating`` board first, as its priority already says. A real
429 on a batch call is the same 429 the tape sees (measure, shrink, block),
and the batch does not fire while the block lasts.

**When.** The loop fires ``activity_lead_s`` (3 s) *before* each minute
close, so the ``1m`` window the response describes ends a few seconds before
the minute the fold judges — the closest a polled aggregate can come to
"the window whose end coincides with the minute". The fold reads the newest
reading received by the minute's close and at most ``activity_max_age_s``
(60 s) old, and writes ``tape_source = activity_1m``, ``tape_as_of`` = the
window's end, so a reader sees exactly which sixty seconds the numbers cover.

**What the batch cannot say** stays unsaid: it does not name traders, so
``creator_net_seller`` keeps ``no_trade_feed`` and ``unique_buyers`` counts
the creator; it counts in USD, so the SOL columns are derived with the quote
the worker read from ``/sol-price`` (its own 50/60 s group) and carry that
quote's instant — ``no_sol_quote`` when none is younger than five minutes.
And the ``1m`` window, accepted by the route's validator but not yet seen
non-null on a trading coin (``market_activity.py``), is written as a zero
only in a cycle that filled it for someone; otherwise the cycle is *dark*
and the heartbeat says so (``activity_dark_60s``) instead of writing zeros.
"""

from __future__ import annotations

import asyncio
import dataclasses
import math
import time
from collections import deque
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Protocol

from hunter_core.db.session import role_session
from hunter_core.domain.types import utcnow
from hunter_core.logging import get_logger
from hunter_exchanges.base import RateLimited
from hunter_exchanges.pumpfun.market_activity import DEFAULT_WINDOWS, MAX_ADDRESSES, ActivityBatch
from hunter_exchanges.pumpfun.rate_shared import HttpRateLimited
from hunter_meme_worker.features_tape import (
    NO_SOL_QUOTE,
    ActivityReading,
    TapeMinute,
    activity_for,
    activity_minute,
)
from hunter_meme_worker.metrics import meme_rows_total, meme_source_messages_total
from hunter_meme_worker.repo_activity import (
    TAPE_WINDOW,
    ActivityRow,
    SolQuote,
    activity_rows,
    insert_activity,
)
from hunter_meme_worker.sources import SWAP_API, SWAP_API_ACTIVITY, SourcesState
from hunter_meme_worker.tape_budget import RATE_LIMITED, TapeBudget

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    from hunter_exchanges.pumpfun.models import NormalizedSolPrice
    from hunter_meme_worker.context import RadarContext
    from hunter_meme_worker.tracker import MintTracker

logger = get_logger(__name__)

WORKER_ROLE = "hunter_worker"
QUOTE_REFRESH_S = 60.0
"""The quote is re-read at most once a minute (its own upstream group, 50/60 s)."""
MIN_WAIT_S = 0.2

__all__ = [
    "ActivityPuller",
    "ActivityReport",
    "ActivitySource",
    "QuoteSource",
    "activity_mints",
    "activity_once",
    "batch_minute",
    "run_activity",
    "seconds_until_fire",
]


class ActivitySource(Protocol):
    async def market_activity_batch(
        self, mints: Sequence[str], *, windows: Sequence[str] = DEFAULT_WINDOWS
    ) -> ActivityBatch: ...


class QuoteSource(Protocol):
    async def get_sol_price(self) -> NormalizedSolPrice: ...


@dataclass(frozen=True, slots=True)
class ActivityReport:
    asked: int = 0
    calls: int = 0
    covered: int = 0
    """Coins with a ``1m`` reading this cycle — a number or a stated zero."""
    live: dict[str, int] = field(default_factory=dict[str, int])
    """Window → coins the route filled (non-null) this cycle."""
    dark: int = 0
    """Coins whose ``1m`` was ``null`` in a cycle nobody's ``1m`` was filled."""
    rows: int = 0
    errors: int = 0
    refused_429: int = 0
    skipped: str | None = None
    """``blocked`` (the edge's block is in force) | ``no_mints``."""
    duration_s: float = 0.0


class ActivityPuller:
    def __init__(
        self,
        client: ActivitySource,
        *,
        budget: TapeBudget,
        quotes: QuoteSource | None,
        sources: SourcesState | None = None,
        windows: Sequence[str] = DEFAULT_WINDOWS,
        batch_size: int = MAX_ADDRESSES,
        max_age_s: float = 60.0,
        quote_max_age_s: float = 300.0,
    ) -> None:
        self._client = client
        self.budget = budget
        self._quotes = quotes
        self._sources = sources
        self.windows = tuple(windows)
        self.batch_size = max(1, min(batch_size, MAX_ADDRESSES))
        self.max_age_s = max_age_s
        self._quote_max_age = timedelta(seconds=quote_max_age_s)
        self.readings: dict[str, deque[ActivityReading]] = {}
        """The newest two ``1m`` readings per coin — two, so a reading that
        landed after the instant judged cannot hide the one that had."""
        self.quote: SolQuote | None = None
        self.quote_error: str | None = None
        self.last_report: ActivityReport | None = None

    def reading_for(self, mint: str, *, at: datetime) -> ActivityReading | None:
        """The newest ``1m`` reading usable at ``at`` (non-anticipation and freshness)."""
        return activity_for(self.readings.get(mint, ()), at=at, max_age_s=self.max_age_s)

    async def sol_usd(self, now: datetime) -> SolQuote | None:
        """The quote to derive SOL with: re-read at most once a minute, kept up
        to ``quote_max_age_s``; ``None`` (and the error named) beyond that."""
        cached = self.quote
        if cached is not None and now - cached.observed_at < timedelta(seconds=QUOTE_REFRESH_S):
            return cached
        if self._quotes is not None:
            try:
                fresh = await self._quotes.get_sol_price()
                self.quote = SolQuote(price_usd=fresh.price_usd, observed_at=fresh.observed_at)
                self.quote_error = None
                return self.quote
            except Exception as exc:  # the quote's failure is not the batch's
                self.quote_error = type(exc).__name__
                logger.warning("meme_activity_quote_unavailable", error=str(exc)[:200])
        else:
            self.quote_error = "no_quote_source"
        if cached is not None and now - cached.observed_at < self._quote_max_age:
            return cached
        return None

    async def pull_once(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        mints: Sequence[str],
        *,
        now: datetime,
    ) -> ActivityReport:
        """One cycle: the quote, then one request per ``batch_size`` coins,
        stopped by the first 429; rows for what came back; the readings kept."""
        started = time.monotonic()
        self.budget.reserve(math.ceil(len(mints) / self.batch_size))
        if not mints:
            return self._done(now, ActivityReport(skipped="no_mints"), started)
        if self.budget.blocked_at(now):
            return self._done(now, ActivityReport(asked=len(mints), skipped="blocked"), started)
        quote = await self.sol_usd(now)
        batches: list[ActivityBatch] = []
        calls = errors = refused = 0
        for start in range(0, len(mints), self.batch_size):
            chunk = list(mints[start : start + self.batch_size])
            calls += 1
            try:
                batch = await self._client.market_activity_batch(chunk, windows=self.windows)
            except HttpRateLimited as exc:  # the edge's word: measure, shrink, block, stop
                errors += 1
                refused += 1
                self.budget.record_refusal(now, retry_after_s=exc.retry_after_s)
                self._error(now, f"{RATE_LIMITED}:{exc.retry_after_s:.0f}s")
                logger.warning("meme_activity_rate_limited", retry_after_s=exc.retry_after_s)
                break
            except RateLimited:  # our own bucket: the minute's budget is spent
                errors += 1
                self._error(now, "budget_refused")
                break
            except Exception as exc:  # one chunk's failure is not the cycle's
                errors += 1
                self._error(now, type(exc).__name__)
                logger.warning("meme_activity_batch_failed", size=len(chunk), error=str(exc)[:200])
                continue
            self.budget.record_ok(batch.received_at)
            batches.append(batch)
            if self._sources is not None:
                for name in (SWAP_API, SWAP_API_ACTIVITY):
                    self._sources[name].record_ok(
                        observed_at=batch.observed_at, received_at=batch.received_at
                    )
        rows, dark = activity_rows(batches, quote=quote)
        if rows:
            async with role_session(session_factory, db_role=WORKER_ROLE) as session:
                await insert_activity(session, rows)
        covered = self._remember(rows, now)
        live: dict[str, int] = {}
        for batch in batches:
            for reading in batch.readings:
                live[reading.window] = live.get(reading.window, 0) + 1
        report = ActivityReport(
            asked=len(mints),
            calls=calls,
            covered=covered,
            live=live,
            dark=dark.get(TAPE_WINDOW, 0),
            rows=len(rows),
            errors=errors,
            refused_429=refused,
        )
        return self._done(now, report, started)

    def _remember(self, rows: Sequence[ActivityRow], now: datetime) -> int:
        covered = 0
        for row in rows:
            if row.window_name != TAPE_WINDOW:
                continue
            self.readings.setdefault(row.mint, deque(maxlen=2)).append(row.as_reading())
            covered += 1
        stale = now - timedelta(minutes=10)
        for mint in [m for m, q in self.readings.items() if q[-1].received_at < stale]:
            del self.readings[mint]
        return covered

    def _error(self, at: datetime, error: str) -> None:
        if self._sources is not None:
            for name in (SWAP_API, SWAP_API_ACTIVITY):
                self._sources[name].record_spent(at)
                self._sources[name].record_error(at, error)

    def _done(self, now: datetime, report: ActivityReport, started: float) -> ActivityReport:
        report = dataclasses.replace(report, duration_s=round(time.monotonic() - started, 3))
        self.last_report = report
        if self._sources is not None:
            quote_age = (
                None if self.quote is None else (now - self.quote.observed_at).total_seconds()
            )
            self._sources.record_activity_cycle(
                now,
                asked=report.asked,
                covered=report.covered,
                calls=report.calls,
                live_1m=report.live.get(TAPE_WINDOW, 0),
                dark=report.dark,
                skipped=report.skipped is not None,
                duration_s=report.duration_s,
                quote_age_s=None if quote_age is None else round(quote_age, 1),
            )
        return report


def batch_minute(
    ctx: RadarContext, mint: str, *, at: datetime, absence: str
) -> tuple[TapeMinute | None, str]:
    """The batch's ``1m`` window as the minute's tape when the per-mint tape
    did not cover it: the newest reading received by ``at`` and young enough,
    or ``None`` with the reason the caller already had — ``no_sol_quote``
    when there was a reading but no quote to turn it into SOL."""
    if ctx.activity is None:
        return None, absence
    reading = ctx.activity.reading_for(mint, at=at)
    if reading is None:
        return None, absence
    minute = activity_minute(reading)
    return minute, (absence if minute is not None else NO_SOL_QUOTE)


def activity_mints(tracker: MintTracker) -> list[str]:
    """Every tracked coin still on the curve and quoted in SOL, newest first."""
    return [t.mint for t in tracker.snapshot() if not t.quote_unsupported and not t.finished]


def seconds_until_fire(now: datetime, *, cycle_s: float, lead_s: float) -> float:
    """How long until the next instant ``k·cycle_s − lead_s`` on the epoch grid
    — ``lead_s`` before every minute close with the default cycle of 60 s."""
    cycle = max(1.0, cycle_s)
    phase = (now.timestamp() + lead_s) % cycle
    wait = cycle - phase
    if wait < MIN_WAIT_S:
        wait += cycle
    return wait


async def activity_once(ctx: RadarContext) -> ActivityReport:
    assert ctx.activity is not None
    now = utcnow()
    report = await ctx.activity.pull_once(ctx.session_factory, activity_mints(ctx.tracker), now=now)
    meme_rows_total.labels(table="meme_market_activity_1m").inc(report.rows)
    meme_source_messages_total.labels(source=SWAP_API_ACTIVITY).inc(report.calls - report.errors)
    return report


async def run_activity(ctx: RadarContext) -> None:
    """The aligned cadence: sleep until ``lead_s`` before the next minute close,
    run one cycle, repeat. A failure is logged and re-raised like ``forever``'s."""
    while True:
        await asyncio.sleep(
            seconds_until_fire(
                utcnow(), cycle_s=ctx.config.activity_cycle_s, lead_s=ctx.config.activity_lead_s
            )
        )
        try:
            await activity_once(ctx)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("meme_loop_failed", loop="activity")
            raise
