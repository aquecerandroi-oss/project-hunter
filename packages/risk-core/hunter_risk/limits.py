"""``RiskLimits`` and ``PAPER_V1`` - the numbers Everton wrote, frozen.

Key names are the ones of ``docs/RISK_ENGINE.md`` v2 §2, because this object is
what ``risk_profiles.limits`` stores: a limit whose key does not match the
contract is a limit nobody will find when they go looking for it.

Every value comes from the verbatim directive of 2026-09-06
(``.claude/state/directive-risk-engine-2026-09-06.md``), from the decisions
delegated to Sexta-feira (``.claude/state/decisions-M3-delegated-2026-09-06.md``)
or, for the four technical guards, from the ``conservative`` preset of the v1
contract, which v2 §2 keeps explicitly ("guardas técnicas, não limites de
capital"). Nothing here was invented by this module.

The model refuses an incoherent profile at construction rather than at the first
proposal: a profile whose per-coin ceiling is above the total ceiling, or whose
warning threshold sits above the blocking one, contains a check that can never
fire, and a limit that can never fire is not a limit.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Final

from pydantic import Field, model_validator

from hunter_risk.base import RiskModel

_ONE = Decimal(1)


class KillSwitchThresholds(RiskModel):
    """One rung of the kill switch - directive §5."""

    daily_loss_pct: Decimal = Field(gt=0, le=_ONE)
    drawdown_pct: Decimal = Field(gt=0, le=_ONE)


class RiskLimits(RiskModel):
    """One risk profile. All ``*_pct`` values are fractions of equity, not percents."""

    profile: str = Field(min_length=1)

    risk_per_trade_pct: Decimal = Field(gt=0, le=_ONE)
    """Directive §2 - planned loss of one entry, costs included."""
    max_aggregate_planned_risk_pct: Decimal = Field(gt=0, le=_ONE)
    """Directive §2 - planned risk of open positions **and** pending entries."""

    max_participation_pct: Decimal = Field(gt=0, le=_ONE)
    """Directive §3 - share of the reference minute a new entry may take."""
    participation_window_s: int = Field(gt=0)
    """Rolling window over which participation already taken is counted (v2 §4)."""

    max_asset_exposure_pct: Decimal = Field(gt=0, le=_ONE)
    """Directive §4 - per coin."""
    max_total_exposure_pct: Decimal = Field(gt=0, le=_ONE)
    """Directive §4."""
    max_beta_btc_exposure: Decimal = Field(gt=0)
    """Directive §4 - ``Sum|notional_i x beta_i| / equity``; may exceed 1 by construction."""
    max_concurrent_positions: int = Field(ge=1)
    """Directive §4 - pending entries occupy a slot."""

    kill_switch_warning: KillSwitchThresholds
    kill_switch_blocked: KillSwitchThresholds
    warning_size_multiplier: Decimal = Field(gt=0, le=_ONE)
    """Directive §5 - applied to the **final approved size**, never to the budget."""

    min_liquidity_usd_24h: Decimal = Field(gt=0)
    """Directive §7 - floor per pair, measured on the execution venue (D1)."""

    max_slippage_pct: Decimal = Field(gt=0, le=_ONE)
    max_spread_pct: Decimal = Field(gt=0, le=_ONE)
    min_stop_distance_pct: Decimal = Field(gt=0, le=_ONE)
    max_stop_distance_pct: Decimal = Field(gt=0, le=_ONE)
    """Technical guards inherited from the v1 ``conservative`` preset and kept by
    v2 §2. They are not capital limits and none was proved redundant; changing a
    value is a question for Everton, not a refactor."""

    max_price_age_s: int = Field(gt=0)
    max_book_age_s: int = Field(gt=0)
    max_volume_age_s: int = Field(gt=0)
    max_beta_age_s: int = Field(gt=0)
    """``R-OPS-2``: every input declares its own maximum age, or the freshness of
    the price silently becomes the freshness of the whole decision."""

    max_leverage: Decimal = Field(gt=0)
    """Directive §6 - spot only, so it is 1 and the validator keeps it there."""
    day_timezone: str = Field(min_length=1)
    """Directive §5 - the day of the daily loss."""

    @model_validator(mode="after")
    def _coherent(self) -> RiskLimits:
        if self.risk_per_trade_pct > self.max_aggregate_planned_risk_pct:
            raise ValueError(
                "risk_per_trade_pct must not exceed max_aggregate_planned_risk_pct: one entry "
                "cannot consume more planned risk than the whole portfolio may hold"
            )
        if self.max_asset_exposure_pct > self.max_total_exposure_pct:
            raise ValueError(
                "max_asset_exposure_pct must not exceed max_total_exposure_pct: a per-coin "
                "ceiling above the total ceiling can never bind"
            )
        if self.kill_switch_warning.daily_loss_pct >= self.kill_switch_blocked.daily_loss_pct:
            raise ValueError(
                "kill_switch_warning.daily_loss_pct must be strictly below the blocking one: the "
                "warning has to exist as a state the portfolio can actually be in"
            )
        if self.kill_switch_warning.drawdown_pct >= self.kill_switch_blocked.drawdown_pct:
            raise ValueError(
                "kill_switch_warning.drawdown_pct must be strictly below the blocking one: the "
                "warning has to exist as a state the portfolio can actually be in"
            )
        if self.min_stop_distance_pct >= self.max_stop_distance_pct:
            raise ValueError(
                "min_stop_distance_pct must be strictly below max_stop_distance_pct: an empty "
                "band rejects every signal"
            )
        if self.max_leverage != _ONE:
            raise ValueError(
                "max_leverage must be exactly 1: directive §6 is spot only, with no borrowing"
            )
        return self


PAPER_V1: Final = RiskLimits(
    profile="paper_v1",
    risk_per_trade_pct=Decimal("0.0025"),
    max_aggregate_planned_risk_pct=Decimal("0.01"),
    max_participation_pct=Decimal("0.01"),
    participation_window_s=60,
    max_asset_exposure_pct=Decimal("0.10"),
    max_total_exposure_pct=Decimal("0.40"),
    max_beta_btc_exposure=Decimal("0.50"),
    max_concurrent_positions=5,
    kill_switch_warning=KillSwitchThresholds(
        daily_loss_pct=Decimal("0.01"), drawdown_pct=Decimal("0.04")
    ),
    kill_switch_blocked=KillSwitchThresholds(
        daily_loss_pct=Decimal("0.02"), drawdown_pct=Decimal("0.08")
    ),
    warning_size_multiplier=Decimal("0.5"),
    min_liquidity_usd_24h=Decimal("50000000"),
    max_slippage_pct=Decimal("0.001"),
    max_spread_pct=Decimal("0.0005"),
    min_stop_distance_pct=Decimal("0.003"),
    max_stop_distance_pct=Decimal("0.03"),
    max_price_age_s=10,
    max_book_age_s=10,
    max_volume_age_s=120,
    max_beta_age_s=7200,
    max_leverage=Decimal("1"),
    day_timezone="America/Sao_Paulo",
)
"""The profile of the virtual paper wallet - docs/RISK_ENGINE.md v2 §2. Frozen: a
change here is a decision of Everton's, not a refactor."""
