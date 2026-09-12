"""One pass of the ``dispersion_24h`` producer: the minutes that have no row yet.

T3.90 / H-P18 (``docs/PIPELINE.md`` §4b item 16). One row per closed minute per
exchange, immutable, anchored on ``end_time`` — the ``breadth_job`` shape, kept on
purpose so that two series a reader will inevitably compare are produced by two
passes with the same rules.

**The cut is the closed minute, never the clock.** A pass at 12:06:41 produces
every missing minute up to and including ``12:06``, and ``12:06``'s reading folds
the candles that opened at ``12:05`` and at ``12:05`` minus 24 h — nothing that
opened at ``12:06``. A second pass inside the same minute recomputes the same cut
from the same candles and writes nothing: idempotency is a property of the unique
key (``ON CONFLICT DO NOTHING``), not of the caller's discipline.

**One rule decides which minutes a pass produces, not two.** As in ``breadth_job``
there is no repair rule, and the absence is deliberate: a reading folded over an
incomplete universe is not *wrong*, it is **unusable and says so**
(``insufficient_coverage``, ``btc_missing``). Healing it in place would rewrite a
number a live decision may already have been gated by. A minute that must be
recomputed after a large candle backfill is a new ``dispersion_version``, which is
a different row by the key.

**The reference is resolved from the same load that defines the universe.** The
spec names a symbol (``BTCUSDT``); the pass looks it up among the eligible members
and hands :func:`hunter_indicators.dispersion.compute_dispersion` its market id, or
``None``. ``None`` is not a crash and not a skip: every minute of that pass is
written as ``btc_missing``, because "the reference left the universe" is a fact
about those minutes and the gate must refuse rather than decide.

**Cost, declared.** A steady-state pass reads two candles per market — 32 rows for
a universe of 16 — because the two endpoint runs are fetched as two ranges rather
than as one 24 h span (``dispersion_repo._CLOSES``). A 90-day backfill walks in
day-sized chunks (:data:`CHUNK_MINUTES`): each chunk reads two adjacent runs that
together cover 2 880 minutes × 16 markets ≈ 46 000 rows and writes 1 440 rows in
one statement.
"""

from __future__ import annotations

import time
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import TYPE_CHECKING

from hunter_core.db.session import role_session
from hunter_core.domain.types import ensure_utc, utcnow, uuid7
from hunter_core.logging import get_logger
from hunter_core.strategies.canonical import canonical_json
from hunter_indicators.dispersion import (
    DispersionSpec,
    compute_dispersion,
    current_spec,
    endpoint_open_times,
)
from hunter_scanner_worker.dispersion_repo import (
    endpoint_closes,
    exchange_id_for,
    existing_minutes,
    universe_members,
    write_readings,
)
from hunter_scanner_worker.persist import DB_ROLE

if TYPE_CHECKING:
    from collections.abc import Sequence
    from decimal import Decimal
    from uuid import UUID

    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    from hunter_indicators.dispersion import DispersionReading

logger = get_logger(__name__)

MINUTE = timedelta(minutes=1)

BACKFILL_MINUTES = 180
"""How far back a normal pass looks for minutes with no row: three hours.

Enough that a worker restart, a deploy or a slow minute heals itself without an
operator; short enough that the steady-state pass stays small. Deeper than this is
the backfill CLI, run by hand (``infra/scripts/backfill_dispersion.py``), which is
also the only thing that ever folds ninety days."""

CHUNK_MINUTES = 1_440
"""Minutes per fold. One day of the universe per statement: a 90-day backfill is
90 statements the planner cannot get wrong instead of one it might."""

STALE_AFTER = timedelta(minutes=10)
"""Age at which the producer is *degraded*, never down. A hole in this series costs
a gated version its decisions (it refuses with ``dispersion_unavailable``,
fail-closed) and costs nothing to the Radar, the baselines or the live regime,
which is all the scanner's ``/ready`` protects."""

__all__ = [
    "BACKFILL_MINUTES",
    "CHUNK_MINUTES",
    "MINUTE",
    "STALE_AFTER",
    "DispersionHealth",
    "DispersionRun",
    "floor_minute",
    "minutes_due",
    "readings_for",
    "run_dispersion_once",
]


def floor_minute(value: datetime) -> datetime:
    """The cut: the start of the minute that has closed at or before ``value``."""
    return ensure_utc(value).replace(second=0, microsecond=0)


def minutes_due(cut: datetime, *, back: int, known: set[datetime]) -> list[datetime]:
    """Every minute of ``[cut - back, cut]`` with no row yet, oldest first.

    The cut itself is included whenever it has no row — its candles are all final
    by construction (they closed at or before it), so there is nothing left to wait
    for.
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
    reference: UUID | None,
    universe_size: int,
    spec: DispersionSpec,
) -> list[DispersionReading]:
    """The fold, per minute, over one already-loaded slice of candles. Pure."""
    return [
        compute_dispersion(
            closes,
            end_time=minute,
            reference=reference,
            universe_size=universe_size,
            horizon_minutes=spec.horizon_minutes,
            min_coverage=spec.min_coverage,
        )
        for minute in minutes
    ]


@dataclass(slots=True)
class DispersionRun:
    """What one pass did, in the numbers the heartbeat and the logs publish."""

    cut: datetime
    universe_size: int = 0
    reference_found: bool = False
    due: int = 0
    written: int = 0
    outcomes: Counter[str] = field(default_factory=Counter[str])
    last_ts: datetime | None = None
    duration_s: float = 0.0


@dataclass(slots=True)
class DispersionHealth:
    """The producer's last pass, read as a status detail — never a readiness check."""

    last_run_at: datetime | None = None
    last_minute: datetime | None = None
    universe_size: int = 0

    def stale(self, *, now: datetime) -> bool:
        return self.last_minute is None or ensure_utc(now) - self.last_minute > STALE_AFTER

    def describe(self, now: datetime) -> str:
        """One line for ``/status``: the word an operator acts on, or the universe."""
        return "stale" if self.stale(now=now) else f"universe {self.universe_size}"


def _inputs(exchange: str, spec: DispersionSpec, universe_as_of: datetime) -> str:
    """The knobs stored next to the result, in the canonical form.

    ``universe_rule``/``universe_as_of`` say which markets the fold was over and
    when membership was judged; ``reference_symbol`` says what the dispersion was
    measured *against*. A reader a month from now must see all of it from the row
    instead of inferring it from the version name.
    """
    return canonical_json(
        {
            "exchange": exchange,
            "horizon_minutes": spec.horizon_minutes,
            "min_coverage": spec.min_coverage,
            "reference_symbol": spec.reference_symbol,
            "universe_as_of": universe_as_of,
            "universe_rule": spec.universe_rule,
        }
    ).decode("utf-8")


async def _universe(
    session: AsyncSession, *, exchange: str, spec: DispersionSpec, universe_as_of: datetime
) -> tuple[list[UUID], UUID | None]:
    """The market ids ``spec`` folds, and which of them is the reference.

    ``universe_as_of`` is the *pass*, not the minute: a 90-day backfill folds the
    markets that have 90 days of history **today**, which is what
    ``market_dispersion.universe_size`` documents itself to mean ("evidence about
    the fold, not about that historical minute"). Asking the question at each
    historical cut would answer "nobody", since no market had 90 days of retained
    candles 90 days ago.
    """
    members = await universe_members(
        session,
        exchange=exchange,
        min_history_days=spec.min_history_days,
        clock=lambda: universe_as_of,
    )
    reference = next(
        (member.market_id for member in members if member.symbol == spec.reference_symbol), None
    )
    return [member.market_id for member in members], reference


async def _fold_chunk(
    session: AsyncSession,
    minutes: list[datetime],
    *,
    market_ids: Sequence[UUID],
    reference: UUID | None,
    spec: DispersionSpec,
) -> list[DispersionReading]:
    old_first, new_first = endpoint_open_times(minutes[0], spec.horizon_minutes)
    old_last, new_last = endpoint_open_times(minutes[-1], spec.horizon_minutes)
    closes = await endpoint_closes(
        session,
        market_ids=market_ids,
        old_first=old_first,
        old_last=old_last,
        new_first=new_first,
        new_last=new_last,
        cut=minutes[-1],
    )
    return readings_for(
        closes, minutes, reference=reference, universe_size=len(market_ids), spec=spec
    )


async def run_dispersion_once(
    factory: async_sessionmaker[AsyncSession],
    *,
    exchange: str,
    cut: datetime,
    back: int = BACKFILL_MINUTES,
    spec: DispersionSpec | None = None,
    universe_as_of: datetime | None = None,
    dry_run: bool = False,
) -> DispersionRun:
    """Produce every missing minute of ``[cut - back, cut]`` for ``exchange``.

    ``spec`` names the series: its version string, its universe rule, its reference
    market, its horizon and its coverage floor
    (:mod:`hunter_indicators.dispersion.spec`). It defaults to
    :func:`hunter_indicators.dispersion.current_spec`.

    ``universe_as_of`` is the instant membership is judged at, defaulting to the
    wall clock of the pass. A backfill passes its own top cut so that ninety days
    of minutes are all folded over *one* universe; if each chunk re-asked at its
    own time the series would change universe halfway through.

    ``dry_run`` folds everything and writes nothing: the numbers in the returned
    :class:`DispersionRun` are the numbers that would have been stored, which is
    what makes the backfill CLI's default mode honest rather than a guess.
    """
    started = time.monotonic()
    series = spec or current_spec()
    as_of = ensure_utc(universe_as_of) if universe_as_of is not None else utcnow()
    run = DispersionRun(cut=cut)
    async with role_session(factory, db_role=DB_ROLE) as session:
        exchange_id = await exchange_id_for(session, exchange)
        if exchange_id is None:
            run.outcomes["no_exchange"] += 1
            return run
        market_ids, reference = await _universe(
            session, exchange=exchange, spec=series, universe_as_of=as_of
        )
        run.universe_size = len(market_ids)
        run.reference_found = reference is not None
        known = await existing_minutes(
            session,
            exchange_id=exchange_id,
            version=series.version,
            first=cut - back * MINUTE,
            last=cut,
        )
    due = minutes_due(cut, back=back, known=known)
    run.due = len(due)
    inputs = _inputs(exchange, series, as_of)
    for index in range(0, len(due), CHUNK_MINUTES):
        chunk = due[index : index + CHUNK_MINUTES]
        # One transaction per chunk — the shape ``regime_job``/``breadth_job`` use:
        # a chunk that fails costs its own day and never the whole backfill.
        async with role_session(factory, db_role=DB_ROLE) as session:
            readings = await _fold_chunk(
                session, chunk, market_ids=market_ids, reference=reference, spec=series
            )
            for reading in readings:
                run.outcomes["usable" if reading.usable else (reading.reason or "unusable")] += 1
            if not dry_run:
                run.written += await write_readings(
                    session,
                    readings,
                    exchange_id=exchange_id,
                    version=series.version,
                    inputs=inputs,
                    ids=[uuid7() for _ in readings],
                )
        run.last_ts = chunk[-1]
    run.duration_s = time.monotonic() - started
    logger.info(
        "scanner_dispersion_pass",
        exchange=exchange,
        version=series.version,
        cut=cut.isoformat(),
        universe=run.universe_size,
        reference=series.reference_symbol if run.reference_found else None,
        due=run.due,
        written=run.written,
        outcomes=dict(run.outcomes),
        dry_run=dry_run,
        duration_s=round(run.duration_s, 3),
    )
    return run
