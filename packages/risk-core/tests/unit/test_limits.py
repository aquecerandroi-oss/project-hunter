"""RiskLimits: the frozen paper_v1 profile and the coherence it refuses to break."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

import pytest
from pydantic import ValidationError

from hunter_risk.limits import PAPER_V1, RiskLimits

pytestmark = pytest.mark.unit


def _with(**over: Any) -> RiskLimits:
    return RiskLimits.model_validate(PAPER_V1.model_dump() | over)


def test_paper_v1_carries_exactly_the_numbers_of_the_directive() -> None:
    assert PAPER_V1.profile == "paper_v1"
    assert PAPER_V1.risk_per_trade_pct == Decimal("0.0025")
    assert PAPER_V1.max_aggregate_planned_risk_pct == Decimal("0.01")
    assert PAPER_V1.max_participation_pct == Decimal("0.01")
    assert PAPER_V1.max_asset_exposure_pct == Decimal("0.10")
    assert PAPER_V1.max_total_exposure_pct == Decimal("0.40")
    assert PAPER_V1.max_beta_btc_exposure == Decimal("0.50")
    assert PAPER_V1.max_concurrent_positions == 5
    assert PAPER_V1.kill_switch_warning.daily_loss_pct == Decimal("0.01")
    assert PAPER_V1.kill_switch_warning.drawdown_pct == Decimal("0.04")
    assert PAPER_V1.kill_switch_blocked.daily_loss_pct == Decimal("0.02")
    assert PAPER_V1.kill_switch_blocked.drawdown_pct == Decimal("0.08")
    assert PAPER_V1.warning_size_multiplier == Decimal("0.5")
    assert PAPER_V1.min_liquidity_usd_24h == Decimal("50000000")
    assert PAPER_V1.max_leverage == Decimal("1")
    assert PAPER_V1.day_timezone == "America/Sao_Paulo"


def test_the_technical_guards_are_the_conservative_preset_of_the_v1_contract() -> None:
    # docs/RISK_ENGINE.md v2 §2: "guardas técnicas, não limites de capital",
    # herdadas do preset conservador. Nada aqui foi inventado por T3.1.
    assert PAPER_V1.max_spread_pct == Decimal("0.0005")
    assert PAPER_V1.max_slippage_pct == Decimal("0.001")
    assert PAPER_V1.min_stop_distance_pct == Decimal("0.003")
    assert PAPER_V1.max_stop_distance_pct == Decimal("0.03")


def test_paper_v1_is_frozen() -> None:
    with pytest.raises(ValidationError):
        PAPER_V1.risk_per_trade_pct = Decimal("0.01")  # type: ignore[misc]


def test_per_asset_ceiling_may_not_exceed_the_total_ceiling() -> None:
    with pytest.raises(ValidationError, match="max_asset_exposure_pct"):
        _with(max_asset_exposure_pct=Decimal("0.50"))


def test_risk_per_trade_may_not_exceed_the_aggregate_risk_budget() -> None:
    with pytest.raises(ValidationError, match="risk_per_trade_pct"):
        _with(risk_per_trade_pct=Decimal("0.02"))


def test_warning_threshold_must_be_below_the_blocking_threshold() -> None:
    with pytest.raises(ValidationError, match="daily_loss_pct"):
        _with(kill_switch_warning={"daily_loss_pct": "0.02", "drawdown_pct": "0.04"})
    with pytest.raises(ValidationError, match="drawdown_pct"):
        _with(kill_switch_warning={"daily_loss_pct": "0.01", "drawdown_pct": "0.09"})


def test_an_empty_stop_distance_band_is_refused() -> None:
    with pytest.raises(ValidationError, match="min_stop_distance_pct"):
        _with(min_stop_distance_pct=Decimal("0.05"))


def test_leverage_is_always_one_because_this_is_spot_only() -> None:
    with pytest.raises(ValidationError, match="max_leverage"):
        _with(max_leverage=Decimal("2"))


def test_a_float_never_becomes_a_limit() -> None:
    with pytest.raises((ValidationError, TypeError), match="float"):
        _with(risk_per_trade_pct=0.0025)


def test_at_least_one_position_slot() -> None:
    with pytest.raises(ValidationError):
        _with(max_concurrent_positions=0)
