"""Readiness of the execution-worker — ARCHITECTURE.md §11, brief T3.5 item 8.

``/ready`` is false unless all of these hold, and each check is registered under
its own ``__name__`` so the payload names what failed instead of returning an
anonymous ``false``:

- **the paper wallet schema is applied** (``0006``/``0007``). Without
  ``portfolio_risk_state`` there is no lock to take, and a worker that "runs"
  while every cycle raises is worse than one that refuses to be ready;
- **the kill switch is legible.** The whole contract rests on re-reading the
  effective state; a worker that cannot read it must not receive traffic, and it
  must certainly not keep executing entries;
- **the MTM is not stale.** The equity curve is what anchors the day, bounds the
  peak and feeds the drawdown, so a frozen MTM freezes the risk state itself —
  ≤ 120 s;
- **no protection is waiting too long.** A fired stop that has been degraded for
  more than 5 s is the one failure that costs information in a paper wallet;
- **the outbox is not lagging.** An event queued and unpublished for longer than
  the alert budget means the rest of the system no longer sees what the ledger
  already committed.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import text

from hunter_core.db.session import role_session
from hunter_core.domain.types import utcnow
from hunter_core.logging import get_logger
from hunter_execution_worker.config import WORKER_ROLE

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    from hunter_execution_worker.config import ExecutionConfig
    from hunter_execution_worker.state import CycleHealth

logger = get_logger(__name__)

_REQUIRED_OBJECTS = ("portfolio_risk_state", "portfolio_exit_intents", "participation_consumptions")
_REQUIRED_COLUMNS = (
    ("trade_proposals", "request_digest"),
    ("portfolio_equity_snapshots", "marks_stale"),
)

__all__ = ["migration_present", "readiness_checks"]


async def migration_present(factory: async_sessionmaker[AsyncSession]) -> bool:
    """Whether ``0006_paper_wallet`` **and** ``0007_paper_roles`` are applied."""
    async with role_session(factory, db_role=WORKER_ROLE) as session:
        return await _objects_exist(session)


async def _objects_exist(session: AsyncSession) -> bool:
    for table in _REQUIRED_OBJECTS:
        if await session.scalar(text("SELECT to_regclass(:name)"), {"name": table}) is None:
            logger.warning("paper_migration_missing", table=table)
            return False
    for table, column in _REQUIRED_COLUMNS:
        found = await session.scalar(
            text(
                "SELECT 1 FROM information_schema.columns "
                "WHERE table_name = :table AND column_name = :column"
            ),
            {"table": table, "column": column},
        )
        if found is None:
            logger.warning("paper_migration_missing", table=table, column=column)
            return False
    return True


def readiness_checks(
    factory: async_sessionmaker[AsyncSession],
    config: ExecutionConfig,
    health: CycleHealth,
) -> list[Callable[[], Awaitable[bool]]]:
    """The checks this worker adds to the runtime's Postgres/Redis pair."""

    async def paper_schema() -> bool:
        return await migration_present(factory)

    async def kill_switch_legible() -> bool:
        """Can this process still read the latch it is supposed to obey?"""
        if health.kill_switch_read_at is None:
            return False
        age = (utcnow() - health.kill_switch_read_at).total_seconds()
        return age <= max(config.kill_switch_poll_s * 3, 30.0)

    async def mtm_fresh() -> bool:
        if health.mtm_written_at is None:
            # Nothing has been marked yet. Ready only while the process is
            # younger than one cadence — after that, silence is a failure.
            return health.age_since_start() <= config.mtm_poll_s * 2
        return (utcnow() - health.mtm_written_at).total_seconds() <= config.mtm_max_age_s

    async def protection_prompt() -> bool:
        return health.protection_delay_s() <= config.protection_max_delay_s

    async def outbox_not_lagging() -> bool:
        async with role_session(factory, db_role=WORKER_ROLE) as session:
            oldest = await session.scalar(
                text(
                    "SELECT extract(epoch FROM now() - min(created_at)) FROM outbox_events "
                    "WHERE dispatched_at IS NULL"
                )
            )
        return oldest is None or float(oldest) <= config.outbox_lag_alert_s

    return [paper_schema, kill_switch_legible, mtm_fresh, protection_prompt, outbox_not_lagging]
