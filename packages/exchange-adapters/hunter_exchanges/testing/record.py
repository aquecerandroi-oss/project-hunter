"""One-off script that records small real Binance USDS-M Futures responses
into ``hunter_exchanges/testing/fixtures/`` for offline, deterministic tests.

Run once, by hand, when a fixture needs refreshing:

    uv run python -m hunter_exchanges.testing.record

Only public endpoints are called (no API key). REST responses are trimmed to
~5 symbols where the payload is a list keyed by symbol. WebSocket messages
are captured by opening the real combined-stream connection for a short,
bounded time per channel and keeping the first message seen; a channel that
does not fire within its budget (this is common for ``forceOrder`` —
liquidations are infrequent — outside of high volatility) is left alone, and
the checked-in fixture for it is instead hand-built from the documented
Binance message shape (``docs/EXCHANGE_INTEGRATION.md`` §4, Binance
Futures WebSocket Market Streams docs) — this is noted in each such file's
sibling ``.provenance.txt`` if one exists, and in the task's final report.

This script is deliberately not a test: it hits the network on purpose and
overwrites fixtures, so it is never imported by pytest.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

import httpx
import websockets

from hunter_core.logging import get_logger

logger = get_logger(__name__)

REST_BASE = "https://fapi.binance.com"
PUBLIC_WS_BASE = "wss://fstream.binance.com/public/stream?streams="
MARKET_WS_BASE = "wss://fstream.binance.com/market/stream?streams="
FIXTURES_DIR = Path(__file__).parent / "fixtures"
SYMBOL = "BTCUSDT"
TRIM_SYMBOLS = 5
WS_TIMEOUT_S = 20.0


def _write(name: str, data: Any) -> None:
    path = FIXTURES_DIR / name
    path.write_text(json.dumps(data, indent=2, sort_keys=False) + "\n", encoding="utf-8")
    logger.info("fixture_written", path=str(path))


def select_exchange_info_symbols(symbols: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """``TRIM_SYMBOLS`` USDT perpetuals (the common case) plus one row for
    each edge case several tests depend on (F15): a delisted/``SETTLING``
    market, a non-USDT quote, and a dated/quarterly future. A blind
    ``[:TRIM_SYMBOLS]`` truncation of "USDT perpetuals only" silently drops
    all three on every re-run of this recorder — they are real recorded
    payloads (not fabricated), kept here deliberately.
    """
    usdt_perp_trading = [
        s
        for s in symbols
        if s.get("quoteAsset") == "USDT"
        and s.get("contractType") == "PERPETUAL"
        and s.get("status") == "TRADING"
    ][:TRIM_SYMBOLS]
    settling = next((s for s in symbols if s.get("status") == "SETTLING"), None)
    non_usdt_quote = next((s for s in symbols if s.get("quoteAsset") not in (None, "USDT")), None)
    quarterly = next((s for s in symbols if s.get("contractType") not in (None, "PERPETUAL")), None)
    seen = {s["symbol"] for s in usdt_perp_trading}
    for edge_case in (settling, non_usdt_quote, quarterly):
        if edge_case is not None and edge_case["symbol"] not in seen:
            usdt_perp_trading.append(edge_case)
            seen.add(edge_case["symbol"])
    return usdt_perp_trading


async def _record_rest(client: httpx.AsyncClient) -> None:
    server_time = (await client.get("/fapi/v1/time")).json()
    _write("server_time.json", server_time)

    exchange_info = (await client.get("/fapi/v1/exchangeInfo")).json()
    trimmed_info = {
        **exchange_info,
        "symbols": select_exchange_info_symbols(exchange_info["symbols"]),
    }
    _write("exchange_info.json", trimmed_info)

    klines = (
        await client.get("/fapi/v1/klines", params={"symbol": SYMBOL, "interval": "1m", "limit": 5})
    ).json()
    _write("klines.json", klines)

    ticker = (await client.get("/fapi/v1/ticker/24hr", params={"symbol": SYMBOL})).json()
    _write("ticker_24hr.json", ticker)

    all_tickers = (await client.get("/fapi/v1/ticker/24hr")).json()
    _write("ticker_24hr_all.json", all_tickers[:TRIM_SYMBOLS])

    depth = (await client.get("/fapi/v1/depth", params={"symbol": SYMBOL, "limit": 20})).json()
    _write("depth.json", depth)

    premium_index = (await client.get("/fapi/v1/premiumIndex", params={"symbol": SYMBOL})).json()
    _write("premium_index.json", premium_index)

    funding_rate = (
        await client.get("/fapi/v1/fundingRate", params={"symbol": SYMBOL, "limit": 1})
    ).json()
    _write("funding_rate.json", funding_rate)

    funding_rate_history = (
        await client.get("/fapi/v1/fundingRate", params={"symbol": SYMBOL, "limit": 5})
    ).json()
    _write("funding_rate_history.json", funding_rate_history)

    open_interest = (await client.get("/fapi/v1/openInterest", params={"symbol": SYMBOL})).json()
    _write("open_interest.json", open_interest)


async def _capture_one(base_url: str, stream_name: str) -> dict[str, Any] | None:
    url = f"{base_url}{stream_name}"
    try:
        async with websockets.connect(url, open_timeout=10) as ws:
            raw = await asyncio.wait_for(ws.recv(), timeout=WS_TIMEOUT_S)
    except (TimeoutError, OSError) as exc:
        logger.warning(
            "ws_capture_timed_out", stream=stream_name, timeout_s=WS_TIMEOUT_S, error=str(exc)
        )
        return None
    payload = json.loads(raw)
    return payload["data"]


async def _record_ws() -> None:
    # Book/bid-ask on /public/stream, everything else on /market/stream
    # (Binance's Important WebSocket Change Notice; docs/plans/M1.md "Decisão
    # conjunta" — see also hunter_exchanges.binance.streams.route_for_channel).
    public_channels = {
        "ws_book_ticker.json": f"{SYMBOL.lower()}@bookTicker",
        "ws_depth20.json": f"{SYMBOL.lower()}@depth20",
    }
    market_channels = {
        "ws_agg_trade.json": f"{SYMBOL.lower()}@aggTrade",
        "ws_kline_1m.json": f"{SYMBOL.lower()}@kline_1m",
        "ws_mark_price.json": f"{SYMBOL.lower()}@markPrice@1s",
        "ws_force_order.json": f"{SYMBOL.lower()}@forceOrder",
    }
    for base_url, channels in (
        (PUBLIC_WS_BASE, public_channels),
        (MARKET_WS_BASE, market_channels),
    ):
        for filename, stream_name in channels.items():
            logger.info("ws_capture_started", stream=stream_name)
            data = await _capture_one(base_url, stream_name)
            if data is not None:
                _write(filename, data)


async def main() -> None:
    FIXTURES_DIR.mkdir(parents=True, exist_ok=True)
    async with httpx.AsyncClient(base_url=REST_BASE, timeout=10.0) as client:
        await _record_rest(client)
    await _record_ws()


if __name__ == "__main__":
    asyncio.run(main())
