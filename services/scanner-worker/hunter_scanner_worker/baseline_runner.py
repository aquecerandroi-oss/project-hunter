"""The loop that keeps the baseline archive alive.

Two jobs share one task because they contend for the same CPU and must not
contend for it blindly: the **hourly refresh** (priority — it is the only thing
keeping the archive current) and the **bootstrap** (background — hours of replay
that must never delay the refresh by more than one budget slice).

Which markets still need a bootstrap is :mod:`hunter_scanner_worker.ledger`'s
question; how a market is replayed is :mod:`hunter_scanner_worker.replay`'s. This
module owns only the order and the budget.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import TYPE_CHECKING

from hunter_core.db.session import role_session
from hunter_core.domain.types import utcnow
from hunter_core.logging import get_logger
from hunter_scanner_worker.backfill import request_gaps
from hunter_scanner_worker.bootstrap import BootstrapOutcome, BootstrapSettings, window_for
from hunter_scanner_worker.ledger import BootstrapLedger, pending_markets
from hunter_scanner_worker.metrics import scanner_bootstrap_markets
from hunter_scanner_worker.persist import DB_ROLE
from hunter_scanner_worker.refresh import closed_hour_before, refresh_hour, reload_market
from hunter_scanner_worker.regime import BTC_SYMBOL
from hunter_scanner_worker.replay import finish_job, prepare_job

if TYPE_CHECKING:
    from collections.abc import Sequence

    import redis.asyncio as redis_asyncio
    from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

    from hunter_core.runtime import WorkerRuntime
    from hunter_scanner_worker.backfill import BackfillRequester
    from hunter_scanner_worker.bootstrap import BootstrapWindow
    from hunter_scanner_worker.config import ScannerConfig
    from hunter_scanner_worker.ledger import LedgerEntry
    from hunter_scanner_worker.registry import MarketRef
    from hunter_scanner_worker.replay import BootstrapJob
    from hunter_scanner_worker.scanner import Scanner

logger = get_logger(__name__)

REASON_FAILED = "bootstrap_failed"
BOOTSTRAP_REASON = "baseline_bootstrap"

__all__ = [
    "REASON_FAILED",
    "BootstrapProgress",
    "baseline_loop",
    "due_hour",
    "settings_from",
    "sleep_for",
]


def settings_from(config: ScannerConfig) -> BootstrapSettings:
    """The bootstrap's knobs, taken from the run's cadences."""
    return BootstrapSettings(window_days=config.baseline_window_days, duty=config.bootstrap_duty)


@dataclass(slots=True)
class BootstrapProgress:
    """What ``/ready`` and the heartbeat say while the archive is being built."""

    total: int = 0
    declared: int = 0
    running: str | None = None
    cuts: int = 0
    last_advance_at: datetime | None = None

    @property
    def ratio(self) -> float:
        return 1.0 if not self.total else self.declared / self.total

    def active(self, *, max_idle_s: float = 900.0) -> bool:
        if self.last_advance_at is None:
            return False
        return (utcnow() - self.last_advance_at).total_seconds() <= max_idle_s

    def describe(self) -> str:
        if self.total and self.declared >= self.total:
            return f"declared ({self.declared}/{self.total})"
        if self.running is not None:
            return f"bootstrapping {self.running} ({self.declared}/{self.total})"
        return f"bootstrapping ({self.declared}/{self.total})"

    def touch(self) -> None:
        self.last_advance_at = utcnow()


async def _start_job(
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


async def _close_job(
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


def due_hour(refreshed: datetime | None, now: datetime) -> datetime:
    """The next hour to refresh: the one after the last, never a jump forward.

    Taking ``closed_hour_before(now)`` directly would silently abandon every hour
    the process was down or failing for (Astra, T2.5b diff review, must-fix 4).
    """
    latest = closed_hour_before(now)
    if refreshed is None:
        return latest
    return min(refreshed + timedelta(hours=1), latest)


def sleep_for(now: datetime, check_s: float) -> float:
    """Until the next hour turns, or the next check — whichever comes first.

    A flat five-minute sleep taken at 10:59:59 would start the refresh of the
    hour that just closed almost five minutes late.
    """
    turn = (now + timedelta(hours=1)).replace(minute=0, second=0, microsecond=0)
    return max(1.0, min(check_s, (turn - now).total_seconds() + 1.0))


async def baseline_loop(
    scanner: Scanner,
    factory: async_sessionmaker[AsyncSession],
    engine: AsyncEngine,
    redis: redis_asyncio.Redis,
    runtime: WorkerRuntime,
    progress: BootstrapProgress,
    requester: BackfillRequester,
) -> None:
    """Refresh the hour that closed; spend what is left on one bootstrap slice.

    The in-flight job survives across iterations on purpose: one generator and
    one collector per market, alive between slices. Recreating them would restart
    the ATR recursion from a different anchor and pay for the cuts twice.

    The two jobs also fail apart. A refresh that raises must not discard a replay
    that has nothing to do with it, and a market that raises every time must not
    be chosen again forever while the other 199 never start — it earns a backoff
    like any other incomplete attempt (Astra, T2.5b diff review, must-fix 3).
    """
    config = scanner.config
    settings = settings_from(config)
    ledger = BootstrapLedger(config.exchange)
    refreshed: datetime | None = None
    job: BootstrapJob | None = None
    entry: LedgerEntry | None = None
    requested = 0
    while True:
        now = utcnow()
        refs = list(scanner.registry.by_symbol.values())
        # The refresh comes first even with a replay in flight: it is bounded and
        # it is the only thing keeping the archive current, while the bootstrap
        # is hours of work that can always wait one more slice.
        if scanner.cache is not None and refs:
            hour = due_hour(refreshed, now)
            if refreshed is None or hour > refreshed:
                try:
                    await refresh_hour(
                        engine,
                        refs,
                        cache=scanner.cache,
                        gate=scanner.policy.gate,
                        closed_hour=hour,
                        now=now,
                        window_days=settings.window_days,
                    )
                    refreshed = hour
                    runtime.mark_success()
                except asyncio.CancelledError:
                    raise
                except Exception:
                    runtime.mark_error()
                    logger.exception("scanner_baseline_refresh_failed", hour=hour.isoformat())
                    await asyncio.sleep(config.baseline_check_s)
                continue
        try:
            if job is None:
                window = window_for(now, days=settings.window_days)
                entries = await ledger.read(redis)
                pending = await pending_markets(
                    factory, redis, refs, window=window, settings=settings, now=now, ledger=ledger
                )
                progress.total = len(refs)
                progress.declared = len(refs) - len(pending)
                scanner_bootstrap_markets.labels(state="declared").set(progress.declared)
                scanner_bootstrap_markets.labels(state="pending").set(len(pending))
                if not pending:
                    progress.running = None
                    await asyncio.sleep(sleep_for(now, config.baseline_check_s))
                    continue
                ref = _first(pending, BTC_SYMBOL)
                entry = entries.get(ref.market_id)
                job, requested = await _start_job(
                    factory,
                    redis,
                    requester,
                    ref,
                    window=window,
                    settings=settings,
                    progress=progress,
                )
            finished = await job.run_slice(config.bootstrap_budget_s)
            progress.cuts = job.cuts_done
            progress.touch()
            if finished:
                await _close_job(
                    scanner,
                    factory,
                    engine,
                    redis,
                    job,
                    settings=settings,
                    ledger=ledger,
                    entry=entry,
                    progress=progress,
                    requested=requested,
                )
                job = None
                entry = None
                requested = 0
            runtime.mark_success()
        except asyncio.CancelledError:
            raise
        except Exception:
            runtime.mark_error()
            symbol = job.ref.symbol if job is not None else "?"
            logger.exception("scanner_bootstrap_failed", symbol=symbol)
            if job is not None:
                # The failure is this market's, and it earns the same backoff an
                # incomplete run earns — otherwise the next pass picks it again
                # and the rest of the universe never starts.
                await _record_failure(redis, ledger, job, settings=settings, entry=entry)
                job = None
                entry = None
            progress.running = None
            await asyncio.sleep(config.baseline_check_s)


async def _record_failure(
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


def _first(pending: Sequence[MarketRef], preferred: str) -> MarketRef:
    """The reference market goes first: the regime and the breadth depend on it."""
    for ref in pending:
        if ref.symbol == preferred:
            return ref
    return pending[0]
