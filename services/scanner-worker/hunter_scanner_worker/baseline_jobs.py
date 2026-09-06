"""One market's bootstrap: start it, close it, or park it.

Split from :mod:`hunter_scanner_worker.baseline_runner`, which owns the *order*
and the *budget* -- which market goes next, how long a slice may hold the loop,
when the hourly refresh takes priority. What one job's lifetime looks like lives
here: read the candles and ask for the repairs, write what the replay produced,
or record the attempt of a market that produced nothing. Every one of them ends
with an entry in the ledger, because an attempt nobody records is a market the
next pass picks again.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from hunter_core.db.session import role_session
from hunter_core.domain.types import utcnow
from hunter_core.logging import get_logger
from hunter_scanner_worker.backfill import request_gaps
from hunter_scanner_worker.bootstrap import REASON_NO_CANDLES, BootstrapOutcome
from hunter_scanner_worker.persist import DB_ROLE
from hunter_scanner_worker.refresh import reload_market
from hunter_scanner_worker.replay_io import finish_job, prepare_job

if TYPE_CHECKING:
    import redis.asyncio as redis_asyncio
    from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

    from hunter_scanner_worker.backfill import BackfillRequester
    from hunter_scanner_worker.baseline_runner import BootstrapProgress
    from hunter_scanner_worker.bootstrap import BootstrapSettings, BootstrapWindow
    from hunter_scanner_worker.ledger import BootstrapLedger, LedgerEntry
    from hunter_scanner_worker.registry import MarketRef
    from hunter_scanner_worker.replay import BootstrapJob
    from hunter_scanner_worker.scanner import Scanner

logger = get_logger(__name__)

REASON_FAILED = "bootstrap_failed"
BOOTSTRAP_REASON = "baseline_bootstrap"

__all__ = [
    "BOOTSTRAP_REASON",
    "REASON_FAILED",
    "close_empty",
    "close_job",
    "record_failure",
    "start_job",
]


async def start_job(
    factory: async_sessionmaker[AsyncSession],
    redis: redis_asyncio.Redis,
    requester: BackfillRequester,
    ref: MarketRef,
    *,
    window: BootstrapWindow,
    settings: BootstrapSettings,
    progress: BootstrapProgress,
) -> tuple[BootstrapJob, int]:
    """Read one market's candles, ask for the repairs it needs, and start it."""
    now = utcnow()
    async with role_session(factory, db_role=DB_ROLE) as session:
        job: BootstrapJob = await prepare_job(
            session, ref, window=window, settings=settings, now=now
        )
    requested = await request_gaps(
        redis, requester, ref, job.gaps, reason=BOOTSTRAP_REASON, now=now
    )
    progress.running = ref.symbol
    progress.touch()
    return job, requested


async def close_job(
    scanner: Scanner,
    factory: async_sessionmaker[AsyncSession],
    engine: AsyncEngine,
    redis: redis_asyncio.Redis,
    job: BootstrapJob,
    *,
    settings: BootstrapSettings,
    ledger: BootstrapLedger,
    entry: LedgerEntry | None,
    progress: BootstrapProgress,
    requested: int,
) -> BootstrapOutcome:
    """Write what the replay produced and record the attempt."""
    outcome = await finish_job(
        factory, job, requested=requested, cache=scanner.cache, gate=scanner.policy.gate
    )
    await ledger.record(redis, outcome, settings=settings, previous=entry, now=utcnow())
    if scanner.cache is not None and outcome.revisions:
        await reload_market(engine, scanner.cache, job.ref, now=utcnow())
    state = scanner.state.get(job.ref.symbol)
    if state is not None:
        # "Under construction, and here is why" — carried per market so the
        # heartbeat can say it and the Radar is never shown a market whose
        # silence has no reason attached.
        state.baseline_note = outcome.reason
    progress.running = None
    progress.touch()
    return outcome


async def close_empty(
    scanner: Scanner,
    redis: redis_asyncio.Redis,
    job: BootstrapJob,
    *,
    settings: BootstrapSettings,
    ledger: BootstrapLedger,
    entry: LedgerEntry | None,
    progress: BootstrapProgress,
    requested: int,
) -> BootstrapOutcome:
    """Nothing was read, so nothing is replayed: say so and give the slot back.

    A market with no persisted candle (a new listing, or this process up before
    the collector) used to spend the whole bootstrap budget computing ~10 000
    empty cuts and finish as ``history_incomplete`` — a sentence that claims a
    replay happened. The repairs were already asked for by ``start_job``, and
    the attempt is still recorded here: without it, ``pending_markets`` would
    pick the same empty market on the next pass and the other 199 would never
    start (code review of T2.5b, MEDIUM 1).
    """
    logger.warning(
        "scanner_bootstrap_no_candles",
        symbol=job.ref.symbol,
        gaps=len(job.gaps),
        requested=requested,
    )
    outcome = BootstrapOutcome(
        ref=job.ref,
        window=job.window,
        gaps=job.gaps,
        reason=REASON_NO_CANDLES,
        requested=requested,
    )
    await ledger.record(redis, outcome, settings=settings, previous=entry, now=utcnow())
    state = scanner.state.get(job.ref.symbol)
    if state is not None:
        state.baseline_note = outcome.reason
    progress.running = None
    progress.touch()
    return outcome


async def record_failure(
    redis: redis_asyncio.Redis,
    ledger: BootstrapLedger,
    job: BootstrapJob,
    *,
    settings: BootstrapSettings,
    entry: LedgerEntry | None,
) -> None:
    """Park a market that raised, with a reason and a growing retry delay."""
    try:
        await ledger.record(
            redis,
            BootstrapOutcome(ref=job.ref, window=job.window, complete=False, reason=REASON_FAILED),
            settings=settings,
            previous=entry,
        )
    except Exception:
        logger.warning("scanner_bootstrap_failure_unrecorded", symbol=job.ref.symbol)
