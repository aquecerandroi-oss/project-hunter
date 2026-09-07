"""Marking positions — valuing what the ledger holds, at one instant.

**No mark is ever fabricated.** When the caller's price source has nothing valid
for a market, the position keeps the last mark the writer persisted
(``positions.mark_price``, or its entry price if even that is missing) and the
build is flagged: ``PortfolioState.marks_complete`` goes false, the risk engine
refuses new entries, and protective exits — which do not need the state at all
(RISK_ENGINE.md §10) — keep working. A missing price is never zero: a position
marked at zero would understate exposure exactly when the data is worst.
"""

from __future__ import annotations

import uuid
from decimal import Decimal, localcontext
from typing import TYPE_CHECKING

from pydantic import BaseModel, ConfigDict

from hunter_core.db.repositories.ledger import PositionRow
from hunter_core.portfolio.attribution import LEDGER_CONTEXT

if TYPE_CHECKING:
    from collections.abc import Mapping

_ZERO = Decimal(0)


class NonLongPosition(ValueError):
    """A stored position is not long. The paper ledger is spot-only (D1: SPOT
    executes, the perpetual decides), so a "short" row is not a state this
    ledger can value — it is data corruption, and raising is the honest
    response, not silently pricing it with a sign convention nobody chose here
    (adversarial review of ``8a6a69f``, suggestion 13)."""


class MarkedPosition(BaseModel):
    """One position valued at ``as_of``, with the provenance of its price."""

    model_config = ConfigDict(frozen=True)

    row: PositionRow
    mark_price: Decimal
    """Never zero and never absent: the live price, else the last durable mark,
    else the entry price."""

    is_stale: bool
    """True when the live source had no valid price for this market."""

    notional: Decimal
    unrealized_pnl: Decimal
    planned_risk_quote: Decimal
    """What the position still loses if its stop is hit. Without a stop it is
    the whole notional: an unknown planned loss is not a zero planned loss, and
    the aggregate ceiling must not be freed by a missing column."""


def mark_positions(
    rows: tuple[PositionRow, ...],
    marks: Mapping[uuid.UUID, Decimal],
    *,
    exit_cost_rate: Decimal,
) -> tuple[MarkedPosition, ...]:
    """Value every position, falling back to its last durable mark, never to zero.

    ``exit_cost_rate`` is the caller's declared hypothesis for what liquidating a
    position costs, as a fraction of its notional (the exit's fee plus its
    slippage). It has **no default**: ``planned_risk_quote`` promises "what this
    position still loses if its stop is hit, *costs included*"
    (``hunter_risk.exposure.OpenPosition``), and a ledger that quietly reported
    the bare stop distance would under-report the aggregate ceiling - 190 of stop
    distance plus 2 of exit cost fits under a ceiling of 200 only because the 2
    was never counted (Astra, review of this diff, must-fix B).

    Every ``row`` must be long: the paper ledger only ever opens spot
    positions (D1), and a "short" row raises :class:`NonLongPosition` rather
    than being valued with a sign convention this spot-only ledger never
    declared (adversarial review of ``8a6a69f``, suggestion 13).
    """
    marked: list[MarkedPosition] = []
    for row in rows:
        if row.direction != "long":
            raise NonLongPosition(
                f"position {row.position_id} has direction {row.direction!r}; the paper "
                "ledger is spot-only (D1) and every stored position must be long"
            )
        live = marks.get(row.market_id)
        is_stale = live is None or live <= 0
        price = row.durable_mark_price if is_stale else live
        if price is None or price <= 0:
            price = row.avg_entry_price
        with localcontext(LEDGER_CONTEXT):
            notional = row.qty * price
            unrealized = row.qty * (price - row.avg_entry_price)
            planned_risk = _planned_risk(row, price, exit_cost_rate)
        marked.append(
            MarkedPosition(
                row=row,
                mark_price=price,
                is_stale=is_stale,
                notional=notional,
                unrealized_pnl=unrealized,
                planned_risk_quote=planned_risk,
            )
        )
    return tuple(marked)


def _planned_risk(row: PositionRow, price: Decimal, exit_cost_rate: Decimal) -> Decimal:
    """Loss at the stop plus the declared cost of getting out.

    Without a stop the position can lose its whole notional *and* still pay to be
    liquidated: an unknown planned loss is not a zero planned loss, and the
    aggregate ceiling must not be freed by a missing column. ``row.direction`` is
    always ``"long"`` here — :func:`mark_positions` has already refused anything
    else — so the stop distance is simply ``price - stop``.
    """
    exit_cost = row.qty * price * exit_cost_rate
    if row.stop_price is None:
        return row.qty * price + exit_cost
    loss = (price - row.stop_price) * row.qty
    return (loss if loss > 0 else _ZERO) + exit_cost
