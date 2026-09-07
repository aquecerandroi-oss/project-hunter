"""T3.0c — ``/api/v1/markets`` and the second listing of a symbol.

Two things are asserted here, and the first matters more than the second:

1. **the default did not change.** The collector now writes spot rows into
   ``markets``; without an explicit filter they would appear in the Markets
   page and in its ``summary`` counts, unannounced, from a task that is not
   allowed to touch ``apps/web``;
2. ``?market_type=spot`` reaches the tradable spot universe.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable
from typing import TYPE_CHECKING

import pytest
from sqlalchemy import select

from hunter_core.db.models.markets import Asset, Exchange, Market
from hunter_core.domain.enums import MarketType

from .conftest import Actor

if TYPE_CHECKING:
    import httpx
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

pytestmark = pytest.mark.integration


async def _seed_both_listings(
    session_factory: async_sessionmaker[AsyncSession],
) -> tuple[str, str]:
    """One exchange, one symbol, **two** rows: perpetual and spot."""
    suffix = uuid.uuid4().hex[:10]
    exchange_code = f"testex{suffix}"
    symbol = f"TEST{suffix.upper()}USDT"
    async with session_factory() as session:
        exchange = Exchange(code=exchange_code, name=exchange_code)
        base_asset = Asset(symbol=f"BASE{suffix}")
        session.add_all([exchange, base_asset])
        await session.flush()
        quote_asset = (
            await session.execute(select(Asset).where(Asset.symbol == "USDT"))
        ).scalar_one_or_none()
        if quote_asset is None:
            quote_asset = Asset(symbol="USDT")
            session.add(quote_asset)
            await session.flush()
        for market_type in (MarketType.PERPETUAL, MarketType.SPOT):
            session.add(
                Market(
                    exchange_id=exchange.id,
                    symbol=symbol,
                    market_type=market_type,
                    base_asset_id=base_asset.id,
                    quote_asset_id=quote_asset.id,
                    is_monitored=True,
                    monitor_rank=1,
                )
            )
        await session.commit()
    return exchange_code, symbol


async def test_the_default_page_still_answers_only_the_perpetual_universe(
    client: httpx.AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    make_actor: Callable[[str], Actor],
) -> None:
    exchange, symbol = await _seed_both_listings(session_factory)
    actor: Actor = make_actor("markets-spot-default")

    response = await client.get(f"/api/v1/markets?exchange={exchange}", headers=actor.headers)

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["summary"]["markets_total"] == 1
    assert [(row["symbol"], row["market_type"]) for row in body["items"]] == [(symbol, "perpetual")]


async def test_market_type_spot_returns_the_spot_listing(
    client: httpx.AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    make_actor: Callable[[str], Actor],
) -> None:
    exchange, symbol = await _seed_both_listings(session_factory)
    actor: Actor = make_actor("markets-spot-filter")

    response = await client.get(
        f"/api/v1/markets?exchange={exchange}&market_type=spot", headers=actor.headers
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["summary"]["markets_total"] == 1
    assert [(row["symbol"], row["market_type"]) for row in body["items"]] == [(symbol, "spot")]


async def test_an_unknown_market_type_is_refused_rather_than_ignored(
    client: httpx.AsyncClient, make_actor: Callable[[str], Actor]
) -> None:
    """A typo must not silently fall back to the perpetual page."""
    actor: Actor = make_actor("markets-spot-bad")

    response = await client.get("/api/v1/markets?market_type=sp0t", headers=actor.headers)

    assert response.status_code == 422, response.text
