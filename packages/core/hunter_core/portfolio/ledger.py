"""Marking positions and appending to the equity curve.

Two jobs, one module, because they are the same arithmetic seen twice: what a
position is worth *now* is what makes the equity, and the equity is what a point
of the curve records. Everything here is measured in the operating currency; the
BRL reading is derived at the end, from the observation the point names.

**No mark is ever fabricated.** When the caller's price source has nothing valid
for a market, the position keeps the last mark the writer persisted
(``positions.mark_price``, or its entry price if even that is missing) and the
build is flagged: ``PortfolioState.marks_complete`` goes false, the risk engine
refuses new entries, and protective exits — which do not need the state at all
(RISK_ENGINE.md §10) — keep working. A missing price is never zero: a position
marked at zero would understate exposure exactly when the data is worst.

**A point of the curve names the rate it used.** With no usable observation the
USDT side of the point is still written and the BRL side is *unavailable with a
reason*, never extrapolated and never back-filled with today's rate (M3 joint
decision, item 1).
"""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal, localcontext
from typing import TYPE_CHECKING, Literal

from pydantic import BaseModel, ConfigDict

from hunter_core.db.models.fx import FxObservation
from hunter_core.db.repositories.equity import REFERENCE_RESOLUTION, EquitySnapshotRepository
from hunter_core.db.repositories.ledger import PositionRow, ReservationRow
from hunter_core.domain.enums import MarketType, Timeframe
from hunter_core.domain.types import ensure_utc
from hunter_core.portfolio.attribution import LEDGER_CONTEXT, BrlAttribution, attribute_brl
from hunter_core.portfolio.opening import (
    PAPER_FX_POLICY,
    FxObservationRejected,
    FxPolicy,
    validate_fx_observation,
)
from hunter_risk.exposure import OpenPosition, PendingEntry
from hunter_risk.inputs import MarketIdentity

if TYPE_CHECKING:
    from collections.abc import Mapping

    from sqlalchemy.ext.asyncio import AsyncSession

    from hunter_core.portfolio.state import PortfolioStateBuild

_ZERO = Decimal(0)

BrlUnavailableReason = Literal["no_fx_observation", "fx_rejected"]


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
    """
    marked: list[MarkedPosition] = []
    for row in rows:
        live = marks.get(row.market_id)
        is_stale = live is None or live <= 0
        price = row.durable_mark_price if is_stale else live
        if price is None or price <= 0:
            price = row.avg_entry_price
        with localcontext(LEDGER_CONTEXT):
            notional = row.qty * price
            direction = Decimal(1) if row.direction == "long" else Decimal(-1)
            unrealized = row.qty * (price - row.avg_entry_price) * direction
            planned_risk = _planned_risk(row, price, direction, exit_cost_rate)
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


def _planned_risk(
    row: PositionRow, price: Decimal, direction: Decimal, exit_cost_rate: Decimal
) -> Decimal:
    """Loss at the stop plus the declared cost of getting out.

    Without a stop the position can lose its whole notional *and* still pay to be
    liquidated: an unknown planned loss is not a zero planned loss, and the
    aggregate ceiling must not be freed by a missing column.
    """
    exit_cost = row.qty * price * exit_cost_rate
    if row.stop_price is None:
        return row.qty * price + exit_cost
    loss = (price - row.stop_price) * direction * row.qty
    return (loss if loss > 0 else _ZERO) + exit_cost


class EquityPoint(BaseModel):
    """One point of the curve, as it was written, with its BRL reading."""

    model_config = ConfigDict(frozen=True)

    portfolio_id: uuid.UUID
    ts: datetime
    resolution: Timeframe
    cash: Decimal
    equity: Decimal
    exposure_notional: Decimal
    unrealized_pnl: Decimal
    realized_pnl_cum: Decimal
    peak_equity: Decimal
    open_positions: int
    fx_observation_id: uuid.UUID | None
    """The observation this point was **converted with**. Null when there was
    none, and null when the one offered was refused: naming an observation the
    BRL figure did not come from would be provenance that lies."""

    brl: BrlAttribution | None
    brl_unavailable_reason: BrlUnavailableReason | None
    brl_unavailable_detail: str | None
    """Which rule refused the observation, in the validator's own words."""


async def record_equity_point(
    session: AsyncSession,
    *,
    build: PortfolioStateBuild,
    fx: FxObservation | None,
    resolution: Timeframe = REFERENCE_RESOLUTION,
    fx_policy: FxPolicy = PAPER_FX_POLICY,
) -> EquityPoint:
    """Append ``build`` to the curve, converting to BRL only if ``fx`` may.

    **The USDT point is always written**, with or without a rate: refusing to
    record the patrimony because the BRL side is unavailable would lose the very
    history the curve exists for, and FX unavailable after the opening leaves
    USDT computable and BRL *unavailable with a reason* (M3 joint decision, item
    1).

    **The rate is validated against this point's own instant**, with the same
    policy the opening uses: pair, source, causality and the two ages. Astra's
    counter-example (review of this diff, must-fix D): rebuilding the point of
    10:00 from an observation that only became available at 11:00 would fold
    future information into a stored BRL figure and report no unavailability at
    all. A refused observation is not recorded as the point's rate either - the
    stored ``fx_observation_id`` is what the number came from, or nothing.
    """
    brl: BrlAttribution | None = None
    reason: BrlUnavailableReason | None = None
    detail: str | None = None
    if fx is None:
        reason = "no_fx_observation"
    else:
        try:
            validate_fx_observation(fx, as_of=build.as_of, policy=fx_policy)
        except FxObservationRejected as refusal:
            reason, detail = "fx_rejected", refusal.reason
        else:
            brl = attribute_brl(
                equity=build.equity,
                credited=build.credited,
                opening_rate=build.opening_rate,
                current_rate=fx.rate,
            )

    exposure_pct = None
    drawdown_pct = None
    with localcontext(LEDGER_CONTEXT):
        if build.equity > 0:
            exposure_pct = build.exposure_notional / build.equity
            if build.peak_equity > 0 and build.equity < build.peak_equity:
                drawdown_pct = (build.peak_equity - build.equity) / build.peak_equity
            else:
                drawdown_pct = _ZERO

    converted_with = fx.id if brl is not None and fx is not None else None
    await EquitySnapshotRepository(session, build.organization_id).record(
        portfolio_id=build.portfolio_id,
        ts=build.as_of,
        cash=build.cash,
        equity=build.equity,
        exposure_notional=build.exposure_notional,
        exposure_pct=exposure_pct,
        unrealized_pnl=build.unrealized_pnl,
        realized_pnl_cum=build.realized_pnl_cum,
        peak_equity=build.peak_equity,
        drawdown_pct=drawdown_pct,
        open_positions=build.open_position_count,
        fx_observation_id=converted_with,
        resolution=resolution,
    )

    return EquityPoint(
        portfolio_id=build.portfolio_id,
        ts=ensure_utc(build.as_of),
        resolution=resolution,
        cash=build.cash,
        equity=build.equity,
        exposure_notional=build.exposure_notional,
        unrealized_pnl=build.unrealized_pnl,
        realized_pnl_cum=build.realized_pnl_cum,
        peak_equity=build.peak_equity,
        open_positions=build.open_position_count,
        fx_observation_id=converted_with,
        brl=brl,
        brl_unavailable_reason=reason,
        brl_unavailable_detail=detail,
    )


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
