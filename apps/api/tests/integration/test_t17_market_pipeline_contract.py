"""T1.7: the API decodes what the REAL ``hunter_market_worker`` ingest path
actually writes -- not a hand-rolled msgpack replica of the wire format.

``test_markets_api.py`` (T1.4's own suite) seeds Redis with its own
``_write_book_and_trades``/``_write_ticker`` helpers that reimplement the
``hot_state.py`` wire shape by hand; that is correct for testing the API in
isolation, but it can never fail if the two shapes drift apart from each
other. This file closes exactly that gap (``.claude/state/review-T1.7.md``
(c): "senão o E2E passa contra uma ficção") by calling
``hunter_market_worker.ingest.handle_event`` -- the actual, stable dispatch
entry point ``run_market``'s ingest task calls for every event kind, per the
brief's "program against public contracts ... so your tests survive internal
refactors" (the lower-level ``hot_state.write_*`` functions are exactly the
kind of internal surface a concurrent optimization task may reshape, and one
did mid-session: see the T1.7 report's contract-gap note) -- and asserting
the API (``apps/api``, T1.4) reads the result back correctly.

Uses ``apps/api/tests/integration/conftest.py``'s own fixtures (not
``tests/integration/conftest.py``'s -- a deliberate, separate database, per
that conftest's own docstring on why it does not import across the
workspace-member boundary).
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator, Callable
from decimal import Decimal
from typing import TYPE_CHECKING

import pytest
import pytest_asyncio
import redis.asyncio as redis_asyncio
from sqlalchemy import select

from hunter_core.db.models.markets import Asset, Exchange, Market
from hunter_core.domain.enums import MarketType, OrderSide
from hunter_core.domain.market import (
    BookLevel,
    NormalizedOrderBook,
    NormalizedTicker,
    NormalizedTrade,
)
from hunter_core.domain.types import utcnow
from hunter_market_worker import hot_state
from hunter_market_worker.ingest import AcceptedEvents, TickCoalescer, flush_ticks, handle_event
from hunter_market_worker.persist import PersistQueues

from .conftest import Actor

if TYPE_CHECKING:
    import httpx
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

pytestmark = pytest.mark.integration


@pytest_asyncio.fixture
async def redis_client(redis_url: str) -> AsyncIterator[redis_asyncio.Redis]:
    client = redis_asyncio.from_url(redis_url, decode_responses=False)
    try:
        yield client
    finally:
        await client.aclose()


async def _seed_market(session_factory: async_sessionmaker[AsyncSession]) -> tuple[str, str]:
    suffix = uuid.uuid4().hex[:10]
    exchange_code = f"t17ex{suffix}"
    symbol = f"T17{suffix.upper()}USDT"
    async with session_factory() as session:
        exchange = Exchange(code=exchange_code, name=exchange_code)
        base_asset = Asset(symbol=f"T17BASE{suffix}")
        session.add_all([exchange, base_asset])
        await session.flush()
        quote_asset = (
            await session.execute(select(Asset).where(Asset.symbol == "USDT"))
        ).scalar_one_or_none()
        if quote_asset is None:
            quote_asset = Asset(symbol="USDT")
            session.add(quote_asset)
            await session.flush()
        session.add(
            Market(
                exchange_id=exchange.id,
                symbol=symbol,
                market_type=MarketType.PERPETUAL,
                base_asset_id=base_asset.id,
                quote_asset_id=quote_asset.id,
                is_monitored=True,
                monitor_rank=1,
            )
        )
        await session.commit()
    return exchange_code, symbol


async def test_api_decodes_the_real_hot_state_writers_book_ticker_and_trades(
    client: httpx.AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    redis_client: redis_asyncio.Redis,
    make_actor: Callable[[str], Actor],
) -> None:
    exchange, symbol = await _seed_market(session_factory)

    ticker = NormalizedTicker(
        exchange=exchange,
        symbol=symbol,
        ts=utcnow(),
        last=Decimal("123.45"),
        bid=Decimal("123.40"),
        ask=Decimal("123.50"),
        volume_24h=Decimal("1000"),
        quote_volume_24h=Decimal("100000"),
    )
    book = NormalizedOrderBook(
        exchange=exchange,
        symbol=symbol,
        ts=utcnow(),
        bids=[BookLevel(price=Decimal("123.40"), qty=Decimal("5"))],
        asks=[BookLevel(price=Decimal("123.50"), qty=Decimal("2"))],
        is_snapshot=True,
    )
    trade = NormalizedTrade(
        exchange=exchange,
        symbol=symbol,
        ts=utcnow(),
        trade_id="t17-1",
        price=Decimal("123.46"),
        qty=Decimal("0.5"),
        side=OrderSide.SELL,
    )

    queues, coalescer, accepted = PersistQueues(), TickCoalescer(), AcceptedEvents()
    trade_memory = hot_state.TradeMemory()
    producer = "market-worker@t17-contract:1"
    args = (redis_client, producer, queues, coalescer, accepted, trade_memory)
    assert await handle_event(ticker, *args)
    assert await handle_event(book, *args)
    assert await handle_event(trade, *args)
    # Ticker/book hot state is written by the coalescer's own flush, not
    # immediately by `handle_event` (B3, hunter_market_worker/ingest.py) --
    # the API reads Redis directly, so this test must flush first.
    await flush_ticks(coalescer, redis_client, producer)

    actor: Actor = make_actor("t17-contract-reader")
    response = await client.get(f"/api/v1/markets/{exchange}/{symbol}", headers=actor.headers)

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["last_price"] == "123.45"
    assert body["book"]["bids"][0]["price"] == "123.40"
    assert body["book"]["asks"][0]["price"] == "123.50"
    assert body["book"]["kind"] == "snapshot"
    assert body["book"]["depth"] == 20
    assert len(body["recent_trades"]) == 1
    assert body["recent_trades"][0]["trade_id"] == "t17-1"
    assert body["recent_trades"][0]["side"] == "sell"
    assert body["recent_trades"][0]["price"] == "123.46"


async def test_a_late_duplicate_ticker_write_is_rejected_and_the_api_never_sees_it(
    client: httpx.AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    redis_client: redis_asyncio.Redis,
    make_actor: Callable[[str], Actor],
) -> None:
    """T1.2/T1.3 invariant re-checked from the API's side: a duplicate/late
    ticker write through the real writer must not rejuvenate what the API
    reports as the last price."""
    exchange, symbol = await _seed_market(session_factory)
    fresh = NormalizedTicker(
        exchange=exchange,
        symbol=symbol,
        ts=utcnow(),
        last=Decimal("100"),
        bid=Decimal("99.9"),
        ask=Decimal("100.1"),
        volume_24h=Decimal("1"),
        quote_volume_24h=Decimal("100"),
    )
    queues, coalescer, accepted = PersistQueues(), TickCoalescer(), AcceptedEvents()
    trade_memory = hot_state.TradeMemory()
    producer = "market-worker@t17-contract:1"
    args = (redis_client, producer, queues, coalescer, accepted, trade_memory)
    assert await handle_event(fresh, *args)

    from datetime import timedelta

    stale = fresh.model_copy(update={"last": Decimal("1"), "ts": fresh.ts - timedelta(seconds=1)})
    # `accepted` (not a fresh instance) is reused deliberately: this is the
    # SAME in-process watermark that just accepted `fresh` -- a late ticker
    # is now rejected in-memory (B3), never even reaching Redis.
    assert not await handle_event(stale, *args)
    await flush_ticks(coalescer, redis_client, producer)

    actor: Actor = make_actor("t17-contract-stale-reject")
    response = await client.get("/api/v1/markets", params={"q": symbol}, headers=actor.headers)
    assert response.status_code == 200, response.text
    row = next(item for item in response.json()["items"] if item["symbol"] == symbol)
    assert row["last_price"] == "100"
