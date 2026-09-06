"""No look-ahead — the property the whole engine exists to guarantee.

Three separate claims, tested separately:

1. a **bar** feature does not change when the candle still forming changes (only
   ``_live`` features may move);
2. nothing changes when a candle that had not closed at ``as_of`` is added to
   the input — the cut drops it;
3. the strict context *refuses* such a candle instead of quietly using it, so a
   scanner bug is an exception, not a biased score.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import timedelta
from decimal import Decimal

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from hunter_core.domain.market import NormalizedCandle
from hunter_indicators.features.context import MarketContext, build_context
from hunter_indicators.features.definitions import LIVE_SUFFIX
from hunter_indicators.features.engine import DEFAULT_REGISTRY, compute_features
from hunter_indicators.features.state import EMPTY_STATE
from hunter_indicators.features.vector import FeatureVector
from packages.indicators.tests.factories import EXCHANGE, MINUTE, ORIGIN, SYMBOL, candle, series

MINUTES = 400
CUT = ORIGIN + timedelta(minutes=MINUTES, seconds=30)


def _candles(count: int = MINUTES):
    closes = [Decimal(100) + Decimal(i % 7) for i in range(count)]
    volumes = [Decimal(10) + Decimal(i % 5) for i in range(count)]
    return series(
        closes,
        volumes=volumes,
        highs=[c + 1 for c in closes],
        lows=[c - 1 for c in closes],
    )


def _forming(close: Decimal, *, second: int = 20):
    return candle(
        ORIGIN + MINUTES * MINUTE,
        close=close,
        high=close + Decimal("5"),
        low=close - Decimal("5"),
        is_final=False,
        volume=Decimal("7"),
        event_ts=ORIGIN + timedelta(minutes=MINUTES, seconds=second),
    )


def _vector(extra: Sequence[NormalizedCandle]) -> FeatureVector:
    ctx = build_context(exchange=EXCHANGE, symbol=SYMBOL, as_of=CUT, candles=[*_candles(), *extra])
    return compute_features(ctx, EMPTY_STATE).vector


def _bar_values(vector: FeatureVector) -> dict[str, Decimal | None]:
    return {
        key: value.value for key, value in vector.values.items() if not key.endswith(LIVE_SUFFIX)
    }


BASELINE = _vector([_forming(Decimal("100"))])


def test_the_forming_candle_does_not_move_a_single_bar_feature() -> None:
    moved = _vector([_forming(Decimal("100000"))])
    assert _bar_values(moved) == _bar_values(BASELINE)


def test_the_forming_candle_does_move_the_live_features() -> None:
    """The mirror image: if it moved nothing, ``_live`` would be pointless."""
    moved = _vector([_forming(Decimal("100000"))])
    live_keys = [key for key in DEFAULT_REGISTRY.keys() if key.endswith(LIVE_SUFFIX)]
    assert live_keys
    assert all(moved.number(key) != BASELINE.number(key) for key in live_keys)


def test_a_candle_that_had_not_closed_is_ignored_by_the_builder() -> None:
    future = candle(
        ORIGIN + MINUTES * MINUTE, close=Decimal("100000"), volume=Decimal("9999")
    )  # final, but it closes after the cut
    assert _bar_values(_vector([future, _forming(Decimal("100"))])) == _bar_values(BASELINE)


def test_the_strict_context_refuses_a_candle_from_the_future() -> None:
    future = candle(ORIGIN + MINUTES * MINUTE, close=Decimal("100000"))
    with pytest.raises(ValueError, match="close_time"):
        MarketContext(
            exchange=EXCHANGE,
            symbol=SYMBOL,
            as_of=CUT,
            final_candles=(*_candles(), future),
        )


def test_a_later_update_of_the_forming_candle_is_not_read_before_it_happened() -> None:
    """A partial stamped after the cut is future information, even at the same minute."""
    ctx = build_context(
        exchange=EXCHANGE,
        symbol=SYMBOL,
        as_of=CUT,
        candles=[*_candles(), _forming(Decimal("100000"), second=50)],
    )
    assert ctx.forming is None


@settings(max_examples=40, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@given(
    close=st.decimals(
        min_value=Decimal("0.01"),
        max_value=Decimal("1000000"),
        allow_nan=False,
        allow_infinity=False,
        places=4,
    ),
    second=st.integers(min_value=0, max_value=29),
)
def test_property_bar_features_are_invariant_to_the_forming_candle(
    close: Decimal, second: int
) -> None:
    assert _bar_values(_vector([_forming(close, second=second)])) == _bar_values(BASELINE)


def test_no_bar_feature_declares_the_forming_candle_as_an_input() -> None:
    for calculator in DEFAULT_REGISTRY.all():
        definition = calculator.definition
        uses_forming = "candles:1m:forming" in definition.inputs
        assert uses_forming == definition.is_live, definition.key


def test_a_partial_without_an_update_timestamp_is_refused() -> None:
    """Astra, T2.2 diff review, must-fix 4: without ``event_ts`` the partial's age
    cannot be proven, and a 12:00:50 update would leak into a 12:00:20 evaluation.
    The market-worker refuses to store such a partial (``push_candle``), so
    accepting one here would only ever admit a leak."""
    partial = candle(ORIGIN + MINUTES * MINUTE, close=Decimal("100000"), is_final=False)
    ctx = build_context(exchange=EXCHANGE, symbol=SYMBOL, as_of=CUT, candles=[*_candles(), partial])
    assert ctx.forming is None
    with pytest.raises(ValueError, match="event_ts"):
        MarketContext(exchange=EXCHANGE, symbol=SYMBOL, as_of=CUT, forming=partial)


def test_a_checkpoint_from_after_the_cut_is_not_used() -> None:
    """Astra, must-fix 1: re-evaluating 12:15 with the state of 12:30 would fold
    bars the market had not printed at the cut."""
    from hunter_indicators.features.atr import advance_from_context
    from hunter_indicators.features.state import FeatureState

    late = build_context(exchange=EXCHANGE, symbol=SYMBOL, as_of=CUT, candles=_candles(MINUTES))
    future_state = advance_from_context(late, None).checkpoint
    assert future_state is not None
    earlier_cut = ORIGIN + timedelta(minutes=MINUTES - 60)
    earlier = build_context(
        exchange=EXCHANGE,
        symbol=SYMBOL,
        as_of=earlier_cut,
        candles=_candles(MINUTES),
    )
    result = compute_features(earlier, FeatureState(atr_15m=future_state))
    assert result.state.atr_15m is not None
    assert result.state.atr_15m.last_bar_open < earlier_cut
    assert result.state.atr_15m.origin_reason == "cut_rebuild"
