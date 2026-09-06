"""Partition guards: a missing partition must be seen, not discovered by a
failed insert (HIGH-3).

Two guards, because the two cases deserve different behaviour:
:func:`assert_writable_partitions` is a fatal startup gate for the *current*
timestamp (nothing can be persisted at all), while :class:`PartitionReadiness`
only turns ``/ready`` false for the ``now + 1 day`` lookahead.

``candles``, ``market_snapshots`` and ``liquidations`` are all RANGE-partitioned
by time (DATABASE.md §1.3/§4); a row with no matching partition aborts the
*whole* transaction it is in, silently taking the rest of that flush's
snapshots/funding/candles/liquidations with it. Neither guard creates a
partition — scheduling ``infra/scripts/create_partitions.py`` is a follow-up
outside T1.3.
"""

from __future__ import annotations

import asyncio
import time
from datetime import timedelta
from typing import TYPE_CHECKING

from sqlalchemy import text

from hunter_core.db.models._partitions import list_partition_name, partition_name
from hunter_core.db.session import role_session
from hunter_core.domain.enums import RiskEventSeverity
from hunter_core.domain.types import utcnow
from hunter_core.logging import get_logger
from hunter_market_worker.heartbeat import record_system_event

if TYPE_CHECKING:
    from collections.abc import Callable
    from datetime import datetime

    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

logger = get_logger(__name__)

RECHECK_INTERVAL_S = 300.0
LOOKAHEAD = timedelta(days=1)
CHECK_TIMEOUT_S = 10.0
"""Budget for one check. The startup gate runs before any collection task, so a
Postgres that accepts the connection and then stalls must not delay today's
ingestion: giving up is treated as a database error (fail open), never as a
missing partition (Astra's second opinion)."""
REPORT_TIMEOUT_S = 5.0
"""Budget for the CRITICAL ``system_event``. It is best-effort — giving up on it
never downgrades a confirmed absence into a normal start."""


def _lookahead_target(now: datetime) -> datetime:
    return now + LOOKAHEAD


def _partition_targets(target: datetime) -> list[str]:
    """``candles_1m``, ``market_snapshots`` and ``liquidations`` leaves that
    would accept a row timestamped ``target`` — named with the same helpers
    the migration and the daily partition jobs use, never hand-rolled."""
    year, month = target.year, target.month
    return [
        partition_name(list_partition_name("candles", "1m"), year, month),
        partition_name("market_snapshots", year, month),
        partition_name("liquidations", year, month),
    ]


async def _missing_partitions(session: AsyncSession, target: datetime) -> list[str]:
    missing: list[str] = []
    for name in _partition_targets(target):
        exists = await session.scalar(text("SELECT to_regclass(:name)"), {"name": name})
        if exists is None:
            missing.append(name)
    return missing


class PartitionsMissing(RuntimeError):
    """No partition would accept a row timestamped *now*: every flush in this
    period aborts whole, so starting the worker would be dishonest."""


async def _report_missing(
    factory: async_sessionmaker[AsyncSession], target: datetime, missing: list[str]
) -> None:
    """Log and record the CRITICAL ``system_event`` DATABASE.md §1.3 requires.
    Never raises: the report must not replace the caller's own decision."""
    logger.error("partition_missing", partitions=missing, target=target.isoformat())
    try:
        async with asyncio.timeout(REPORT_TIMEOUT_S):
            await record_system_event(
                factory,
                "partition_missing",
                f"missing partitions for {target.date().isoformat()}: {', '.join(missing)}",
                RiskEventSeverity.CRITICAL,
            )
    except Exception:
        logger.exception("partition_missing_system_event_failed")


class PartitionReadiness:
    """A readiness check with its own cheap re-check cadence.

    A missing partition must not require a restart to be noticed, but a
    present one must not cost a query per ``/ready`` probe — so the result is
    cached for :data:`RECHECK_INTERVAL_S` and only re-queried after that.
    Fails **open** on a database error: a Postgres blip already has its own
    readiness signal (``check_database``), and this check must not add a
    second way to wedge ``/ready``.
    """

    def __init__(
        self,
        factory: async_sessionmaker[AsyncSession],
        *,
        recheck_interval: float = RECHECK_INTERVAL_S,
        clock: Callable[[], float] = time.monotonic,
        now: Callable[[], datetime] = utcnow,
    ) -> None:
        self.factory = factory
        self.recheck_interval = recheck_interval
        self.clock = clock
        self.now = now
        self._last_checked_at: float | None = None
        self._ready = True

    async def ready(self) -> bool:
        if self._last_checked_at is not None and (
            self.clock() - self._last_checked_at < self.recheck_interval
        ):
            return self._ready
        # Update the cached result and its timestamp together, only after the
        # check actually completes (Astra's second opinion): if the caller's
        # own timeout (``/ready``'s 2s backstop in runtime.py) cancels this
        # await mid-flight, ``_last_checked_at`` must stay unset so the next
        # probe retries immediately instead of reusing a result from a check
        # that never finished.
        result = await self._check()
        self._ready = result
        self._last_checked_at = self.clock()
        return self._ready

    async def _check(self) -> bool:
        target = _lookahead_target(self.now())
        try:
            async with asyncio.timeout(CHECK_TIMEOUT_S):
                async with role_session(self.factory, db_role="hunter_worker") as session:
                    missing = await _missing_partitions(session, target)
        except Exception:
            logger.warning("partition_check_failed", exc_info=True)
            return True
        if not missing:
            return True
        await _report_missing(self.factory, target, missing)
        return False


async def assert_writable_partitions(
    factory: async_sessionmaker[AsyncSession], *, now: Callable[[], datetime] = utcnow
) -> None:
    """Startup gate: refuse to start when *nothing* written right now can land.

    Checks the leaves for the **current** timestamp, not the lookahead — a
    missing lookahead is tomorrow's problem and only turns ``/ready`` false
    (:class:`PartitionReadiness`), while a missing partition for *now* aborts
    every flush together with its snapshots, funding, candles and liquidations.
    Fails **open** on a database error or on :data:`CHECK_TIMEOUT_S`, for the
    same reason :class:`PartitionReadiness` does: Postgres availability already
    has ``check_database``, and this check must not become a second way to wedge
    startup. Only a completed query that finds a leaf absent is fatal.

    :raises PartitionsMissing: a leaf for ``now`` genuinely does not exist.
    """
    target = now()
    try:
        async with asyncio.timeout(CHECK_TIMEOUT_S):
            async with role_session(factory, db_role="hunter_worker") as session:
                missing = await _missing_partitions(session, target)
    except Exception:
        logger.warning("partition_startup_check_failed", exc_info=True)
        return
    if not missing:
        logger.info("partition_startup_check_ok", target=target.isoformat())
        return
    await _report_missing(factory, target, missing)
    raise PartitionsMissing(
        f"no partition accepts rows timestamped {target.isoformat()}: {', '.join(missing)}"
    )


async def storable_months(
    session: AsyncSession, months: set[tuple[int, int]]
) -> set[tuple[int, int]]:
    """Which ``(year, month)`` pairs already have a ``candles_1m`` partition.

    T2.5-backfill. Inserting a minute no partition accepts aborts the whole
    transaction — candles, outbox rows and the gap's own status transition
    together — and the gap would burn its five attempts on a condition no retry
    can fix. So the consumer asks first and plans only what can be stored,
    saying in the log which month is missing. Only ``candles`` is checked: a
    REST backfill writes candles and nothing else.

    **The policy this reflects changed in T2.5f.** The daily job used to create
    the current month and the months *ahead* only, so a request for seven days
    made early in a month was refused for the whole previous month (3 300 of
    8 547 minutes, 2026-09-06). ``infra/scripts/create_partitions.py`` now also
    keeps ``--months-behind`` (default 2) of the past writable, bounded by
    retention: a month the pruner would drop is not created, because creating it
    would only start a nightly fight between the two jobs.

    This function is unchanged by that, and deliberately so: it asks the
    database what exists (``to_regclass``) instead of recomputing the policy.
    The policy is what *should* be there; ``to_regclass`` is what *is*. A month
    older than the horizon, a month past retention, a job that has not run yet
    or was skipped on a ``lock_timeout`` (it exits 75 and retries tomorrow) —
    all of them still produce a month the consumer must refuse rather than
    abort a transaction on.
    """
    storable: set[tuple[int, int]] = set()
    for year, month in months:
        name = partition_name(list_partition_name("candles", "1m"), year, month)
        if await session.scalar(text("SELECT to_regclass(:name)"), {"name": name}) is not None:
            storable.add((year, month))
    return storable
