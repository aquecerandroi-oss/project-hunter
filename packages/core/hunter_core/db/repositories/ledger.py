"""The reads that reconstruct a wallet from the database and nothing else.

Cash, open positions, standing reservations and the day's realised result are
all *derived from durable rows*, never from a number a process kept in memory:
after a restart the ledger has to arrive at the same wallet, and the only way to
promise that is to have no other source (T3.3 acceptance, "reconstrução após
restart").

Three conventions are declared here rather than assumed, because the writer
(T3.5) does not exist yet and a reader that guesses is a reader that will
disagree with it:

- **cash** is the anchored credit plus every sale minus every purchase minus the
  fees charged *in the operating currency*. A fee charged in the base asset does
  not touch cash — it reduces the units the wallet actually received, which is
  the position's problem (RISK_ENGINE.md §3, "fee em ativo-base reduz a
  quantidade vendável");
- **the day's realised result is gross**, computed from the trade's own prices
  (``qty × (exit − entry)``, signed by direction) instead of ``trades.pnl``,
  whose net-or-gross convention no migration fixes. The costs are then
  subtracted exactly once, as ``daily_costs``;
- **the day's costs** are the fills' fees, in the operating currency *and* in
  the base asset. A base-asset fee never debits cash - it reduces the units the
  wallet received - but it is a cost of the day, and a costs figure that ignored
  it reported zero for a purchase that took a unit off the patrimony (Astra,
  review of the T3.3 diff, must-fix A). It is returned as a quantity, for the
  caller to value at the same marks it used for the positions. Slippage is
  already inside the fill price and counting ``trades.slippage_cost`` again
  would charge it twice.

The day's window is bounded by the **reference instant**, inclusive, not by
midnight: the daily equity reference already contains everything committed
before it (RISK_ENGINE.md section 5, and must-fix C of the same review).
"""

from __future__ import annotations

import uuid
from decimal import Decimal
from typing import TYPE_CHECKING

from pydantic import BaseModel, ConfigDict
from sqlalchemy import text

from hunter_core.db.repositories.base import TenantRepository

if TYPE_CHECKING:
    from datetime import datetime

_ZERO = Decimal(0)

_MARKET_JOIN = """
    JOIN markets m ON m.id = {alias}.market_id
    JOIN exchanges x ON x.id = m.exchange_id
    LEFT JOIN assets ba ON ba.id = m.base_asset_id
    LEFT JOIN assets qa ON qa.id = m.quote_asset_id
"""

_MARKET_COLUMNS = (
    "x.code AS exchange, m.symbol AS symbol, m.market_type::text AS market_type, "
    "ba.symbol AS base_asset, qa.symbol AS quote_asset"
)


class PositionRow(BaseModel):
    """One open (or closing) position, with the identity of its market."""

    model_config = ConfigDict(frozen=True)

    position_id: uuid.UUID
    market_id: uuid.UUID
    exchange: str
    symbol: str
    market_type: str
    base_asset: str | None
    quote_asset: str | None
    direction: str
    qty: Decimal
    avg_entry_price: Decimal
    stop_price: Decimal | None
    status: str
    """``positions.status`` — ``open`` or ``closing``. Read because the two are
    not the same kind of holding: see :attr:`is_residual`."""

    durable_mark_price: Decimal | None
    """``positions.mark_price`` — the last mark the writer persisted. Used only
    as the *fallback* when the live source has no valid price, and never as an
    excuse to report a fresh equity: the state is flagged incomplete instead."""

    @property
    def is_residual(self) -> bool:
        """Is what this row still holds *dust* rather than a position?

        A spot buy pays its fee in the coin, so the wallet receives
        ``qty × 0,999`` and almost never a whole number of ``step_size``: after
        the exit, a leftover below ``min_qty`` stays for ever because no price
        makes it sellable. The writer marks that with ``status = 'closing'``
        (``hunter_execution_worker.positions.reduce_position``), which today is
        exactly and only the dust case.

        The residual is still **owned, marked and part of the patrimony** — it
        is simply not a position: it takes no slot, is not the coin "already in
        the wallet" for D3, and commits no planned risk (T3.5b review, item 3).
        A durable ``positions.is_residual`` is filed for T3.1e; until it lands,
        this property is the single place that reading knows the difference."""
        return self.status == "closing"


class ReservationRow(BaseModel):
    """One proposal whose reservation is still standing (``reservation_state='held'``)."""

    model_config = ConfigDict(frozen=True)

    proposal_id: uuid.UUID
    market_id: uuid.UUID
    exchange: str
    symbol: str
    market_type: str
    base_asset: str | None
    quote_asset: str | None
    reserved_notional: Decimal
    reserved_cash: Decimal
    reserved_risk: Decimal
    reserved_slot: bool


class CashReconciliation(BaseModel):
    """Cash rebuilt from the anchor and every fill, with the parts kept visible."""

    model_config = ConfigDict(frozen=True)

    credited: Decimal
    bought: Decimal
    sold: Decimal
    fees: Decimal

    @property
    def cash(self) -> Decimal:
        return self.credited + self.sold - self.bought - self.fees


class LedgerRepository(TenantRepository):
    """Everything the ledger reads about one wallet, scoped to one organization."""

    async def open_positions(self, portfolio_id: uuid.UUID) -> tuple[PositionRow, ...]:
        # S608: the only interpolated fragments are the module constants above
        # (column list and join). Every value is a bound parameter.
        statement = text(
            "SELECT p.id AS position_id, p.market_id, p.direction::text AS direction, p.qty, "  # noqa: S608
            "p.avg_entry_price, p.stop_price, p.status::text AS status, "
            "p.mark_price AS durable_mark_price, "
            f"{_MARKET_COLUMNS} FROM positions p "
            + _MARKET_JOIN.format(alias="p")
            + " WHERE p.organization_id = :org AND p.portfolio_id = :pf "
            "AND p.status <> 'closed' AND p.qty > 0 ORDER BY p.opened_at"
        )
        rows = await self.session.execute(
            statement, {"org": self.organization_id, "pf": portfolio_id}
        )
        return tuple(PositionRow.model_validate(row, from_attributes=True) for row in rows)

    async def held_reservations(self, portfolio_id: uuid.UUID) -> tuple[ReservationRow, ...]:
        """Proposals still holding cash, risk, exposure and a slot.

        Gated on ``reservation_state`` alone, never on ``reserved_until``: the
        schema puts the tenure in the state precisely so that what counts
        against a limit is one column, and expiry is a sweep that competes for
        the same portfolio lock (DATABASE.md §18.3).
        """
        # S608: same module constants; every value is a bound parameter.
        statement = text(
            "SELECT tp.id AS proposal_id, tp.market_id, tp.reserved_notional, tp.reserved_cash, "  # noqa: S608
            f"tp.reserved_risk, tp.reserved_slot, {_MARKET_COLUMNS} FROM trade_proposals tp "
            + _MARKET_JOIN.format(alias="tp")
            + " WHERE tp.organization_id = :org AND tp.portfolio_id = :pf "
            "AND tp.reservation_state = 'held' ORDER BY tp.admission_seq"
        )
        rows = await self.session.execute(
            statement, {"org": self.organization_id, "pf": portfolio_id}
        )
        return tuple(ReservationRow.model_validate(row, from_attributes=True) for row in rows)

    async def reconcile_cash(
        self, portfolio_id: uuid.UUID, *, credited: Decimal, operating_currency: str
    ) -> CashReconciliation:
        """Rebuild cash from the anchored credit and every fill of this wallet."""
        statement = text(
            "SELECT "
            "coalesce(sum(f.qty * f.price) FILTER (WHERE o.side = 'buy'), 0) AS bought, "
            "coalesce(sum(f.qty * f.price) FILTER (WHERE o.side = 'sell'), 0) AS sold, "
            "coalesce(sum(f.fee) FILTER (WHERE f.fee_asset = :quote), 0) AS fees "
            "FROM fills f JOIN orders o ON o.id = f.order_id "
            "AND o.organization_id = f.organization_id AND o.portfolio_id = f.portfolio_id "
            "WHERE f.organization_id = :org AND f.portfolio_id = :pf"
        )
        row = (
            await self.session.execute(
                statement,
                {"org": self.organization_id, "pf": portfolio_id, "quote": operating_currency},
            )
        ).one()
        return CashReconciliation(
            credited=credited, bought=row.bought, sold=row.sold, fees=row.fees
        )

    async def daily_realized_pnl(
        self, portfolio_id: uuid.UUID, *, since: datetime, until: datetime
    ) -> Decimal:
        """Gross realised result of the trades closed inside the day's window.

        ``since`` is the daily reference's own instant, inclusive of it.
        """
        statement = text(
            "SELECT coalesce(sum(t.qty * CASE WHEN t.direction = 'long' "
            "THEN t.exit_price - t.entry_price ELSE t.entry_price - t.exit_price END), 0) AS pnl "
            "FROM trades t WHERE t.organization_id = :org AND t.portfolio_id = :pf "
            "AND t.closed_at >= :since AND t.closed_at <= :until"
        )
        value = await self.session.scalar(
            statement,
            {"org": self.organization_id, "pf": portfolio_id, "since": since, "until": until},
        )
        return Decimal(value) if value is not None else _ZERO

    async def daily_costs(
        self,
        portfolio_id: uuid.UUID,
        *,
        since: datetime,
        until: datetime,
        operating_currency: str,
    ) -> Decimal:
        """Fees charged in the operating currency inside the day's window."""
        statement = text(
            "SELECT coalesce(sum(f.fee), 0) AS fees FROM fills f "
            "WHERE f.organization_id = :org AND f.portfolio_id = :pf "
            "AND f.fee_asset = :quote AND f.ts >= :since AND f.ts <= :until"
        )
        value = await self.session.scalar(
            statement,
            {
                "org": self.organization_id,
                "pf": portfolio_id,
                "quote": operating_currency,
                "since": since,
                "until": until,
            },
        )
        return Decimal(value) if value is not None else _ZERO

    async def daily_base_asset_fees(
        self,
        portfolio_id: uuid.UUID,
        *,
        since: datetime,
        until: datetime,
        operating_currency: str,
    ) -> tuple[tuple[uuid.UUID, Decimal], ...]:
        """Fees charged in a market's **base asset**, per market, in base units.

        Returned as quantities rather than money: valuing them needs a price,
        and the price the ledger uses is the caller's, the same one the
        positions were marked with. A fee in some third asset (a discount token)
        is deliberately **not** matched here - it would need its own market and
        its own price, and reporting it as base units would be a lie about which
        units moved.
        """
        statement = text(
            "SELECT o.market_id AS market_id, sum(f.fee) AS qty FROM fills f "
            "JOIN orders o ON o.id = f.order_id AND o.organization_id = f.organization_id "
            "AND o.portfolio_id = f.portfolio_id "
            "JOIN markets m ON m.id = o.market_id "
            "JOIN assets ba ON ba.id = m.base_asset_id "
            "WHERE f.organization_id = :org AND f.portfolio_id = :pf "
            "AND f.fee > 0 AND f.fee_asset IS NOT NULL AND f.fee_asset <> :quote "
            "AND f.fee_asset = ba.symbol AND f.ts >= :since AND f.ts <= :until "
            "GROUP BY o.market_id"
        )
        rows = await self.session.execute(
            statement,
            {
                "org": self.organization_id,
                "pf": portfolio_id,
                "quote": operating_currency,
                "since": since,
                "until": until,
            },
        )
        return tuple((row.market_id, Decimal(row.qty)) for row in rows)

    async def realized_pnl_cum(self, portfolio_id: uuid.UUID) -> Decimal:
        """Gross realised result of every trade this wallet ever closed."""
        statement = text(
            "SELECT coalesce(sum(t.qty * CASE WHEN t.direction = 'long' "
            "THEN t.exit_price - t.entry_price ELSE t.entry_price - t.exit_price END), 0) AS pnl "
            "FROM trades t WHERE t.organization_id = :org AND t.portfolio_id = :pf"
        )
        value = await self.session.scalar(
            statement, {"org": self.organization_id, "pf": portfolio_id}
        )
        return Decimal(value) if value is not None else _ZERO
