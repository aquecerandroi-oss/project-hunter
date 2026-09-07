"""Building the risk engine's ``PortfolioState`` from the database, under the lock.

This is the seam between the ledger and the pure engine. The engine reads no
clock, no Redis and no Postgres (ARCHITECTURE.md §6), so *something* has to
gather the wallet at one instant and hand it over whole — and that something has
to do it under the wallet's own row lock, in the same transaction that will
apply whatever effect follows, because a state read outside the lock is a state
that was already false when it arrived (M3 joint decision, item 4).

The state object is **not redefined here**: :func:`build_portfolio_state`
constructs :class:`hunter_risk.exposure.PortfolioState` with its own validators —
the peak is monotonic, ``day_start_utc`` really is the Sao Paulo day of
``as_of`` — so an assembly error becomes a refusal rather than a plausible
number.

**Two kinds of unavailability, kept apart.**

- *The daily reference is missing or belongs to another day* — the state cannot
  be built at all (``state`` is ``None``). RISK_ENGINE.md §5: entries blocked,
  protections preserved. The USDT figures are still returned, because a
  protective exit and the operator's screen both need them.
- *A price or the day's decomposition is missing* — the state **is** built, with
  ``marks_complete=False`` or with the three reporting fields at ``None``. The
  engine then rejects new entries on its own terms, and
  ``evaluate_exit`` keeps working.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal, localcontext
from typing import TYPE_CHECKING

from pydantic import BaseModel, ConfigDict

from hunter_core.db.repositories.equity import EquitySnapshotRepository
from hunter_core.db.repositories.ledger import LedgerRepository
from hunter_core.db.repositories.portfolio import PortfolioRepository
from hunter_core.domain.enums import PortfolioStatus
from hunter_core.domain.types import ensure_utc
from hunter_core.portfolio.attribution import LEDGER_CONTEXT
from hunter_core.portfolio.ledger import mark_positions, to_open_positions, to_pending_entries
from hunter_risk.exposure import PortfolioState, advance_peak, sao_paulo_day_start_utc

if TYPE_CHECKING:
    from collections.abc import Mapping

    from sqlalchemy.ext.asyncio import AsyncSession

_ZERO = Decimal(0)


class WalletNotOpen(LookupError):
    """No anchor or no lock row: this id is not an opened wallet, not a degraded one."""


class PortfolioStateBuild(BaseModel):
    """What the ledger read, and the engine state it could build from it."""

    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)

    organization_id: uuid.UUID
    portfolio_id: uuid.UUID
    as_of: datetime
    cash: Decimal
    equity: Decimal
    exposure_notional: Decimal
    unrealized_pnl: Decimal
    realized_pnl_cum: Decimal
    peak_equity: Decimal
    open_position_count: int
    credited: Decimal
    """``E0`` from the anchor — what the BRL attribution is measured against."""

    opening_rate: Decimal
    """``F0`` from the anchor."""

    state: PortfolioState | None
    """``None`` when the daily reference could not be rebuilt. Never a guess."""

    stale_marks: tuple[uuid.UUID, ...]
    """Markets whose live price was missing or non-positive at ``as_of``."""

    unavailable: tuple[str, ...]
    """Why something is missing, in the words the panel and the audit use."""


async def build_portfolio_state(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID,
    portfolio_id: uuid.UUID,
    as_of: datetime,
    marks: Mapping[uuid.UUID, Decimal],
    exit_cost_rate: Decimal,
    betas: Mapping[uuid.UUID, Decimal] | None = None,
) -> PortfolioStateBuild:
    """Read one wallet at ``as_of`` under its row lock and assemble the state.

    ``marks`` and ``betas`` are parameters, not lookups: the price source and
    the beta revision are decisions of the caller (the execution worker names
    the SPOT marking policy, the risk path names the beta revision it consumed),
    and a ledger that fetched them would be choosing them silently. A market
    absent from ``betas`` produces ``beta_btc=None``, which is *not validated*
    and rejects the aggregate — never a zero that would remove the position from
    the sum exactly when it matters.

    ``exit_cost_rate`` is the third such parameter and has **no default**: the
    planned loss the engine sums includes the cost of getting out
    (``hunter_risk.exposure.OpenPosition.planned_risk_quote``), and a ledger that
    reported the bare stop distance would let 190 of distance plus 2 of exit cost
    fit under a ceiling of 200 (Astra, review of this diff, must-fix B).
    """
    moment = ensure_utc(as_of)
    portfolios = PortfolioRepository(session, organization_id)
    await portfolios.require_tenant_context()

    risk_state = await portfolios.lock_risk_state(portfolio_id)
    anchor = await portfolios.get_anchor(portfolio_id)
    if risk_state is None or anchor is None:
        raise WalletNotOpen(
            f"portfolio {portfolio_id} has no lock row or no currency anchor; it was never "
            "opened, and an unopened wallet has no state to degrade to"
        )
    wallet = await portfolios.get(portfolio_id)

    ledger = LedgerRepository(session, organization_id)
    reconciliation = await ledger.reconcile_cash(
        portfolio_id,
        credited=anchor.credited_amount,
        operating_currency=anchor.operating_currency,
    )
    cash = reconciliation.cash
    marked = mark_positions(
        await ledger.open_positions(portfolio_id), marks, exit_cost_rate=exit_cost_rate
    )
    reservations = await ledger.held_reservations(portfolio_id)

    exposure = sum((position.notional for position in marked), _ZERO)
    unrealized = sum((position.unrealized_pnl for position in marked), _ZERO)
    equity = cash + exposure
    peak = advance_peak(risk_state.peak_equity, equity)
    realized_cum = await ledger.realized_pnl_cum(portfolio_id)

    unavailable: list[str] = []
    stale = tuple(p.row.market_id for p in marked if p.is_stale)
    if stale:
        unavailable.append("marks")

    open_positions, identity_gaps = to_open_positions(marked, betas or {})
    pending_entries, pending_gaps = to_pending_entries(reservations, betas or {})
    if identity_gaps or pending_gaps:
        unavailable.append("market_identity")

    def finish(state: PortfolioState | None) -> PortfolioStateBuild:
        return PortfolioStateBuild(
            organization_id=organization_id,
            portfolio_id=portfolio_id,
            as_of=moment,
            cash=cash,
            equity=equity,
            exposure_notional=exposure,
            unrealized_pnl=unrealized,
            realized_pnl_cum=realized_cum,
            peak_equity=peak,
            open_position_count=len(marked),
            credited=anchor.credited_amount,
            opening_rate=anchor.rate,
            state=state,
            stale_marks=stale,
            unavailable=tuple(unavailable),
        )

    day_start = sao_paulo_day_start_utc(moment)
    if (
        risk_state.equity_day_start is None
        or risk_state.trading_day_start_utc is None
        or ensure_utc(risk_state.trading_day_start_utc) != day_start
    ):
        unavailable.append("daily_reference")
        return finish(None)

    decomposition = await _daily_decomposition(
        session,
        ledger=ledger,
        organization_id=organization_id,
        portfolio_id=portfolio_id,
        risk_state_observed_at=risk_state.day_reference_observed_at,
        operating_currency=anchor.operating_currency,
        as_of=moment,
        unrealized_now=unrealized,
        marks={item.row.market_id: item.mark_price for item in marked},
    )
    if decomposition is None:
        unavailable.append("daily_decomposition")
    realized, unrealized_delta, costs = decomposition or (None, None, None)

    state = PortfolioState(
        portfolio_id=portfolio_id,
        as_of=moment,
        equity=equity,
        cash=cash,
        peak_equity=peak,
        day_start_equity=risk_state.equity_day_start,
        day_start_utc=day_start,
        open_positions=open_positions,
        pending_entries=pending_entries,
        daily_realized_pnl=realized,
        daily_unrealized_pnl=unrealized_delta,
        daily_costs=costs,
        marks_complete=not stale and not identity_gaps and not pending_gaps,
        is_active=_is_active(wallet),
    )
    return finish(state)


def _is_active(wallet: object | None) -> bool:
    status = getattr(wallet, "status", None)
    deleted_at = getattr(wallet, "deleted_at", None)
    return status == PortfolioStatus.ACTIVE and deleted_at is None


async def _daily_decomposition(
    session: AsyncSession,
    *,
    ledger: LedgerRepository,
    organization_id: uuid.UUID,
    portfolio_id: uuid.UUID,
    risk_state_observed_at: datetime | None,
    operating_currency: str,
    as_of: datetime,
    unrealized_now: Decimal,
    marks: Mapping[uuid.UUID, Decimal],
) -> tuple[Decimal, Decimal, Decimal] | None:
    """``(realised, Δunrealised, costs)`` of the trading day, or ``None``.

    The unrealised term is a **difference**, not a level: with a position bought
    at 100 and marked at 110 at midnight, sold today at 110, the realised result
    of the day is 10 while the patrimony did not move — the identity only closes
    once the unrealised carried into the day is subtracted (Astra, notes of
    T3.2, item 5).

    The level it is measured from is read from the curve point **bound to the
    day's reference instant**, matched exactly, never from the nearest earlier
    point: a predecessor proves temporal order, not that it is the state the
    reference was taken on (Astra, T3.3 policy review, must-fix 2). Without that
    point the whole decomposition is reported as unavailable, which is what
    ``None`` means everywhere in ``PortfolioState`` — never zero.

    **All three components share one accounting cut, and it is the reference's
    own instant** — not midnight (Astra, review of this diff, must-fix C). The
    day's equity reference is the equity *at that instant*, so a fee paid at
    00:00:00,5 with the reference sampled at 00:00:01 is already inside
    ``equity_day_start``; measuring the costs from midnight would subtract it a
    second time. The declared inclusion rule at the boundary is **inclusive**
    (``ts >= reference``), matching what the reference itself sees: it values a
    wallet from the rows committed before it, so a row stamped at the very same
    instant was not in it.

    The costs include the fees charged **in the base asset**, valued at the same
    marks this build used. Astra's counter-example (must-fix A): buying one unit
    at 100 with a fee of 0,01 units leaves the wallet with 0,99 units, cash down
    100 and a patrimony down 1, while a costs figure that only counted quote
    fees reported zero. That fee never touches cash — it reduces the units
    received — but it is a cost of the day and the decomposition has to say so.

    That valuation multiplies two ``NUMERIC(28,10)`` columns, each already up
    to 18 integer digits; the product can need more than the ambient default
    context's 28 significant digits, and the ambient default is what Python
    uses when nothing more specific is asked for. Run under
    :data:`hunter_core.portfolio.attribution.LEDGER_CONTEXT` (adversarial
    review of ``8a6a69f``, suggestion 12) — the same reason ``attribute_brl``
    needs it, for the same product of two ten-decimal numbers.
    """
    if risk_state_observed_at is None:
        return None
    since = ensure_utc(risk_state_observed_at)
    reference = await EquitySnapshotRepository(session, organization_id).at(
        portfolio_id=portfolio_id, ts=since
    )
    if reference is None:
        return None
    realized = await ledger.daily_realized_pnl(portfolio_id, since=since, until=as_of)
    costs = await ledger.daily_costs(
        portfolio_id, since=since, until=as_of, operating_currency=operating_currency
    )
    for market_id, qty in await ledger.daily_base_asset_fees(
        portfolio_id, since=since, until=as_of, operating_currency=operating_currency
    ):
        price = marks.get(market_id)
        if price is None:
            return None
        with localcontext(LEDGER_CONTEXT):
            costs += qty * price
    return realized, unrealized_now - reference.unrealized_pnl, costs
