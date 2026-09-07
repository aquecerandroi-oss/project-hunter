"""What a blocked wallet does, and what a reservation's clock does.

Two small cycles that share one property: both compete for the **wallet's lock
row** with admission and with the order cycle, so a slot is never freed while
somebody else is counting it (DATABASE.md §18.7).

**BLOCKED cancels pendings and never touches a protection.** RISK_ENGINE.md §5
and rule 3 of the directive: an entry latch may not stop an exit. So this cancels
every standing reservation — ``held → released``, audited, giving back only what
was not executed — and does not look at ``portfolio_exit_intents`` at all. A
position that is blocked from being *opened* is not a position that may not be
*closed*.

**Expiry is the reservation's own clock.** 30 s without an order and the
commitment dies (PIPELINE.md §5); ``status`` is left alone, because the decision
does not stop being true when the tenure runs out — the two axes are separate on
purpose (DATABASE.md §18.3).
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import text

from hunter_core.admission.reservation import (
    ReservationCycleClosed,
    close_reservation,
    expire_reservations,
)
from hunter_core.domain.enums import ReservationState
from hunter_core.logging import get_logger
from hunter_core.risk.scopes import effective_state

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from hunter_core.risk.scopes import EffectiveKillSwitch
    from hunter_execution_worker.wallet import WalletRef

__all__ = ["cancel_pending_entries", "expire_stale_reservations", "read_effective_state"]

logger = get_logger(__name__)


async def read_effective_state(
    session: AsyncSession, *, wallet: WalletRef, lock: bool = True
) -> EffectiveKillSwitch:
    """The effective state, in the contract's lock order (system → org → wallet)."""
    return await effective_state(session, wallet.portfolio_id, lock=lock)


async def _standing(session: AsyncSession, *, wallet: WalletRef) -> tuple[uuid.UUID, ...]:
    rows = await session.execute(
        text(
            "SELECT id FROM trade_proposals WHERE organization_id = :org AND portfolio_id = :pf "
            "AND reservation_state = 'held' ORDER BY admission_seq FOR UPDATE"
        ),
        {"org": wallet.organization_id, "pf": wallet.portfolio_id},
    )
    return tuple(row.id for row in rows)


async def cancel_pending_entries(
    session: AsyncSession,
    *,
    wallet: WalletRef,
    now: datetime,
    scopes: EffectiveKillSwitch | None = None,
) -> tuple[uuid.UUID, ...]:
    """Release every standing reservation while the wallet is blocked.

    Returns the proposals it cancelled — empty when the wallet is not blocked,
    which is the common case and costs one row read.
    """
    switch = scopes or await read_effective_state(session, wallet=wallet)
    if not switch.blocks_entries:
        return ()
    cancelled: list[uuid.UUID] = []
    for proposal_id in await _standing(session, wallet=wallet):
        try:
            await close_reservation(
                session,
                organization_id=wallet.organization_id,
                proposal_id=proposal_id,
                target=ReservationState.RELEASED,
                now=now,
                reason=f"kill switch {switch.effective.value} cancels pending entries",
            )
        except ReservationCycleClosed:
            # Somebody closed it between the read and here. Nothing to give
            # back, nothing to complain about — the commitment is already gone.
            continue
        cancelled.append(proposal_id)
    if cancelled:
        logger.warning(
            "pending_entries_cancelled",
            portfolio_id=str(wallet.portfolio_id),
            state=switch.effective.value,
            count=len(cancelled),
        )
    return tuple(cancelled)


async def expire_stale_reservations(
    session: AsyncSession, *, wallet: WalletRef, now: datetime
) -> tuple[uuid.UUID, ...]:
    """Expire every reservation whose 30 s ran out, under the wallet's lock."""
    await read_effective_state(session, wallet=wallet)
    expired = await expire_reservations(
        session,
        organization_id=wallet.organization_id,
        portfolio_id=wallet.portfolio_id,
        now=now,
    )
    if expired:
        logger.info(
            "reservations_expired", portfolio_id=str(wallet.portfolio_id), count=len(expired)
        )
    return expired
