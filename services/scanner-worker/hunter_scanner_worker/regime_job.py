"""One pass of the hourly regime producer: the hours that are missing or moved.

``market_regimes`` held **one** row on 2026-09-08 — the live ``regime_v0``
classifier writes on transition, and a classifier warming up since it started has
never transitioned, so every Shadow Lab and replay cohort was uncuttable by
context (Astra C4, T3.32, T3.33e/g). This job is the missing series: one row per
hour per exchange, changed or not, back thirty-one days.

**The cut is the closed hour, never the clock.** A pass at 12:37 produces the
hour ``12:00`` from data that was final before ``12:00``; the row is in force over
``[12:00, 13:00)``. A second pass inside the same hour recomputes the same cut
from the same candles and writes nothing (``unchanged``) — idempotency is a
property of the key and the digest, not of the caller's discipline.

**Which hours a pass produces is two rules** (``regime_window``): the hours of the
window with **no row**, and every hour of the **repair window** (the last 72 h,
row or not). The second is what makes a hole heal — an hour written ``unknown``
because a minute was missing *has* a row, so the first would never look at it
again. Recomputing is cheap; *rewriting* is what costs, and the digest gates it:
an hour whose candles did not move does not even open a transaction, and one
whose candles moved is updated in place, so its id survives for the foreign keys
pointing at it. Deeper than 72 h, after a large candle backfill, is an operator
decision (``regime_hourly --once --repair-days N``).

**Cost, declared.** The reference needs 745 closed hours behind the earliest hour
due (the deepest window any component reads) and the universe 25 hours behind it
for the breadth; the earliest hour due is the start of the repair window, so a
steady-state pass folds ~34 days of BTC minutes plus 97 hours x N markets, and a
first pass ~62 days of BTC plus 32 days x N markets, once. The measured numbers
are in ``.claude/state/notes-T3.43.md``.
"""

from __future__ import annotations

import time
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import TYPE_CHECKING

from hunter_core.db.session import role_session
from hunter_core.domain.types import ensure_utc
from hunter_core.logging import get_logger
from hunter_indicators.regime import (
    DEFAULT_HOURLY_THRESHOLDS,
    HourlyThresholds,
    build_snapshot,
    count_breadth,
)
from hunter_scanner_worker.metrics import regime_last_hour, regime_rows_total
from hunter_scanner_worker.persist import DB_ROLE
from hunter_scanner_worker.regime import BTC_SYMBOL
from hunter_scanner_worker.regime_repo import (
    FUNDING_WINDOW,
    funding_average,
    funding_settlements,
    hourly_closes,
)
from hunter_scanner_worker.regime_window import (
    BACKFILL_DAYS,
    HOUR,
    REPAIR_HOURS,
    floor_hour,
    hours_due,
)
from hunter_scanner_worker.regime_writer import (
    UNCHANGED,
    existing_hours,
    supporting_features,
    write_snapshots,
)

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence
    from decimal import Decimal
    from uuid import UUID

    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    from hunter_indicators.regime import RegimeSnapshot
    from hunter_scanner_worker.registry import MarketRef

logger = get_logger(__name__)

STALE_AFTER = timedelta(hours=2)
"""Age at which the producer is *degraded*, never down: one missed hour plus its
retry. A regime series with a hole is a research problem, not a trading one —
nothing in the live path reads it, which is why it is a status detail and not a
readiness check."""

__all__ = [
    "BACKFILL_DAYS",
    "FUNDING_WINDOW",
    "REPAIR_HOURS",
    "STALE_AFTER",
    "RegimeHealth",
    "RegimeRun",
    "floor_hour",
    "funding_average",
    "hours_due",
    "run_regime_once",
]


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


WRITE_BATCH_HOURS = 24
"""Hours per transaction. A day: the 31-day backfill (745 hours) measured 186,5 s
with one transaction per hour against the testcontainer and **11-12 s** at
twenty-four, because the cost was round trips and not rows. Bigger buys little —
the fixed cost is already amortised — and makes the retry below coarser."""


def _record(run: RegimeRun, outcome: str, ts: datetime) -> None:
    """One hour's verdict, in the run and in the metric, in one place.

    ``last_ts`` is the newest hour the pass touched, whatever order the hours
    were written in: the unchanged ones are recorded before the batches, so
    "the last one processed" would name the wrong hour the day an older hour is
    repaired and the cut is not.
    """
    run.outcomes[outcome] += 1
    regime_rows_total.labels(outcome=outcome).inc()
    if outcome != UNCHANGED:
        run.hours += 1
    if run.last_ts is None or ts > run.last_ts:
        run.last_ts = ts


async def _write_batch(
    factory: async_sessionmaker[AsyncSession],
    batch: Sequence[RegimeSnapshot],
    *,
    exchange: str,
    thresholds: HourlyThresholds,
    run: RegimeRun,
) -> bool:
    """One transaction for up to a day of hours. ``False`` if it raised."""
    try:
        async with role_session(factory, db_role=DB_ROLE) as session:
            written = await write_snapshots(
                session, batch, exchange=exchange, thresholds=thresholds
            )
    except Exception:
        logger.exception(
            "scanner_regime_batch_failed", first=batch[0].ts.isoformat(), hours=len(batch)
        )
        return False
    for ts, outcome in written:
        _record(run, outcome, ts)
    return True


async def _write_hours(
    factory: async_sessionmaker[AsyncSession],
    snapshots: Sequence[RegimeSnapshot],
    *,
    exchange: str,
    thresholds: HourlyThresholds,
    known: Mapping[datetime, str | None],
    run: RegimeRun,
) -> None:
    """The write phase: the digest first, then one transaction per day.

    The digest is compared **before** any session is opened, because the repair
    window recomputes seventy-two hours on every pass and in steady state every
    one of them is identical to the row on disk; opening a transaction to find
    that out would make the common case the expensive one. What did move is
    written a day at a time, and a batch that raises is retried hour by hour --
    so a single unrepresentable hour costs its own hour and no other, which is
    the property the per-hour transaction was there to buy.
    """
    changed: list[RegimeSnapshot] = []
    for snapshot in snapshots:
        digest = supporting_features(snapshot, exchange=exchange, thresholds=thresholds)[1]
        if known.get(snapshot.ts) == digest:
            _record(run, UNCHANGED, snapshot.ts)
        else:
            changed.append(snapshot)
    for start in range(0, len(changed), WRITE_BATCH_HOURS):
        batch = changed[start : start + WRITE_BATCH_HOURS]
        if await _write_batch(factory, batch, exchange=exchange, thresholds=thresholds, run=run):
            continue
        for snapshot in batch:
            if await _write_batch(
                factory, [snapshot], exchange=exchange, thresholds=thresholds, run=run
            ):
                continue
            run.outcomes["failed"] += 1
            regime_rows_total.labels(outcome="failed").inc()


async def run_regime_once(
    factory: async_sessionmaker[AsyncSession],
    refs: Sequence[MarketRef],
    *,
    now: datetime,
    exchange: str,
    thresholds: HourlyThresholds = DEFAULT_HOURLY_THRESHOLDS,
    days: int = BACKFILL_DAYS,
    repair_hours: int = REPAIR_HOURS,
    reference_symbol: str = BTC_SYMBOL,
) -> RegimeRun:
    """Produce every missing hour of the window and recompute the repair window."""
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
        due = hours_due(cut, days=days, known=known, repair_hours=repair_hours)
        inputs = await _read_inputs(
            session,
            refs,
            reference=reference,
            earliest=min(due),
            cut=cut,
            thresholds=thresholds,
        )
    snapshots = [
        _snapshot_for(ts, inputs=inputs, universe_size=len(refs), thresholds=thresholds)
        for ts in due
    ]
    await _write_hours(
        factory, snapshots, exchange=exchange, thresholds=thresholds, known=known, run=run
    )
    run.duration_s = time.monotonic() - started
    if run.last_ts is not None:
        regime_last_hour.set(run.last_ts.timestamp())
    logger.info(
        "scanner_regime_pass",
        cut=cut.isoformat(),
        due=len(due),
        repair_hours=repair_hours,
        written=run.hours,
        markets=len(refs),
        reference_hours=len(inputs.reference),
        outcomes=dict(run.outcomes),
        duration_s=round(run.duration_s, 3),
    )
    return run
