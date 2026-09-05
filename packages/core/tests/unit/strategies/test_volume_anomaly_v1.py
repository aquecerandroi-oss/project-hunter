"""``volume_anomaly_v1`` — SHADOW-LAB.md "Desenho" and brief S1.

Base series: 291 previous 5m bars closing at 100 (high 100.5, low 99.5, volume
10), then a signal bar with four times the median volume closing above its own
midpoint. Every previous 15m bar is therefore (100, 100.5, 99.5, 100), so the
Wilder ATR(14) on 15m is exactly 1 and ATR% exactly 1%.

The signal bar is the **first** 5m bar of a new 15m bucket on purpose: the ATR
window has to end at the last *completed* 15m close (00:15 earlier), never
reaching into the bucket the signal is still forming.
"""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

import pytest

from hunter_core.domain.enums import Timeframe, TradeDirection
from hunter_core.domain.market import NormalizedCandle
from hunter_core.strategies.base import StrategyContext, build_context
from hunter_core.strategies.envelope import AssumedCosts
from hunter_core.strategies.volume_anomaly_v1 import VOLUME_ANOMALY_V1

from .conftest import EXCHANGE, ORIGIN, SYMBOL, BarSpec, D, flat, series

pytestmark = pytest.mark.unit

PARAMS = VOLUME_ANOMALY_V1.default_parameters
PREVIOUS = 291
"""288 bars for the volume median plus the 3 that complete the last 15m bucket."""
QUIET = flat(D("100"), D("0.5"), D("10"))
SIGNAL_BAR = BarSpec(D("100"), D("100.6"), D("99.8"), D("100.4"), D("40"))
CUT = ORIGIN + timedelta(minutes=5 * (PREVIOUS + 1))
ATR_END = ORIGIN + timedelta(minutes=1455)
"""Last completed 15m close at or before the cut (the cut itself is 00:20 later)."""


def build_series(
    *,
    signal: BarSpec = SIGNAL_BAR,
    previous: BarSpec = QUIET,
    bars: int = PREVIOUS,
    origin: object = ORIGIN,
) -> list[NormalizedCandle]:
    return series(
        [*[previous] * bars, signal],
        timeframe=Timeframe.M5,
        origin=origin,  # pyright: ignore[reportArgumentType]
    )


def context(**kwargs: object) -> StrategyContext:
    candles = kwargs.pop("candles", None) or build_series()
    cut = kwargs.pop("cut", None) or CUT
    return build_context(candles, exchange=EXCHANGE, symbol=SYMBOL, source_bar_close=cut, **kwargs)  # pyright: ignore[reportArgumentType]


def test_it_signals_on_the_constructed_setup() -> None:
    decision = VOLUME_ANOMALY_V1.evaluate(context(), PARAMS)

    assert decision is not None
    assert decision.direction is TradeDirection.LONG
    assert decision.reference_price == D("100.4")
    assert decision.stop == D("99.8")  # the low of the signal bar
    assert decision.target1 == D("101.9")  # close + 1.5 * ATR(1)
    assert decision.targets_informational == ()
    assert decision.horizon_s == 7200
    assert decision.confidence == D("0.5")


def test_the_invalidation_is_the_midpoint_of_the_signal_bar() -> None:
    decision = VOLUME_ANOMALY_V1.evaluate(context(), PARAMS)

    assert decision is not None
    assert len(decision.invalidations) == 1
    invalidation = decision.invalidations[0]
    assert invalidation.kind == "close_below"
    assert invalidation.level == D("100.2")  # (100.6 + 99.8) / 2
    assert invalidation.timeframe == "5m"


def test_the_atr_window_ends_at_the_last_completed_15m_close() -> None:
    """The signal bar opens a 15m bucket that is still forming: reaching into it
    would be look-ahead, and flooring the cut to 15m is what avoids it."""
    decision = VOLUME_ANOMALY_V1.evaluate(context(), PARAMS)

    assert decision is not None
    atr = decision.supporting_features.atr
    assert atr is not None
    assert atr.timeframe == "15m"
    assert atr.window_end == ATR_END
    assert atr.window_end < CUT
    assert atr.window_start == ORIGIN
    assert atr.value == D("1")
    assert atr.percent == D("0.01")
    assert atr.seed == D("1")
    assert atr.bars_used == 97
    assert atr.method == "wilder_v1"
    assert atr.origin == "rolling_window_v1"


def test_the_envelope_carries_the_computed_values() -> None:
    decision = VOLUME_ANOMALY_V1.evaluate(context(), PARAMS)

    assert decision is not None
    envelope = decision.supporting_features
    assert envelope.observation_ts == CUT
    assert envelope.strategy_key == "volume_anomaly_v1"
    assert envelope.timeframe == "5m"
    values = {feature.name: feature.value for feature in envelope.features}
    assert values["close_5m"] == D("100.4")
    assert values["volume_5m"] == D("40")
    assert values["volume_median_5m"] == D("10")
    assert values["volume_ratio_5m"] == D("4")
    assert values["bar_mid_5m"] == D("100.2")
    assert values["return_5m"] == D("0.004")
    assert values["atr_pct_15m"] == D("0.01")
    assert envelope.assumed_costs == AssumedCosts(
        spread_bps=D("2"), slippage_bps=D("5"), fee_bps=D("4"), max_entry_delay_s=120
    )


def test_the_reason_is_deterministic_and_quotes_the_numbers() -> None:
    first = VOLUME_ANOMALY_V1.evaluate(context(), PARAMS)
    second = VOLUME_ANOMALY_V1.evaluate(context(), PARAMS)

    assert first is not None and second is not None
    assert first.reason == second.reason
    assert first.reason == (
        "Volume anomaly 5m: volume 40 é 4.00x a mediana das 288 barras anteriores, "
        "fechamento 100.4 acima do meio da barra (100.2), retorno 5m 0.40% dentro do "
        "teto de 2.00% (2x ATR% de 15m)"
    )


# --------------------------------------------------------------- each condition, in isolation


def test_volume_below_the_multiple_blocks_the_signal() -> None:
    signal = BarSpec(D("100"), D("100.6"), D("99.8"), D("100.4"), D("39"))
    evaluation = VOLUME_ANOMALY_V1.explain(context(candles=build_series(signal=signal)), PARAMS)

    assert evaluation.decision is None
    assert evaluation.reason == "volume_below_threshold"
    assert evaluation.detail["volume_ratio_5m"] == "3.9"


def test_volume_exactly_at_the_multiple_signals() -> None:
    assert VOLUME_ANOMALY_V1.evaluate(context(), PARAMS) is not None


def test_a_close_at_or_below_the_midpoint_blocks_the_signal() -> None:
    signal = BarSpec(D("100"), D("100.6"), D("99.8"), D("100.2"), D("40"))
    evaluation = VOLUME_ANOMALY_V1.explain(context(candles=build_series(signal=signal)), PARAMS)

    assert evaluation.decision is None
    assert evaluation.reason == "close_below_mid"
    assert evaluation.detail == {"close_5m": "100.2", "bar_mid_5m": "100.2"}


def test_a_return_above_two_atr_percent_blocks_the_signal() -> None:
    signal = BarSpec(D("100"), D("103.2"), D("99.8"), D("103"), D("40"))
    evaluation = VOLUME_ANOMALY_V1.explain(context(candles=build_series(signal=signal)), PARAMS)

    assert evaluation.decision is None
    assert evaluation.reason == "return_out_of_range"
    assert evaluation.detail == {"return_5m": "0.03", "return_max_5m": "0.02"}


def test_a_negative_return_blocks_the_signal() -> None:
    signal = BarSpec(D("100"), D("100"), D("99"), D("99.9"), D("40"))
    evaluation = VOLUME_ANOMALY_V1.explain(context(candles=build_series(signal=signal)), PARAMS)

    assert evaluation.decision is None
    assert evaluation.reason == "return_out_of_range"
    assert evaluation.detail["return_5m"] == "-0.001"


@pytest.mark.parametrize(
    ("signal", "expected_return"),
    [
        # exactly return_min: closes flat on the previous close, still above its mid
        (BarSpec(D("100"), D("100"), D("99.6"), D("100"), D("40")), D("0")),
        # exactly return_max_atr * atr_pct = 2 * 1% = 2%
        (BarSpec(D("100"), D("102"), D("99.8"), D("102"), D("40")), D("0.02")),
    ],
    ids=["return_min", "return_max"],
)
def test_the_return_band_is_inclusive_at_both_ends(
    signal: BarSpec, expected_return: Decimal
) -> None:
    decision = VOLUME_ANOMALY_V1.evaluate(context(candles=build_series(signal=signal)), PARAMS)

    assert decision is not None
    values = {feature.name: feature.value for feature in decision.supporting_features.features}
    assert values["return_5m"] == expected_return


def test_a_zero_volume_baseline_leaves_the_ratio_unavailable() -> None:
    evaluation = VOLUME_ANOMALY_V1.explain(
        context(candles=build_series(previous=flat(D("100"), D("0.5"), D("0")))), PARAMS
    )

    assert evaluation.decision is None
    assert evaluation.reason == "volume_baseline_unavailable"


# --------------------------------------------------------------- data availability


def test_insufficient_warmup_returns_none_with_reason_warmup() -> None:
    candles = build_series(bars=200)
    cut = ORIGIN + timedelta(minutes=5 * 201)

    evaluation = VOLUME_ANOMALY_V1.explain(context(candles=candles, cut=cut), PARAMS)

    assert evaluation.decision is None
    assert evaluation.reason == "warmup"


def test_the_atr_window_has_its_own_warmup_reason() -> None:
    """The 5m window is complete but the 15m ATR window is not: the two windows
    are requested separately and fail separately."""
    candles = build_series(bars=288, origin=ORIGIN + timedelta(minutes=15))

    evaluation = VOLUME_ANOMALY_V1.explain(context(candles=candles), PARAMS)

    assert evaluation.decision is None
    assert evaluation.reason == "atr_warmup"


def test_a_missing_minute_makes_the_window_unavailable() -> None:
    candles = build_series()
    del candles[1000]

    evaluation = VOLUME_ANOMALY_V1.explain(context(candles=candles), PARAMS)

    assert evaluation.decision is None
    assert evaluation.reason == "gap"
    assert evaluation.detail["missing_minute"] == "2026-01-01T16:40:00Z"


def test_an_ineligible_market_is_not_evaluated() -> None:
    evaluation = VOLUME_ANOMALY_V1.explain(
        context(eligible=False, eligibility_reason="not_in_universe"), PARAMS
    )

    assert evaluation.decision is None
    assert evaluation.reason == "ineligible"


def test_a_close_that_is_not_a_5m_boundary_is_misaligned() -> None:
    evaluation = VOLUME_ANOMALY_V1.explain(context(cut=CUT - timedelta(minutes=2)), PARAMS)

    assert evaluation.decision is None
    assert evaluation.reason == "misaligned"


def test_a_degenerate_target_is_refused_by_geometry() -> None:
    """``close > (high+low)/2`` already implies ``low < close``, so the stop is
    below the reference for every bar that can fire. The geometry guard is
    therefore only reachable through the parameters — proven here with a zero
    target distance, and kept because the levels are revalidated at the entry."""
    evaluation = VOLUME_ANOMALY_V1.explain(context(), {**PARAMS, "target_atr": D("0")})

    assert evaluation.decision is None
    assert evaluation.reason == "geometry"
    assert evaluation.state.value == "rejected"


# --------------------------------------------------------------- frozen identity


def test_default_parameters_are_the_frozen_contract() -> None:
    assert dict(PARAMS) == {
        "volume_window": 288,
        "volume_mult": D("4"),
        "atr_period": 14,
        "atr_timeframe": "15m",
        "atr_bars": 97,
        "return_min": D("0"),
        "return_max_atr": D("2"),
        "target_atr": D("1.5"),
        "horizon_s": 7200,
        "base_confidence": D("0.5"),
        "assumed_spread_bps": D("2"),
        "slippage_bps": D("5"),
        "fee_bps": D("4"),
        "max_entry_delay_s": 120,
    }
