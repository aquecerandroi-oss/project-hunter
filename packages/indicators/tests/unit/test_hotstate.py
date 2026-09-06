"""Loading a ``MarketContext`` from the exact payloads the market-worker writes."""

from __future__ import annotations

from datetime import UTC, timedelta
from decimal import Decimal
from typing import Any

import pytest

from hunter_core.domain.enums import OrderSide
from hunter_indicators.features.context import MISSING_INPUT
from hunter_indicators.features.hotstate import HotStateRaw, load_context, read_hot_state
from packages.indicators.tests.factories import (
    EXCHANGE,
    MINUTE,
    ORIGIN,
    SYMBOL,
    book_payload,
    candle,
    candle_rows,
    deriv_hash,
    series,
    trade_rows,
)

AS_OF = ORIGIN + timedelta(minutes=10, seconds=30)


def _closes(n: int) -> list[Decimal]:
    return [Decimal(100 + i) for i in range(n)]


class TestCandles:
    def test_newest_first_rows_become_an_increasing_final_series(self) -> None:
        rows = candle_rows(series(_closes(10)))
        ctx = load_context(HotStateRaw(candles=rows), exchange=EXCHANGE, symbol=SYMBOL, as_of=AS_OF)
        assert [c.close for c in ctx.final_candles] == _closes(10)
        assert ctx.forming is None

    def test_the_forming_candle_is_kept_apart(self) -> None:
        forming = candle(
            ORIGIN + 10 * MINUTE,
            close=Decimal("999"),
            is_final=False,
            event_ts=ORIGIN + timedelta(minutes=10, seconds=20),
        )
        rows = candle_rows([*series(_closes(10)), forming])
        ctx = load_context(HotStateRaw(candles=rows), exchange=EXCHANGE, symbol=SYMBOL, as_of=AS_OF)
        assert len(ctx.final_candles) == 10
        assert ctx.forming is not None
        assert ctx.forming.close == Decimal("999")
        assert ctx.forming.event_ts == ORIGIN + timedelta(minutes=10, seconds=20)

    def test_a_candle_after_the_cut_is_dropped(self) -> None:
        rows = candle_rows(series(_closes(20)))
        ctx = load_context(HotStateRaw(candles=rows), exchange=EXCHANGE, symbol=SYMBOL, as_of=AS_OF)
        assert len(ctx.final_candles) == 10

    def test_a_full_candle_buffer_is_flagged_truncated(self) -> None:
        """Cross-review nice-to-have (b): ``candles_limit`` was carried but never
        read. A list that came back exactly as long as the request may have been
        cut by the ring buffer, and ``relative_volume_1h`` needs 1440 of the 1500
        minutes — whether the history was capped is part of the sample."""
        rows = candle_rows(series(_closes(3)))
        raw = HotStateRaw(candles=rows, candles_limit=3)
        ctx = load_context(raw, exchange=EXCHANGE, symbol=SYMBOL, as_of=ORIGIN + 3 * MINUTE)
        assert len(ctx.final_candles) == 3
        assert ctx.candles_truncated is True

    def test_a_buffer_shorter_than_the_request_is_not_truncated(self) -> None:
        rows = candle_rows(series(_closes(3)))
        raw = HotStateRaw(candles=rows, candles_limit=1500)
        ctx = load_context(raw, exchange=EXCHANGE, symbol=SYMBOL, as_of=ORIGIN + 3 * MINUTE)
        assert ctx.candles_truncated is False

    def test_prices_survive_as_exact_decimals(self) -> None:
        rows = candle_rows(series([Decimal("0.000000123456789")]))
        ctx = load_context(HotStateRaw(candles=rows), exchange=EXCHANGE, symbol=SYMBOL, as_of=AS_OF)
        assert ctx.final_candles[0].close == Decimal("0.000000123456789")


class TestBook:
    def test_snapshot_is_decoded_with_decimal_levels(self) -> None:
        ts = AS_OF - timedelta(seconds=1)
        raw = HotStateRaw(book=book_payload(ts, [("100.5", "2")], [("100.7", "3")]))
        ctx = load_context(raw, exchange=EXCHANGE, symbol=SYMBOL, as_of=AS_OF)
        book = ctx.book.value
        assert book is not None
        assert book.ts == ts
        assert book.depth == 20
        assert book.bids == ((Decimal("100.5"), Decimal("2")),)
        assert book.asks == ((Decimal("100.7"), Decimal("3")),)
        assert ctx.book.available is True

    def test_absent_key_is_missing_not_empty(self) -> None:
        ctx = load_context(HotStateRaw(), exchange=EXCHANGE, symbol=SYMBOL, as_of=AS_OF)
        assert ctx.book.available is False
        assert ctx.book.reason == MISSING_INPUT
        assert ctx.book.value is None

    def test_a_snapshot_after_the_cut_is_dropped_with_a_reason(self) -> None:
        raw = HotStateRaw(book=book_payload(AS_OF + timedelta(seconds=1), [("1", "1")], []))
        ctx = load_context(raw, exchange=EXCHANGE, symbol=SYMBOL, as_of=AS_OF)
        assert ctx.book.available is False
        assert ctx.book.reason == "after_cut"


class TestTrades:
    def test_tape_is_oldest_first_with_its_coverage(self) -> None:
        rows = trade_rows(
            [
                (AS_OF - timedelta(seconds=30), "100", "1", OrderSide.BUY),
                (AS_OF - timedelta(seconds=10), "101", "2", OrderSide.SELL),
            ]
        )
        ctx = load_context(
            HotStateRaw(trades=rows, trades_limit=10),
            exchange=EXCHANGE,
            symbol=SYMBOL,
            as_of=AS_OF,
        )
        tape = ctx.trades.value
        assert tape is not None
        assert [t.price for t in tape] == [Decimal("100"), Decimal("101")]
        assert [t.side for t in tape] == [OrderSide.BUY, OrderSide.SELL]
        assert ctx.trades.ts == AS_OF - timedelta(seconds=10)
        assert ctx.trades.covers_from == AS_OF - timedelta(seconds=30)
        assert ctx.trades.truncated is False

    def test_a_full_ring_buffer_is_flagged_truncated(self) -> None:
        rows = trade_rows(
            [(AS_OF - timedelta(seconds=i), "100", "1", OrderSide.BUY) for i in (3, 2, 1)]
        )
        ctx = load_context(
            HotStateRaw(trades=rows, trades_limit=3),
            exchange=EXCHANGE,
            symbol=SYMBOL,
            as_of=AS_OF,
        )
        assert ctx.trades.truncated is True

    def test_trades_after_the_cut_are_dropped(self) -> None:
        rows = trade_rows(
            [
                (AS_OF - timedelta(seconds=5), "100", "1", OrderSide.BUY),
                (AS_OF + timedelta(seconds=5), "200", "1", OrderSide.BUY),
            ]
        )
        ctx = load_context(
            HotStateRaw(trades=rows, trades_limit=10),
            exchange=EXCHANGE,
            symbol=SYMBOL,
            as_of=AS_OF,
        )
        tape = ctx.trades.value
        assert tape is not None
        assert [t.price for t in tape] == [Decimal("100")]


class TestDeriv:
    def test_per_field_timestamps_are_kept_apart(self) -> None:
        fields = deriv_hash(
            funding_rate="0.0001",
            funding_ts=AS_OF - timedelta(seconds=5),
            mark_price="100.25",
            mark_ts=AS_OF - timedelta(seconds=5),
            open_interest="123456",
            oi_ts=AS_OF - timedelta(minutes=20),
        )
        ctx = load_context(HotStateRaw(deriv=fields), exchange=EXCHANGE, symbol=SYMBOL, as_of=AS_OF)
        deriv = ctx.deriv.value
        assert deriv is not None
        assert deriv.funding_rate == Decimal("0.0001")
        assert deriv.funding_kind == "estimated"
        assert deriv.mark_price == Decimal("100.25")
        assert deriv.open_interest == Decimal("123456")
        assert deriv.oi_ts == AS_OF - timedelta(minutes=20)
        assert deriv.funding_ts == AS_OF - timedelta(seconds=5)

    def test_the_next_funding_time_survives_the_decode(self) -> None:
        """Cross-review nice-to-have (f): the writer keeps ``next_funding_time``
        (``hot_state.FUNDING_FIELDS``) and T2.3 needs it — a funding rate is
        cheap eight hours before the settlement and expensive two minutes
        before. It is an **appointment**, not an observation, so it is the one
        deriv timestamp allowed to be in the future and it never joins
        ``timestamps()``."""
        fields = deriv_hash(
            funding_rate="0.0001",
            funding_ts=AS_OF - timedelta(seconds=5),
            next_funding_time=AS_OF + timedelta(hours=3),
        )
        ctx = load_context(HotStateRaw(deriv=fields), exchange=EXCHANGE, symbol=SYMBOL, as_of=AS_OF)
        deriv = ctx.deriv.value
        assert deriv is not None
        assert deriv.next_funding_time == AS_OF + timedelta(hours=3)
        assert ctx.deriv.ts == AS_OF - timedelta(seconds=5)  # the appointment is not an age

    def test_the_next_funding_time_of_a_dropped_group_goes_with_it(self) -> None:
        fields = deriv_hash(
            funding_rate="0.0001",
            funding_ts=AS_OF + timedelta(seconds=5),
            next_funding_time=AS_OF + timedelta(hours=3),
            open_interest="10",
            oi_ts=AS_OF - timedelta(seconds=5),
        )
        ctx = load_context(HotStateRaw(deriv=fields), exchange=EXCHANGE, symbol=SYMBOL, as_of=AS_OF)
        deriv = ctx.deriv.value
        assert deriv is not None
        assert deriv.next_funding_time is None

    def test_empty_hash_is_missing(self) -> None:
        ctx = load_context(HotStateRaw(), exchange=EXCHANGE, symbol=SYMBOL, as_of=AS_OF)
        assert ctx.deriv.available is False
        assert ctx.deriv.reason == MISSING_INPUT

    def test_a_field_after_the_cut_is_dropped_and_the_rest_survives(self) -> None:
        fields = deriv_hash(
            funding_rate="0.0001",
            funding_ts=AS_OF + timedelta(seconds=5),
            open_interest="10",
            oi_ts=AS_OF - timedelta(seconds=5),
        )
        ctx = load_context(HotStateRaw(deriv=fields), exchange=EXCHANGE, symbol=SYMBOL, as_of=AS_OF)
        deriv = ctx.deriv.value
        assert deriv is not None
        assert deriv.funding_rate is None
        assert deriv.open_interest == Decimal("10")


class _FakePipeline:
    """Mimics ``redis.asyncio`` pipelining: queue commands, ``execute`` in order."""

    def __init__(self, store: dict[str, Any]) -> None:
        self._store = store
        self._results: list[Any] = []

    async def __aenter__(self) -> _FakePipeline:
        return self

    async def __aexit__(self, *_: object) -> None:
        return None

    def lrange(self, key: str, start: int, stop: int) -> None:
        rows: list[bytes] = list(self._store.get(key, []))
        self._results.append(rows[start : None if stop == -1 else stop + 1])

    def get(self, key: str) -> None:
        self._results.append(self._store.get(key))

    def hgetall(self, key: str) -> None:
        self._results.append(self._store.get(key, {}))

    async def execute(self) -> list[Any]:
        return self._results


class _FakeRedis:
    def __init__(self, store: dict[str, Any]) -> None:
        self._store = store

    def pipeline(self, transaction: bool = True) -> _FakePipeline:
        return _FakePipeline(self._store)


@pytest.mark.unit
async def test_read_hot_state_uses_one_pipeline_and_the_documented_keys() -> None:
    store: dict[str, Any] = {
        f"mkt:{EXCHANGE}:{SYMBOL}:candles:1m": candle_rows(series(_closes(3))),
        f"mkt:{EXCHANGE}:{SYMBOL}:book": book_payload(ORIGIN, [("1", "1")], [("2", "1")]),
        f"mkt:{EXCHANGE}:{SYMBOL}:trades": trade_rows([(ORIGIN, "1", "1", OrderSide.BUY)]),
        f"mkt:{EXCHANGE}:{SYMBOL}:deriv": deriv_hash(open_interest="5", oi_ts=ORIGIN),
    }
    raw = await read_hot_state(_FakeRedis(store), EXCHANGE, SYMBOL, candles=3, trades=1)
    assert len(raw.candles) == 3
    assert raw.book is not None
    assert raw.candles_limit == 3
    assert raw.trades_limit == 1
    ctx = load_context(raw, exchange=EXCHANGE, symbol=SYMBOL, as_of=ORIGIN + 3 * MINUTE)
    assert len(ctx.final_candles) == 3
    assert ctx.deriv.value is not None


def test_load_context_never_reads_a_clock() -> None:
    """``as_of`` is an argument; two loads of the same bytes are the same context."""
    rows = candle_rows(series(_closes(5)))
    first = load_context(HotStateRaw(candles=rows), exchange=EXCHANGE, symbol=SYMBOL, as_of=AS_OF)
    second = load_context(HotStateRaw(candles=rows), exchange=EXCHANGE, symbol=SYMBOL, as_of=AS_OF)
    assert first == second
    assert first.as_of == AS_OF
    assert first.as_of.tzinfo is UTC


def test_a_non_finite_number_in_the_payload_is_refused() -> None:
    """``Decimal("NaN")`` parses; a corrupted field must not become a value."""
    row = book_payload(AS_OF - timedelta(seconds=1), [("NaN", "1")], [("Infinity", "1")])
    ctx = load_context(HotStateRaw(book=row), exchange=EXCHANGE, symbol=SYMBOL, as_of=AS_OF)
    assert ctx.book.available is False
    assert ctx.book.value is None
    assert ctx.book.reason == "corrupt"


def test_a_crossed_snapshot_is_refused_at_the_door() -> None:
    """Cross-review MUST-FIX 3, at the loader: a best bid at or above the best
    ask is not a market, so the snapshot is dropped exactly like a corrupt
    level. The number that would have been published (a negative spread) is
    about the decode, not about the exchange."""
    row = book_payload(AS_OF - timedelta(seconds=1), [("101", "1")], [("100", "1")])
    ctx = load_context(HotStateRaw(book=row), exchange=EXCHANGE, symbol=SYMBOL, as_of=AS_OF)
    assert ctx.book.available is False
    assert ctx.book.value is None
    assert ctx.book.reason == "crossed"


def test_a_locked_snapshot_is_refused_too() -> None:
    row = book_payload(AS_OF - timedelta(seconds=1), [("100", "1")], [("100", "1")])
    ctx = load_context(HotStateRaw(book=row), exchange=EXCHANGE, symbol=SYMBOL, as_of=AS_OF)
    assert ctx.book.reason == "crossed"


def test_a_one_sided_snapshot_is_kept_as_it_came() -> None:
    """An empty side is not a crossed book: nothing is quoted on that side, and
    the calculators say ``missing_input`` for it on their own."""
    row = book_payload(AS_OF - timedelta(seconds=1), [("100", "1")], [])
    ctx = load_context(HotStateRaw(book=row), exchange=EXCHANGE, symbol=SYMBOL, as_of=AS_OF)
    assert ctx.book.available is True


def test_a_corrupt_level_invalidates_the_whole_snapshot() -> None:
    """Astra, T2.2 round 2: dropping the bad level would silently promote the
    second-best bid to best bid and publish a spread that never existed."""
    row = book_payload(AS_OF - timedelta(seconds=1), [("100", "NaN"), ("99", "1")], [("101", "1")])
    ctx = load_context(HotStateRaw(book=row), exchange=EXCHANGE, symbol=SYMBOL, as_of=AS_OF)
    assert ctx.book.available is False
    assert ctx.book.reason == "corrupt"
