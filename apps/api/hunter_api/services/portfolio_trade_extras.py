"""Fees/PnL in BRL and protection intents for the Trades/Positions pages — T3.25.

Two things a closed position's row needs beyond what ``trades``/``positions``
store directly: the same amount converted to BRL (honest ``None`` with a
reason when no FX observation covers the instant, never extrapolated — the
convention ``hunter_api.services.portfolio_queries._brl_reading`` already
uses for the wallet's equity), and the durable protections
(``portfolio_exit_intents``, DATABASE.md §18.4) that existed on the position,
which a single order/fill row cannot show on its own.
"""

from __future__ import annotations

import uuid
from decimal import Decimal, localcontext
from typing import TYPE_CHECKING

from sqlalchemy import select

from hunter_api.schemas.portfolio_lists import ExitIntentOut
from hunter_core.db.models.paper_execution import PortfolioExitIntent
from hunter_core.db.repositories.fx import FxObservationRepository
from hunter_core.portfolio.attribution import LEDGER_CONTEXT
from hunter_core.portfolio.opening import PAPER_FX_POLICY

if TYPE_CHECKING:
    from collections.abc import Sequence
    from datetime import datetime

    from sqlalchemy.ext.asyncio import AsyncSession


async def brl_amount(
    session: AsyncSession, amount: Decimal, *, as_of: datetime
) -> tuple[Decimal | None, str | None]:
    """``amount`` (USDT) converted at the newest FX observation available at
    ``as_of``, or ``(None, reason)``. A flat multiply, not the equity-split
    ``attribute_brl`` does: a fee or a realized PnL has no operational/currency
    decomposition to attribute, only a rate to apply.
    """
    fx = await FxObservationRepository(session).latest_available(
        pair=PAPER_FX_POLICY.pair, source=PAPER_FX_POLICY.source, as_of=as_of
    )
    if fx is None:
        return None, "no_fx_observation"
    with localcontext(LEDGER_CONTEXT):
        return amount * fx.rate, None


def _exit_intent_out(row: PortfolioExitIntent) -> ExitIntentOut:
    return ExitIntentOut(
        id=row.id,
        reason=row.reason,
        protection_key=row.protection_key,
        state=row.state,
        intended_qty=row.intended_qty,
        filled_qty=row.filled_qty,
        trigger_price=row.trigger_price,
        degraded_since=row.degraded_since,
        degraded_reason=row.degraded_reason,
        closed_reason=row.closed_reason,
        created_at=row.created_at,
        closed_at=row.closed_at,
    )


async def load_exit_intents(
    session: AsyncSession,
    org_id: uuid.UUID,
    portfolio_id: uuid.UUID,
    position_ids: Sequence[uuid.UUID],
) -> dict[uuid.UUID, list[ExitIntentOut]]:
    """Every protection intent of the given positions, grouped by ``position_id``.

    One query for a whole page of positions/trades rather than one per row —
    the same shape as ``portfolio_queries._brl_reading``'s FX cache, applied to
    a list this time.
    """
    if not position_ids:
        return {}
    rows = (
        await session.execute(
            select(PortfolioExitIntent)
            .where(
                PortfolioExitIntent.organization_id == org_id,
                PortfolioExitIntent.portfolio_id == portfolio_id,
                PortfolioExitIntent.position_id.in_(position_ids),
            )
            .order_by(PortfolioExitIntent.created_at)
        )
    ).scalars()
    by_position: dict[uuid.UUID, list[ExitIntentOut]] = {}
    for row in rows:
        by_position.setdefault(row.position_id, []).append(_exit_intent_out(row))
    return by_position
