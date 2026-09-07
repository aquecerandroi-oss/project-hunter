"""The position a fill opens, reduces or closes — and the trade it becomes.

Three conventions, declared here because the ledger reads the rows and not this
module:

- **quantity is net of the base-asset fee.** A spot buy pays its fee in the coin,
  so the wallet receives ``filled_qty − fee`` units and that is what
  ``positions.qty`` holds (RISK_ENGINE.md §3). The fee never debits cash.
- **``avg_entry_price`` is the price really paid per unit bought**
  (``gross ÷ filled``), not ``gross ÷ net``: the fee is accounted once, as a
  cost of the day (``LedgerRepository.daily_costs`` values base-asset fees at the
  same marks the state used), and folding it into the entry price would charge it
  a second time inside every future PnL.
- **``trades`` is written when the position closes**, which is what the table is
  (``UNIQUE (position_id)``, "one row per closed position"). A partial exit
  accumulates in ``positions.realized_pnl``; the day's realised figure the kill
  switch reads comes from ``trades``, so a partially-closed position contributes
  to it only when the last unit leaves. Declared, not discovered: closing that
  gap needs a column the schema does not have.
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, localcontext
from typing import TYPE_CHECKING, Any, cast

from sqlalchemy import text

from hunter_core.domain.enums import ExitReason, PositionStatus, TradeDirection
from hunter_core.domain.types import uuid7
from hunter_core.strategies.numeric import CONTEXT

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from hunter_execution_worker.reference import MarketReference
    from hunter_execution_worker.wallet import WalletRef

__all__ = [
    "OpenPositionRow",
    "close_position",
    "load_open_position",
    "load_open_positions",
    "open_position",
    "reduce_position",
]

_ZERO = Decimal(0)

_SELECT = (
    "SELECT p.id AS position_id, p.market_id, p.qty, p.avg_entry_price, p.stop_price, "
    "p.realized_pnl, p.fees_paid, p.mark_price, p.opened_at, p.metadata "
    "FROM positions p WHERE p.organization_id = :org AND p.portfolio_id = :pf "
    "AND p.status <> 'closed' AND p.qty > 0 "
)


@dataclass(frozen=True, slots=True)
class OpenPositionRow:
    """One live position, as the protection cycle needs to read it."""

    position_id: uuid.UUID
    market_id: uuid.UUID
    qty: Decimal
    avg_entry_price: Decimal
    stop_price: Decimal | None
    realized_pnl: Decimal
    fees_paid: Decimal
    mark_price: Decimal | None
    opened_at: datetime
    proposal_id: uuid.UUID | None = None
    opened_qty: Decimal | None = None
    """The quantity this position was opened with, kept so a ``trades`` row can
    say how much was really liquidated after several attempts."""


def _row(row: Any) -> OpenPositionRow:
    """One ``positions`` row, read by name. ``Any`` because a SQLAlchemy ``Row``
    is dynamically shaped by its ``SELECT``; every value is narrowed here."""
    meta: dict[str, Any] = dict(row.metadata or {})
    raw_proposal = meta.get("proposal_id")
    raw_opened = meta.get("opened_qty")
    return OpenPositionRow(
        position_id=cast("uuid.UUID", row.position_id),
        market_id=cast("uuid.UUID", row.market_id),
        qty=cast("Decimal", row.qty),
        avg_entry_price=cast("Decimal", row.avg_entry_price),
        stop_price=cast("Decimal | None", row.stop_price),
        realized_pnl=cast("Decimal", row.realized_pnl),
        fees_paid=cast("Decimal", row.fees_paid),
        mark_price=cast("Decimal | None", row.mark_price),
        opened_at=cast("datetime", row.opened_at),
        proposal_id=uuid.UUID(raw_proposal) if isinstance(raw_proposal, str) else None,
        opened_qty=Decimal(str(raw_opened)) if raw_opened else None,
    )


async def load_open_positions(
    session: AsyncSession, *, wallet: WalletRef, lock: bool = False
) -> tuple[OpenPositionRow, ...]:
    """Every live position of the wallet, oldest first.

    ``lock=True`` takes ``FOR UPDATE`` on the position rows themselves. The
    wallet's lock row already serialises admission, expiry and the cycles of this
    worker; this second, narrower lock is what stops a stop and a manual close
    arriving through different code paths from reading the same balance
    (notes-T3.4.md §10: "a trava é da T3.5").
    """
    statement = _SELECT + "ORDER BY p.opened_at" + (" FOR UPDATE OF p" if lock else "")
    rows = await session.execute(
        text(statement), {"org": wallet.organization_id, "pf": wallet.portfolio_id}
    )
    return tuple(_row(row) for row in rows)


async def load_open_position(
    session: AsyncSession, *, wallet: WalletRef, market_id: uuid.UUID, lock: bool = False
) -> OpenPositionRow | None:
    """The live position of one market, if there is one."""
    statement = _SELECT + "AND p.market_id = :market" + (" FOR UPDATE OF p" if lock else "")
    row = (
        await session.execute(
            text(statement),
            {"org": wallet.organization_id, "pf": wallet.portfolio_id, "market": market_id},
        )
    ).one_or_none()
    return None if row is None else _row(row)


async def open_position(
    session: AsyncSession,
    *,
    wallet: WalletRef,
    market: MarketReference,
    qty: Decimal,
    entry_price: Decimal,
    stop_price: Decimal | None,
    fees_quote: Decimal,
    now: datetime,
    proposal_id: uuid.UUID | None,
) -> uuid.UUID:
    """Create the position the entry's fill opened."""
    position_id = uuid7()
    with localcontext(CONTEXT):
        notional = qty * entry_price
    await session.execute(
        text(
            "INSERT INTO positions (id, organization_id, portfolio_id, market_id, direction, "
            "qty, avg_entry_price, mark_price, notional, unrealized_pnl, realized_pnl, "
            "fees_paid, stop_price, status, opened_at, metadata) VALUES (:id, :org, :pf, "
            ":market, :direction, :qty, :price, :price, :notional, 0, 0, :fees, :stop, "
            ":status, :now, CAST(:meta AS jsonb))"
        ),
        {
            "id": position_id,
            "org": wallet.organization_id,
            "pf": wallet.portfolio_id,
            "market": market.market_id,
            "direction": TradeDirection.LONG.value,
            "qty": qty,
            "price": entry_price,
            "notional": notional,
            "fees": fees_quote,
            "stop": stop_price,
            "status": PositionStatus.OPEN.value,
            "now": now,
            "meta": json.dumps(
                {
                    "proposal_id": str(proposal_id) if proposal_id else None,
                    "opened_qty": str(qty),
                }
            ),
        },
    )
    return position_id


@dataclass(frozen=True, slots=True)
class Reduction:
    """What one exit fill did to a position."""

    position_id: uuid.UUID
    qty_sold: Decimal
    exit_price: Decimal
    realized_pnl: Decimal
    """Gross of costs — ``qty × (exit − entry)``, the same convention
    ``LedgerRepository.daily_realized_pnl`` recomputes from the trade's prices."""
    remaining_qty: Decimal
    closed: bool
    settled: bool
    """The position holds nothing sellable any more — zero, or only dust."""
    total_realized_pnl: Decimal
    """Everything this position has realised, this reduction included."""
    total_fees_quote: Decimal
    """Every fee this position has paid, in the operating currency."""


async def reduce_position(
    session: AsyncSession,
    *,
    wallet: WalletRef,
    position: OpenPositionRow,
    qty: Decimal,
    exit_price: Decimal,
    fees_quote: Decimal,
    now: datetime,
    dust: bool = False,
) -> Reduction:
    """Take ``qty`` off the position and accumulate what it realised.

    ``dust=True`` says the leftover is below the exchange minimum, so nothing
    sellable remains: the position moves to ``closing`` and keeps holding the
    residual, which stays in the wallet's equity and stays visible. It is never
    zeroed — "resíduo contabilizado e visível, nunca quitado como se tivesse
    sido vendido" (RISK_ENGINE.md §10, spec V7 item 5).
    """
    if qty <= 0:
        raise ValueError("a reduction needs a positive quantity")
    if qty > position.qty:
        raise ValueError(
            f"cannot sell {qty} of a position holding {position.qty}: the sellable quantity is "
            "shared under one lock and never exceeds the position (RISK_ENGINE.md §10)"
        )
    with localcontext(CONTEXT):
        realized = qty * (exit_price - position.avg_entry_price)
        remaining = position.qty - qty
        notional = remaining * exit_price
    closed = remaining == _ZERO
    settled = closed or (dust and remaining > _ZERO)
    status = (
        PositionStatus.CLOSED
        if closed
        else PositionStatus.CLOSING
        if settled
        else PositionStatus.OPEN
    )
    await session.execute(
        text(
            "UPDATE positions SET qty = :qty, notional = :notional, mark_price = :price, "
            "realized_pnl = realized_pnl + :realized, fees_paid = fees_paid + :fees, "
            "unrealized_pnl = :unrealized, status = :status, closed_at = :closed_at, "
            "updated_at = :now WHERE id = :id AND organization_id = :org AND portfolio_id = :pf"
        ),
        {
            "qty": remaining,
            "notional": notional,
            "price": exit_price,
            "realized": realized,
            "fees": fees_quote,
            "unrealized": remaining * (exit_price - position.avg_entry_price),
            "status": status.value,
            "closed_at": now if closed else None,
            "now": now,
            "id": position.position_id,
            "org": wallet.organization_id,
            "pf": wallet.portfolio_id,
        },
    )
    return Reduction(
        position_id=position.position_id,
        qty_sold=qty,
        exit_price=exit_price,
        realized_pnl=realized,
        remaining_qty=remaining,
        closed=closed,
        settled=settled,
        total_realized_pnl=position.realized_pnl + realized,
        total_fees_quote=position.fees_paid + fees_quote,
    )


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
