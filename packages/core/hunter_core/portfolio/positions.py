"""Turning ledger rows into the engine's own position/entry objects.

Split out of ``ledger.py`` (file-size budget): marking a position and naming
its market are two different questions, and this module only answers the
second one — whether the reference data can name a market at all, which is a
question the engine's ``PortfolioState`` never sees answered *no* silently.
"""

from __future__ import annotations

import uuid
from decimal import Decimal
from typing import TYPE_CHECKING

from hunter_core.db.repositories.ledger import PositionRow, ReservationRow
from hunter_core.domain.enums import MarketType
from hunter_risk.exposure import OpenPosition, PendingEntry
from hunter_risk.inputs import MarketIdentity

if TYPE_CHECKING:
    from collections.abc import Mapping

    from hunter_core.portfolio.marking import MarkedPosition


def market_identity(row: PositionRow | ReservationRow) -> MarketIdentity | None:
    """The market's identity, or ``None`` when the reference data cannot name it.

    The engine compares identities (D1: spot executes, the perpetual decides), so
    a market with no base or quote asset is not a market it can reason about.
    """
    if row.base_asset is None or row.quote_asset is None:
        return None
    return MarketIdentity(
        exchange=row.exchange,
        symbol=row.symbol,
        market_type=MarketType(row.market_type),
        base_asset=row.base_asset,
        quote_asset=row.quote_asset,
    )


def to_open_positions(
    marked: tuple[MarkedPosition, ...], betas: Mapping[uuid.UUID, Decimal]
) -> tuple[tuple[OpenPosition, ...], int]:
    """The engine's own ``OpenPosition`` objects, plus how many were unnameable.

    A market whose reference data has no base or quote asset is skipped and
    counted: the caller turns that count into an unavailability, because an
    equity that quietly omitted a position would be a smaller number than the
    wallet really has.
    """
    positions: list[OpenPosition] = []
    gaps = 0
    for item in marked:
        identity = market_identity(item.row)
        if identity is None:
            gaps += 1
            continue
        positions.append(
            OpenPosition(
                position_id=item.row.position_id,
                market=identity,
                qty=item.row.qty,
                notional=item.notional,
                planned_risk_quote=item.planned_risk_quote,
                beta_btc=betas.get(item.row.market_id),
            )
        )
    return tuple(positions), gaps


def to_pending_entries(
    reservations: tuple[ReservationRow, ...], betas: Mapping[uuid.UUID, Decimal]
) -> tuple[tuple[PendingEntry, ...], int]:
    """The engine's ``PendingEntry`` objects, plus how many were unnameable.

    ``reserved_cash`` travels as the reservation's **own** number: re-estimating
    it with the next candidate's cost hypothesis is how 900 got committed
    against 500 (notes of T3.2, item 4).
    """
    entries: list[PendingEntry] = []
    gaps = 0
    for row in reservations:
        identity = market_identity(row)
        if identity is None:
            gaps += 1
            continue
        entries.append(
            PendingEntry(
                market=identity,
                reserved_notional=row.reserved_notional,
                reserved_cash=row.reserved_cash,
                planned_risk_quote=row.reserved_risk,
                beta_btc=betas.get(row.market_id),
            )
        )
    return tuple(entries), gaps
