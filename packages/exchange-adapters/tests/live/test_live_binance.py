"""Contract test against the real Binance public API.

Never runs in CI (``docs/EXCHANGE_INTEGRATION.md`` §6): only when a human
explicitly opts in with ``HUNTER_LIVE_TESTS=1``, e.g.

    HUNTER_LIVE_TESTS=1 uv run pytest packages/exchange-adapters -m live
"""

from __future__ import annotations

import asyncio
import os
from typing import Any

import pytest

from hunter_exchanges.base import StreamChannel
from hunter_exchanges.binance.rest import BinanceRestClient
from hunter_exchanges.binance.ws import BinanceWsClient

pytestmark = [
    pytest.mark.live,
    pytest.mark.skipif(
        os.environ.get("HUNTER_LIVE_TESTS") != "1",
        reason="set HUNTER_LIVE_TESTS=1 to hit the real Binance public API",
    ),
]


async def test_fetch_ticker_returns_a_live_btcusdt_price() -> None:
    client = BinanceRestClient()
    try:
        ticker = await client.fetch_ticker("BTCUSDT")
    finally:
        await client.aclose()

    assert ticker.symbol == "BTCUSDT"
    assert ticker.last > 0


async def test_server_time_returns_a_live_clock() -> None:
    client = BinanceRestClient()
    try:
        server_time = await client.server_time()
    finally:
        await client.aclose()

    assert server_time.year >= 2026


async def test_stream_receives_real_data_on_both_public_and_market_routes() -> None:
    """F16: the joint checklist's "an ACK alone does not prove data was
    received" applies to the live stream too, not just REST. Opens the real
    combined-stream connections for one symbol and asserts a genuine data
    payload arrives on *both* routes: ``BOOK_TICKER`` (``/public``, once a
    trade has established a last price) and ``TRADES`` (``/market``). Hard
    60s timeout so a Binance outage never hangs a human's terminal (or CI,
    which never sets ``HUNTER_LIVE_TESTS`` in the first place)."""
    client = BinanceWsClient()
    # `AsyncIterator` (the Protocol's declared return type) has no `aclose`;
    # the concrete implementation is always an async generator, which does
    # (same pattern as `ws_test_helpers.collect`).
    agen: Any = client.stream(
        ["BTCUSDT"], [StreamChannel.BOOK_TICKER, StreamChannel.TRADES]
    ).__aiter__()
    seen_routes: set[str] = set()
    try:
        async with asyncio.timeout(60):
            while seen_routes != {"public", "market"}:
                event = await agen.__anext__()
                if event.kind == "ticker":
                    seen_routes.add("public")
                elif event.kind == "trade":
                    seen_routes.add("market")
    finally:
        await agen.aclose()
        await client.aclose()

    assert seen_routes == {"public", "market"}
