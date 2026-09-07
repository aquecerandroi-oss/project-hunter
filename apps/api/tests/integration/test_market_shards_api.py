"""T2.5g — ``/system/market-status`` and ``/markets`` over N collector shards.

With ``MARKET_SHARD=i/N`` the collector writes one heartbeat per shard
(``hb:market:{exchange}:{i}of{N}``). The API is the only place that can say
"4 shards, 200 markets" honestly: it must union the shards, refuse to call a
partial cluster healthy, and never fabricate a topology nobody declared.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator, Callable
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

import pytest
import pytest_asyncio
import redis.asyncio as redis_asyncio

from hunter_core.db.models.markets import Exchange, Market
from hunter_core.domain.enums import MarketType
from hunter_core.redis import keys

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


async def _seed(session_factory: async_sessionmaker[AsyncSession], markets: int) -> str:
    code = f"shardex{uuid.uuid4().hex[:10]}"
    async with session_factory() as session:
        exchange = Exchange(code=code, name=code)
        session.add(exchange)
        await session.flush()
        for index in range(markets):
            session.add(
                Market(
                    exchange_id=exchange.id,
                    symbol=f"S{index}USDT",
                    market_type=MarketType.PERPETUAL,
                    is_monitored=True,
                    monitor_rank=index,
                )
            )
        await session.commit()
    return code


async def _write_shard(
    redis: redis_asyncio.Redis,
    code: str,
    index: int,
    total: int,
    *,
    ws_state: str = "connected",
    last_event_at: datetime | None = None,
    reconnects: int = 1,
    subscriptions: int = 300,
) -> str:
    key = keys.market_heartbeat(code, index, total)
    now = datetime.now(UTC)
    await redis.hset(  # type: ignore[reportUnknownMemberType]
        key,
        mapping={
            "ts": now.isoformat(),
            "errors": "0",
            "last_event_at": (last_event_at or now).isoformat(),
            "ws_state": ws_state,
            "reconnects": str(reconnects),
            "subscriptions": str(subscriptions),
            "markets_monitored": "50",
            "open_gaps": "7",
            "rest_gate": "ok",
            "shard_index": str(index),
            "shard_total": str(total),
        },
    )
    await redis.expire(key, 30)
    return key


async def test_four_shards_are_one_exchange_row_with_the_topology_named(
    client: httpx.AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    redis_client: redis_asyncio.Redis,
    make_actor: Callable[[str], Actor],
) -> None:
    code = await _seed(session_factory, markets=8)
    oldest = datetime.now(UTC) - timedelta(seconds=4)
    keys_written = [
        await _write_shard(redis_client, code, 0, 4, reconnects=2),
        await _write_shard(redis_client, code, 1, 4, reconnects=1, last_event_at=oldest),
        await _write_shard(redis_client, code, 2, 4, reconnects=0),
        await _write_shard(redis_client, code, 3, 4, reconnects=0),
    ]
    try:
        actor: Actor = make_actor("shards-reader-1")
        response = await client.get("/api/v1/system/market-status", headers=actor.headers)

        assert response.status_code == 200, response.text
        entry = next(row for row in response.json()["exchanges"] if row["exchange"] == code)
        assert entry["ws_state"] == "connected"
        assert entry["shards_expected"] == 4
        assert entry["shards_reporting"] == 4
        # Postgres decides how many markets exist, never the shards' own counts.
        assert entry["markets_monitored"] == 8
        assert entry["reconnects"] == 3
        # The most-behind shard is the honest "last event" of the exchange.
        assert entry["last_event_at"] is not None
        assert entry["last_event_age_ms"] >= 3500
    finally:
        await redis_client.delete(*keys_written)


async def test_a_missing_shard_makes_the_exchange_stale_instead_of_connected(
    client: httpx.AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    redis_client: redis_asyncio.Redis,
    make_actor: Callable[[str], Actor],
) -> None:
    """The M1 blocker in one assertion: with a shared hash a dead shard was
    invisible and the page kept reading ``connected``."""
    code = await _seed(session_factory, markets=8)
    keys_written = [
        await _write_shard(redis_client, code, 0, 4),
        await _write_shard(redis_client, code, 1, 4),
        await _write_shard(redis_client, code, 3, 4),
    ]
    try:
        actor: Actor = make_actor("shards-reader-2")
        response = await client.get("/api/v1/system/market-status", headers=actor.headers)

        entry = next(row for row in response.json()["exchanges"] if row["exchange"] == code)
        assert entry["ws_state"] == "stale"
        assert entry["shards_expected"] == 4
        assert entry["shards_reporting"] == 3
    finally:
        await redis_client.delete(*keys_written)


async def test_the_worst_shard_state_wins(
    client: httpx.AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    redis_client: redis_asyncio.Redis,
    make_actor: Callable[[str], Actor],
) -> None:
    code = await _seed(session_factory, markets=4)
    keys_written = [
        await _write_shard(redis_client, code, 0, 2),
        await _write_shard(redis_client, code, 1, 2, ws_state="reconnecting"),
    ]
    try:
        actor: Actor = make_actor("shards-reader-3")
        response = await client.get("/api/v1/system/market-status", headers=actor.headers)

        entry = next(row for row in response.json()["exchanges"] if row["exchange"] == code)
        assert entry["ws_state"] == "reconnecting"
        assert entry["shards_reporting"] == 2
    finally:
        await redis_client.delete(*keys_written)


async def test_a_solo_collector_still_reports_one_shard(
    client: httpx.AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    redis_client: redis_asyncio.Redis,
    make_actor: Callable[[str], Actor],
) -> None:
    code = await _seed(session_factory, markets=2)
    key = keys.heartbeat("market", code)
    await redis_client.hset(  # type: ignore[reportUnknownMemberType]
        key,
        mapping={
            "ts": datetime.now(UTC).isoformat(),
            "errors": "0",
            "last_event_at": datetime.now(UTC).isoformat(),
            "ws_state": "connected",
            "reconnects": "0",
            "shard_index": "0",
            "shard_total": "1",
        },
    )
    try:
        actor: Actor = make_actor("shards-reader-4")
        response = await client.get("/api/v1/system/market-status", headers=actor.headers)

        entry = next(row for row in response.json()["exchanges"] if row["exchange"] == code)
        assert entry["ws_state"] == "connected"
        assert entry["shards_expected"] == 1
        assert entry["shards_reporting"] == 1
    finally:
        await redis_client.delete(key)


async def test_no_collector_at_all_declares_an_unknown_topology(
    client: httpx.AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    make_actor: Callable[[str], Actor],
) -> None:
    """Never "1 shard, reporting 0": with nothing in Redis the API does not
    know how many shards *should* exist, and says so."""
    code = await _seed(session_factory, markets=2)
    actor: Actor = make_actor("shards-reader-5")

    response = await client.get("/api/v1/system/market-status", headers=actor.headers)

    entry = next(row for row in response.json()["exchanges"] if row["exchange"] == code)
    assert entry["ws_state"] == "unavailable"
    assert entry["shards_expected"] is None
    assert entry["shards_reporting"] == 0


async def test_a_stale_solo_heartbeat_is_unavailable_not_connected(
    client: httpx.AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    redis_client: redis_asyncio.Redis,
    make_actor: Callable[[str], Actor],
) -> None:
    """Astra, T2.5g diff review: a hash that outlived its own freshness (or
    whose clock ran ahead) must not have its ``ws_state`` passed through — the
    row would read ``connected`` next to "0 shards reporting"."""
    code = await _seed(session_factory, markets=2)
    key = keys.heartbeat("market", code)
    old = datetime.now(UTC) - timedelta(minutes=5)
    await redis_client.hset(  # type: ignore[reportUnknownMemberType]
        key,
        mapping={
            "ts": old.isoformat(),
            "errors": "0",
            "last_event_at": old.isoformat(),
            "ws_state": "connected",
            "shard_index": "0",
            "shard_total": "1",
        },
    )
    try:
        actor: Actor = make_actor("shards-reader-7")
        response = await client.get("/api/v1/system/market-status", headers=actor.headers)

        entry = next(row for row in response.json()["exchanges"] if row["exchange"] == code)
        assert entry["ws_state"] == "unavailable"
        assert entry["shards_expected"] is None
        assert entry["shards_reporting"] == 0
        assert entry["last_event_at"] is None
    finally:
        await redis_client.delete(key)


async def test_a_shard_with_no_event_yet_is_not_covered_by_its_siblings_freshness(
    client: httpx.AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    redis_client: redis_asyncio.Redis,
    make_actor: Callable[[str], Actor],
) -> None:
    """Astra, T2.5g diff review: ``min`` over the shards that *have* a timestamp
    would let a shard which has never received an event inherit a sibling's
    freshness — 50 markets with no data reading as live."""
    code = await _seed(session_factory, markets=4)
    keys_written = [await _write_shard(redis_client, code, 0, 2)]
    silent = keys.market_heartbeat(code, 1, 2)
    await redis_client.hset(  # type: ignore[reportUnknownMemberType]
        silent,
        mapping={
            "ts": datetime.now(UTC).isoformat(),
            "errors": "0",
            "last_event_at": "",
            "ws_state": "connected",
            "shard_index": "1",
            "shard_total": "2",
        },
    )
    keys_written.append(silent)
    try:
        actor: Actor = make_actor("shards-reader-8")
        response = await client.get("/api/v1/system/market-status", headers=actor.headers)

        entry = next(row for row in response.json()["exchanges"] if row["exchange"] == code)
        assert entry["shards_reporting"] == 2
        assert entry["last_event_at"] is None
        assert entry["last_event_age_ms"] is None
    finally:
        await redis_client.delete(*keys_written)


async def test_the_markets_page_gets_the_shard_count_for_its_own_exchanges(
    client: httpx.AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    redis_client: redis_asyncio.Redis,
    make_actor: Callable[[str], Actor],
) -> None:
    """``apps/web`` prints "N shards, M mercados" off this summary — the label
    exists only when a collector actually declared a topology."""
    code = await _seed(session_factory, markets=3)
    keys_written = [
        await _write_shard(redis_client, code, 0, 4),
        await _write_shard(redis_client, code, 1, 4),
        await _write_shard(redis_client, code, 2, 4),
        await _write_shard(redis_client, code, 3, 4),
    ]
    try:
        actor: Actor = make_actor("shards-reader-6")
        response = await client.get(
            f"/api/v1/markets?exchange={code}&monitored=true", headers=actor.headers
        )

        assert response.status_code == 200, response.text
        summary = response.json()["summary"]
        assert summary["markets_monitored"] == 3
        assert summary["collector_shards_expected"] == 4
        assert summary["collector_shards_reporting"] == 4
    finally:
        await redis_client.delete(*keys_written)
