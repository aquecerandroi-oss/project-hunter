"""``/api/v1/orgs/{org_id}/portfolios`` — the wallet the T3.3 ledger already builds.

RISK_ENGINE.md §5 (kill switch), DATABASE.md §18.2 (the FX ledger) and the M3
joint decision, item 1 (BRL is "unavailable with a reason", never extrapolated).
This module is the *shape* of a read; the numbers themselves are assembled in
``hunter_api.services.portfolio_queries`` from ``hunter_core.portfolio`` and
``hunter_core.risk`` — nothing here recomputes a check or an attribution.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel

from hunter_api.schemas.risk import ScopeStatesOut, TransitionOut
from hunter_core.domain.enums import KillSwitchState, PortfolioStatus, PortfolioType


class PortfolioListItemOut(BaseModel):
    """One row of ``GET /api/v1/orgs/{org_id}/portfolios``."""

    id: uuid.UUID
    workspace_id: uuid.UUID
    name: str
    type: PortfolioType
    status: PortfolioStatus
    is_arena: bool
    base_currency: str
    created_at: datetime


class FxObservationOut(BaseModel):
    """One ``fx_observations`` row — global, immutable (DATABASE.md §18.2)."""

    id: uuid.UUID
    pair: str
    source: str
    rate: Decimal
    observed_at: datetime
    available_at: datetime


class AnchorOut(BaseModel):
    """``portfolio_currency_anchor`` — the opening conversion, written once."""

    portfolio_id: uuid.UUID
    origin_currency: str
    origin_amount: Decimal
    operating_currency: str
    credited_amount: Decimal
    rate: Decimal
    conversion_residual: Decimal
    rounding_policy: str
    anchored_at: datetime
    fx_observation: FxObservationOut


class BrlDecompositionOut(BaseModel):
    """The operational/exchange split — ``hunter_core.portfolio.attribution``.

    ``operational_brl`` and ``currency_brl`` sum to ``total_brl``; the
    convention (attribution at the *opening* rate) is declared, not universal,
    and this is why the screen names ``opening_rate``/``current_rate`` instead
    of hiding them behind the totals.
    """

    opening_brl: Decimal
    operational_brl: Decimal
    currency_brl: Decimal
    equity_brl: Decimal
    total_brl: Decimal
    opening_rate: Decimal
    current_rate: Decimal
    fx_observation: FxObservationOut


class KillSwitchSummaryOut(BaseModel):
    """The kill switch, embedded in the portfolio summary.

    Mirrors ``hunter_api.schemas.risk.KillSwitchOut`` minus the daily
    reference/peak (reported once, in ``PortfolioRiskStateOut``, not twice).
    """

    effective: KillSwitchState
    blocks_entries: bool
    scopes: ScopeStatesOut
    reason: str | None
    last_transition: TransitionOut | None


class PortfolioRiskStateOut(BaseModel):
    """``portfolio_risk_state`` plus the engine's own read of it.

    ``daily_loss_pct``/``drawdown_pct`` are ``None`` exactly when
    ``hunter_core.portfolio.state.build_portfolio_state`` could not rebuild the
    daily reference (a restart before the first evaluation of the day) — never
    a silent zero (RISK_ENGINE.md §5, the "daily_loss PASSED value=0" defect
    this contract was written to close).
    """

    trading_day: date | None
    trading_day_timezone: str
    trading_day_start_utc: datetime | None
    equity_day_start: Decimal | None
    day_reference_observed_at: datetime | None
    peak_equity: Decimal
    peak_equity_observed_at: datetime
    peak_sampling_interval_s: int
    daily_loss_pct: Decimal | None
    drawdown_pct: Decimal | None
    kill_switch: KillSwitchSummaryOut


class PortfolioSummaryOut(BaseModel):
    """``GET /api/v1/orgs/{org_id}/portfolios/{portfolio_id}``.

    ``unavailable`` names *why*, in the words ``PortfolioStateBuild`` uses
    (``"marks"``, ``"market_identity"``, ``"daily_reference"``,
    ``"daily_decomposition"``) — never a silent gap in the numbers above it.
    """

    id: uuid.UUID
    organization_id: uuid.UUID
    workspace_id: uuid.UUID
    name: str
    type: PortfolioType
    status: PortfolioStatus
    base_currency: str
    as_of: datetime
    cash: Decimal
    equity: Decimal
    exposure_notional: Decimal
    unrealized_pnl: Decimal
    realized_pnl_cum: Decimal
    open_position_count: int
    reserved_cash: Decimal
    reserved_notional: Decimal
    reserved_risk: Decimal
    marks_complete: bool
    unavailable: list[str]
    brl: BrlDecompositionOut | None
    brl_unavailable_reason: str | None
    brl_unavailable_detail: str | None
    risk_state: PortfolioRiskStateOut
