"""Contract test against the real Binance **SPOT** public API.

Never runs in CI (``docs/EXCHANGE_INTEGRATION.md`` §6): only when a human
opts in explicitly, e.g.

    HUNTER_LIVE_TESTS=1 uv run pytest packages/exchange-adapters -m live

No API key is used (public endpoints only), and every test has a hard
timeout so a Binance outage can never hang a terminal.
"""

from __future__ import annotations

import asyncio
import os
import time
from collections import Counter
from typing import Any

import pytest

from hunter_core.domain.enums import MarketType
from hunter_exchanges.base import StreamChannel
from hunter_exchanges.binance_spot.rest import REQUEST_WEIGHT_CAPACITY, BinanceSpotRestClient
from hunter_exchanges.binance_spot.ws import BinanceSpotWsClient

pytestmark = [
    pytest.mark.live,
    pytest.mark.skipif(
        os.environ.get("HUNTER_LIVE_TESTS") != "1",
        reason="set HUNTER_LIVE_TESTS=1 to hit the real Binance spot API",
    ),
]

STREAM_SECONDS = 20.0


async def test_exchange_info_still_reports_the_weight_budget_we_assume() -> None:
    """If Binance changes the spot REQUEST_WEIGHT limit, this fails loudly
    instead of the token bucket silently assuming the old number."""
    client = BinanceSpotRestClient()
    try:
        capacity, period_s = await client.refresh_request_weight_limit()
    finally:
        await client.aclose()

    assert (capacity, period_s) == (REQUEST_WEIGHT_CAPACITY, 60.0)


async def test_the_tradable_universe_floor_is_measurable_on_spot() -> None:
    """D1: the universe is spot pairs with >= 50M USDT of 24h volume **on
    spot**. This checks the two calls that produce it really work together."""
    client = BinanceSpotRestClient()
    try:
        markets = await client.list_markets(MarketType.SPOT)
        tickers = await client.fetch_tickers_24h()
    finally:
        await client.aclose()

    symbols = {m.symbol for m in markets}
    eligible = [
        t
        for t in tickers
        if t.symbol in symbols
        and t.quote_volume_24h is not None
        and t.quote_volume_24h >= 50_000_000
    ]
    print(f"\nspot USDT pairs: {len(symbols)}; >= 50M USDT/24h: {len(eligible)}")
    assert eligible, "no spot pair over the 50M floor - suspicious, check the data"
    assert "BTCUSDT" in {t.symbol for t in eligible}


async def test_market_order_filters_are_present_for_the_pairs_we_would_trade() -> None:
    client = BinanceSpotRestClient()
    try:
        filters = await client.fetch_filters(["BTCUSDT", "ETHUSDT", "SOLUSDT"])
        avg = await client.fetch_avg_price("BTCUSDT")
    finally:
        await client.aclose()

    btc = filters["BTCUSDT"]
    check = btc.check_market_order(btc.min_qty, avg_price=avg.price)
    print(f"\nBTCUSDT min_qty={btc.min_qty} avg={avg.price} -> {check}")
    assert btc.step_size > 0
    assert btc.min_notional is not None


async def test_three_live_streams_deliver_data_within_twenty_seconds() -> None:
    """Opens the three streams the paper wallet needs (trades, best bid/ask,
    top-20 book) for 20s and reports what actually arrived - the honest
    measurement of "is this connection carrying data", not an ACK."""
    client = BinanceSpotWsClient()
    agen: Any = client.stream(
        ["BTCUSDT", "ETHUSDT"],
        [StreamChannel.TRADES, StreamChannel.BOOK_TICKER, StreamChannel.BOOK],
    ).__aiter__()
    kinds: Counter[str] = Counter()
    started = time.monotonic()
    deadline = started + STREAM_SECONDS
    last_event_at = started
    try:
        # An explicit deadline per event, not one ``asyncio.timeout`` around
        # the whole loop. The rate is measured to the **last event**, not to
        # the moment the timeout unwinds: cancelling ``stream()`` runs the
        # adapter's own teardown (``on_close``) inside the cancellation, so
        # wall time after the last event is shutdown, not streaming.
        while (remaining := deadline - time.monotonic()) > 0:
            try:
                async with asyncio.timeout(remaining):
                    event = await agen.__anext__()
            except TimeoutError:
                break
            last_event_at = time.monotonic()
            kinds[f"{event.kind}:{event.symbol}"] += 1  # type: ignore[union-attr]
    finally:
        wall = time.monotonic() - started
        await agen.aclose()
        await client.aclose()

    elapsed = last_event_at - started
    total = sum(kinds.values())
    print(
        f"\n{total} events in {elapsed:.1f}s of streaming ({total / elapsed:.1f}/s), "
        f"{wall:.1f}s wall including teardown; breakdown={dict(kinds)}; "
        f"out_of_sequence={client.out_of_sequence_count}; "
        f"duplicates={client.duplicate_book_count}; "
        f"malformed={client.malformed_count}; generation={client.connection_generation()}"
    )
    assert any(k.startswith("trade:") for k in kinds), "no trades arrived"
    assert any(k.startswith("book:") for k in kinds), "no book snapshots arrived"
    assert any(k.startswith("ticker:") for k in kinds), "no bookTicker arrived"
    assert client.malformed_count == 0
