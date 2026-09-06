"""Price features — hand-computed fractions, never percentages."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime, timedelta
from decimal import Decimal

from hunter_core.domain.market import NormalizedCandle
from hunter_indicators.features.context import MarketContext, build_context
from hunter_indicators.features.price import (
    DistanceFromExtreme,
    Return,
    price_calculators,
)
from hunter_indicators.features.state import EMPTY_STATE
from hunter_indicators.features.vector import Quality, Reason
from packages.indicators.tests.factories import EXCHANGE, MINUTE, ORIGIN, SYMBOL, candle, series


def _ctx(candles: Sequence[NormalizedCandle], as_of: datetime) -> MarketContext:
    return build_context(exchange=EXCHANGE, symbol=SYMBOL, as_of=as_of, candles=candles)


class TestReturn:
    def test_five_minute_return_is_a_fraction(self) -> None:
        # closes 100,101,...,105 over 6 minutes -> 105/100 - 1 = 0.05
        closes = [Decimal(100 + i) for i in range(6)]
        ctx = _ctx(series(closes), ORIGIN + 6 * MINUTE)
        value = Return(minutes=5).compute(ctx, EMPTY_STATE)
        assert value.key == "return_5m"
        assert value.value == Decimal("0.05")
        assert value.quality is Quality.OK

    def test_a_fall_is_negative(self) -> None:
        closes = [Decimal("200"), Decimal("100")]
        ctx = _ctx(series(closes), ORIGIN + 2 * MINUTE)
        assert Return(minutes=1).compute(ctx, EMPTY_STATE).value == Decimal("-0.5")

    def test_warmup_without_the_reference_close(self) -> None:
        ctx = _ctx(series([Decimal("100")] * 3), ORIGIN + 3 * MINUTE)
        value = Return(minutes=5).compute(ctx, EMPTY_STATE)
        assert value.value is None
        assert value.reason is Reason.WARMUP

    def test_a_zero_reference_has_no_return(self) -> None:
        ctx = _ctx(series([Decimal("0"), Decimal("1")]), ORIGIN + 2 * MINUTE)
        assert Return(minutes=1).compute(ctx, EMPTY_STATE).reason is Reason.ZERO_DIVISOR

    def test_the_live_variant_reads_the_forming_candle(self) -> None:
        closes = [Decimal(100 + i) for i in range(6)]
        forming = candle(
            ORIGIN + 6 * MINUTE,
            close=Decimal("110"),
            is_final=False,
            event_ts=ORIGIN + timedelta(minutes=6, seconds=30),
        )
        ctx = _ctx([*series(closes), forming], ORIGIN + timedelta(minutes=6, seconds=40))
        live = Return(minutes=5, live=True).compute(ctx, EMPTY_STATE)
        assert live.key == "return_5m_live"
        # denominator: close of the candle that closed 4 minutes before the
        # forming candle opened -> 101; 110/101 - 1
        assert live.value == (Decimal("110") / Decimal("101") - 1)

    def test_the_live_variant_without_a_forming_candle_is_unavailable(self) -> None:
        ctx = _ctx(series([Decimal(100 + i) for i in range(6)]), ORIGIN + 6 * MINUTE)
        live = Return(minutes=5, live=True).compute(ctx, EMPTY_STATE)
        assert live.reason is Reason.MISSING_INPUT

    def test_definitions_declare_their_inputs(self) -> None:
        bar = Return(minutes=15).definition
        live = Return(minutes=15, live=True).definition
        assert bar.inputs == ("candles:1m",)
        assert live.inputs == ("candles:1m", "candles:1m:forming")
        assert bar.params == {"minutes": 15}
        assert live.is_live is True


class TestDistanceFromExtreme:
    def test_distance_from_the_high_is_zero_or_negative(self) -> None:
        closes = [Decimal("100"), Decimal("120"), Decimal("110")]
        ctx = _ctx(series(closes), ORIGIN + 3 * MINUTE)
        calc = DistanceFromExtreme(kind="high", window_minutes=3)
        value = calc.compute(ctx, EMPTY_STATE)
        assert value.key == "distance_from_3m_high"
        # highest high in the window is 120 (candle 2), last close 110
        assert value.value == (Decimal("110") - Decimal("120")) / Decimal("120")

    def test_distance_from_the_low_is_zero_or_positive(self) -> None:
        closes = [Decimal("100"), Decimal("120"), Decimal("110")]
        ctx = _ctx(series(closes), ORIGIN + 3 * MINUTE)
        calc = DistanceFromExtreme(kind="low", window_minutes=3)
        value = calc.compute(ctx, EMPTY_STATE)
        assert value.value == (Decimal("110") - Decimal("100")) / Decimal("100")

    def test_at_the_high_it_is_exactly_zero(self) -> None:
        closes = [Decimal("100"), Decimal("120")]
        ctx = _ctx(series(closes), ORIGIN + 2 * MINUTE)
        calc = DistanceFromExtreme(kind="high", window_minutes=2)
        assert calc.compute(ctx, EMPTY_STATE).value == Decimal("0")

    def test_the_whole_window_must_be_there(self) -> None:
        ctx = _ctx(series([Decimal("100")] * 5), ORIGIN + 5 * MINUTE)
        calc = DistanceFromExtreme(kind="high", window_minutes=1440)
        assert calc.compute(ctx, EMPTY_STATE).reason is Reason.WARMUP


def test_the_registered_v1_set_is_frozen() -> None:
    keys = [calc.definition.key for calc in price_calculators()]
    assert keys == [
        "distance_from_24h_high",
        "distance_from_24h_low",
        "return_15m",
        "return_15m_live",
        "return_1h",
        "return_1h_live",
        "return_1m",
        "return_1m_live",
        "return_4h",
        "return_5m",
        "return_5m_live",
    ]
