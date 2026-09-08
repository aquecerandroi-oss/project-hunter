"""``breakout_v1`` — brief T3.33a, EXP-0008.

Every expected number here is exact and written by hand. The series is built so
the Wilder recursion **terminates** in decimal, which is the only way an ATR
measured over a *changing* true range can be asserted without re-implementing
the strategy in the test:

- a wide bar has ``TR = 2.475789056 = 1 + 14**8 / 10**9``; a compressed bar has
  ``TR = 1``. The difference is exactly ``14**8 / 10**9``, so after the eight
  smoothing steps of the compression the ATR is ``1 + 13**8 / 10**9 =
  1.815730721`` — every intermediate value is a terminating decimal;
- the breakout bar true range is ``1.675730721 = 1.815730721 - 14 * 0.01``, so
  the last smoothing step lands on ``1.805730721`` exactly.

Eight compressed bars is the smallest run that moves ``mtr_short`` without
moving ``mtr_long``: the median of the last 32 true ranges still sits on the
wide value while the median of the last 8 sits on the compressed one.

Run: ``uv run pytest packages/core/tests/unit/strategies/test_breakout_v1.py -q``
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

import hunter_core.strategies.breakout_v1 as breakout_module
from hunter_core.domain.enums import Timeframe, TradeDirection
from hunter_core.domain.market import NormalizedCandle
from hunter_core.strategies.base import EvaluationState, StrategyContext, build_context
from hunter_core.strategies.breakout_v1 import BREAKOUT_V1
from hunter_core.strategies.envelope import AssumedCosts

from .conftest import EXCHANGE, ORIGIN, SYMBOL, BarSpec, D, flat, series

pytestmark = pytest.mark.unit

PARAMS: Mapping[str, Any] = BREAKOUT_V1.default_parameters

PREVIOUS = 96
"""``rvol_window`` bars before the breakout bar — the longest lookback."""
SQUEEZED = 8
"""``squeeze_window_bars`` compressed bars, ending at ``t-1``."""

BASE_CLOSE = D("100")
WIDE_HALF = D("1.237894528")
"""Half-range of a wide bar: ``TR = 2.475789056 = 1 + 14**8 / 10**9``."""
COMPRESSED_HALF = D("0.5")
"""Half-range of a compressed bar: ``TR = 1``."""
WIDE_TR = D("2.475789056")
COMPRESSED_TR = D("1")
SIGNAL_TR = D("1.675730721")
"""``1.815730721 - 14 * 0.01``: the last Wilder step lands on a round decimal."""

ATR = D("1.805730721")
REFERENCE = BASE_CLOSE + SIGNAL_TR  # 101.675730721
STOP = D("99.41856731975")  # reference - 1.25 * ATR
TARGET1 = D("106.1900575235")  # reference + 2.50 * ATR
TARGET2 = D("108.898653605")  # reference + 4.00 * ATR
BASE_LOW = BASE_CLOSE - COMPRESSED_HALF  # 99.5
MAX_PREVIOUS_HIGH = BASE_CLOSE + WIDE_HALF  # 101.237894528
SQUEEZE_RATIO = COMPRESSED_TR / WIDE_TR
CUT = ORIGIN + timedelta(minutes=15 * (PREVIOUS + 1))
BASE_VOLUME = D("100")
SIGNAL_VOLUME = D("200")


def wide(close: Decimal = BASE_CLOSE, volume: Decimal = BASE_VOLUME) -> BarSpec:
    return flat(close, WIDE_HALF, volume)


def compressed(close: Decimal = BASE_CLOSE, volume: Decimal = BASE_VOLUME) -> BarSpec:
    return flat(close, COMPRESSED_HALF, volume)


def breakout_bar(
    close: Decimal = BASE_CLOSE, rise: Decimal = SIGNAL_TR, volume: Decimal = SIGNAL_VOLUME
) -> BarSpec:
    """Opens and bottoms at the base close, closes ``rise`` above it (``TR = rise``)."""
    return BarSpec(close, close + rise, close, close + rise, volume)


def build_series(
    *,
    signal: BarSpec | None = None,
    base_close: Decimal = BASE_CLOSE,
    squeezed: int = SQUEEZED,
    volume: Decimal = BASE_VOLUME,
    previous: int = PREVIOUS,
) -> list[NormalizedCandle]:
    specs = [
        *[wide(base_close, volume)] * (previous - squeezed),
        *[compressed(base_close, volume)] * squeezed,
        signal if signal is not None else breakout_bar(base_close),
    ]
    return series(specs, timeframe=Timeframe.M15)


def context(**kwargs: object) -> StrategyContext:
    candles = kwargs.pop("candles", None) or build_series()
    cut = kwargs.pop("cut", None) or CUT
    return build_context(candles, exchange=EXCHANGE, symbol=SYMBOL, source_bar_close=cut, **kwargs)  # pyright: ignore[reportArgumentType]


def variant(**overrides: object) -> Mapping[str, Any]:
    return {**PARAMS, **overrides}


# --------------------------------------------------------------------------- 1. it fires


def test_it_signals_on_the_compressed_breakout() -> None:
    decision = BREAKOUT_V1.evaluate(context(), PARAMS)

    assert decision is not None
    assert decision.direction is TradeDirection.LONG
    assert decision.reference_price == REFERENCE
    assert decision.stop == STOP
    assert decision.target1 == TARGET1
    assert decision.targets_informational == (TARGET2,)
    assert decision.horizon_s == 21600
    assert decision.confidence == D("0.5")


def test_the_geometry_is_asymmetric_two_r_at_the_reference() -> None:
    """1.25 ATR of risk against 2.5 ATR of target: 2 R nominal, not 1 R."""
    decision = BREAKOUT_V1.evaluate(context(), PARAMS)

    assert decision is not None
    risk = decision.reference_price - decision.stop
    assert decision.target1 - decision.reference_price == 2 * risk


def test_the_invalidation_is_the_base_low_strictly_between_stop_and_reference() -> None:
    decision = BREAKOUT_V1.evaluate(context(), PARAMS)

    assert decision is not None
    assert len(decision.invalidations) == 1
    invalidation = decision.invalidations[0]
    assert invalidation.kind == "close_below"
    assert invalidation.level == BASE_LOW
    assert invalidation.timeframe == "15m"
    assert decision.stop < invalidation.level < decision.reference_price


def test_the_envelope_carries_every_number_the_decision_used() -> None:
    decision = BREAKOUT_V1.evaluate(context(), PARAMS)

    assert decision is not None
    envelope = decision.supporting_features
    assert envelope.observation_ts == CUT
    assert envelope.strategy_key == "breakout_v1"
    assert envelope.strategy_version == "v1"
    assert envelope.timeframe == "15m"
    values = {feature.name: feature.value for feature in envelope.features}
    assert values["open_15m"] == BASE_CLOSE
    assert values["high_15m"] == REFERENCE
    assert values["low_15m"] == BASE_CLOSE
    assert values["volume_15m"] == D("200")
    assert values["close_15m"] == REFERENCE
    assert values["max_previous_high_15m"] == MAX_PREVIOUS_HIGH
    assert values["relative_volume_15m"] == D("2")
    assert values["volume_median_15m"] == D("100")
    assert values["mtr_short"] == COMPRESSED_TR
    assert values["mtr_long"] == WIDE_TR
    assert values["squeeze_ratio"] == SQUEEZE_RATIO
    assert values["base_low_15m"] == BASE_LOW
    assert values["atr_pct_15m"] == ATR / REFERENCE
    windows = {feature.name: feature.window for feature in envelope.features}
    assert windows["max_previous_high_15m"] == 20
    assert windows["relative_volume_15m"] == 96
    assert windows["mtr_short"] == 8
    assert windows["mtr_long"] == 32
    assert windows["base_low_15m"] == 8
    assert envelope.atr is not None
    assert envelope.atr.value == ATR
    assert envelope.atr.seed == WIDE_TR
    assert envelope.atr.period == 14
    assert envelope.atr.method == "wilder_v1"
    assert envelope.atr.origin == "rolling_window_v1"
    assert envelope.atr.timeframe == "15m"
    assert envelope.atr.bars_used == 97
    assert envelope.atr.window_start == ORIGIN
    assert envelope.atr.window_end == CUT
    assert envelope.atr.seed_anchor == ORIGIN + timedelta(minutes=15 * 14)
    assert envelope.assumed_costs == AssumedCosts(
        spread_bps=D("2"), slippage_bps=D("5"), fee_bps=D("4"), max_entry_delay_s=120
    )
    assert envelope.confidence_method == "constant_uncalibrated_v1"
    assert envelope.purpose == "research_only"


def test_the_reason_quotes_the_compression_and_is_deterministic() -> None:
    first = BREAKOUT_V1.explain(context(), PARAMS)
    second = BREAKOUT_V1.explain(context(), PARAMS)

    assert first.state is EvaluationState.TRIGGERED
    assert first.reason == "signal"
    assert first.decision is not None and second.decision is not None
    assert first.decision.reason == second.decision.reason
    assert first.decision.reason == (
        "Breakout 15m: fechamento 101.675730721 acima da máxima das 20 máximas "
        "anteriores (101.237894528), após compressão do true range "
        "(mediana de 8 barras / mediana de 32 barras = 0.40), "
        "volume relativo 2.00x da mediana de 96 barras, ATR% 1.78%"
    )


# --------------------------------------------------------------------------- 2. not triggered


@pytest.mark.parametrize(
    ("kwargs", "reason"),
    [
        ({"squeezed": 0}, "not_compressed"),
        ({"signal": breakout_bar(rise=D("1"))}, "no_breakout"),
        ({"signal": breakout_bar(volume=D("100"))}, "rvol_low"),
        ({"base_close": D("20")}, "atr_out_of_range"),
        ({"base_close": D("1000")}, "atr_out_of_range"),
    ],
    ids=["not_compressed", "no_breakout", "rvol_low", "atr_too_high", "atr_too_low"],
)
def test_the_branches_that_do_not_trigger(kwargs: dict[str, Any], reason: str) -> None:
    evaluation = BREAKOUT_V1.explain(context(candles=build_series(**kwargs)), PARAMS)

    assert evaluation.state is EvaluationState.NOT_TRIGGERED
    assert evaluation.reason == reason
    assert evaluation.decision is None


def test_not_compressed_reports_the_ratio_it_measured() -> None:
    evaluation = BREAKOUT_V1.explain(context(candles=build_series(squeezed=0)), PARAMS)

    assert evaluation.reason == "not_compressed"
    assert evaluation.detail == {"squeeze_ratio": "1", "squeeze_max": "0.75"}


def test_a_ratio_exactly_at_the_ceiling_still_fires() -> None:
    """``squeeze_max`` is inclusive: the boundary belongs to the compressed side."""
    at_the_ceiling = variant(squeeze_max=SQUEEZE_RATIO)
    just_below = variant(squeeze_max=SQUEEZE_RATIO - D("0.0000001"))

    assert BREAKOUT_V1.explain(context(), at_the_ceiling).state is EvaluationState.TRIGGERED
    assert BREAKOUT_V1.explain(context(), just_below).reason == "not_compressed"


def test_no_breakout_reports_the_level_it_had_to_clear() -> None:
    evaluation = BREAKOUT_V1.explain(
        context(candles=build_series(signal=breakout_bar(rise=D("1")))), PARAMS
    )

    assert evaluation.detail == {
        "close_15m": "101",
        "max_previous_high_15m": "101.237894528",
    }


def test_the_breakout_level_is_the_highs_not_the_closes() -> None:
    """The difference from ``momentum_v1``: every base bar closes at 100, so a
    rule reading closes would fire on a close of 100.5 — this one does not."""
    over_the_closes = build_series(signal=breakout_bar(rise=D("0.5")))

    assert BREAKOUT_V1.explain(context(candles=over_the_closes), PARAMS).reason == "no_breakout"


def test_an_ineligible_market_is_never_evaluated() -> None:
    evaluation = BREAKOUT_V1.explain(
        context(eligible=False, eligibility_reason="not_monitored"), PARAMS
    )

    assert evaluation.state is EvaluationState.INELIGIBLE
    assert evaluation.reason == "ineligible"
    assert evaluation.detail == {"eligibility_reason": "not_monitored"}


# --------------------------------------------------------------------------- 3. unavailable


def test_a_short_history_is_warmup_not_a_false_condition() -> None:
    """41 bars against a 97-bar window: the history does not reach back far
    enough, which is warm-up — a hole *inside* a reachable window is a gap."""
    short = build_series(previous=40)
    evaluation = BREAKOUT_V1.explain(
        context(candles=short, cut=ORIGIN + timedelta(minutes=15 * 41)), PARAMS
    )

    assert evaluation.state is EvaluationState.UNAVAILABLE
    assert evaluation.reason == "warmup"


def test_one_missing_minute_in_the_middle_makes_the_window_a_gap() -> None:
    candles = build_series()
    missing = candles[len(candles) // 2].open_time
    holed = [candle for candle in candles if candle.open_time != missing]

    evaluation = BREAKOUT_V1.explain(context(candles=holed), PARAMS)

    assert evaluation.state is EvaluationState.UNAVAILABLE
    assert evaluation.reason == "gap"
    assert evaluation.detail["missing_minute"] == missing.isoformat().replace("+00:00", "Z")


@pytest.mark.parametrize("atr_bars", [200, 15], ids=["window_too_long", "indicator_warmup"])
def test_the_atr_reports_its_own_warmup(atr_bars: int) -> None:
    """Two different holes with one name: the ATR window does not reach back far
    enough, or it does and Wilder has not released a reading yet."""
    evaluation = BREAKOUT_V1.explain(context(), variant(atr_bars=atr_bars))

    assert evaluation.state is EvaluationState.UNAVAILABLE
    assert evaluation.reason == "atr_warmup"


def test_a_flat_baseline_has_no_compression_to_measure() -> None:
    """Median true range of the baseline is zero: a ratio would be a division by
    zero dressed as a signal."""
    dead = series(
        [*[flat(BASE_CLOSE, D("0"), D("100"))] * PREVIOUS, breakout_bar()],
        timeframe=Timeframe.M15,
    )

    evaluation = BREAKOUT_V1.explain(context(candles=dead), PARAMS)

    assert evaluation.state is EvaluationState.UNAVAILABLE
    assert evaluation.reason == "squeeze_baseline_unavailable"


def test_a_baseline_without_volume_makes_relative_volume_unavailable() -> None:
    evaluation = BREAKOUT_V1.explain(context(candles=build_series(volume=D("0"))), PARAMS)

    assert evaluation.state is EvaluationState.UNAVAILABLE
    assert evaluation.reason == "rvol_unavailable"
    assert evaluation.detail == {"rvol_window": "96"}


# --------------------------------------------------------------------------- 4. rejected


@pytest.mark.parametrize(
    "override",
    [{"target_atr": D("0")}, {"stop_atr": D("100")}],
    ids=["target_at_the_reference", "stop_below_zero"],
)
def test_a_geometry_that_does_not_close_is_rejected(override: dict[str, Any]) -> None:
    evaluation = BREAKOUT_V1.explain(context(), variant(**override))

    assert evaluation.state is EvaluationState.REJECTED
    assert evaluation.reason == "geometry"
    assert evaluation.decision is None


def test_a_base_wider_than_the_stop_is_rejected_not_silently_accepted() -> None:
    """A breakout bar five points above the base leaves ``base_low`` (99.5) below
    the stop (102.446...): the invalidation would be dead code, so the decision
    is refused — and REJECTED, never NOT_TRIGGERED, so the market cannot re-arm."""
    wide_break = build_series(signal=breakout_bar(rise=D("5")))

    evaluation = BREAKOUT_V1.explain(context(candles=wide_break), PARAMS)

    assert evaluation.state is EvaluationState.REJECTED
    assert evaluation.reason == "geometry_invalidation"
    assert evaluation.detail["base_low_15m"] == "99.5"
    assert Decimal(evaluation.detail["stop"]) > D("99.5")


def test_the_invalidation_guard_is_checked_after_the_geometry() -> None:
    """Both guards fail on the same bar; the order of reasons is the contract."""
    wide_break = build_series(signal=breakout_bar(rise=D("5")))

    evaluation = BREAKOUT_V1.explain(context(candles=wide_break), variant(target_atr=D("0")))

    assert evaluation.reason == "geometry"


# --------------------------------------------------------------------------- 5. purity


def test_evaluate_is_a_pure_function_of_the_context() -> None:
    ctx = context()

    assert BREAKOUT_V1.evaluate(ctx, PARAMS) == BREAKOUT_V1.evaluate(ctx, PARAMS)
    assert BREAKOUT_V1.evaluate(ctx, PARAMS) == BREAKOUT_V1.evaluate(context(), PARAMS)


@pytest.mark.parametrize(
    "forbidden",
    [
        "datetime.now",
        "utcnow",
        "import time",
        "time.time",
        "redis",
        "sqlalchemy",
        "random",
        "open(",
    ],
)
def test_the_module_reads_no_clock_and_does_no_io(forbidden: str) -> None:
    source = Path(breakout_module.__file__).read_text(encoding="utf-8")

    assert forbidden not in source


# --------------------------------------------------------------------------- 6. window budget


def test_the_longest_window_fits_the_shadow_context() -> None:
    """``SHADOW_CONTEXT_MINUTES`` is a worker-wide knob shared by every version;
    a version that needed more would silently cost coverage for all of them."""
    signal_bars = max(
        PARAMS["breakout_highs"] + 1,
        PARAMS["rvol_window"] + 1,
        PARAMS["squeeze_baseline_bars"] + 2,
    )
    signal_minutes = signal_bars * 15
    atr_minutes = PARAMS["atr_bars"] * 15

    assert signal_bars == 97
    assert signal_minutes == 1455
    assert atr_minutes == 1455
    assert max(signal_minutes, atr_minutes) <= 1560


def test_the_declared_identity_is_the_registry_key() -> None:
    assert BREAKOUT_V1.key == "breakout_v1"
    assert BREAKOUT_V1.version == "v1"
    assert BREAKOUT_V1.timeframe is Timeframe.M15
    assert set(PARAMS) == set(BREAKOUT_V1.parameters_schema["required"])
