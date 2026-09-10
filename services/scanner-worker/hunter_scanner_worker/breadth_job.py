"""One pass of the ``breadth_5m`` producer: the minutes that have no row yet.

T3.77 / H-P8 (``docs/PIPELINE.md`` §4b item 14). One row per closed minute per exchange,
immutable, anchored on ``end_time``.

**The cut is the closed minute, never the clock.** A pass at 12:06:41 produces
every missing minute up to and including ``12:06``, and ``12:06``'s reading folds
candles whose ``open_time`` is ``12:00`` through ``12:05`` — nothing that opened
at ``12:06``. A second pass inside the same minute recomputes the same cut from
the same candles and writes nothing: idempotency is a property of the unique key
(``ON CONFLICT DO NOTHING``), not of the caller's discipline.

**One rule decides which minutes a pass produces, not two.** Unlike the hourly
regime (``regime_window``: backfill *and* repair), there is no repair rule here,
and the absence is deliberate. A regime row can be *wrong* while a candle gap is
open and must be healed once the gap closes; a breadth reading that was folded
over an incomplete universe is not wrong, it is **unusable, and says so**
(``reason = insufficient_coverage``). Healing it in place would rewrite a number
a live decision may already have been gated by — the one thing an immutable
series exists to forbid. A minute that must be recomputed after a large candle
backfill is a new ``breadth_version``, which is a different row by the key.

**Cost, declared.** One pass folds ``minutes + 6`` minutes of the universe. In
steady state (one missing minute) that is 6 × ~200 = 1 200 candle rows; a
90-day backfill is 129 606 minutes × ~200 = ~26 M rows, which is why the backfill
walks in day-sized chunks (:data:`CHUNK_MINUTES`) instead of one statement.
"""

from __future__ import annotations

import time
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import TYPE_CHECKING

from hunter_core.db.session import role_session
from hunter_core.domain.types import ensure_utc, uuid7
from hunter_core.logging import get_logger
from hunter_core.strategies.canonical import canonical_json
from hunter_indicators.breadth import (
    BREADTH_VERSION,
    MIN_COVERAGE,
    WINDOW_MINUTES,
    compute_breadth,
)
from hunter_scanner_worker.breadth_repo import (
    exchange_id_for,
    existing_minutes,
    monitored_universe,
    window_closes,
    write_readings,
)
from hunter_scanner_worker.persist import DB_ROLE

if TYPE_CHECKING:
    from decimal import Decimal
    from uuid import UUID

    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    from hunter_indicators.breadth import BreadthReading

logger = get_logger(__name__)

MINUTE = timedelta(minutes=1)

BACKFILL_MINUTES = 180
"""How far back a normal pass looks for minutes with no row: three hours.

Enough that a worker restart, a deploy or a slow minute heals itself without an
operator; short enough that the steady-state pass reads three hours of the
universe and not a day of it. Deeper than this is the backfill CLI, run by hand
(``infra/scripts/backfill_breadth.py``), which is also the only thing that ever
folds ninety days."""

CHUNK_MINUTES = 1_440
"""Minutes per fold. One day of the universe per statement: a 90-day backfill is
90 statements the planner cannot get wrong instead of one it might."""

STALE_AFTER = timedelta(minutes=10)
"""Age at which the producer is *degraded*, never down. A hole in this series
costs a gated version its decisions (it refuses with ``breadth_unavailable``,
fail-closed) and costs nothing to the Radar, the baselines or the live regime,
which is all the scanner's ``/ready`` protects."""

__all__ = [
    "BACKFILL_MINUTES",
    "CHUNK_MINUTES",
    "MINUTE",
    "STALE_AFTER",
    "BreadthHealth",
    "BreadthRun",
    "floor_minute",
    "minutes_due",
    "readings_for",
    "run_breadth_once",
]


def floor_minute(value: datetime) -> datetime:
    """The cut: the start of the minute that has closed at or before ``value``."""
    return ensure_utc(value).replace(second=0, microsecond=0)


def minutes_due(cut: datetime, *, back: int, known: set[datetime]) -> list[datetime]:
    """Every minute of ``[cut - back, cut]`` with no row yet, oldest first.

    The cut itself is included whenever it has no row — its candles are all final
    by construction (they closed at or before it), so there is nothing left to
    wait for.
    """
    minutes: list[datetime] = []
    minute = cut - back * MINUTE
    while minute <= cut:
        if minute not in known:
            minutes.append(minute)
        minute += MINUTE
    return minutes


def readings_for(
    closes: dict[UUID, dict[datetime, Decimal]],
    minutes: list[datetime],
    *,
    universe_size: int,
    window: int = WINDOW_MINUTES,
) -> list[BreadthReading]:
    """The fold, per minute, over one already-loaded slice of candles. Pure."""
    return [
        compute_breadth(closes, end_time=minute, universe_size=universe_size, window_minutes=window)
        for minute in minutes
    ]


@dataclass(slots=True)
class BreadthRun:
    """What one pass did, in the numbers the heartbeat and the logs publish."""

    cut: datetime
    universe_size: int = 0
    due: int = 0
    written: int = 0
    outcomes: Counter[str] = field(default_factory=Counter[str])
    last_ts: datetime | None = None
    duration_s: float = 0.0


@dataclass(slots=True)
class BreadthHealth:
    """The producer's last pass, read as a status detail — never a readiness check."""

    last_run_at: datetime | None = None
    last_minute: datetime | None = None
    universe_size: int = 0

    def stale(self, *, now: datetime) -> bool:
        return self.last_minute is None or ensure_utc(now) - self.last_minute > STALE_AFTER


def _inputs(exchange: str, window: int) -> str:
    """The knobs stored next to the result, in the canonical form."""
    return canonical_json(
        {
            "exchange": exchange,
            "min_coverage": MIN_COVERAGE,
            "window_minutes": window,
        }
    ).decode("utf-8")


async def _fold_chunk(
    session: AsyncSession,
    minutes: list[datetime],
    *,
    exchange: str,
    universe_size: int,
    window: int,
) -> list[BreadthReading]:
    closes = await window_closes(
        session,
        exchange=exchange,
        first_minute=minutes[0] - (window + 1) * MINUTE,
        cut=minutes[-1],
    )
    return readings_for(closes, minutes, universe_size=universe_size, window=window)


async def run_breadth_once(
    factory: async_sessionmaker[AsyncSession],
    *,
    exchange: str,
    cut: datetime,
    back: int = BACKFILL_MINUTES,
    window: int = WINDOW_MINUTES,
    version: str = BREADTH_VERSION,
    dry_run: bool = False,
) -> BreadthRun:
    """Produce every missing minute of ``[cut - back, cut]`` for ``exchange``.

    ``dry_run`` folds everything and writes nothing: the numbers in the returned
    :class:`BreadthRun` are the numbers that would have been stored, which is
    what makes the backfill CLI's default mode honest rather than a guess.
    """
    started = time.monotonic()
    run = BreadthRun(cut=cut)
    async with role_session(factory, db_role=DB_ROLE) as session:
        exchange_id = await exchange_id_for(session, exchange)
        if exchange_id is None:
            run.outcomes["no_exchange"] += 1
            return run
        run.universe_size = len(await monitored_universe(session, exchange))
        known = await existing_minutes(
            session,
            exchange_id=exchange_id,
            version=version,
            window=window,
            first=cut - back * MINUTE,
            last=cut,
        )
    due = minutes_due(cut, back=back, known=known)
    run.due = len(due)
    inputs = _inputs(exchange, window)
    for index in range(0, len(due), CHUNK_MINUTES):
        chunk = due[index : index + CHUNK_MINUTES]
        # One transaction per chunk — the shape ``regime_job._write_batch`` uses:
        # a chunk that fails costs its own day and never the whole backfill.
        async with role_session(factory, db_role=DB_ROLE) as session:
            readings = await _fold_chunk(
                session,
                chunk,
                exchange=exchange,
                universe_size=run.universe_size,
                window=window,
            )
            for reading in readings:
                run.outcomes["usable" if reading.usable else (reading.reason or "unusable")] += 1
            if not dry_run:
                run.written += await write_readings(
                    session,
                    readings,
                    exchange_id=exchange_id,
                    version=version,
                    inputs=inputs,
                    ids=[uuid7() for _ in readings],
                )
        run.last_ts = chunk[-1]
    run.duration_s = time.monotonic() - started
    logger.info(
        "scanner_breadth_pass",
        exchange=exchange,
        cut=cut.isoformat(),
        universe=run.universe_size,
        due=run.due,
        written=run.written,
        outcomes=dict(run.outcomes),
        dry_run=dry_run,
        duration_s=round(run.duration_s, 3),
    )
    return run
