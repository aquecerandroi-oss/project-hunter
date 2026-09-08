"""T3.29 item 2 — the ``NOTIONAL`` reference is read, cached and bounded.

Astra's review of 2026-09-08 (§2, row "Ordem") reproduced the gap: the reader
returned ``None`` for ever (``market_data.py:149``) and every market whose
MARKET filter needs an average deferred until its reservation expired. The VPS
measurement of the same day made it total — all 15 monitored SPOT markets
declare ``avgPriceMins = 5`` and ``applyMinToMarket = true``, so 22 of 22
admissible ``momentum v3`` signals in 24 h would have deferred.

No network anywhere here: the exchange is a labelled double (CLAUDE.md) and the
clock is injected, so "five seconds later" is a value, never a sleep.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any, cast

from hunter_core.domain.enums import MarketType
from hunter_exchanges.binance_spot.normalize import AvgPrice
from hunter_execution_worker.avg_price import (
    AVG_PRICE_MAX_AGE_S,
    AVG_PRICE_SOURCE,
    ExchangeAvgPrice,
)
from hunter_execution_worker.entry_inputs import stale_average
from hunter_execution_worker.market_data import RedisSpotMarketData, SpotSnapshot
from hunter_risk.inputs import MarketIdentity

NOW = datetime(2026, 9, 8, 18, 30, tzinfo=UTC)
MARKET = MarketIdentity(
    exchange="binance",
    symbol="SOLUSDT",
    market_type=MarketType.SPOT,
    base_asset="SOL",
    quote_asset="USDT",
)


class _FakeExchange:
    """A **labelled double** for ``GET /api/v3/avgPrice`` — no HTTP at all."""

    def __init__(self, prices: list[Decimal | Exception]) -> None:
        self.prices = prices
        self.calls: list[str] = []

    async def fetch_avg_price(self, symbol: str) -> AvgPrice:
        self.calls.append(symbol)
        answer = self.prices[min(len(self.calls), len(self.prices)) - 1]
        if isinstance(answer, Exception):
            raise answer
        return AvgPrice(symbol=symbol, price=answer, mins=5)


class _EmptyRedis:
    """A **labelled double** for the hot state: no book, no tape, no keys."""

    async def get(self, key: str) -> bytes | None:
        return None

    async def lrange(self, key: str, start: int, end: int) -> list[bytes]:
        return []


class _Clock:
    def __init__(self, start: datetime) -> None:
        self.now = start

    def __call__(self) -> datetime:
        return self.now


class TestTheReferenceIsTheExchangesOwnAverage:
    """**O que refuta:** a reader that keeps answering ``None`` (the state Astra
    measured), or one that substitutes a last trade for the average."""

    async def test_a_fetched_average_is_returned_with_our_receipt_instant(self) -> None:
        reader = ExchangeAvgPrice(_FakeExchange([Decimal("142.37")]), clock=_Clock(NOW))
        quote = await reader.read(MARKET)
        assert quote is not None
        assert quote.price == Decimal("142.37")
        assert quote.mins == 5
        assert quote.observed_at == NOW
        assert quote.source == AVG_PRICE_SOURCE

    async def test_the_price_is_decimal_never_float(self) -> None:
        reader = ExchangeAvgPrice(_FakeExchange([Decimal("0.00001234")]), clock=_Clock(NOW))
        quote = await reader.read(MARKET)
        assert quote is not None
        assert isinstance(quote.price, Decimal)


class TestOneQuotePerRefreshWindow:
    """The entry and protection cycles poll at 1 s against a shared 6000
    weight/min IP budget; a request per pass per market is how a paper wallet
    earns an IP ban for the whole deployment.

    **O que refuta:** a reader that calls the exchange on every cycle."""

    async def test_a_second_read_inside_the_window_does_not_call_the_exchange(self) -> None:
        clock = _Clock(NOW)
        exchange = _FakeExchange([Decimal("100"), Decimal("200")])
        reader = ExchangeAvgPrice(exchange, clock=clock)
        first = await reader.read(MARKET)
        clock.now = NOW + timedelta(seconds=4)
        second = await reader.read(MARKET)
        assert exchange.calls == ["SOLUSDT"]
        assert first is not None and second is not None
        assert second.price == first.price

    async def test_past_the_window_the_exchange_is_asked_again(self) -> None:
        clock = _Clock(NOW)
        exchange = _FakeExchange([Decimal("100"), Decimal("200")])
        reader = ExchangeAvgPrice(exchange, clock=clock)
        await reader.read(MARKET)
        clock.now = NOW + timedelta(seconds=6)
        second = await reader.read(MARKET)
        assert exchange.calls == ["SOLUSDT", "SOLUSDT"]
        assert second is not None
        assert second.price == Decimal("200")
        assert second.observed_at == clock.now


class TestAFailureNeverBecomesAFabricatedNumber:
    """RISK_ENGINE.md §7: a missing input is ``unavailable``, and the entry
    defers. The last quote is honest evidence *while it is inside the hard
    bound*; past it there is nothing to report.

    **O que refuta:** a reader that keeps serving a quote from another minute
    after the endpoint went down; one that returns zero; one that raises into
    the cycle and takes the protection loop down with it."""

    async def test_inside_the_hard_bound_the_last_quote_survives_an_outage(self) -> None:
        clock = _Clock(NOW)
        exchange = _FakeExchange([Decimal("100"), TimeoutError("api.binance.com")])
        reader = ExchangeAvgPrice(exchange, clock=clock)
        await reader.read(MARKET)
        clock.now = NOW + timedelta(seconds=20)
        quote = await reader.read(MARKET)
        assert quote is not None
        assert quote.price == Decimal("100")
        assert quote.observed_at == NOW  # its own instant, never restamped

    async def test_past_the_hard_bound_the_outage_leaves_nothing(self) -> None:
        clock = _Clock(NOW)
        exchange = _FakeExchange([Decimal("100"), TimeoutError("api.binance.com")])
        reader = ExchangeAvgPrice(exchange, clock=clock)
        await reader.read(MARKET)
        clock.now = NOW + timedelta(seconds=AVG_PRICE_MAX_AGE_S + 1)
        assert await reader.read(MARKET) is None

    async def test_a_clock_that_stepped_backwards_is_not_freshness(self) -> None:
        clock = _Clock(NOW)
        exchange = _FakeExchange([Decimal("100"), TimeoutError("api.binance.com")])
        reader = ExchangeAvgPrice(exchange, clock=clock)
        await reader.read(MARKET)
        clock.now = NOW - timedelta(seconds=5)
        assert await reader.read(MARKET) is None

    async def test_a_non_positive_average_is_refused_not_stored(self) -> None:
        clock = _Clock(NOW)
        exchange = _FakeExchange([Decimal(0)])
        reader = ExchangeAvgPrice(exchange, clock=clock)
        assert await reader.read(MARKET) is None

    async def test_a_first_read_that_fails_reports_nothing(self) -> None:
        reader = ExchangeAvgPrice(
            _FakeExchange([RuntimeError("connection reset")]), clock=_Clock(NOW)
        )
        assert await reader.read(MARKET) is None


class TestOneCachePerMarket:
    """**O que refuta:** a cache keyed by nothing, serving SOL's average for BTC."""

    async def test_two_markets_do_not_share_one_quote(self) -> None:
        clock = _Clock(NOW)
        exchange = _FakeExchange([Decimal("100"), Decimal("200")])
        reader = ExchangeAvgPrice(exchange, clock=clock)
        other = MarketIdentity(
            exchange="binance",
            symbol="BTCUSDT",
            market_type=MarketType.SPOT,
            base_asset="BTC",
            quote_asset="USDT",
        )
        first = await reader.read(MARKET)
        second = await reader.read(other)
        assert exchange.calls == ["SOLUSDT", "BTCUSDT"]
        assert first is not None and second is not None
        assert first.price != second.price


class TestTheSnapshotCarriesTheReferenceAndItsStamp:
    """``RedisSpotMarketData`` without a reader keeps the old, honest answer;
    with one it publishes the price **and** the instant we received it.

    **O que refuta:** a snapshot that carries a price with no stamp (an input
    with no age is an input §7 cannot bound), or one that keeps reporting
    ``not_collected`` after the reader was wired."""

    async def test_without_a_reader_the_reference_is_absent_by_name(self) -> None:
        data = RedisSpotMarketData(cast("Any", _EmptyRedis()), avg_price=None)
        snapshot = await data.snapshot(MARKET)
        assert snapshot.avg_price is None
        assert snapshot.avg_price_source == "not_collected"
        assert snapshot.avg_price_ts is None
        assert "avg_price" in snapshot.unavailable

    async def test_with_a_reader_the_price_and_the_receipt_instant_travel_together(
        self,
    ) -> None:
        reader = ExchangeAvgPrice(_FakeExchange([Decimal("142.37")]), clock=_Clock(NOW))
        data = RedisSpotMarketData(cast("Any", _EmptyRedis()), avg_price=reader)
        snapshot = await data.snapshot(MARKET)
        assert snapshot.avg_price == Decimal("142.37")
        assert snapshot.avg_price_ts == NOW
        assert snapshot.avg_price_source == AVG_PRICE_SOURCE
        assert "avg_price" not in snapshot.unavailable

    async def test_a_reader_with_nothing_to_say_is_unavailable_not_not_collected(
        self,
    ) -> None:
        reader = ExchangeAvgPrice(_FakeExchange([RuntimeError("boom")]), clock=_Clock(NOW))
        data = RedisSpotMarketData(cast("Any", _EmptyRedis()), avg_price=reader)
        snapshot = await data.snapshot(MARKET)
        assert snapshot.avg_price is None
        assert snapshot.avg_price_source == "unavailable"


class TestTheEntryMeasuresTheAgeAgainstItsOwnNow:
    """The bound that catches a snapshot assembled before a stall and used
    after it — the reader's own clock cannot see that gap.

    **O que refuta:** an entry judged by an average from another minute; a price
    with no stamp treated as fresh; a stamp in the future treated as fresh."""

    def _snapshot(self, price: Decimal | None, ts: datetime | None) -> SpotSnapshot:
        return SpotSnapshot(
            market=MARKET,
            book=None,
            avg_price=price,
            avg_price_source=AVG_PRICE_SOURCE if price is not None else "unavailable",
            avg_price_ts=ts,
        )

    def test_a_fresh_reference_passes(self) -> None:
        got = stale_average(self._snapshot(Decimal(100), NOW), now=NOW + timedelta(seconds=3))
        assert got == ""

    def test_past_the_bound_the_entry_defers_with_its_reason(self) -> None:
        got = stale_average(
            self._snapshot(Decimal(100), NOW),
            now=NOW + timedelta(seconds=AVG_PRICE_MAX_AGE_S + 1),
        )
        assert got == "avg_price_stale"

    def test_a_stamp_in_the_future_is_refused_like_an_expired_one(self) -> None:
        got = stale_average(self._snapshot(Decimal(100), NOW + timedelta(seconds=5)), now=NOW)
        assert got == "avg_price_stale"

    def test_a_price_with_no_stamp_is_not_a_reference(self) -> None:
        assert stale_average(self._snapshot(Decimal(100), None), now=NOW) == "avg_price_undated"

    def test_an_absent_reference_still_names_its_source(self) -> None:
        assert stale_average(self._snapshot(None, None), now=NOW) == "avg_price_unavailable"
