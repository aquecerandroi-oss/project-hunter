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
from hunter_core.strategies.breakout_v1 import BREAKOUT_V1
from hunter_core.strategies.canonical import canonical_json
from hunter_core.strategies.mean_reversion_v1 import MEAN_REVERSION_V1
from hunter_core.strategies.momentum_v1 import MOMENTUM_V1
from hunter_core.strategies.session_orb_v1 import SESSION_ORB_V1
from hunter_core.strategies.volume_anomaly_v1 import VOLUME_ANOMALY_V1

from .conftest import EXCHANGE, ORIGIN, SYMBOL, BarSpec, D, explode, flat, minute, series
from .test_breakout_v1 import CUT as BREAKOUT_CUT
from .test_breakout_v1 import PREVIOUS as BREAKOUT_PREVIOUS
from .test_breakout_v1 import build_series as breakout_series
from .test_mean_reversion_v1 import CUT as MEAN_REVERSION_CUT
from .test_mean_reversion_v1 import FORMING_HOUR_CUT, forming_hour_series
from .test_mean_reversion_v1 import build_series as mean_reversion_series
from .test_momentum_v1 import CUT as MOMENTUM_CUT
from .test_momentum_v1 import build_series as momentum_series
from .test_session_orb_v1 import CUT as SESSION_ORB_CUT
from .test_session_orb_v1 import build_series as session_orb_series
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


# ------------------------------------------------------------- mean_reversion_v1 (T3.33b)


def mean_reversion_decision(
    candles: list[NormalizedCandle], cut: object = MEAN_REVERSION_CUT
) -> Decision | None:
    return MEAN_REVERSION_V1.evaluate(ctx_of(candles, cut), MEAN_REVERSION_V1.default_parameters)


def test_mean_reversion_ignores_the_future_the_forming_candle_and_a_mutated_future() -> None:
    """As três mutações do brief T3.33a/b, comparadas no JSON canônico do
    envelope: uma vela **não final** dentro da janela, uma vela final que fecha
    **depois** do corte, e uma vela futura adulterada."""
    clean = mean_reversion_series()
    baseline = mean_reversion_decision(clean)

    forming = minute(
        MEAN_REVERSION_CUT - timedelta(minutes=1),
        D("100"),
        D("9999"),
        D("1"),
        D("5000"),
        D("999"),
        is_final=False,
    )
    with_future = [*clean, *explode(ABSURD, MEAN_REVERSION_CUT, 15)]
    mutated_future = [
        *clean,
        *explode(BarSpec(D("1"), D("2"), D("0.5"), D("1.5"), D("3")), MEAN_REVERSION_CUT, 15),
    ]

    assert baseline is not None
    for polluted in ([*clean, forming], with_future, mutated_future):
        decision = mean_reversion_decision(polluted)
        assert decision is not None
        assert canonical_json(decision.supporting_features.to_jsonable()) == canonical_json(
            baseline.supporting_features.to_jsonable()
        )
        assert decision == baseline


def test_the_forming_hour_never_reaches_the_trend_gate() -> None:
    """Corte às :30. A barra 100 está dentro da hora em formação: mexer no
    fechamento dela move o z-score de 15 min (−4,3589 -> −3, e isso é correto) e
    **não pode** mover ``close_1h``, ``sma_1h`` nem os níveis da decisão. Se a
    porta de tendência usasse a hora ainda aberta, ``close_1h`` cairia de 100
    para 99 e a média de 20 horas andaria junto."""
    baseline = mean_reversion_decision(forming_hour_series(), FORMING_HOUR_CUT)
    mutated = mean_reversion_decision(forming_hour_series(forming_close=D("99")), FORMING_HOUR_CUT)

    assert baseline is not None and mutated is not None
    hourly = [
        {f.name: f.value for f in decision.supporting_features.features}
        for decision in (baseline, mutated)
    ]
    assert hourly[0]["close_1h"] == hourly[1]["close_1h"] == D("100")
    assert hourly[0]["sma_1h"] == hourly[1]["sma_1h"] == D("75.2")
    assert (baseline.reference_price, baseline.stop, baseline.target1) == (
        mutated.reference_price,
        mutated.stop,
        mutated.target1,
    )
    # a mutação é real e aparece exatamente onde deve: no z-score de 15 min
    assert hourly[0]["zscore_15m"] != hourly[1]["zscore_15m"]
    assert hourly[1]["zscore_15m"] == D("-3")


def test_mean_reversion_bootstrap_equals_a_longer_history() -> None:
    """A janela de ATR (97 barras de 15 min) é a mais longa das três, então uma
    série cortada nela decide o mesmo que uma com o dobro do histórico."""
    candles = mean_reversion_series()
    atr_start = MEAN_REVERSION_CUT - timedelta(minutes=15 * 97)
    trimmed = [candle for candle in candles if candle.open_time >= atr_start]

    full = mean_reversion_decision(candles)
    bootstrap = mean_reversion_decision(trimmed)

    assert full is not None
    assert len(trimmed) < len(candles)
    # a janela de tendência (1260 min) cabe dentro da de ATR (1455 min), e é por
    # isso que o contexto aparado ainda decide — ver o teste de domínio da T3.33b
    assert bootstrap == full


def test_mean_reversion_survives_a_hostile_ambient_decimal_context() -> None:
    ctx = ctx_of(mean_reversion_series(), MEAN_REVERSION_CUT)
    params = MEAN_REVERSION_V1.default_parameters
    baseline = MEAN_REVERSION_V1.evaluate(ctx, params)

    with localcontext() as context:
        context.prec = 6
        context.rounding = ROUND_DOWN
        narrowed = MEAN_REVERSION_V1.evaluate(ctx, params)

    assert baseline is not None
    assert narrowed == baseline


# --------------------------------------------------------------------------- breakout_v1 (T3.33a)


def breakout_decision(candles: list[NormalizedCandle]) -> Decision | None:
    return BREAKOUT_V1.evaluate(ctx_of(candles, BREAKOUT_CUT), BREAKOUT_V1.default_parameters)


def _envelope_json(decision: Decision | None) -> str:
    assert decision is not None
    return canonical_json(decision.supporting_features.to_jsonable())


def test_breakout_is_identical_under_three_kinds_of_pollution() -> None:
    """The whole point of the design, in one test: a candle still forming inside
    the window, a final candle closing after the cut, and a *different* future —
    the decision and its canonical envelope must be byte-identical in all three."""
    clean = breakout_series()
    forming_inside = minute(
        BREAKOUT_CUT - timedelta(minutes=1),
        D("100"),
        D("9999"),
        D("0.01"),
        D("5000"),
        D("999999"),
        is_final=False,
    )
    after_the_cut = explode(ABSURD, BREAKOUT_CUT, 15)
    another_future = explode(
        BarSpec(D("100"), D("101"), D("1"), D("2"), D("7")), BREAKOUT_CUT, 15
    )

    baseline = breakout_decision(clean)

    assert baseline is not None
    for polluted in (
        [*clean, forming_inside],
        [*clean, *after_the_cut],
        [*clean, *another_future],
        [*clean, forming_inside, *after_the_cut],
    ):
        assert breakout_decision(polluted) == baseline
        assert _envelope_json(breakout_decision(polluted)) == _envelope_json(baseline)


@pytest.mark.parametrize(
    ("high", "low", "close", "volume"),
    [
        (D("9999"), D("0.01"), D("5000"), D("999999")),
        (D("100"), D("100"), D("100"), D("0")),
        (D("102"), D("99"), D("101.9"), D("300")),
    ],
    ids=["absurd", "flat", "plausible"],
)
def test_mutating_the_candle_still_forming_never_moves_the_breakout(
    high: Decimal, low: Decimal, close: Decimal, volume: Decimal
) -> None:
    """Not just "a non-final candle is dropped": *whatever* it says, and however
    many times it is revised, the frozen decision is the same one."""
    clean = breakout_series()
    forming = minute(
        BREAKOUT_CUT - timedelta(minutes=1), D("100"), high, low, close, volume, is_final=False
    )

    baseline = breakout_decision(clean)

    assert baseline is not None
    assert breakout_decision([*clean, forming]) == baseline
    assert _envelope_json(breakout_decision([*clean, forming])) == _envelope_json(baseline)


def test_breakout_bootstrap_equals_continuous_execution() -> None:
    """One 1560-minute read against a context grown bar by bar: the same
    decision at the same reference close, and nothing before it."""
    candles = breakout_series()
    params = BREAKOUT_V1.default_parameters

    bootstrap = BREAKOUT_V1.evaluate(ctx_of(candles, BREAKOUT_CUT), params)

    grown: list[NormalizedCandle] = []
    decisions: list[Decision | None] = []
    for index in range(BREAKOUT_PREVIOUS + 1):
        grown.extend(candles[index * 15 : (index + 1) * 15])
        bar_close = ORIGIN + timedelta(minutes=15 * (index + 1))
        decisions.append(BREAKOUT_V1.evaluate(ctx_of(list(grown), bar_close), params))

    assert bootstrap is not None
    assert decisions[-1] == bootstrap
    assert [decision for decision in decisions[:-1] if decision is not None] == []


@pytest.mark.parametrize("prec", [2, 6, 28])
@pytest.mark.parametrize("rounding", [ROUND_DOWN, ROUND_UP, ROUND_HALF_EVEN])
def test_the_breakout_numbers_do_not_depend_on_the_ambient_decimal_context(
    prec: int, rounding: str
) -> None:
    ctx = ctx_of(breakout_series(), BREAKOUT_CUT)
    params = BREAKOUT_V1.default_parameters

    baseline = BREAKOUT_V1.evaluate(ctx, params)

    with localcontext() as context:
        context.prec = prec
        context.rounding = rounding
        narrowed = BREAKOUT_V1.evaluate(ctx, params)

    assert baseline is not None and narrowed is not None
    assert narrowed == baseline
    assert _envelope_json(narrowed) == _envelope_json(baseline)


# ------------------------------------------------------------------ session_orb_v1 (T3.33c)


def session_orb_decision(candles: list[NormalizedCandle]) -> Decision | None:
    return SESSION_ORB_V1.evaluate(
        ctx_of(candles, SESSION_ORB_CUT), SESSION_ORB_V1.default_parameters
    )


def test_session_orb_is_identical_under_three_kinds_of_pollution() -> None:
    """As três mutações do brief T3.33c §11.6, comparadas no JSON canônico do
    envelope: uma vela **não final** dentro da janela, uma vela final que fecha
    **depois** do corte, e um futuro adulterado. A sessão vem de
    ``source_bar_close``, então nenhuma delas pode mover a faixa de abertura."""
    clean = session_orb_series()
    baseline = session_orb_decision(clean)

    forming_inside = minute(
        SESSION_ORB_CUT - timedelta(minutes=1),
        D("100"),
        D("9999"),
        D("0.01"),
        D("5000"),
        D("999999"),
        is_final=False,
    )
    after_the_cut = explode(ABSURD, SESSION_ORB_CUT, 15)
    another_future = explode(
        BarSpec(D("100"), D("101"), D("1"), D("2"), D("7")), SESSION_ORB_CUT, 15
    )

    assert baseline is not None
    for polluted in (
        [*clean, forming_inside],
        [*clean, *after_the_cut],
        [*clean, *another_future],
        [*clean, forming_inside, *after_the_cut],
    ):
        decision = session_orb_decision(polluted)
        assert decision == baseline
        assert _envelope_json(decision) == _envelope_json(baseline)


@pytest.mark.parametrize(
    ("high", "low", "close", "volume"),
    [
        (D("9999"), D("0.01"), D("5000"), D("999999")),
        (D("100"), D("100"), D("100"), D("0")),
        (D("102"), D("99"), D("101.9"), D("300")),
    ],
    ids=["absurd", "flat", "plausible"],
)
def test_mutating_the_forming_candle_never_moves_the_session_orb(
    high: Decimal, low: Decimal, close: Decimal, volume: Decimal
) -> None:
    clean = session_orb_series()
    forming = minute(
        SESSION_ORB_CUT - timedelta(minutes=1), D("100"), high, low, close, volume, is_final=False
    )

    baseline = session_orb_decision(clean)

    assert baseline is not None
    assert session_orb_decision([*clean, forming]) == baseline
    assert _envelope_json(session_orb_decision([*clean, forming])) == _envelope_json(baseline)


@pytest.mark.parametrize("prec", [2, 6, 28])
@pytest.mark.parametrize("rounding", [ROUND_DOWN, ROUND_UP, ROUND_HALF_EVEN])
def test_the_session_orb_numbers_do_not_depend_on_the_ambient_decimal_context(
    prec: int, rounding: str
) -> None:
    ctx = ctx_of(session_orb_series(), SESSION_ORB_CUT)
    params = SESSION_ORB_V1.default_parameters

    baseline = SESSION_ORB_V1.evaluate(ctx, params)

    with localcontext() as context:
        context.prec = prec
        context.rounding = rounding
        narrowed = SESSION_ORB_V1.evaluate(ctx, params)

    assert baseline is not None and narrowed is not None
    assert narrowed == baseline
    assert _envelope_json(narrowed) == _envelope_json(baseline)
