"""Replaying the candles we already have into baseline revisions, one market at a time.

Without this a fresh install is a week away from its first anomaly, and the
operational proof of T2.5 showed exactly that: 30 minutes of real data, zero
usable baselines, zero scores, zero Radar rows — all of it correct behaviour of a
pipeline with nothing to compare against (``.claude/state/t25-proof.md`` §5).

Two properties this module exists to hold:

**One pass per minute, not one per feature.** ``replay_vectors`` computes the
whole vector once per cut and a single :class:`ObservationCollector` fans it out
to every bucket, so the cost is proportional to the number of *minutes* replayed
and not to features × minutes. Nothing here loops over features.

**Cooperative, because the loop it shares is already saturated.** A market is
10 080 cuts and a cut costs tens of milliseconds, so the replay yields on a
wall-clock budget checked *per vector* (``settings.slice_s``) and then sleeps for
the complement of its duty cycle. Blocking the event loop for a whole market
would stall the consumers, the persistence cycle and ``/ready`` — the bootstrap
must never be the reason live evaluation stops.

The replay starts from ``EMPTY_STATE`` while the live scanner carries its own ATR
checkpoint, so the two anchors differ. Wilder's recursion forgets its seed
geometrically (13/14 per 15-minute bar): after the warm-up prefix the seed's
weight is already below 10⁻³ and after a day it is numerically gone. The
bootstrap therefore never writes its replay state into the live checkpoint — the
anchors are allowed to differ, the *numbers* converge, and claiming byte equality
would be a claim nobody proved (Astra, T2.5b design review, must-fix 5).
"""

from __future__ import annotations

import asyncio
import time
from datetime import datetime, timedelta
from typing import TYPE_CHECKING

from hunter_core.db.session import role_session
from hunter_core.domain.enums import BaselineSource
from hunter_core.domain.types import ensure_utc, utcnow
from hunter_core.logging import get_logger
from hunter_indicators.baselines import BaselineRevision, ObservationCollector
from hunter_indicators.baselines.bootstrap import (
    BOOTSTRAP_ALGO_VERSION,
    bootstrap_feature_keys,
    replay_vectors,
)
from hunter_indicators.features import DEFAULT_REGISTRY
from hunter_scanner_worker import writers
from hunter_scanner_worker.backfill import request_gaps
from hunter_scanner_worker.bootstrap import (
    MINUTE,
    REASON_INCOMPLETE,
    REASON_NO_CANDLES,
    BootstrapOutcome,
    BootstrapSettings,
    BootstrapWindow,
    merge_runs,
    missing_runs,
)
from hunter_scanner_worker.metrics import (
    scanner_baseline_revisions_total,
    scanner_bootstrap_cuts_total,
)
from hunter_scanner_worker.persist import DB_ROLE
from hunter_scanner_worker.refresh import admissible
from hunter_scanner_worker.repo import load_candles

if TYPE_CHECKING:
    from collections.abc import Sequence

    import redis.asyncio as redis_asyncio
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    from hunter_core.domain.market import NormalizedCandle
    from hunter_indicators.baselines import BaselineGate
    from hunter_scanner_worker.backfill import BackfillRequester
    from hunter_scanner_worker.baselines import BaselineCache
    from hunter_scanner_worker.registry import MarketRef

logger = get_logger(__name__)

__all__ = [
    "BootstrapJob",
    "finish_job",
    "prepare_job",
    "run_bootstrap",
    "store_revisions",
]


class BootstrapJob:
    """One market's replay, resumable across slices so the loop stays responsive."""

    __slots__ = (
        "_collector",
        "_cuts",
        "_finished",
        "_reported",
        "_vectors",
        "candles",
        "gaps",
        "ref",
        "settings",
        "total_cuts",
        "window",
    )

    def __init__(
        self,
        ref: MarketRef,
        *,
        window: BootstrapWindow,
        settings: BootstrapSettings,
        candles: Sequence[NormalizedCandle],
        gaps: Sequence[tuple[datetime, datetime]] = (),
    ) -> None:
        self.ref = ref
        self.window = window
        self.settings = settings
        self.candles = candles
        self.gaps = tuple(gaps)
        self.total_cuts = int((window.end - window.start).total_seconds() // 60)
        self._cuts = 0
        self._reported = 0
        self._finished = False
        self._collector = ObservationCollector(ref.market_id, bootstrap_feature_keys())
        self._vectors = replay_vectors(
            exchange=ref.exchange,
            symbol=ref.symbol,
            candles=candles,
            cuts=window.cuts(),
            buffer_minutes=settings.buffer_minutes,
        )

    @property
    def cuts_done(self) -> int:
        return self._cuts

    @property
    def finished(self) -> bool:
        return self._finished

    @property
    def progress(self) -> float:
        return 0.0 if not self.total_cuts else self._cuts / self.total_cuts

    async def run_slice(self, budget_s: float | None = None) -> bool:
        """Replay for at most ``budget_s`` of wall time. ``True`` when finished."""
        started = time.perf_counter()
        slice_started = started
        for vector, _state in self._vectors:
            self._collector.add(vector)
            self._cuts += 1
            now = time.perf_counter()
            if now - slice_started < self.settings.slice_s:
                continue
            if budget_s is not None and now - started >= budget_s:
                self._report_cuts()
                return False
            await asyncio.sleep(self.settings.pause_s)
            slice_started = time.perf_counter()
        self._finished = True
        self._report_cuts()
        return True

    def _report_cuts(self) -> None:
        """Only the cuts this slice added. A counter is monotonic, not cumulative:
        incrementing by the running total once per slice would multiply the cost
        of every market that took more than one."""
        scanner_bootstrap_cuts_total.inc(self._cuts - self._reported)
        self._reported = self._cuts

    def revisions(self, *, available_at: datetime) -> tuple[BaselineRevision, ...]:
        """The revisions of every non-empty bucket, dropping the unavailable ones.

        ``available_at`` is when *this* computation becomes usable — never
        back-dated to the age of the candles it read (``docs/DATABASE.md``
        section 17.2).
        """
        versions = {
            definition.key: definition.version
            for definition in DEFAULT_REGISTRY.definitions()
            if definition.key in set(self._collector.features)
        }
        produced = self._collector.revisions(
            window_start=self.window.start,
            window_end=self.window.end,
            available_at=ensure_utc(available_at),
            source=BaselineSource.BOOTSTRAP,
            expected_size=self.settings.expected_size,
            feature_versions=versions,
            algo_version=BOOTSTRAP_ALGO_VERSION,
        )
        return tuple(item for item in produced if isinstance(item, BaselineRevision))

    def rejections(self) -> dict[str, dict[str, int]]:
        return {feature: dict(reasons) for feature, reasons in self._collector.rejections().items()}


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


async def run_bootstrap(
    factory: async_sessionmaker[AsyncSession],
    redis: redis_asyncio.Redis,
    requester: BackfillRequester,
    ref: MarketRef,
    *,
    window: BootstrapWindow,
    settings: BootstrapSettings,
    now: datetime | None = None,
) -> BootstrapOutcome:
    """One market, end to end: read, ask for repairs, replay, write."""
    moment = now or utcnow()
    async with role_session(factory, db_role=DB_ROLE) as session:
        job = await prepare_job(session, ref, window=window, settings=settings, now=moment)
    requested = await request_gaps(
        redis, requester, ref, job.gaps, reason="baseline_bootstrap", now=moment
    )
    if not job.candles:
        logger.warning("scanner_bootstrap_no_candles", symbol=ref.symbol)
        return BootstrapOutcome(
            ref=ref,
            window=window,
            gaps=job.gaps,
            reason=REASON_NO_CANDLES,
            requested=requested,
        )
    await job.run_slice()
    return await finish_job(factory, job, now=moment, requested=requested)


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
