"""``GET /api/v1/orgs/{org_id}/portfolios/{portfolio_id}/risk/limits`` — brief T3.25.

The numeric ``paper_v1`` preset, alongside the wallet's current usage against
every cap it names. ``hunter_api.services.risk_limits`` is the seam: this module
is only the shape, exactly like ``schemas/portfolio.py`` says of itself.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel

from hunter_api.schemas.lab_common import DecimalStr
from hunter_api.schemas.risk import KillSwitchOut, TransitionOut


class KillSwitchThresholdsOut(BaseModel):
    daily_loss_pct: DecimalStr
    drawdown_pct: DecimalStr


class RiskLimitsPresetOut(BaseModel):
    """``hunter_risk.limits.RiskLimits``, field for field, in its own order.

    ``source`` names where this copy was read from: ``risk_profile`` when the
    wallet's ``risk_profile_id`` names a row (``risk_profiles.limits``,
    DATABASE.md §7), ``engine_default`` when it does not — the principal wallet
    opened by ``infra/scripts/open_paper_wallet.py`` today never sets that
    column (no production caller of ``open_paper_wallet`` passes one), so the
    number this reports is ``hunter_risk.limits.PAPER_V1`` itself, the same
    object ``hunter_core.admission.service`` defaults every paper evaluation
    to. Either way the two are byte-for-byte the same profile (DATABASE.md §2,
    proved by ``test_schema_paper.py``); this field says which fact the
    response is standing on, never which number is right.
    """

    profile: str
    risk_per_trade_pct: DecimalStr
    max_aggregate_planned_risk_pct: DecimalStr
    max_participation_pct: DecimalStr
    participation_window_s: int
    max_asset_exposure_pct: DecimalStr
    max_total_exposure_pct: DecimalStr
    max_beta_btc_exposure: DecimalStr
    max_concurrent_positions: int
    kill_switch_warning: KillSwitchThresholdsOut
    kill_switch_blocked: KillSwitchThresholdsOut
    warning_size_multiplier: DecimalStr
    min_liquidity_usd_24h: DecimalStr
    max_slippage_pct: DecimalStr
    max_spread_pct: DecimalStr
    min_stop_distance_pct: DecimalStr
    max_stop_distance_pct: DecimalStr
    max_entry_deviation_pct: DecimalStr
    max_price_age_s: int
    max_book_age_s: int
    max_volume_age_s: int
    max_beta_age_s: int
    max_leverage: DecimalStr
    day_timezone: str
    source: Literal["risk_profile", "engine_default"]
    diverged_from_engine: bool = False
    """True when the wallet's stored row is **not** ``hunter_risk.limits.PAPER_V1``
    field by field — the same comparison the execution-worker runs before it
    admits anything (T3.69b, ``hunter_execution_worker.risk_profile``).

    It matters because the two are not two profiles: the seeded row *is*
    ``PAPER_V1.model_dump(mode="json")`` by construction (RISK_ENGINE.md §2), so
    a difference is a ceiling moved by nobody — and against such a row the
    engine admits **nothing**. With ``source="risk_profile"`` and this flag set,
    the numbers below are the row's and none of them is in force; with
    ``source="engine_default"`` and this flag set, the row exists but does not
    validate as ``RiskLimits`` at all, and the numbers below are the engine
    constant's, reported so the Risk Center still renders while an operator
    reconciles the row (the alternative was a 500 exactly when it is needed).
    """


class AssetExposureOut(BaseModel):
    """One coin's exposure, open plus reserved, across markets — ``PortfolioState.
    exposure_for_asset`` (``packages/risk-core/hunter_risk/exposure.py``)."""

    base_asset: str
    notional: DecimalStr


class UsageOut(BaseModel):
    """The wallet's current draw against every cap ``preset`` names.

    ``total_exposure``/``per_asset``/``beta_weighted_exposure``/``slots_used``/
    ``committed_planned_risk``/``available_cash`` are ``None`` exactly when
    ``hunter_core.portfolio.state.build_portfolio_state`` could not rebuild the
    daily reference (``unavailable`` then names why, the same words
    ``PortfolioSummaryOut.unavailable`` uses) — never a silent zero, for the
    same reason ``PortfolioRiskStateOut.daily_loss_pct`` is nullable.
    ``open_position_count``/``pending_entry_count``/``reserved_*`` do not
    depend on the daily reference and are always reported.
    """

    open_position_count: int
    pending_entry_count: int
    reserved_cash: DecimalStr
    reserved_notional: DecimalStr
    reserved_risk: DecimalStr
    total_exposure: DecimalStr | None
    per_asset: list[AssetExposureOut] | None
    beta_weighted_exposure: DecimalStr | None
    beta_weighted_exposure_reason: str | None
    slots_used: int | None
    committed_planned_risk: DecimalStr | None
    available_cash: DecimalStr | None
    daily_loss_pct: DecimalStr | None
    drawdown_pct: DecimalStr | None
    unavailable: list[str]


class RiskLimitsOut(BaseModel):
    portfolio_id: uuid.UUID
    as_of: datetime
    preset: RiskLimitsPresetOut
    usage: UsageOut
    kill_switch: KillSwitchOut
    recent_transitions: list[TransitionOut]
    """The last few audited moves, newest first — ``kill_switch.last_transition``
    repeated as the list's first item when one exists, so a client that only
    ever reads this list still sees the current motive."""
