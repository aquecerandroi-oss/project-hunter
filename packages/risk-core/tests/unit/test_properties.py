"""Properties that must hold for every proposal, not just for the table cases."""

from __future__ import annotations

from decimal import Decimal

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from hunter_core.domain.enums import KillSwitchState
from hunter_risk.evaluate import evaluate
from hunter_risk.kill_switch import KillSwitchInputs
from hunter_risk.limits import PAPER_V1

from .factories import beta, liquidity, portfolio, proposal, spec

pytestmark = pytest.mark.unit

SETTINGS = settings(max_examples=150, deadline=None, suppress_health_check=[HealthCheck.too_slow])

equities = st.decimals(
    min_value=Decimal("2000"), max_value=Decimal("5000000"), places=2, allow_nan=False
)
stop_pcts = st.decimals(min_value=Decimal("0.001"), max_value=Decimal("0.2"), places=4)
minute_volumes = st.decimals(min_value=Decimal("100"), max_value=Decimal("5000000"), places=2)
cash_fractions = st.decimals(min_value=Decimal("0.05"), max_value=Decimal("1"), places=2)


def _decide(
    equity: Decimal,
    stop_pct: Decimal,
    minute_volume: Decimal,
    cash_fraction: Decimal,
    state: KillSwitchState,
):
    entry = Decimal("100")
    return evaluate(
        proposal(stop=(entry * (Decimal(1) - stop_pct)).quantize(Decimal("0.00000001"))),
        portfolio(equity=equity, cash=(equity * cash_fraction).quantize(Decimal("0.01"))),
        PAPER_V1,
        liquidity(last_minute_quote_volume=minute_volume, median_30m_quote_volume=minute_volume),
        KillSwitchInputs(portfolio=state),
        beta(),
        spec=spec(),
    )


@SETTINGS
@given(equities, stop_pcts, minute_volumes, cash_fractions)
def test_the_size_never_exceeds_any_ceiling(
    equity: Decimal, stop_pct: Decimal, minute_volume: Decimal, cash_fraction: Decimal
) -> None:
    got = _decide(equity, stop_pct, minute_volume, cash_fraction, KillSwitchState.ACTIVE)
    assert got.sizing is not None
    for cap in got.sizing.caps:
        if cap.notional is not None:
            assert got.sizing.notional <= cap.notional


@SETTINGS
@given(equities, stop_pcts, minute_volumes, cash_fractions)
def test_the_planned_risk_never_exceeds_the_quarter_percent(
    equity: Decimal, stop_pct: Decimal, minute_volume: Decimal, cash_fraction: Decimal
) -> None:
    got = _decide(equity, stop_pct, minute_volume, cash_fraction, KillSwitchState.ACTIVE)
    assert got.sizing is not None
    assert got.sizing.planned_risk_pct <= PAPER_V1.risk_per_trade_pct


@SETTINGS
@given(equities, stop_pcts, minute_volumes, cash_fractions)
def test_warning_never_produces_a_larger_size_than_active(
    equity: Decimal, stop_pct: Decimal, minute_volume: Decimal, cash_fraction: Decimal
) -> None:
    full = _decide(equity, stop_pct, minute_volume, cash_fraction, KillSwitchState.ACTIVE)
    half = _decide(equity, stop_pct, minute_volume, cash_fraction, KillSwitchState.WARNING)
    assert full.sizing is not None
    assert half.sizing is not None
    assert half.sizing.notional <= full.sizing.notional
    # R-KS-1: whenever the full size was tradable at all, the warning really halves it.
    if full.approved:
        assert half.sizing.notional_after_multiplier == full.sizing.notional_before_multiplier / 2


@SETTINGS
@given(equities, stop_pcts, minute_volumes, cash_fractions)
def test_an_approved_entry_is_always_tradable(
    equity: Decimal, stop_pct: Decimal, minute_volume: Decimal, cash_fraction: Decimal
) -> None:
    got = _decide(equity, stop_pct, minute_volume, cash_fraction, KillSwitchState.ACTIVE)
    if got.approved:
        assert got.sizing is not None
        assert got.sizing.qty > Decimal(0)
        assert got.sizing.notional >= spec().min_notional
        assert got.sizing.qty % spec().step_size == Decimal(0)


@SETTINGS
@given(equities, stop_pcts, minute_volumes, cash_fractions)
def test_the_declared_stop_survives_every_ceiling(
    equity: Decimal, stop_pct: Decimal, minute_volume: Decimal, cash_fraction: Decimal
) -> None:
    entry = Decimal("100")
    expected = (entry * (Decimal(1) - stop_pct)).quantize(Decimal("0.00000001"))
    got = _decide(equity, stop_pct, minute_volume, cash_fraction, KillSwitchState.ACTIVE)
    assert got.sizing is not None
    assert got.sizing.stop == expected
