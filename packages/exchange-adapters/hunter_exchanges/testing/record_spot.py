"""One-off script that records small real Binance **SPOT** responses into
``hunter_exchanges/testing/fixtures/`` (``spot_*.json``) for offline tests.

Run by hand when a fixture needs refreshing:

    uv run python -m hunter_exchanges.testing.record_spot

Sibling of :mod:`hunter_exchanges.testing.record` (USDS-M Futures), kept
separate because every URL, weight and payload shape differs: ``/api/v3``
instead of ``/fapi/v1``, ``wss://stream.binance.com:9443`` instead of
``fstream``. Only public endpoints (no API key). REST list payloads are
trimmed to a handful of rows; ``exchangeInfo`` keeps the USDT pairs the
universe cares about plus the edge cases the tests need (a non-``TRADING``
symbol, a non-USDT quote) and the whole ``rateLimits`` block, which is the
authority for the REST budget in ``binance_spot/rest.py``.

WebSocket frames are captured from the real combined stream and stored
**with their envelope** (``{"stream": ..., "data": ...}``): on spot the
partial-depth payload carries no symbol at all, so the stream name is part
of the message's meaning, not decoration.

Deliberately not a test: it hits the network and overwrites fixtures.
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

REST_BASE = "https://api.binance.com"
WS_BASE = "wss://stream.binance.com:9443/stream?streams="
FIXTURES_DIR = Path(__file__).parent / "fixtures"
SYMBOL = "BTCUSDT"
TRIM_SYMBOLS = 5
WS_TIMEOUT_S = 30.0


def _symbols_param(symbols: list[str]) -> str:
    """Binance rejects the spaces ``json.dumps`` puts after each comma."""
    return json.dumps(symbols, separators=(",", ":"))


def _write(name: str, data: Any) -> None:
    path = FIXTURES_DIR / name
    path.write_text(json.dumps(data, indent=2, sort_keys=False) + "\n", encoding="utf-8")
    logger.info("fixture_written", path=str(path))


def select_exchange_info_symbols(symbols: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """``TRIM_SYMBOLS`` USDT spot pairs plus one row per edge case the tests
    depend on: a symbol that is not ``TRADING`` (halted/delisted) and a
    non-USDT quote. A blind ``[:TRIM_SYMBOLS]`` truncation drops both on
    every re-run — they are real recorded rows, never fabricated."""
    wanted = ("BTCUSDT", "ETHUSDT", "BNBUSDT", "SOLUSDT", "XRPUSDT")
    by_symbol = {s["symbol"]: s for s in symbols}
    selected = [by_symbol[s] for s in wanted if s in by_symbol][:TRIM_SYMBOLS]
    seen = {s["symbol"] for s in selected}
    not_trading = next((s for s in symbols if s.get("status") != "TRADING"), None)
    non_usdt = next((s for s in symbols if s.get("quoteAsset") not in (None, "USDT")), None)
    for edge_case in (not_trading, non_usdt):
        if edge_case is not None and edge_case["symbol"] not in seen:
            selected.append(edge_case)
            seen.add(edge_case["symbol"])
    return selected


async def _record_rest(client: httpx.AsyncClient) -> None:
    _write("spot_server_time.json", (await client.get("/api/v3/time")).json())

    exchange_info = (await client.get("/api/v3/exchangeInfo")).json()
    _write(
        "spot_exchange_info.json",
        {**exchange_info, "symbols": select_exchange_info_symbols(exchange_info["symbols"])},
    )

    klines = (
        await client.get("/api/v3/klines", params={"symbol": SYMBOL, "interval": "1m", "limit": 5})
    ).json()
    _write("spot_klines.json", klines)

    _write(
        "spot_ticker_24hr.json",
        (await client.get("/api/v3/ticker/24hr", params={"symbol": SYMBOL})).json(),
    )
    all_tickers = (
        await client.get(
            "/api/v3/ticker/24hr",
            params={
                "symbols": _symbols_param(["BTCUSDT", "ETHUSDT", "BNBUSDT", "SOLUSDT", "XRPUSDT"])
            },
        )
    ).json()
    _write("spot_ticker_24hr_all.json", all_tickers)

    for limit, name in ((20, "spot_depth.json"), (100, "spot_depth_100.json")):
        depth = (
            await client.get("/api/v3/depth", params={"symbol": SYMBOL, "limit": limit})
        ).json()
        _write(name, depth)

    _write(
        "spot_trades.json",
        (await client.get("/api/v3/trades", params={"symbol": SYMBOL, "limit": 5})).json(),
    )
    _write(
        "spot_agg_trades.json",
        (await client.get("/api/v3/aggTrades", params={"symbol": SYMBOL, "limit": 5})).json(),
    )
    _write(
        "spot_avg_price.json",
        (await client.get("/api/v3/avgPrice", params={"symbol": SYMBOL})).json(),
    )


async def _record_ws() -> None:
    """One connection, four streams; keep the first frame of each."""
    low = SYMBOL.lower()
    wanted = {
        f"{low}@kline_1m": "spot_ws_kline_1m.json",
        f"{low}@depth20@100ms": "spot_ws_depth20.json",
        f"{low}@aggTrade": "spot_ws_agg_trade.json",
        f"{low}@bookTicker": "spot_ws_book_ticker.json",
    }
    url = WS_BASE + "/".join(wanted)
    pending = dict(wanted)
    try:
        async with websockets.connect(url, open_timeout=10) as ws:
            while pending:
                raw = await asyncio.wait_for(ws.recv(), timeout=WS_TIMEOUT_S)
                envelope: dict[str, Any] = json.loads(raw)
                name = pending.pop(envelope["stream"], None)
                if name is not None:
                    _write(name, envelope)
    except (TimeoutError, OSError) as exc:
        logger.warning("ws_capture_timed_out", pending=sorted(pending), error=str(exc))


async def main() -> None:
    FIXTURES_DIR.mkdir(parents=True, exist_ok=True)
    async with httpx.AsyncClient(base_url=REST_BASE, timeout=15.0) as client:
        await _record_rest(client)
    await _record_ws()


if __name__ == "__main__":
    asyncio.run(main())
