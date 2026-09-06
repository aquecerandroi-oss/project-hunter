"""Microstructure features from the book and the trade tape."""

from __future__ import annotations

import decimal
from collections.abc import Callable
from datetime import datetime, timedelta
from decimal import Decimal

from hunter_core.domain.enums import OrderSide
from hunter_indicators.features.context import (
    BookSnapshot,
    SourceEntry,
    TapeTrade,
    build_context,
)
from hunter_indicators.features.micro import (
    BookImbalance,
    SpreadPct,
    TakerPressure,
    TradeVelocity,
    micro_calculators,
)
from hunter_indicators.features.state import EMPTY_STATE
from hunter_indicators.features.vector import Reason
from packages.indicators.tests.factories import EXCHANGE, ORIGIN, SYMBOL, series

AS_OF = ORIGIN + timedelta(minutes=10, seconds=30)


def _ctx(**kwargs: object):
    return build_context(
        exchange=EXCHANGE,
        symbol=SYMBOL,
        as_of=AS_OF,
        candles=series([Decimal("100")] * 10),
        **kwargs,  # type: ignore[arg-type]
    )


def _book(bids: list[tuple[str, str]], asks: list[tuple[str, str]]):
    snapshot = BookSnapshot(
        ts=AS_OF - timedelta(seconds=1),
        depth=20,
        bids=tuple((Decimal(p), Decimal(q)) for p, q in bids),
        asks=tuple((Decimal(p), Decimal(q)) for p, q in asks),
    )
    return SourceEntry(value=snapshot, ts=snapshot.ts)


def _levels(count: int, qty: str, *, top: str, step: str) -> list[tuple[str, str]]:
    """``count`` levels walking away from ``top`` by ``step`` — a book of real depth."""
    return [(str(Decimal(top) + i * Decimal(step)), qty) for i in range(count)]


def _tape(
    trades: list[tuple[int, str, str, OrderSide]],
    covers_s: int = 600,
    covered_until: datetime | None = None,
):
    tape = tuple(
        TapeTrade(
            ts=AS_OF - timedelta(seconds=age),
            price=Decimal(price),
            qty=Decimal(qty),
            side=side,
            trade_id=f"t{i}",
        )
        for i, (age, price, qty, side) in enumerate(sorted(trades, key=lambda t: -t[0]))
    )
    return SourceEntry(
        value=tape,
        ts=tape[-1].ts if tape else None,
        covers_from=AS_OF - timedelta(seconds=covers_s),
        covered_until=covered_until,
    )


class TestSpread:
    def test_spread_is_a_fraction_of_the_mid(self) -> None:
        ctx = _ctx(book=_book([("100", "1")], [("100.2", "1")]))
        value = SpreadPct().compute(ctx, EMPTY_STATE)
        assert value.key == "spread_pct"
        # (100.2 - 100) / ((100.2 + 100)/2) = 0.2 / 100.1
        assert value.value == Decimal("0.2") / Decimal("100.1")
        assert value.value is not None and value.value < Decimal("0.01")  # a fraction, never x100

    def test_a_crossed_book_is_not_a_negative_spread(self) -> None:
        """Cross-review MUST-FIX 3: ``bid = 101`` over ``ask = 100`` is not a
        negative spread, it is a book no exchange ever quoted. Same principle as
        ``decode_book``: corruption looks like an absent book, never a different
        one."""
        ctx = _ctx(book=_book([("101", "1")], [("100", "1")]))
        value = SpreadPct().compute(ctx, EMPTY_STATE)
        assert value.value is None
        assert value.reason is Reason.CORRUPT_INPUT

    def test_a_locked_book_is_refused_too(self) -> None:
        ctx = _ctx(book=_book([("100", "1")], [("100", "1")]))
        assert SpreadPct().compute(ctx, EMPTY_STATE).reason is Reason.CORRUPT_INPUT

    def test_an_empty_side_has_no_spread(self) -> None:
        ctx = _ctx(book=_book([], [("100.2", "1")]))
        assert SpreadPct().compute(ctx, EMPTY_STATE).reason is Reason.MISSING_INPUT

    def test_no_book_at_all_is_missing_input(self) -> None:
        assert SpreadPct().compute(_ctx(), EMPTY_STATE).reason is Reason.MISSING_INPUT


class TestBookImbalance:
    def test_imbalance_over_the_top_twenty_levels(self) -> None:
        # 20 bid levels of 0.2 = 4; 20 ask levels of 0.1 = 2; (4-2)/(4+2)
        ctx = _ctx(
            book=_book(
                _levels(20, "0.2", top="100", step="-1"),
                _levels(20, "0.1", top="101", step="1"),
            )
        )
        value = BookImbalance().compute(ctx, EMPTY_STATE)
        assert value.key == "orderbook_imbalance_20"
        assert value.value == Decimal("2") / Decimal("6")

    def test_only_the_first_levels_count(self) -> None:
        ctx = _ctx(
            book=_book(
                _levels(21, "1", top="100", step="-1"),
                _levels(20, "1", top="101", step="1"),
            )
        )
        value = BookImbalance(depth=20).compute(ctx, EMPTY_STATE)
        assert value.value == Decimal("0")  # 20 bids vs 20 asks, the 21st bid ignored

    def test_a_book_thinner_than_the_depth_is_insufficient_sample(self) -> None:
        """Cross-review MUST-FIX 2: 7 bids against 20 asks of qty 1 published
        -0.48 as ``ok`` - a number about how many levels the venue happened to
        send, not about pressure 20 levels deep."""
        ctx = _ctx(
            book=_book(
                _levels(7, "1", top="100", step="-1"),
                _levels(20, "1", top="101", step="1"),
            )
        )
        value = BookImbalance(depth=20).compute(ctx, EMPTY_STATE)
        assert value.value is None
        assert value.reason is Reason.INSUFFICIENT_SAMPLE

    def test_a_crossed_book_has_no_imbalance(self) -> None:
        ctx = _ctx(
            book=_book(
                _levels(20, "1", top="101", step="-1"),
                _levels(20, "1", top="100", step="1"),
            )
        )
        assert BookImbalance(depth=20).compute(ctx, EMPTY_STATE).reason is Reason.CORRUPT_INPUT

    def test_an_empty_book_is_missing_not_thin(self) -> None:
        ctx = _ctx(book=_book([], []))
        assert BookImbalance().compute(ctx, EMPTY_STATE).reason is Reason.MISSING_INPUT

    def test_a_deep_book_with_no_quantity_is_a_zero_divisor(self) -> None:
        """20 levels a side, every one of them empty: the ratio is undefined,
        and it is a different fact from a book too thin to measure."""
        ctx = _ctx(
            book=_book(
                _levels(20, "0", top="100", step="-1"),
                _levels(20, "0", top="101", step="1"),
            )
        )
        assert BookImbalance().compute(ctx, EMPTY_STATE).reason is Reason.ZERO_DIVISOR


class TestTakerPressure:
    def test_buy_pressure_is_taker_buy_over_total(self) -> None:
        ctx = _ctx(
            trades=_tape(
                [
                    (30, "100", "3", OrderSide.BUY),
                    (20, "100", "1", OrderSide.SELL),
                    (400, "100", "100", OrderSide.SELL),  # outside the 5m window
                ],
                covered_until=AS_OF,
            )
        )
        value = TakerPressure(side="buy", window_minutes=5).compute(ctx, EMPTY_STATE)
        assert value.key == "buy_pressure_5m"
        assert value.value == Decimal("0.75")

    def test_sell_pressure_is_its_mirror(self) -> None:
        ctx = _ctx(
            trades=_tape(
                [(30, "100", "3", OrderSide.BUY), (20, "100", "1", OrderSide.SELL)],
                covered_until=AS_OF,
            )
        )
        value = TakerPressure(side="sell", window_minutes=5).compute(ctx, EMPTY_STATE)
        assert value.value == Decimal("0.25")

    def test_a_window_without_trades_is_not_a_zero_unless_coverage_is_proven(self) -> None:
        """Astra, T2.2 diff review, must-fix 3: an old trade does not prove the
        collector was still connected during the window."""
        unproven = _ctx(trades=_tape([(400, "100", "1", OrderSide.BUY)]))
        assert (
            TakerPressure(side="buy", window_minutes=5).compute(unproven, EMPTY_STATE).reason
            is Reason.INSUFFICIENT_COVERAGE
        )
        proven = _ctx(trades=_tape([(400, "100", "1", OrderSide.BUY)], covered_until=AS_OF))
        value = TakerPressure(side="buy", window_minutes=5).compute(proven, EMPTY_STATE)
        assert value.reason is Reason.ZERO_DIVISOR

    def test_an_unproven_window_is_not_a_zero(self) -> None:
        ctx = _ctx(trades=_tape([(30, "100", "1", OrderSide.BUY)], covers_s=60))
        value = TakerPressure(side="buy", window_minutes=5).compute(ctx, EMPTY_STATE)
        assert value.reason is Reason.INSUFFICIENT_COVERAGE


class TestTradeVelocity:
    def test_velocity_is_trades_per_second(self) -> None:
        ctx = _ctx(
            trades=_tape(
                [
                    (50, "100", "1", OrderSide.BUY),
                    (30, "100", "1", OrderSide.BUY),
                    (10, "100", "1", OrderSide.SELL),
                    (90, "100", "1", OrderSide.SELL),  # outside the 60 s window
                ],
                covered_until=AS_OF,
            )
        )
        value = TradeVelocity().compute(ctx, EMPTY_STATE)
        assert value.key == "trade_velocity_1m"
        assert value.value == Decimal("3") / Decimal("60")

    def test_a_covered_but_silent_window_is_a_real_zero(self) -> None:
        ctx = _ctx(trades=_tape([(300, "100", "1", OrderSide.BUY)], covered_until=AS_OF))
        value = TradeVelocity().compute(ctx, EMPTY_STATE)
        assert value.value == Decimal("0")

    def test_silence_without_proof_of_coverage_is_unavailable(self) -> None:
        ctx = _ctx(trades=_tape([(300, "100", "1", OrderSide.BUY)]))
        assert TradeVelocity().compute(ctx, EMPTY_STATE).reason is Reason.INSUFFICIENT_COVERAGE

    def test_an_uncovered_window_is_unavailable(self) -> None:
        ctx = _ctx(trades=_tape([(10, "100", "1", OrderSide.BUY)], covers_s=30))
        assert TradeVelocity().compute(ctx, EMPTY_STATE).reason is Reason.INSUFFICIENT_COVERAGE


def test_the_registered_v1_set_is_frozen() -> None:
    assert [calc.definition.key for calc in micro_calculators()] == [
        "buy_pressure_5m",
        "orderbook_imbalance_20",
        "sell_pressure_5m",
        "spread_pct",
        "trade_velocity_1m",
    ]


class TestAmbientDecimalContext:
    """Astra, T2.2 diff review, must-fix 5: a sum outside ``localcontext(CONTEXT)``
    rounds under whatever precision the process happens to have."""

    def _hostile(
        self, compute: Callable[[], Decimal | None]
    ) -> tuple[Decimal | None, Decimal | None]:
        clean = compute()
        with decimal.localcontext() as ambient:
            ambient.prec = 6
            hostile = compute()
        return clean, hostile

    def test_book_imbalance_is_immune(self) -> None:
        ctx = _ctx(
            book=_book(
                [("100", "1.2345678901234567"), ("99", "2.3456789012345678")],
                [("101", "3.4567890123456789")],
            )
        )
        clean, hostile = self._hostile(lambda: BookImbalance().compute(ctx, EMPTY_STATE).value)
        assert clean == hostile

    def test_taker_pressure_is_immune(self) -> None:
        ctx = _ctx(
            trades=_tape(
                [
                    (30, "100", "1.2345678901234567", OrderSide.BUY),
                    (20, "100", "2.3456789012345678", OrderSide.SELL),
                ],
                covered_until=AS_OF,
            )
        )
        clean, hostile = self._hostile(
            lambda: TakerPressure(side="buy", window_minutes=5).compute(ctx, EMPTY_STATE).value
        )
        assert clean == hostile
