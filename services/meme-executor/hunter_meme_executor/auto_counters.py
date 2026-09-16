"""The two hourly counters stage 1 reports on ``hb:meme:executor`` — split out of
``auto_approve.py`` (T4.28g) for the 350-line budget, unchanged in behaviour.

Both are read from the **rows**, never from memory, so a restart cannot hand the
robot a fresh budget; both are bounded to the last hour and ride
``ix_meme_proposals_live_decided_at`` / ``ix_meme_live_orders_status_received_at``.
"""

from __future__ import annotations

from datetime import timedelta
from typing import TYPE_CHECKING

from sqlalchemy import text

from hunter_core.execution.meme.approval import AUTO_STAGE1_DECIDED_BY

if TYPE_CHECKING:
    from datetime import datetime

    from sqlalchemy.ext.asyncio import AsyncSession

__all__ = ["auto_approved_last_hour", "auto_refused_last_hour"]

_APPROVED_LAST_HOUR = text(
    "SELECT count(*) FROM meme_proposals "
    "WHERE decided_by = :by AND decided_at >= :since AND status <> 'rejected'"
)
"""What the hourly cap counts: proposals the robot opened **and the admission
let through**. An auto-opened proposal the admission refused is ``rejected`` in
the same transaction as its ``refused`` order (``auto_approve.reject_if_auto``)
and does not spend the budget — T4.28e, 16/09/2026: four refusals of one mint in
80 s had eaten 4 of the 5 slots of the hour before a single lamport moved, and
the owner said he does not want the robot rate-limited by its own refusals. The
money brakes are the scope (``max_trades``, ``max_total_sol``) and the admission;
the hourly cap only bounds *fills*."""

_REFUSED_LAST_HOUR = text(
    "SELECT o.reason, count(*) AS n FROM meme_live_orders o "
    "JOIN meme_proposals p ON p.id = o.proposal_id "
    "WHERE p.decided_by = :by AND o.side = 'buy' AND o.status = 'refused' "
    "  AND o.received_at >= :since GROUP BY o.reason"
)


async def auto_approved_last_hour(session: AsyncSession, *, now: datetime) -> int:
    since = now - timedelta(hours=1)
    return int(
        (
            await session.execute(
                _APPROVED_LAST_HOUR, {"by": AUTO_STAGE1_DECIDED_BY, "since": since}
            )
        ).scalar()
        or 0
    )


async def auto_refused_last_hour(session: AsyncSession, *, now: datetime) -> dict[str, int]:
    since = now - timedelta(hours=1)
    rows = await session.execute(_REFUSED_LAST_HOUR, {"by": AUTO_STAGE1_DECIDED_BY, "since": since})
    return {str(r[0]): int(r[1]) for r in rows}
