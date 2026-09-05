"""Anti-look-ahead and reproducibility, for both v1 strategies.

Four properties, each of which a leak would break:

1. **Invariance to the future.** Adding candles after ``source_bar_close`` — with
   absurd prices and volumes — cannot change the decision.
2. **Invariance to the candle still forming.** A non-final candle, whatever it
   says, cannot change the decision.
3. **Bootstrap == continuous.** A context assembled once from a long history and
   a context grown bar by bar produce identical decisions at the same reference
   close (the rolling ATR window is what makes this true, and this is the test
   that would fail if a calculator started depending on how much history it was
   handed).
4. **Decision identity.** The same context evaluated twice yields byte-identical
   canonical envelopes: nothing in a decision comes from the clock or the run, so
   a replay cohort and a prospective cohort cannot disagree about the same bar.
"""

from __future__ import annotations

from datetime import timedelta
from decimal import ROUND_DOWN, ROUND_HALF_EVEN, ROUND_UP, Decimal, localcontext

import pytest

from hunter_core.domain.enums import Timeframe
from hunter_core.domain.market import NormalizedCandle
from hunter_core.strategies.base import Decision, StrategyContext, build_context
from hunter_core.strategies.canonical import canonical_json
from hunter_core.strategies.momentum_v1 import MOMENTUM_V1
from hunter_core.strategies.volume_anomaly_v1 import VOLUME_ANOMALY_V1

from .conftest import EXCHANGE, ORIGIN, SYMBOL, BarSpec, D, explode, flat, minute, series
from .test_momentum_v1 import CUT as MOMENTUM_CUT
from .test_momentum_v1 import build_series as momentum_series
from .test_volume_anomaly_v1 import CUT as VOLUME_CUT
from .test_volume_anomaly_v1 import build_series as volume_series

pytestmark = pytest.mark.unit

ABSURD = BarSpec(D("100"), D("9999"), D("0.01"), D("5000"), D("999999"))


def ctx_of(candles: list[NormalizedCandle], cut: object) -> StrategyContext:
    return build_context(
        candles,
        exchange=EXCHANGE,
        symbol=SYMBOL,
        source_bar_close=cut,  # pyright: ignore[reportArgumentType]
    )


def momentum_decision(candles: list[NormalizedCandle]) -> Decision | None:
    return MOMENTUM_V1.evaluate(ctx_of(candles, MOMENTUM_CUT), MOMENTUM_V1.default_parameters)


def volume_decision(candles: list[NormalizedCandle]) -> Decision | None:
    return VOLUME_ANOMALY_V1.evaluate(
        ctx_of(candles, VOLUME_CUT), VOLUME_ANOMALY_V1.default_parameters
    )


def test_momentum_ignores_candles_after_the_reference_close() -> None:
    clean = momentum_series()
    with_future = [*clean, *explode(ABSURD, MOMENTUM_CUT, 15)]
    other_future = [
        *clean,
        *explode(BarSpec(D("100"), D("101"), D("1"), D("2"), D("7")), MOMENTUM_CUT, 15),
    ]

    baseline = momentum_decision(clean)

    assert baseline is not None
    assert momentum_decision(with_future) == baseline
    assert momentum_decision(other_future) == baseline


def test_momentum_ignores_the_candle_still_forming() -> None:
    clean = momentum_series()
    forming = minute(MOMENTUM_CUT, D("100"), D("9999"), D("1"), D("5000"), D("999"), is_final=False)
    # ... and a non-final *revision* of the last minute of the reference bar
    revised = minute(
        MOMENTUM_CUT - timedelta(minutes=1),
        D("100"),
        D("9999"),
        D("1"),
        D("5000"),
        D("999"),
        is_final=False,
    )

    baseline = momentum_decision(clean)

    assert baseline is not None
    assert momentum_decision([*clean, forming, revised]) == baseline


def test_volume_anomaly_ignores_the_future_and_the_forming_candle() -> None:
    clean = volume_series()
    polluted = [
        *clean,
        *explode(ABSURD, VOLUME_CUT, 5),
        minute(
            VOLUME_CUT + timedelta(minutes=5),
            D("100"),
            D("9999"),
            D("1"),
            D("5000"),
            D("9"),
            is_final=False,
        ),
    ]

    baseline = volume_decision(clean)

    assert baseline is not None
    assert volume_decision(polluted) == baseline


def test_momentum_bootstrap_equals_continuous_execution() -> None:
    """The worker bootstraps from Postgres with one window and then grows the
    context bar by bar; both paths must agree on every reference close."""
    quiet = flat(D("99"), D("1"), D("100"))
    signal = BarSpec(D("99"), D("101"), D("99"), D("100"), D("200"))
    long_history = series([*[quiet] * 200, signal], timeframe=Timeframe.M15)
    cut = ORIGIN + timedelta(minutes=15 * 201)

    bootstrap = MOMENTUM_V1.evaluate(ctx_of(long_history, cut), MOMENTUM_V1.default_parameters)

    # continuous: replay the same minutes one bar at a time, evaluating at every close
    grown: list[NormalizedCandle] = []
    decisions: list[Decision | None] = []
    for index in range(201):
        grown.extend(long_history[index * 15 : (index + 1) * 15])
        bar_close = ORIGIN + timedelta(minutes=15 * (index + 1))
        decisions.append(
            MOMENTUM_V1.evaluate(ctx_of(list(grown), bar_close), MOMENTUM_V1.default_parameters)
        )

    assert bootstrap is not None
    assert decisions[-1] == bootstrap
    assert [d for d in decisions[:-1] if d is not None] == []  # only the signal bar fires


def test_momentum_decision_does_not_depend_on_how_much_history_is_kept() -> None:
    """97 bars is the declared window; a context holding 201 bars must decide the
    same thing. The extra prefix is deliberately five times more volatile (true
    range 10 instead of 2), so an ATR that quietly used "everything it was given"
    would land far outside the 0.3%-5% band and the decision would change."""
    quiet = flat(D("99"), D("1"), D("100"))
    signal = BarSpec(D("99"), D("101"), D("99"), D("100"), D("200"))
    short = momentum_series()
    long_ = series(
        [*[flat(D("99"), D("5"), D("100"))] * 104, *[quiet] * 96, signal],
        timeframe=Timeframe.M15,
    )
    cut = ORIGIN + timedelta(minutes=15 * 201)

    from_short = momentum_decision(short)
    from_long = MOMENTUM_V1.evaluate(ctx_of(long_, cut), MOMENTUM_V1.default_parameters)

    assert from_short is not None and from_long is not None
    assert from_long.stop == from_short.stop == D("97")
    assert from_long.target1 == from_short.target1 == D("103")
    assert from_long.supporting_features.atr is not None
    assert from_short.supporting_features.atr is not None
    assert from_long.supporting_features.atr.value == from_short.supporting_features.atr.value
    assert from_long.supporting_features.atr.bars_used == 97


def test_volume_bootstrap_equals_a_longer_history() -> None:
    """Same reference close, two context lengths: the trimmed context keeps only
    what the declared windows need (the 15m ATR window starts earliest)."""
    from hunter_core.domain.market import align_open_time

    from .test_volume_anomaly_v1 import PREVIOUS

    extra = 120
    candles = volume_series(bars=PREVIOUS + extra)
    cut = ORIGIN + timedelta(minutes=5 * (PREVIOUS + extra + 1))
    atr_start = align_open_time(cut, Timeframe.M15) - timedelta(minutes=15 * 97)
    trimmed = [candle for candle in candles if candle.open_time >= atr_start]

    params = VOLUME_ANOMALY_V1.default_parameters
    full = VOLUME_ANOMALY_V1.evaluate(ctx_of(candles, cut), params)
    bootstrap = VOLUME_ANOMALY_V1.evaluate(ctx_of(trimmed, cut), params)

    assert full is not None
    assert bootstrap == full
    assert len(trimmed) < len(candles)


def test_the_same_context_always_produces_the_same_canonical_envelope() -> None:
    ctx = ctx_of(momentum_series(), MOMENTUM_CUT)

    first = MOMENTUM_V1.evaluate(ctx, MOMENTUM_V1.default_parameters)
    second = MOMENTUM_V1.evaluate(ctx, MOMENTUM_V1.default_parameters)

    assert first is not None and second is not None
    assert canonical_json(first.supporting_features.to_jsonable()) == canonical_json(
        second.supporting_features.to_jsonable()
    )
    assert first == second


def test_a_cheating_strategy_is_caught_by_the_context() -> None:
    """The leak this suite exists to catch: a strategy that peeks at the bar
    after the reference close cannot even build the context to do it."""
    candles = [*momentum_series(), *explode(ABSURD, MOMENTUM_CUT, 15)]

    with pytest.raises(ValueError, match="source_bar_close"):
        StrategyContext(
            exchange=EXCHANGE,
            symbol=SYMBOL,
            source_bar_close=MOMENTUM_CUT,
            candles_1m=tuple(candles),
        )


@pytest.mark.parametrize("prec", [2, 6, 28])
@pytest.mark.parametrize("rounding", [ROUND_DOWN, ROUND_UP, ROUND_HALF_EVEN])
def test_no_arithmetic_escapes_the_declared_context(prec: int, rounding: str) -> None:
    """Astra reproduced this one on the S1 diff: a ``quantize`` outside
    ``localcontext(CONTEXT)`` changed the reason text under ROUND_UP/ROUND_DOWN and
    raised ``InvalidOperation`` under ``prec = 2`` — after every condition had
    already passed. The contexts are built first, then the ambient context is
    changed, so only the evaluation is exercised."""
    signal = BarSpec(D("99"), D("101"), D("99"), D("100"), D("200.5"))  # rvol 2.005
    momentum_ctx = ctx_of(momentum_series(signal=signal), MOMENTUM_CUT)
    volume_ctx = ctx_of(volume_series(), VOLUME_CUT)

    baseline = MOMENTUM_V1.evaluate(momentum_ctx, MOMENTUM_V1.default_parameters)
    volume_baseline = VOLUME_ANOMALY_V1.evaluate(volume_ctx, VOLUME_ANOMALY_V1.default_parameters)

    with localcontext() as context:
        context.prec = prec
        context.rounding = rounding
        assert MOMENTUM_V1.evaluate(momentum_ctx, MOMENTUM_V1.default_parameters) == baseline
        assert (
            VOLUME_ANOMALY_V1.evaluate(volume_ctx, VOLUME_ANOMALY_V1.default_parameters)
            == volume_baseline
        )

    assert baseline is not None
    assert "2.00x" in baseline.reason  # 200.5/100 = 2.005 under ROUND_HALF_EVEN, never 2.01x


def test_a_decimal_of_the_ambient_context_cannot_move_the_numbers() -> None:
    """A library that lowered ``decimal.getcontext().prec`` must not change a
    frozen version's ATR, ratios or levels."""
    baseline = momentum_decision(momentum_series())

    with localcontext() as context:
        context.prec = 6
        narrowed = momentum_decision(momentum_series())

    assert baseline is not None
    assert narrowed is not None
    assert narrowed == baseline
    assert isinstance(baseline.stop, Decimal)
    # and the persisted form too: the 28-digit return_15m must not be re-rounded
    with localcontext() as context:
        context.prec = 6
        assert canonical_json(narrowed.supporting_features.to_jsonable()) == canonical_json(
            baseline.supporting_features.to_jsonable()
        )
