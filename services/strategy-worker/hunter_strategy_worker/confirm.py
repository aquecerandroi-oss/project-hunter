"""Proving that a decision was durable *before* the open it chose.

SHADOW-LAB.md §3: "a barra escolhida e a decisão persistidas antes dessa
abertura"; a commit that misses the open is ``no_entry: late``, never a
retroactive entry.

The commit instant is not observable from inside the transaction, and Postgres
does not record it (``track_commit_timestamp`` is off, and ``now()`` is the
transaction *start*). So the proof is built from outside:

    commit_1 finished  ->  read the clock t  ->  t < entry_bar_open

therefore ``commit_1 < entry_bar_open``. This module reads that clock and writes
the attestation (``meta.entry_plan.confirmed_at``) in a second transaction. The
second commit does not need to beat the open — it only records a fact that was
already established (Astra, S2 design review).

If the clock is already past the open, the same transaction turns the tracking
into ``no_entry: late`` and frees the slot. If the process dies before either
write, the outcome engine finds a ``pending_entry`` with no attestation and
closes it as ``late: unconfirmed``: a countable, conservative loss instead of an
entry nobody can prove was legitimate.
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from hunter_core.db.session import role_session
from hunter_core.domain.enums import ShadowTrackingState
from hunter_core.domain.types import utcnow
from hunter_core.logging import get_logger
from hunter_strategy_worker import slots
from hunter_strategy_worker.plan import LateReason
from hunter_strategy_worker.tracking_repo import load_tracking, merged_meta, save_tracking
from hunter_strategy_worker.walker import Progress

if TYPE_CHECKING:
    from collections.abc import Callable

    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    from hunter_strategy_worker.record import ShadowRecord

logger = get_logger(__name__)

__all__ = ["confirm_or_lapse"]


async def confirm_or_lapse(
    factory: async_sessionmaker[AsyncSession],
    record: ShadowRecord,
    *,
    clock: Callable[[], datetime] = utcnow,
) -> str:
    """``"confirmed"``, ``"late"`` or ``"skipped"`` for one just-committed decision.

    ``clock`` is injectable for the same reason the replay cohort exists: a
    replayed run reads its own timeline, and a test must be able to place the
    decision relative to its entry bar instead of relative to the wall clock.
    """
    async with role_session(factory, db_role="hunter_worker") as session:
        await slots.lock_slot(
            session,
            strategy_version_id=record.strategy_version_id,
            market_id=record.market_id,
            cohort=record.cohort,
        )
        tracking = await load_tracking(session, record.signal_id)
        if tracking is None or tracking.tracking_state is not ShadowTrackingState.PENDING_ENTRY:
            return "skipped"
        entry_plan = dict(tracking.meta.get("entry_plan") or {})
        if entry_plan.get("confirmed_at"):
            return "skipped"
        now = clock()
        plan = tracking.plan
        if now >= plan.entry_bar_open:
            lapsed = Progress(
                tracking_state=ShadowTrackingState.NO_ENTRY,
                result=tracking.progress.result,
                no_entry_reason=LateReason.MISSED_OPEN.value,
            )
            excursions = lapsed.excursions(plan)
            await save_tracking(
                session,
                record.signal_id,
                progress=lapsed,
                meta=merged_meta(
                    tracking.meta, progress=lapsed.to_jsonable(), excursions=excursions
                ),
                exit_price=None,
                r_multiple=None,
                excursions=excursions,
                tracked_until=now,
            )
            await slots.release_tracking(session, signal_id=record.signal_id, ended_at=now)
            logger.info("shadow_entry_missed_open", signal_id=str(record.signal_id))
            return "late"
        entry_plan["confirmed_at"] = now.isoformat()
        await save_tracking(
            session,
            record.signal_id,
            progress=tracking.progress,
            meta=merged_meta(tracking.meta, entry_plan=entry_plan),
            exit_price=None,
            r_multiple=None,
            excursions={},
            tracked_until=None,
        )
        return "confirmed"
