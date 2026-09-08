"""One pass of the hourly regime producer: every closed hour that has no row yet.

``market_regimes`` held **one** row on 2026-09-08 — the live ``regime_v0``
classifier writes on transition, and a classifier that has been warming up since
it started has never transitioned. Every cohort the Shadow Lab and the replays
produced is therefore uncuttable by context (Astra C4, T3.32, T3.33e/g). This job
is the missing series: one row per hour per exchange, whether or not anything
changed, back thirty-one days so the replays already on disk can be split.

**The cut is the closed hour, never the clock.** A pass at 12:37 produces the
hour ``12:00`` from data that was final before ``12:00``; the row is in force over
``[12:00, 13:00)``. A second pass inside the same hour recomputes the same cut
from the same candles and writes nothing (``unchanged``) — idempotency is a
property of the key and the digest, not of the caller's discipline.

**The backfill is "every hour that has no row", not "the last N hours".** The
pass asks the table which hours it already has and produces the rest, so the
first run fills thirty-one days, every later run produces one hour, and a run
after a candle backfill repairs exactly the hours whose inputs moved (the digest
changes, the row is updated in place, its id survives for the foreign keys that
point at it). The current cut is **always** recomputed: it is the one hour whose
candles may still be arriving through a gap repair.

**Cost, declared.** The reference market needs 745 closed hours behind the
earliest hour due (the deepest window any component reads), and the universe
needs 25 hours behind it for the breadth. So a steady-state pass folds ~31 days
of BTC minutes plus 25 hours x N markets, and a first pass folds ~62 days of BTC
plus 32 days x N markets, once. Measured numbers are in
``.claude/state/notes-T3.43.md``.
"""

from __future__ import annotations

import time
from bisect import bisect_right
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from decimal import Decimal, localcontext
from typing import TYPE_CHECKING

from hunter_core.db.session import role_session
from hunter_core.domain.types import ensure_utc
from hunter_core.logging import get_logger
from hunter_core.strategies.numeric import CONTEXT
from hunter_indicators.regime import (
    DEFAULT_HOURLY_THRESHOLDS,
    FundingAverage,
    HourlyThresholds,
    build_snapshot,
    count_breadth,
)
from hunter_scanner_worker.metrics import regime_last_hour, regime_rows_total
from hunter_scanner_worker.persist import DB_ROLE
from hunter_scanner_worker.regime import BTC_SYMBOL
from hunter_scanner_worker.regime_repo import funding_settlements, hourly_closes
from hunter_scanner_worker.regime_writer import existing_hours, write_snapshot

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence
    from uuid import UUID

    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    from hunter_indicators.regime import RegimeSnapshot
    from hunter_scanner_worker.registry import MarketRef

logger = get_logger(__name__)

HOUR = timedelta(hours=1)

BACKFILL_DAYS = 31
"""How far back the first run fills. Thirty-one days is the replay window the
cohorts on disk cover (``docs/PIPELINE.md`` §6c) plus a day of margin."""

FUNDING_WINDOW = timedelta(hours=8)
"""One settlement interval. A market whose last settlement is older than this has
no current funding, and is left out of the average rather than counted at zero."""

STALE_AFTER = timedelta(hours=2)
"""Age at which the producer is *degraded*, never down: one missed hour plus its
retry. A regime series with a hole is a research problem, not a trading one —
nothing in the live path reads it, which is why it is a status detail and not a
readiness check."""

__all__ = [
    "BACKFILL_DAYS",
    "FUNDING_WINDOW",
    "STALE_AFTER",
    "RegimeHealth",
    "RegimeRun",
    "floor_hour",
    "funding_average",
    "hours_due",
    "run_regime_once",
]


def floor_hour(value: datetime) -> datetime:
    """The cut: the start of the hour that has closed at or before ``value``."""
    return ensure_utc(value).replace(minute=0, second=0, microsecond=0)


def hours_due(cut: datetime, *, days: int, known: Mapping[datetime, str | None]) -> list[datetime]:
    """Every hour of the window with no row yet, plus the current cut always."""
    first = cut - timedelta(days=days)
    due: list[datetime] = []
    hour = first
    while hour <= cut:
        if hour == cut or hour not in known:
            due.append(hour)
        hour += HOUR
    return due


def funding_average(
    settlements: Mapping[UUID, Sequence[tuple[datetime, Decimal]]],
    *,
    ts: datetime,
    window: timedelta = FUNDING_WINDOW,
) -> FundingAverage:
    """The mean of each market's **latest** settlement inside ``(ts - window, ts]``.

    One value per market and then the mean, not the mean of every settlement: a
    market that settled twice inside the window would otherwise weigh twice, and
    the number is meant to say what the universe pays right now.
    """
    values: list[Decimal] = []
    for series in settlements.values():
        times = [when for when, _ in series]
        index = bisect_right(times, ts) - 1
        if index < 0:
            continue
        when, rate = series[index]
        if when > ts - window:
            values.append(rate)
    if not values:
        return FundingAverage()
    with localcontext(CONTEXT):
        return FundingAverage(
            value=sum(values, Decimal(0)) / Decimal(len(values)), markets=len(values)
        )


@dataclass(slots=True)
class RegimeRun:
    """What one pass did, in the numbers the heartbeat and the metrics publish."""

    cut: datetime
    hours: int = 0
    outcomes: Counter[str] = field(default_factory=Counter[str])
    last_ts: datetime | None = None
    duration_s: float = 0.0


@dataclass(slots=True)
class RegimeHealth:
    """The producer's last pass, read by ``hb:scanner:*`` and the status detail."""

    last_run_at: datetime | None = None
    last_ts: datetime | None = None
    hours: int = 0

    def stale(self, now: datetime, *, after: timedelta = STALE_AFTER) -> bool:
        return self.last_run_at is None or (now - self.last_run_at) > after

    def describe(self, now: datetime) -> str:
        """A sentence, never a verdict — the same shape ``BetaHealth`` uses."""
        if self.last_run_at is None:
            return "never ran"
        age = (now - self.last_run_at).total_seconds() / 3600
        state = "stale" if self.stale(now) else "ok"
        last = self.last_ts.isoformat() if self.last_ts else "none"
        return f"{state} (last hour {last}, {self.hours} written, {age:.1f}h ago)"

    def record(self, run: RegimeRun, *, now: datetime) -> None:
        self.last_run_at = now
        self.hours = run.hours
        if run.last_ts is not None:
            self.last_ts = run.last_ts


@dataclass(slots=True)
class _Inputs:
    """Everything the pass read, once, for every hour it is about to produce."""

    reference: dict[datetime, Decimal]
    universe: dict[UUID, dict[datetime, Decimal]]
    funding: dict[UUID, list[tuple[datetime, Decimal]]]


def _depth_hours(thresholds: HourlyThresholds) -> int:
    """The deepest window any component reads, in closed hours."""
    return max(
        thresholds.sma_slow_hours + thresholds.slope_lookback_hours,
        thresholds.vol_reference_hours + thresholds.vol_window_hours + 1,
        thresholds.drawdown_window_hours,
    )


async def _read_inputs(
    session: AsyncSession,
    refs: Sequence[MarketRef],
    *,
    reference: MarketRef,
    earliest: datetime,
    cut: datetime,
    thresholds: HourlyThresholds,
) -> _Inputs:
    """One read per source, sized by the earliest hour the pass has to produce."""
    ids = [ref.market_id for ref in refs]
    breadth_hours = thresholds.vol_window_hours + 1
    reference_closes = await hourly_closes(
        session, [reference.market_id], start=earliest - _depth_hours(thresholds) * HOUR, cut=cut
    )
    universe = await hourly_closes(session, ids, start=earliest - breadth_hours * HOUR, cut=cut)
    funding = await funding_settlements(session, ids, start=earliest - FUNDING_WINDOW, cut=cut)
    return _Inputs(
        reference=reference_closes.get(reference.market_id, {}), universe=universe, funding=funding
    )


def _snapshot_for(
    ts: datetime, *, inputs: _Inputs, universe_size: int, thresholds: HourlyThresholds
) -> RegimeSnapshot:
    """The pure call, with the three inputs resolved for exactly this hour."""
    return build_snapshot(
        ts=ts,
        closes=inputs.reference,
        breadth=count_breadth(
            inputs.universe, ts=ts, universe=universe_size, thresholds=thresholds
        ),
        funding=funding_average(inputs.funding, ts=ts),
        thresholds=thresholds,
    )


async def _write_hour(
    factory: async_sessionmaker[AsyncSession],
    snapshot: RegimeSnapshot,
    *,
    exchange: str,
    thresholds: HourlyThresholds,
    known: Mapping[datetime, str | None],
    run: RegimeRun,
) -> None:
    """One hour, in one transaction of its own: a failure costs that hour only."""
    try:
        async with role_session(factory, db_role=DB_ROLE) as session:
            outcome = await write_snapshot(
                session, snapshot, exchange=exchange, thresholds=thresholds, known=known
            )
    except Exception:
        logger.exception("scanner_regime_hour_failed", ts=snapshot.ts.isoformat())
        run.outcomes["failed"] += 1
        regime_rows_total.labels(outcome="failed").inc()
        return
    run.outcomes[outcome] += 1
    regime_rows_total.labels(outcome=outcome).inc()
    if outcome != "unchanged":
        run.hours += 1
    run.last_ts = snapshot.ts


async def run_regime_once(
    factory: async_sessionmaker[AsyncSession],
    refs: Sequence[MarketRef],
    *,
    now: datetime,
    exchange: str,
    thresholds: HourlyThresholds = DEFAULT_HOURLY_THRESHOLDS,
    days: int = BACKFILL_DAYS,
    reference_symbol: str = BTC_SYMBOL,
) -> RegimeRun:
    """Produce every missing hour of the window, plus the hour that just closed."""
    now = ensure_utc(now)
    cut = floor_hour(now)
    run = RegimeRun(cut=cut)
    started = time.monotonic()
    reference = next((ref for ref in refs if ref.symbol == reference_symbol), None)
    if reference is None:
        # Nothing is written: every component of the snapshot is anchored on the
        # reference market, and a regime with no reference is not a regime.
        logger.error("scanner_regime_no_reference", reference=reference_symbol, markets=len(refs))
        run.outcomes["no_reference"] += 1
        regime_rows_total.labels(outcome="no_reference").inc()
        return run
    async with role_session(factory, db_role=DB_ROLE) as session:
        known = await existing_hours(
            session,
            exchange=exchange,
            version=thresholds.identity,
            first=cut - timedelta(days=days),
            last=cut,
        )
        due = hours_due(cut, days=days, known=known)
        inputs = await _read_inputs(
            session,
            refs,
            reference=reference,
            earliest=min(due),
            cut=cut,
            thresholds=thresholds,
        )
    for ts in due:
        snapshot = _snapshot_for(ts, inputs=inputs, universe_size=len(refs), thresholds=thresholds)
        await _write_hour(
            factory,
            snapshot,
            exchange=exchange,
            thresholds=thresholds,
            known=known,
            run=run,
        )
    run.duration_s = time.monotonic() - started
    if run.last_ts is not None:
        regime_last_hour.set(run.last_ts.timestamp())
    logger.info(
        "scanner_regime_pass",
        cut=cut.isoformat(),
        due=len(due),
        written=run.hours,
        markets=len(refs),
        reference_hours=len(inputs.reference),
        outcomes=dict(run.outcomes),
        duration_s=round(run.duration_s, 3),
    )
    return run
