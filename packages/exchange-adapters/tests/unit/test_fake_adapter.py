"""FakeExchangeAdapter: the double the market-worker's tests drive against."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

import pytest

from hunter_core.domain.enums import MarketStatus, MarketType, OrderSide, Timeframe
from hunter_core.domain.market import NormalizedMarket, NormalizedTrade
from hunter_exchanges.base import ExchangeAdapter, StreamChannel
from hunter_exchanges.testing.fake_adapter import FakeExchangeAdapter

pytestmark = pytest.mark.unit


def _market(
    symbol: str = "BTCUSDT", market_type: MarketType = MarketType.PERPETUAL
) -> NormalizedMarket:
    return NormalizedMarket(
        exchange="fake",
        symbol=symbol,
        market_type=market_type,
        base="BTC",
        quote="USDT",
        status=MarketStatus.ACTIVE,
        tick_size=Decimal("0.1"),
        step_size=Decimal("0.001"),
        min_notional=Decimal("5"),
    )


def _trade() -> NormalizedTrade:
    return NormalizedTrade(
        exchange="fake",
        symbol="BTCUSDT",
        ts=datetime(2026, 1, 1, tzinfo=UTC),
        trade_id="1",
        price=Decimal("100"),
        qty=Decimal("1"),
        side=OrderSide.BUY,
    )


def test_fake_adapter_satisfies_the_exchange_adapter_protocol() -> None:
    fake = FakeExchangeAdapter()
    assert isinstance(fake, ExchangeAdapter)


def test_fake_adapter_satisfies_the_extras_protocol_too() -> None:
    from hunter_exchanges.base import ExchangeAdapterExtras

    fake = FakeExchangeAdapter()
    assert isinstance(fake, ExchangeAdapterExtras)


async def test_list_markets_filters_by_market_type() -> None:
    fake = FakeExchangeAdapter(
        markets=[_market("BTCUSDT", MarketType.PERPETUAL), _market("BTCUSDT", MarketType.SPOT)]
    )

    perpetuals = await fake.list_markets(MarketType.PERPETUAL)

    assert len(perpetuals) == 1
    assert perpetuals[0].market_type is MarketType.PERPETUAL


async def test_stream_yields_scripted_events_then_blocks_until_cancelled() -> None:
    trade = _trade()
    fake = FakeExchangeAdapter(events=[trade])

    agen: Any = fake.stream(["BTCUSDT"], [StreamChannel.TRADES]).__aiter__()
    first = await agen.__anext__()
    assert first is trade

    with pytest.raises(asyncio.TimeoutError):
        await asyncio.wait_for(agen.__anext__(), timeout=0.05)
    await agen.aclose()

    assert fake.stream_calls == [(("BTCUSDT",), (StreamChannel.TRADES,))]


async def test_connection_state_is_scriptable_and_holds_the_last_value() -> None:
    fake = FakeExchangeAdapter(connection_states=["connecting", "connected"])

    assert fake.connection_state() == "connecting"
    assert fake.connection_state() == "connected"
    assert fake.connection_state() == "connected"  # holds once exhausted


async def test_connection_states_returns_the_configured_per_connection_detail() -> None:
    from hunter_exchanges.base import ConnectionState

    state = ConnectionState(route="market", ws_state="connected")
    fake = FakeExchangeAdapter(per_connection_states={"market:0": state})

    assert fake.connection_states() == {"market:0": state}


async def test_connection_states_defaults_to_empty() -> None:
    fake = FakeExchangeAdapter()

    assert fake.connection_states() == {}


async def test_server_time_returns_the_configured_clock() -> None:
    configured = datetime(2026, 1, 1, tzinfo=UTC)
    fake = FakeExchangeAdapter(server_time=configured)

    assert await fake.server_time() == configured


async def test_server_time_raises_when_unconfigured() -> None:
    fake = FakeExchangeAdapter()

    with pytest.raises(LookupError):
        await fake.server_time()


async def test_fetch_realized_funding_filters_by_symbol_and_window() -> None:
    from hunter_core.domain.market import NormalizedFunding

    in_window = NormalizedFunding(
        exchange="fake",
        symbol="BTCUSDT",
        ts=datetime(2026, 1, 1, 8, tzinfo=UTC),
        funding_rate=Decimal("0.0001"),
        mark_price=Decimal("100"),
        funding_kind="realized",
    )
    before_window = NormalizedFunding(
        exchange="fake",
        symbol="BTCUSDT",
        ts=datetime(2025, 1, 1, tzinfo=UTC),
        funding_rate=Decimal("0.0001"),
        mark_price=Decimal("100"),
        funding_kind="realized",
    )
    fake = FakeExchangeAdapter(realized_funding=[in_window, before_window])

    result = await fake.fetch_realized_funding("BTCUSDT", datetime(2026, 1, 1, tzinfo=UTC))

    assert result == [in_window]


async def test_update_subscriptions_records_the_diff() -> None:
    fake = FakeExchangeAdapter()

    await fake.update_subscriptions(["BTCUSDT"], ["ETHUSDT"], [StreamChannel.TRADES])

    assert fake.subscription_changes == [(["BTCUSDT"], ["ETHUSDT"])]


async def test_aclose_marks_the_fake_closed() -> None:
    fake = FakeExchangeAdapter()

    await fake.aclose()

    assert fake.closed is True


async def test_fetch_methods_raise_lookup_error_when_unconfigured() -> None:
    fake = FakeExchangeAdapter()

    with pytest.raises(LookupError):
        await fake.fetch_ticker("BTCUSDT")
    with pytest.raises(LookupError):
        await fake.fetch_order_book("BTCUSDT")
    with pytest.raises(LookupError):
        await fake.fetch_funding("BTCUSDT")
    with pytest.raises(LookupError):
        await fake.fetch_open_interest("BTCUSDT")


async def test_fetch_candles_filters_by_symbol_timeframe_and_window() -> None:
    from hunter_core.domain.market import NormalizedCandle

    in_window = NormalizedCandle(
        exchange="fake",
        symbol="BTCUSDT",
        timeframe=Timeframe.M1,
        open_time=datetime(2026, 1, 1, 0, 1, tzinfo=UTC),
        close_time=datetime(2026, 1, 1, 0, 2, tzinfo=UTC),
        open=Decimal("1"),
        high=Decimal("1"),
        low=Decimal("1"),
        close=Decimal("1"),
        volume=Decimal("1"),
        is_final=True,
    )
    fake = FakeExchangeAdapter(candles=[in_window])

    result = await fake.fetch_candles(
        "BTCUSDT", Timeframe.M1, datetime(2026, 1, 1, tzinfo=UTC), datetime(2026, 1, 2, tzinfo=UTC)
    )

    assert result == [in_window]
