"""Writing the ``trades`` row of a position that has nothing sellable left.

Split out of :mod:`hunter_execution_worker.positions` along the line that
module's own docstring already draws: ``positions`` answers *what the fill did
to the position*, this answers *what the position became when it settled*.
``trades`` is one row per closed position (``UNIQUE (position_id)``), so it is
written exactly once, in the transaction of the attempt that settled it.
"""

from __future__ import annotations

import uuid
from decimal import Decimal, localcontext
from typing import TYPE_CHECKING

from sqlalchemy import text

from hunter_core.domain.types import uuid7
from hunter_core.strategies.numeric import CONTEXT

if TYPE_CHECKING:
    from datetime import datetime

    from sqlalchemy.ext.asyncio import AsyncSession

    from hunter_core.domain.enums import ExitReason
    from hunter_execution_worker.positions import OpenPositionRow, Reduction
    from hunter_execution_worker.reference import MarketReference
    from hunter_execution_worker.wallet import WalletRef

__all__ = ["close_position"]


async def close_position(
    session: AsyncSession,
    *,
    wallet: WalletRef,
    market: MarketReference,
    position: OpenPositionRow,
    reduction: Reduction,
    exit_reason: ExitReason,
    now: datetime,
) -> uuid.UUID | None:
    """Write the ``trades`` row of a position that just reached zero.

    ``pnl`` is **net** of the fees this position paid and ``entry_price``/
    ``exit_price`` are the execution prices, which is what
    ``LedgerRepository.daily_realized_pnl`` recomputes the gross result from —
    the two never disagree because they measure different things and the costs
    are subtracted exactly once, as ``daily_costs``.
    """
    opened = position.opened_qty or position.qty
    total_qty = opened - reduction.remaining_qty
    with localcontext(CONTEXT):
        gross = reduction.total_realized_pnl
        fees = reduction.total_fees_quote
        net = gross - fees
        cost = total_qty * position.avg_entry_price
        pnl_pct = (net / cost) if cost > 0 else None
        # The *effective* exit price: the one that makes the trade's own
        # arithmetic (``qty x (exit - entry)``) equal the result the position
        # really accumulated across every attempt. With a single attempt it is
        # the fill price; with several it is their weighted average, and it is
        # exact by construction rather than "the last one we saw".
        effective_exit = (
            (position.avg_entry_price + gross / total_qty).quantize(Decimal("0.0000000001"))
            if total_qty > 0
            else reduction.exit_price
        )
    trade_id = uuid7()
    inserted = await session.scalar(
        text(
            "INSERT INTO trades (id, organization_id, portfolio_id, market_id, position_id, "
            "proposal_id, execution_mode, direction, entry_price, exit_price, qty, notional, "
            "fees, slippage_cost, pnl, pnl_pct, exit_reason, opened_at, closed_at) "
            "VALUES (:id, :org, :pf, :market, :position, :proposal, 'paper', 'long', :entry, "
            ":exit, :qty, :notional, :fees, 0, :pnl, :pnl_pct, :reason, :opened, :closed) "
            "ON CONFLICT (position_id) DO NOTHING RETURNING id"
        ),
        {
            "id": trade_id,
            "org": wallet.organization_id,
            "pf": wallet.portfolio_id,
            "market": market.market_id,
            "position": position.position_id,
            "proposal": position.proposal_id,
            "entry": position.avg_entry_price,
            "exit": effective_exit,
            "qty": total_qty,
            "notional": total_qty * effective_exit,
            "fees": fees,
            "pnl": net,
            "pnl_pct": pnl_pct,
            "reason": exit_reason.value,
            "opened": position.opened_at,
            "closed": now,
        },
    )
    return None if inserted is None else trade_id
