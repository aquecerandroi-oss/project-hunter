"""``MarketContext`` is the anti-look-ahead guarantee, enforced by the type."""

from __future__ import annotations

import decimal
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from hunter_indicators.features.context import (
    INPUT_BOOK,
    BookSnapshot,
    DerivSnapshot,
    MarketContext,
    SourceEntry,
    build_context,
    missing,
)
from packages.indicators.tests.factories import EXCHANGE, MINUTE, ORIGIN, SYMBOL, candle, series

AS_OF = ORIGIN + 10 * MINUTE


def _closes(n: int) -> list[Decimal]:
    return [Decimal(100 + i) for i in range(n)]


class TestCut:
    def test_final_candle_closing_after_as_of_is_refused(self) -> None:
        candles = series(_closes(10))
        with pytest.raises(ValueError, match="close_time"):
            MarketContext(
                exchange=EXCHANGE,
                symbol=SYMBOL,
                as_of=candles[-1].close_time - timedelta(seconds=30),
                final_candles=tuple(candles),
            )

    def test_final_candle_closing_exactly_at_as_of_is_admitted(self) -> None:
        candles = series(_closes(10))
        ctx = MarketContext(
            exchange=EXCHANGE,
            symbol=SYMBOL,
            as_of=candles[-1].close_time,
            final_candles=tuple(candles),
        )
        assert len(ctx.final_candles) == 10

    def test_non_final_candle_is_refused_in_final_candles(self) -> None:
        forming = candle(ORIGIN, close=Decimal("100"), is_final=False)
        with pytest.raises(ValueError, match="is_final"):
            MarketContext(exchange=EXCHANGE, symbol=SYMBOL, as_of=AS_OF, final_candles=(forming,))

    def test_forming_candle_must_straddle_as_of(self) -> None:
        forming = candle(AS_OF + MINUTE, close=Decimal("100"), is_final=False)
        with pytest.raises(ValueError, match="forming"):
            MarketContext(exchange=EXCHANGE, symbol=SYMBOL, as_of=AS_OF, forming=forming)

    def test_forming_update_after_as_of_is_refused(self) -> None:
        forming = candle(
            AS_OF, close=Decimal("100"), is_final=False, event_ts=AS_OF + timedelta(seconds=30)
        )
        with pytest.raises(ValueError, match="event_ts"):
            MarketContext(
                exchange=EXCHANGE,
                symbol=SYMBOL,
                as_of=AS_OF + timedelta(seconds=10),
                forming=forming,
            )

    def test_book_newer_than_as_of_is_refused(self) -> None:
        book = BookSnapshot(ts=AS_OF + timedelta(seconds=1), depth=20, bids=(), asks=())
        with pytest.raises(ValueError, match="as_of"):
            MarketContext(
                exchange=EXCHANGE,
                symbol=SYMBOL,
                as_of=AS_OF,
                book=SourceEntry(value=book, ts=book.ts),
            )

    def test_deriv_field_newer_than_as_of_is_refused(self) -> None:
        deriv = DerivSnapshot(open_interest=Decimal("1"), oi_ts=AS_OF + timedelta(seconds=1))
        with pytest.raises(ValueError, match="as_of"):
            MarketContext(
                exchange=EXCHANGE,
                symbol=SYMBOL,
                as_of=AS_OF,
                deriv=SourceEntry(value=deriv, ts=deriv.oi_ts),
            )

    def test_candles_must_be_strictly_increasing(self) -> None:
        candles = series(_closes(3))
        with pytest.raises(ValueError, match="increasing"):
            MarketContext(
                exchange=EXCHANGE,
                symbol=SYMBOL,
                as_of=AS_OF,
                final_candles=(candles[1], candles[0], candles[2]),
            )

    def test_foreign_symbol_is_refused(self) -> None:
        alien = candle(ORIGIN, close=Decimal("100"), symbol="ETHUSDT")
        with pytest.raises(ValueError, match="ETHUSDT"):
            MarketContext(exchange=EXCHANGE, symbol=SYMBOL, as_of=AS_OF, final_candles=(alien,))

    def test_naive_as_of_is_refused(self) -> None:
        with pytest.raises(ValueError, match="UTC"):
            # a naive timestamp is the bug this test exists to catch
            MarketContext(exchange=EXCHANGE, symbol=SYMBOL, as_of=datetime(2026, 9, 1, 0, 10))  # noqa: DTZ001


class TestBuildContext:
    def test_filters_instead_of_raising(self) -> None:
        candles = series(_closes(20))
        forming = candle(ORIGIN + 20 * MINUTE, close=Decimal("999"), is_final=False)
        ctx = build_context(
            exchange=EXCHANGE,
            symbol=SYMBOL,
            as_of=AS_OF,
            candles=[*candles, forming],
        )
        assert [c.open_time for c in ctx.final_candles] == [ORIGIN + i * MINUTE for i in range(10)]
        assert ctx.forming is None  # it opens after the cut

    def test_keeps_the_candle_forming_at_the_cut(self) -> None:
        candles = series(_closes(10))
        forming = candle(
            AS_OF,
            close=Decimal("999"),
            is_final=False,
            event_ts=AS_OF + timedelta(seconds=10),
        )
        ctx = build_context(
            exchange=EXCHANGE,
            symbol=SYMBOL,
            as_of=AS_OF + timedelta(seconds=20),
            candles=[*candles, forming],
        )
        assert ctx.forming is not None
        assert ctx.forming.open_time == AS_OF

    def test_drops_a_stale_forming_update(self) -> None:
        forming = candle(
            AS_OF, close=Decimal("999"), is_final=False, event_ts=AS_OF + timedelta(seconds=40)
        )
        ctx = build_context(
            exchange=EXCHANGE,
            symbol=SYMBOL,
            as_of=AS_OF + timedelta(seconds=20),
            candles=[forming],
        )
        assert ctx.forming is None

    def test_only_the_candle_list_is_filtered(self) -> None:
        """Cross-review nice-to-have (e): the door filters **candles** and
        nothing else, and now says so.

        A candle list legitimately contains items outside the cut — the minute
        still forming, minutes that close later — so choosing among them is
        selection. A book, a trade or a deriv field stamped after the cut is not
        a selection problem: it is a broken clock or a broken source, and the
        production path already turns those into ``after_cut`` entries inside
        ``decode_book``/``decode_trades``/``decode_deriv``. Here it raises, so a
        bespoke loader that skips the decoders finds out.
        """
        book = BookSnapshot(ts=AS_OF + timedelta(seconds=1), depth=20, bids=(), asks=())
        with pytest.raises(ValueError, match="as_of"):
            build_context(
                exchange=EXCHANGE,
                symbol=SYMBOL,
                as_of=AS_OF,
                candles=series(_closes(5)),
                book=SourceEntry(value=book, ts=book.ts),
            )

    def test_a_deriv_field_after_the_cut_still_raises(self) -> None:
        deriv = DerivSnapshot(open_interest=Decimal("1"), oi_ts=AS_OF + timedelta(seconds=1))
        with pytest.raises(ValueError, match="as_of"):
            build_context(
                exchange=EXCHANGE,
                symbol=SYMBOL,
                as_of=AS_OF,
                deriv=SourceEntry(value=deriv, ts=deriv.oi_ts),
            )

    def test_drops_foreign_markets(self) -> None:
        mine = series(_closes(5))
        alien = candle(ORIGIN, close=Decimal("100"), symbol="ETHUSDT")
        ctx = build_context(exchange=EXCHANGE, symbol=SYMBOL, as_of=AS_OF, candles=[*mine, alien])
        assert len(ctx.final_candles) == 5


class TestSourceEntry:
    def test_missing_entry_is_unavailable_with_a_reason(self) -> None:
        entry: SourceEntry[BookSnapshot] = missing(INPUT_BOOK)
        assert entry.available is False
        assert entry.value is None
        assert entry.reason == "missing_input"

    def test_age_is_a_decimal_number_of_seconds(self) -> None:
        entry: SourceEntry[BookSnapshot] = SourceEntry(value=None, ts=AS_OF - timedelta(seconds=90))
        assert entry.age_s(AS_OF) == Decimal("90")

    def test_age_is_built_from_the_integer_fields_not_from_a_float(self) -> None:
        """Cross-review nice-to-have (c): ``timedelta.total_seconds()`` is a
        binary float, so the seconds it reports are an approximation. At
        100000 days + 1 us it already reports ``...000002``; the age is computed
        from ``days``/``seconds``/``microseconds`` instead, and is exact for
        every delta, not merely for the small ones.
        """
        entry: SourceEntry[BookSnapshot] = SourceEntry(
            value=None, ts=AS_OF - timedelta(days=100000, microseconds=1)
        )
        assert entry.age_s(AS_OF) == Decimal("8640000000.000001")

    def test_a_negative_age_is_still_exact(self) -> None:
        entry: SourceEntry[BookSnapshot] = SourceEntry(
            value=None, ts=AS_OF + timedelta(seconds=1, microseconds=500000)
        )
        assert entry.age_s(AS_OF) == Decimal("-1.5")

    def test_the_age_does_not_depend_on_the_ambient_precision(self) -> None:
        """Astra, fix-pass review, must-fix 1: killing the float is not enough —
        the sum and the division still ran under whatever precision the process
        had. Under ``prec = 6`` a 10.000001 s old book rounded to 10.0000 and
        stopped being over its 10 s budget: the quality of a sample depended on
        the ambient context of the worker that computed it."""
        entry: SourceEntry[BookSnapshot] = SourceEntry(
            value=None, ts=AS_OF - timedelta(seconds=10, microseconds=1)
        )
        clean = entry.age_s(AS_OF)
        with decimal.localcontext() as ambient:
            ambient.prec = 6
            hostile = entry.age_s(AS_OF)
        assert clean == hostile == Decimal("10.000001")

    def test_age_is_none_without_a_timestamp(self) -> None:
        empty: SourceEntry[BookSnapshot] = SourceEntry(value=None, ts=None)
        assert empty.age_s(AS_OF) is None


class TestBtcReference:
    def test_btc_must_share_the_cut(self) -> None:
        btc = MarketContext(exchange=EXCHANGE, symbol="ETHUSDT", as_of=AS_OF - MINUTE)
        with pytest.raises(ValueError, match="as_of"):
            MarketContext(exchange=EXCHANGE, symbol=SYMBOL, as_of=AS_OF, btc=btc)

    def test_btc_reference_cannot_nest(self) -> None:
        inner = MarketContext(exchange=EXCHANGE, symbol="BTCUSDT", as_of=AS_OF)
        middle = MarketContext(exchange=EXCHANGE, symbol="BTCUSDT", as_of=AS_OF, btc=inner)
        with pytest.raises(ValueError, match="nest"):
            MarketContext(exchange=EXCHANGE, symbol=SYMBOL, as_of=AS_OF, btc=middle)


def test_context_is_frozen() -> None:
    ctx = MarketContext(exchange=EXCHANGE, symbol=SYMBOL, as_of=AS_OF)
    with pytest.raises((AttributeError, TypeError)):
        ctx.as_of = datetime.now(UTC)  # type: ignore[misc]
