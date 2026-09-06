"""The database half of a bootstrap: read the candles, write the revisions.

Split from :mod:`hunter_scanner_worker.replay`, which owns the *replay* -- the
cooperative job that turns candles into observations without ever holding the
event loop. The seam is the one the 350-line budget forced and the one the
responsibilities already had: nothing here computes a number, and nothing there
touches Postgres or Redis.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import TYPE_CHECKING

from hunter_core.db.session import role_session
from hunter_core.domain.types import ensure_utc, utcnow
from hunter_core.logging import get_logger
from hunter_scanner_worker import writers
from hunter_scanner_worker.bootstrap import (
    MINUTE,
    REASON_INCOMPLETE,
    BootstrapOutcome,
    BootstrapSettings,
    BootstrapWindow,
    merge_runs,
    missing_runs,
)
from hunter_scanner_worker.metrics import scanner_baseline_revisions_total
from hunter_scanner_worker.persist import DB_ROLE
from hunter_scanner_worker.refresh import admissible
from hunter_scanner_worker.replay import BootstrapJob
from hunter_scanner_worker.repo import load_candles

if TYPE_CHECKING:
    from collections.abc import Sequence

    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    from hunter_indicators.baselines import BaselineGate, BaselineRevision
    from hunter_scanner_worker.baselines import BaselineCache
    from hunter_scanner_worker.registry import MarketRef

logger = get_logger(__name__)

__all__ = [
    "finish_job",
    "prepare_job",
    "store_revisions",
]


async def prepare_job(
    session: AsyncSession,
    ref: MarketRef,
    *,
    window: BootstrapWindow,
    settings: BootstrapSettings,
    now: datetime,
) -> BootstrapJob:
    """Read the candles this market's replay needs, and find what is missing."""
    first = window.start - timedelta(minutes=settings.buffer_minutes)
    candles = await load_candles(
        session,
        ref.market_id,
        exchange=ref.exchange,
        symbol=ref.symbol,
        since=first,
        until=window.end - MINUTE,
    )
    tail = ensure_utc(now) - timedelta(minutes=settings.tail_lag_minutes)
    runs = [
        (run_start, min(run_end, tail))
        for run_start, run_end in missing_runs(
            [candle.open_time for candle in candles], start=first, end=window.end
        )
        if run_start < tail
    ]
    return BootstrapJob(
        ref,
        window=window,
        settings=settings,
        candles=candles,
        gaps=merge_runs(runs, settings=settings),
    )


async def store_revisions(
    factory: async_sessionmaker[AsyncSession], revisions: Sequence[BaselineRevision]
) -> int:
    """Append-only, in one transaction. A retry collides and writes nothing."""
    if not revisions:
        return 0
    async with role_session(factory, db_role=DB_ROLE) as session:
        await writers.write_revisions(session, list(revisions))
    scanner_baseline_revisions_total.labels(source="bootstrap", outcome="written").inc(
        len(revisions)
    )
    return len(revisions)


async def finish_job(
    factory: async_sessionmaker[AsyncSession],
    job: BootstrapJob,
    *,
    now: datetime | None = None,
    requested: int = 0,
    cache: BaselineCache | None = None,
    gate: BaselineGate | None = None,
) -> BootstrapOutcome:
    """Compute the revisions of a finished replay, write them, and report.

    ``available_at`` is stamped **here**, after the replay, never at the instant
    the job was created: a revision published with an earlier stamp than the
    moment its population was closed would pass ``available_at <= as_of`` for a
    cut that could not have known it (Astra, T2.5b diff review, must-fix 1).

    And a bootstrap is subject to the same maturity policy as the hourly refresh:
    a re-run over a window with holes can produce a non-empty bucket below the
    gate, and publishing it would *demote* a usable baseline, because the
    projection prefers the newest ``available_at`` and knows nothing about
    maturity (must-fix 2).
    """
    # Never earlier than the real clock, and never earlier than the caller's
    # reference: publication is *after* the population was closed, whichever of
    # the two is later. A test that reasons at a fixed instant keeps its instant;
    # production always lands on the wall clock, which is the point of MF-1.
    moment = utcnow() if now is None else max(now, utcnow())
    produced = job.revisions(available_at=moment)
    revisions, withheld = (
        admissible(produced, cache, gate)
        if cache is not None and gate is not None
        else (list(produced), [])
    )
    if withheld:
        scanner_baseline_revisions_total.labels(source="bootstrap", outcome="withheld").inc(
            len(withheld)
        )
        logger.info(
            "scanner_bootstrap_revision_withheld",
            symbol=job.ref.symbol,
            withheld=len(withheld),
        )
    await store_revisions(factory, revisions)
    complete = not job.gaps
    logger.info(
        "scanner_bootstrap_market_done",
        symbol=job.ref.symbol,
        cuts=job.cuts_done,
        buckets=len(revisions),
        gaps=len(job.gaps),
        complete=complete,
    )
    return BootstrapOutcome(
        ref=job.ref,
        window=job.window,
        cuts=job.cuts_done,
        revisions=tuple(revisions),
        complete=complete,
        reason=None if complete else REASON_INCOMPLETE,
        gaps=job.gaps,
        rejections=job.rejections(),
        requested=requested,
        withheld=len(withheld),
    )
