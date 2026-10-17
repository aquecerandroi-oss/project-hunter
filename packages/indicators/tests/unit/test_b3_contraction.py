"""H-041 contraction breakout on the WIN (``hunter_indicators.b3.contraction``) — synthetic fixtures.

Session Monday 04/03/2024: OPEN = 10:00 BRT = 13:00Z. Flat price 120000; a 1-minute bar of
"amplitude a" spans [p − a/2, p + a/2], so a 5-minute bar of such bars has range a and
``A = a / 120000 × 10 000`` bp.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from fractions import Fraction

import pytest

from hunter_indicators.b3.bars import Bar
from hunter_indicators.b3.contract import Side
from hunter_indicators.b3.contraction import (
    CONTRACTION_DEFINITION,
    CONTRACTION_V1,
    amplitude_profile,
    baseline,
    scan_contraction,
)
from hunter_indicators.b3.intraday_plan import IntradayWindow, NoPlan, TradePlan

pytestmark = pytest.mark.unit

OPEN = datetime(2024, 3, 4, 13, 0, tzinfo=UTC)
WINDOW = IntradayWindow(date(2024, 3, 4), open_at=OPEN, exit_at=OPEN + timedelta(minutes=390))
P = 120000


def amp_bar(minute: int, amplitude: int, close: int = P) -> Bar:
    half = amplitude // 2
    return Bar(
        OPEN + timedelta(minutes=minute),
        1,
        Decimal(P),
        Decimal(max(P + half, close)),
        Decimal(min(P - half, close)),
        Decimal(close),
    )


def quiet_session(amplitude: int = 40, overrides: dict[int, Bar] | None = None) -> list[Bar]:
    bars = {m: amp_bar(m, amplitude) for m in range(390)}
    bars.update(overrides or {})
    return [bars[m] for m in sorted(bars)]


def past_profiles(n: int = 20, amplitude: int = 40) -> list[dict[int, Fraction]]:
    profile = amplitude_profile(quiet_session(amplitude), WINDOW, CONTRACTION_V1)
    return [dict(profile) for _ in range(n)]


def breakout_session(close: int = P + 100, quiet: int = 10) -> list[Bar]:
    """Window bars 0..5 (minutes 0..29) quiet; decision bar 6 (minutes 30..34) closes at ``close``."""
    return quiet_session(quiet, {34: amp_bar(34, quiet, close)})


def test_frozen_parameters_and_feature_definition() -> None:
    p = CONTRACTION_V1
    assert p.version == "contraction_win/1"
    assert (p.bar_minutes, p.window_bars, p.theta, p.target_r) == (
        5,
        6,
        Decimal("0.6"),
        Decimal("2"),
    )
    assert (p.baseline_sessions, p.baseline_min) == (20, 15)
    assert CONTRACTION_DEFINITION.key == "win_range_contraction_5m"
    assert CONTRACTION_DEFINITION.version == 1


def test_amplitude_profile_is_mean_relative_range_of_the_window_in_bp() -> None:
    profile = amplitude_profile(quiet_session(40), WINDOW, CONTRACTION_V1)
    assert profile[6] == Fraction(40, P) * 10000  # exact, no rounding
    assert min(profile) == 6  # first decision bar j = k
    assert max(profile) == 47  # bar 47 ends 14:00 BRT (OPEN + 240 min)


def test_baseline_is_the_median_of_the_last_twenty_and_needs_fifteen() -> None:
    old = [{6: Fraction(1000)}] * 5
    recent = [{6: Fraction(v)} for v in range(1, 21)]
    assert baseline(old + recent, 6, CONTRACTION_V1) == Fraction(21, 2)
    holes: list[dict[int, Fraction]] = [{6: Fraction(3)}] * 14 + [{}] * 6
    assert baseline(holes, 6, CONTRACTION_V1) is None
    assert baseline(holes[:-1] + [{6: Fraction(3)}], 6, CONTRACTION_V1) == Fraction(3)


def test_compressed_window_and_upside_close_buys() -> None:
    plan = scan_contraction(breakout_session(), WINDOW, past_profiles(), CONTRACTION_V1)
    assert isinstance(plan, TradePlan)
    assert plan.side is Side.BUY
    assert plan.decided_at == OPEN + timedelta(minutes=35)
    assert plan.stop_level == Decimal(P - 5)  # window low
    assert plan.target_r == Decimal("2")
    assert plan.exit_at == WINDOW.exit_at
    assert Decimal(plan.supporting_features["contraction"]) == Decimal("0.25")


def test_downside_close_sells_with_stop_at_the_window_high() -> None:
    plan = scan_contraction(
        breakout_session(close=P - 100), WINDOW, past_profiles(), CONTRACTION_V1
    )
    assert isinstance(plan, TradePlan) and plan.side is Side.SELL
    assert plan.stop_level == Decimal(P + 5)


def test_no_contraction_means_no_trade_even_with_a_breakout() -> None:
    bars = quiet_session(40, {34: amp_bar(34, 40, P + 100)})
    assert scan_contraction(bars, WINDOW, past_profiles(), CONTRACTION_V1) == NoPlan(
        WINDOW.trading_date, "no_signal"
    )


def test_theta_is_inclusive() -> None:
    # quiet 24 against a baseline of 40 → c = 0.6 exactly (exact rationals, no tolerance)
    plan = scan_contraction(breakout_session(quiet=24), WINDOW, past_profiles(), CONTRACTION_V1)
    assert isinstance(plan, TradePlan)
    # a wider quiet window (26 → c = 0.65) is outside θ
    above = scan_contraction(breakout_session(quiet=26), WINDOW, past_profiles(), CONTRACTION_V1)
    assert above == NoPlan(WINDOW.trading_date, "no_signal")


def test_the_breakout_bar_is_outside_the_window() -> None:
    # a wide breakout bar would lift A above θ·B if it were inside the window
    wide = amp_bar(34, 2000, P + 1000)
    plan = scan_contraction(quiet_session(10, {34: wide}), WINDOW, past_profiles(), CONTRACTION_V1)
    assert isinstance(plan, TradePlan) and plan.side is Side.BUY


def test_without_baseline_there_is_no_decision() -> None:
    plan = scan_contraction(breakout_session(), WINDOW, past_profiles(14), CONTRACTION_V1)
    assert plan == NoPlan(WINDOW.trading_date, "no_baseline")


def test_an_empty_window_bar_blocks_the_decision() -> None:
    bars = [b for b in breakout_session() if not 10 <= (b.start - OPEN).total_seconds() / 60 < 15]
    plan = scan_contraction(bars, WINDOW, past_profiles(), CONTRACTION_V1)
    assert not (isinstance(plan, TradePlan) and plan.decided_at == OPEN + timedelta(minutes=35))


def test_neighbour_window_lengths_move_the_first_decision() -> None:
    for k, first in ((4, 25), (9, 50)):
        params = replace(CONTRACTION_V1, version=f"contraction_win/1@k{k}", window_bars=k)
        profiles = [amplitude_profile(quiet_session(40), WINDOW, params)] * 20
        bars = quiet_session(10, {first - 1: amp_bar(first - 1, 10, P + 100)})
        plan = scan_contraction(bars, WINDOW, profiles, params)
        assert isinstance(plan, TradePlan) and plan.decided_at == OPEN + timedelta(minutes=first)


def test_changing_bars_after_the_decision_never_changes_it() -> None:
    base = breakout_session()
    plan = scan_contraction(base, WINDOW, past_profiles(), CONTRACTION_V1)
    assert isinstance(plan, TradePlan)
    future = [
        b
        if b.end <= plan.decided_at
        else amp_bar(int((b.start - OPEN).total_seconds() // 60), 3000)
        for b in base
    ]
    assert scan_contraction(future, WINDOW, past_profiles(), CONTRACTION_V1) == plan
