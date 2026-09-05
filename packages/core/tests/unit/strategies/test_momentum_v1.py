"""``momentum_v1`` — SHADOW-LAB.md "Desenho" and brief S1.

The base series is built so every expected number is exact and written by hand:
96 previous 15m bars closing at 99 with a true range of 2 (so Wilder ATR(14) is
exactly 2), volume 100 each (median 100), and a signal bar closing at 100 with
volume 200. That gives the brief's "1 R nominal at the reference" example:
reference 100, stop 97, target 103.
"""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

import pytest

from hunter_core.domain.enums import Timeframe, TradeDirection
from hunter_core.domain.market import NormalizedCandle
from hunter_core.strategies.base import StrategyContext, build_context
from hunter_core.strategies.envelope import AssumedCosts
from hunter_core.strategies.momentum_v1 import MOMENTUM_V1

from .conftest import EXCHANGE, ORIGIN, SYMBOL, BarSpec, D, flat, series

pytestmark = pytest.mark.unit

PARAMS = MOMENTUM_V1.default_parameters
PREVIOUS = 96
"""``rvol_window`` bars before the signal bar — the longest lookback."""
SIGNAL_BAR = BarSpec(D("99"), D("101"), D("99"), D("100"), D("200"))
CUT = ORIGIN + timedelta(minutes=15 * (PREVIOUS + 1))


def build_series(
    *,
    signal: BarSpec = SIGNAL_BAR,
    previous: BarSpec | None = None,
    bars: int = PREVIOUS,
) -> list[NormalizedCandle]:
    base = previous or flat(D("99"), D("1"), D("100"))
    return series([*[base] * bars, signal], timeframe=Timeframe.M15)


def context(**kwargs: object) -> StrategyContext:
    candles = kwargs.pop("candles", None) or build_series()
    cut = kwargs.pop("cut", None) or CUT
    return build_context(candles, exchange=EXCHANGE, symbol=SYMBOL, source_bar_close=cut, **kwargs)  # pyright: ignore[reportArgumentType]


def test_it_signals_on_the_constructed_setup() -> None:
    decision = MOMENTUM_V1.evaluate(context(), PARAMS)

    assert decision is not None
    assert decision.direction is TradeDirection.LONG
    assert decision.reference_price == D("100")
    assert decision.stop == D("97")
    assert decision.target1 == D("103")
    assert decision.targets_informational == (D("106"), D("109"))
    assert decision.horizon_s == 14400
    assert decision.confidence == D("0.5")


def test_the_target_is_one_nominal_r_at_the_reference() -> None:
    """100 / 97 / 103: stop and target are both 1.5 ATR from the reference price."""
    decision = MOMENTUM_V1.evaluate(context(), PARAMS)

    assert decision is not None
    risk = decision.reference_price - decision.stop
    assert decision.target1 - decision.reference_price == risk


def test_the_invalidation_is_the_breakout_level_not_the_stop() -> None:
    decision = MOMENTUM_V1.evaluate(context(), PARAMS)

    assert decision is not None
    assert len(decision.invalidations) == 1
    invalidation = decision.invalidations[0]
    assert invalidation.kind == "close_below"
    assert invalidation.level == D("99")  # max of the previous 20 closes
    assert invalidation.timeframe == "15m"


def test_the_envelope_carries_the_computed_values_and_the_atr_seed() -> None:
    decision = MOMENTUM_V1.evaluate(context(), PARAMS)

    assert decision is not None
    envelope = decision.supporting_features
    assert envelope.observation_ts == CUT
    assert envelope.strategy_key == "momentum_v1"
    assert envelope.timeframe == "15m"
    assert envelope.eligible is True
    values = {feature.name: feature.value for feature in envelope.features}
    assert values["close_15m"] == D("100")
    assert values["max_previous_close_15m"] == D("99")
    assert values["return_15m"] == D("100") / D("99") - 1
    assert values["relative_volume_15m"] == D("2")
    assert values["atr_pct_15m"] == D("0.02")
    assert envelope.atr is not None
    assert envelope.atr.value == D("2")
    assert envelope.atr.seed == D("2")
    assert envelope.atr.period == 14
    assert envelope.atr.method == "wilder_v1"
    assert envelope.atr.seed_anchor == ORIGIN + timedelta(minutes=15 * 14)
    assert envelope.atr.window_end == CUT
    assert envelope.assumed_costs == AssumedCosts(
        spread_bps=D("2"), slippage_bps=D("5"), fee_bps=D("4"), max_entry_delay_s=120
    )
    assert envelope.confidence_method == "constant_uncalibrated_v1"
    assert envelope.atr.origin == "rolling_window_v1"
    assert envelope.atr.window_start == ORIGIN
    assert envelope.atr.bars_used == 97


def test_the_reason_is_deterministic_and_quotes_the_numbers() -> None:
    first = MOMENTUM_V1.evaluate(context(), PARAMS)
    second = MOMENTUM_V1.evaluate(context(), PARAMS)

    assert first is not None and second is not None
    assert first.reason == second.reason
    assert first.reason == (
        "Momentum 15m: fechamento 100 acima da máxima dos 20 fechamentos anteriores (99), "
        "retorno 15m 1.01%, volume relativo 2.00x da mediana de 96 barras, ATR% 2.00%"
    )


# --------------------------------------------------------------- each condition, in isolation


def test_no_breakout_when_the_close_does_not_clear_the_lookback_high() -> None:
    signal = BarSpec(D("99"), D("101"), D("99"), D("99"), D("200"))
    evaluation = MOMENTUM_V1.explain(context(candles=build_series(signal=signal)), PARAMS)

    assert evaluation.decision is None
    assert evaluation.reason == "no_breakout"
    assert evaluation.detail == {"close_15m": "99", "max_previous_close_15m": "99"}


def test_a_positive_15m_return_is_implied_by_the_breakout() -> None:
    """With ``lookback_closes >= 1`` the previous close is inside the lookback,
    so ``close > max(previous closes)`` already implies ``return_15m > 0``. The
    guard from the spec is kept and asserted, never silently dropped."""
    decision = MOMENTUM_V1.evaluate(context(), PARAMS)

    assert decision is not None
    values = {feature.name: feature.value for feature in decision.supporting_features.features}
    assert isinstance(values["return_15m"], Decimal)
    assert values["return_15m"] > 0


def test_relative_volume_below_the_floor_blocks_the_signal() -> None:
    signal = BarSpec(D("99"), D("101"), D("99"), D("100"), D("149"))
    evaluation = MOMENTUM_V1.explain(context(candles=build_series(signal=signal)), PARAMS)

    assert evaluation.decision is None
    assert evaluation.reason == "rvol_low"
    assert evaluation.detail["relative_volume_15m"] == "1.49"


def test_relative_volume_exactly_at_the_floor_signals() -> None:
    signal = BarSpec(D("99"), D("101"), D("99"), D("100"), D("150"))
    assert MOMENTUM_V1.evaluate(context(candles=build_series(signal=signal)), PARAMS) is not None


def test_a_zero_volume_baseline_leaves_relative_volume_unavailable() -> None:
    quiet = BarSpec(D("99"), D("100"), D("98"), D("99"), D("0"))
    evaluation = MOMENTUM_V1.explain(context(candles=build_series(previous=quiet)), PARAMS)

    assert evaluation.decision is None
    assert evaluation.reason == "rvol_unavailable"


def test_volatility_below_the_floor_blocks_the_signal() -> None:
    """ATR 0.02 on a close of 99.005 is 0.0202% — under ``atr_pct_min`` (0.3%)."""
    calm = flat(D("99"), D("0.01"), D("100"))
    signal = BarSpec(D("99"), D("99.01"), D("98.99"), D("99.005"), D("200"))
    evaluation = MOMENTUM_V1.explain(
        context(candles=build_series(previous=calm, signal=signal)), PARAMS
    )

    assert evaluation.decision is None
    assert evaluation.reason == "atr_out_of_range"
    assert evaluation.detail["atr_pct_15m"] == "0.0002020099994949750012625624968"  # 0.02/99.005


def test_volatility_above_the_ceiling_blocks_the_signal() -> None:
    """ATR 20 on a ~100 close is 20% — over ``atr_pct_max`` (5%)."""
    wild = flat(D("99"), D("10"), D("100"))
    signal = BarSpec(D("99"), D("109"), D("89"), D("100"), D("200"))
    evaluation = MOMENTUM_V1.explain(
        context(candles=build_series(previous=wild, signal=signal)), PARAMS
    )

    assert evaluation.decision is None
    assert evaluation.reason == "atr_out_of_range"


@pytest.mark.parametrize(
    ("previous", "signal", "atr_pct"),
    [
        # every true range is 0.3 -> ATR 0.3 on a close of 100 = exactly atr_pct_min
        (
            flat(D("99.9"), D("0.15"), D("100")),
            BarSpec(D("99.9"), D("100.1"), D("99.8"), D("100"), D("200")),
            "0.003",
        ),
        # every true range is 5 -> ATR 5 on a close of 100 = exactly atr_pct_max
        (
            flat(D("99"), D("2.5"), D("100")),
            BarSpec(D("99"), D("101.5"), D("96.5"), D("100"), D("200")),
            "0.05",
        ),
    ],
)
def test_the_volatility_band_is_inclusive_at_both_ends(
    previous: BarSpec, signal: BarSpec, atr_pct: str
) -> None:
    candles = build_series(previous=previous, signal=signal)

    decision = MOMENTUM_V1.evaluate(context(candles=candles), PARAMS)

    assert decision is not None
    values = {feature.name: feature.value for feature in decision.supporting_features.features}
    assert values["atr_pct_15m"] == D(atr_pct)


# --------------------------------------------------------------- data availability


def test_insufficient_warmup_returns_none_with_reason_warmup() -> None:
    candles = build_series(bars=PREVIOUS - 1)
    cut = ORIGIN + timedelta(minutes=15 * PREVIOUS)

    evaluation = MOMENTUM_V1.explain(context(candles=candles, cut=cut), PARAMS)

    assert evaluation.decision is None
    assert evaluation.reason == "warmup"


def test_a_missing_minute_makes_the_window_unavailable_never_shorter() -> None:
    candles = build_series()
    del candles[500]

    evaluation = MOMENTUM_V1.explain(context(candles=candles), PARAMS)

    assert evaluation.decision is None
    assert evaluation.reason == "gap"
    assert evaluation.detail["missing_minute"] == "2026-01-01T08:20:00Z"


def test_the_reference_bar_missing_its_last_minute_never_signals() -> None:
    """A 14-minute "15m bar" would have a different close, high and volume."""
    candles = build_series()
    del candles[-1]

    evaluation = MOMENTUM_V1.explain(context(candles=candles), PARAMS)

    assert evaluation.decision is None
    assert evaluation.reason == "gap"
    assert evaluation.state.value == "unavailable"


def test_an_ineligible_market_is_not_evaluated() -> None:
    evaluation = MOMENTUM_V1.explain(
        context(eligible=False, eligibility_reason="not_in_universe"), PARAMS
    )

    assert evaluation.decision is None
    assert evaluation.reason == "ineligible"
    assert evaluation.detail == {"eligibility_reason": "not_in_universe"}


def test_a_close_that_is_not_a_15m_boundary_is_misaligned() -> None:
    evaluation = MOMENTUM_V1.explain(context(cut=CUT - timedelta(minutes=5)), PARAMS)

    assert evaluation.decision is None
    assert evaluation.reason == "misaligned"


def test_a_degenerate_target_is_refused_by_geometry() -> None:
    """With a positive ATR the geometry always holds, so the guard is only
    reachable through the parameters; it stays because the entry revalidates the
    frozen levels against the real entry price (SHADOW-LAB.md §3)."""
    evaluation = MOMENTUM_V1.explain(context(), {**PARAMS, "target_atr": D("0")})

    assert evaluation.decision is None
    assert evaluation.reason == "geometry"
    assert evaluation.state.value == "rejected"


# --------------------------------------------------------------- frozen identity


def test_default_parameters_are_the_frozen_contract() -> None:
    assert dict(PARAMS) == {
        "lookback_closes": 20,
        "rvol_window": 96,
        "rvol_min": D("1.5"),
        "atr_period": 14,
        "atr_timeframe": "15m",
        "atr_bars": 97,
        "atr_pct_min": D("0.003"),
        "atr_pct_max": D("0.05"),
        "return_min": D("0"),
        "stop_atr": D("1.5"),
        "target_atr": D("1.5"),
        "target2_atr": D("3"),
        "target3_atr": D("4.5"),
        "horizon_s": 14400,
        "base_confidence": D("0.5"),
        "assumed_spread_bps": D("2"),
        "slippage_bps": D("5"),
        "fee_bps": D("4"),
        "max_entry_delay_s": 120,
    }
