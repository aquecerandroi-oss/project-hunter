"""Assembling ``GET /api/v1/orgs/{org_id}/portfolios/{portfolio_id}/risk/limits``.

Every number is read through ``hunter_core.portfolio``/``hunter_core.risk``
(T3.3/T3.6) and ``hunter_risk.limits`` — nothing here recomputes a check or a
limit. ``build_portfolio_state`` is called exactly as
``hunter_api.services.portfolio_queries.build_summary`` calls it (``marks={}``,
no live price feed wired into the API), so ``usage``'s per-cap fields carry the
same honest gaps the wallet page already shows for a fresh restart.
"""

from __future__ import annotations

import uuid
from decimal import Decimal
from typing import TYPE_CHECKING, Literal

from sqlalchemy import desc, select

from hunter_api.schemas.risk import TransitionOut
from hunter_api.schemas.risk_limits import (
    AssetExposureOut,
    KillSwitchThresholdsOut,
    RiskLimitsOut,
    RiskLimitsPresetOut,
    UsageOut,
)
from hunter_core.db.models.portfolios import Portfolio, RiskProfile
from hunter_core.db.models.risk import KillSwitchTransition
from hunter_core.db.repositories.ledger import LedgerRepository
from hunter_core.domain.enums import KillSwitchScope
from hunter_core.portfolio.state import WalletNotOpen, build_portfolio_state
from hunter_risk.limits import PAPER_V1, RiskLimits, diverged_fields

if TYPE_CHECKING:
    from datetime import datetime

    from sqlalchemy.ext.asyncio import AsyncSession

_ZERO = Decimal(0)
RECENT_TRANSITIONS_LIMIT = 5


def _preset_out(
    limits: RiskLimits,
    *,
    source: Literal["risk_profile", "engine_default"],
    diverged: bool | None = None,
) -> RiskLimitsPresetOut:
    return RiskLimitsPresetOut(
        diverged_from_engine=bool(diverged_fields(limits)) if diverged is None else diverged,
        profile=limits.profile,
        risk_per_trade_pct=limits.risk_per_trade_pct,
        max_aggregate_planned_risk_pct=limits.max_aggregate_planned_risk_pct,
        max_participation_pct=limits.max_participation_pct,
        participation_window_s=limits.participation_window_s,
        max_asset_exposure_pct=limits.max_asset_exposure_pct,
        max_total_exposure_pct=limits.max_total_exposure_pct,
        max_beta_btc_exposure=limits.max_beta_btc_exposure,
        max_concurrent_positions=limits.max_concurrent_positions,
        kill_switch_warning=KillSwitchThresholdsOut(
            daily_loss_pct=limits.kill_switch_warning.daily_loss_pct,
            drawdown_pct=limits.kill_switch_warning.drawdown_pct,
        ),
        kill_switch_blocked=KillSwitchThresholdsOut(
            daily_loss_pct=limits.kill_switch_blocked.daily_loss_pct,
            drawdown_pct=limits.kill_switch_blocked.drawdown_pct,
        ),
        warning_size_multiplier=limits.warning_size_multiplier,
        min_liquidity_usd_24h=limits.min_liquidity_usd_24h,
        max_slippage_pct=limits.max_slippage_pct,
        max_spread_pct=limits.max_spread_pct,
        min_stop_distance_pct=limits.min_stop_distance_pct,
        max_stop_distance_pct=limits.max_stop_distance_pct,
        max_entry_deviation_pct=limits.max_entry_deviation_pct,
        max_price_age_s=limits.max_price_age_s,
        max_book_age_s=limits.max_book_age_s,
        max_volume_age_s=limits.max_volume_age_s,
        max_beta_age_s=limits.max_beta_age_s,
        max_leverage=limits.max_leverage,
        day_timezone=limits.day_timezone,
        source=source,
    )


async def _load_preset(session: AsyncSession, wallet: Portfolio) -> RiskLimitsPresetOut:
    """The wallet's profile as the engine resolves it (T3.69b), never a guess.

    Same three answers as ``hunter_execution_worker.risk_profile``: the row when
    it validates (with ``diverged_from_engine`` saying whether the worker will
    apply it or refuse), and the engine constant — flagged as diverged — when
    the row exists but cannot be validated at all. This never reports a number
    as being in force that the worker would refuse to enforce.
    """
    if wallet.risk_profile_id is not None:
        profile = await session.get(RiskProfile, wallet.risk_profile_id)
        if profile is not None:
            try:
                # A fraction re-typed as a JSON number raises TypeError, not
                # ValidationError (``RiskModel._refuse_float``): both are "this
                # row is not a profile", and neither may blank the screen.
                stored = RiskLimits.model_validate(profile.limits)
            except Exception:
                return _preset_out(PAPER_V1, source="engine_default", diverged=True)
            return _preset_out(stored, source="risk_profile")
    # No profile wired (every principal wallet until ACTIVATION.md §8b is run):
    # the engine's own constant is the one number this can honestly report — and
    # with T3.69b deployed it is also a wallet the worker admits nothing for.
    return _preset_out(PAPER_V1, source="engine_default")


async def _recent_transitions(
    session: AsyncSession, portfolio_id: uuid.UUID, *, limit: int
) -> list[KillSwitchTransition]:
    rows = (
        await session.execute(
            select(KillSwitchTransition)
            .where(
                KillSwitchTransition.scope == KillSwitchScope.PORTFOLIO,
                KillSwitchTransition.scope_id == portfolio_id,
            )
            .order_by(desc(KillSwitchTransition.created_at), desc(KillSwitchTransition.id))
            .limit(limit)
        )
    ).scalars()
    return list(rows)


def _transition_out(row: KillSwitchTransition) -> TransitionOut:
    return TransitionOut(
        from_state=row.from_state,
        to_state=row.to_state,
        reason=row.reason,
        actor_type=row.actor_type,
        actor_id=row.actor_id,
        evidence=row.evidence,
        created_at=row.created_at,
    )


async def build_risk_limits(
    session: AsyncSession, org_id: uuid.UUID, portfolio_id: uuid.UUID, as_of: datetime
) -> RiskLimitsOut | None:
    """The whole Risk Center read at ``as_of``, or ``None`` for "not this org's"."""
    wallet = await session.get(Portfolio, portfolio_id)
    if wallet is None or wallet.organization_id != org_id:
        return None

    preset = await _load_preset(session, wallet)

    try:
        build = await build_portfolio_state(
            session,
            organization_id=org_id,
            portfolio_id=portfolio_id,
            as_of=as_of,
            marks={},
            exit_cost_rate=_ZERO,
        )
    except WalletNotOpen:
        return None

    reservations = await LedgerRepository(session, org_id).held_reservations(portfolio_id)
    reserved_notional = sum((row.reserved_notional for row in reservations), _ZERO)
    reserved_cash = sum((row.reserved_cash for row in reservations), _ZERO)
    reserved_risk = sum((row.reserved_risk for row in reservations), _ZERO)

    state = build.state
    per_asset: list[AssetExposureOut] | None = None
    beta_weighted: Decimal | None = None
    beta_reason: str | None = None
    slots_used: int | None = None
    committed_planned_risk: Decimal | None = None
    available_cash: Decimal | None = None
    total_exposure: Decimal | None = None
    daily_loss_pct: Decimal | None = None
    drawdown_pct: Decimal | None = None
    if state is not None:
        per_asset = [
            AssetExposureOut(base_asset=asset, notional=state.exposure_for_asset(asset))
            for asset in sorted(state.assets_held)
        ]
        beta_weighted = state.beta_exposure()
        if beta_weighted is None and (state.open_positions or state.pending_entries):
            beta_reason = "beta_unavailable"
        slots_used = state.slots_used
        committed_planned_risk = state.committed_planned_risk
        available_cash = state.available_cash
        total_exposure = state.total_exposure
        daily_loss_pct = state.daily_loss_pct
        drawdown_pct = state.drawdown_pct

    usage = UsageOut(
        open_position_count=build.open_position_count,
        pending_entry_count=len(reservations),
        reserved_cash=reserved_cash,
        reserved_notional=reserved_notional,
        reserved_risk=reserved_risk,
        total_exposure=total_exposure,
        per_asset=per_asset,
        beta_weighted_exposure=beta_weighted,
        beta_weighted_exposure_reason=beta_reason,
        slots_used=slots_used,
        committed_planned_risk=committed_planned_risk,
        available_cash=available_cash,
        daily_loss_pct=daily_loss_pct,
        drawdown_pct=drawdown_pct,
        unavailable=list(build.unavailable),
    )

    # Imported here, not at module scope: ``routers/risk.py`` imports this
    # module's sibling schemas, and a top-level import back would be a cycle
    # between the router and its own service layer.
    from hunter_api.routers.risk import build_kill_switch_out

    kill_switch = await build_kill_switch_out(session, portfolio_id)
    recent = await _recent_transitions(session, portfolio_id, limit=RECENT_TRANSITIONS_LIMIT)

    return RiskLimitsOut(
        portfolio_id=portfolio_id,
        as_of=as_of,
        preset=preset,
        usage=usage,
        kill_switch=kill_switch,
        recent_transitions=[_transition_out(row) for row in recent],
    )
