"""Records the **whole** spot ``ticker/24hr`` USDT slice for universe tests.

    uv run python -m hunter_exchanges.testing.record_spot_universe

Sibling of :mod:`hunter_exchanges.testing.record_spot`, kept separate because
it is the one fixture that must **not** be trimmed to a handful of rows: the
tradable universe is a *floor* (D1: ``quote_volume_24h >= 50M USDT`` measured
on spot), and a floor applied to five hand-picked megacaps proves nothing.
Every USDT-quoted row of one real ``GET /api/v3/ticker/24hr`` snapshot is kept
verbatim, so the test can assert how many pairs the floor actually admits out
of how many listed.

Non-USDT quotes are dropped (the adapter never sees them: ``parse_exchange_info``
filters on ``quoteAsset``) and nothing else is touched — no row is edited, no
row is synthesised.

Deliberately not a test: it hits the network and overwrites a fixture.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

import httpx

from hunter_core.logging import get_logger

logger = get_logger(__name__)

REST_BASE = "https://api.binance.com"
FIXTURES_DIR = Path(__file__).parent / "fixtures"
FIXTURE_NAME = "spot_universe_ticker_24hr.json"
QUOTE = "USDT"


def usdt_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Every row whose symbol is quoted in USDT, in the exchange's own order."""
    return [row for row in rows if str(row.get("symbol", "")).endswith(QUOTE)]


async def main() -> None:
    FIXTURES_DIR.mkdir(parents=True, exist_ok=True)
    async with httpx.AsyncClient(base_url=REST_BASE, timeout=30.0) as client:
        response = await client.get("/api/v3/ticker/24hr")
        response.raise_for_status()
        rows = usdt_rows(response.json())
    path = FIXTURES_DIR / FIXTURE_NAME
    path.write_text(json.dumps(rows, indent=2, sort_keys=False) + "\n", encoding="utf-8")
    logger.info("fixture_written", path=str(path), rows=len(rows))


if __name__ == "__main__":
    asyncio.run(main())
