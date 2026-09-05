"""Integration tests for ``/api/v1/markets*`` — real Postgres (seeded
``exchanges``/``assets``/``markets``/``candles``) and real Redis hot state.

Every test seeds its own uniquely-named exchange/symbol (the session-scoped
database is shared across this whole file) and filters list queries down to
it, so tests never see each other's rows or the seed script's own
``binance``/``bybit``.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator, Callable
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import TYPE_CHECKING, cast

import msgpack
import pytest
import pytest_asyncio
import redis.asyncio as redis_asyncio
from sqlalchemy import select

from hunter_api.repositories.markets import MarketRepository
from hunter_core.db.models.market_data import Candle, IngestionGap
from hunter_core.db.models.markets import Asset, Exchange, Market
from hunter_core.domain.enums import MarketType, Timeframe
from hunter_core.redis import keys

from .conftest import Actor

if TYPE_CHECKING:
    import httpx
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    from hunter_api.settings import ApiSettings

pytestmark = pytest.mark.integration


@pytest_asyncio.fixture
async def redis_client(redis_url: str) -> AsyncIterator[redis_asyncio.Redis]:
    client = redis_asyncio.from_url(redis_url, decode_responses=False)
    try:
        yield client
    finally:
        await client.aclose()


async def _seed_market(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    is_monitored: bool = True,
    monitor_rank: int | None = 1,
) -> tuple[str, str, uuid.UUID]:
    """A fresh exchange + base/quote assets + one perpetual market, uniquely
    named so it can never collide with another test or the seed script.
    """
    suffix = uuid.uuid4().hex[:10]
    exchange_code = f"testex{suffix}"
    symbol = f"TEST{suffix.upper()}USDT"
    async with session_factory() as session:
        exchange = Exchange(code=exchange_code, name=exchange_code)
        base_asset = Asset(symbol=f"BASE{suffix}")
        session.add_all([exchange, base_asset])
        await session.flush()
        # "USDT" is shared across every seeded market in this suite (Asset.symbol
        # is UNIQUE) — reuse the row a prior test already inserted instead of a
        # fresh one colliding with it.
        quote_asset = (
            await session.execute(select(Asset).where(Asset.symbol == "USDT"))
        ).scalar_one_or_none()
        if quote_asset is None:
            quote_asset = Asset(symbol="USDT")
            session.add(quote_asset)
            await session.flush()
        market = Market(
            exchange_id=exchange.id,
            symbol=symbol,
            market_type=MarketType.PERPETUAL,
            base_asset_id=base_asset.id,
            quote_asset_id=quote_asset.id,
            is_monitored=is_monitored,
            monitor_rank=monitor_rank,
        )
        session.add(market)
        await session.commit()
        return exchange_code, symbol, market.id


async def _write_ticker(
    redis_client: redis_asyncio.Redis, exchange: str, symbol: str, *, age_s: float = 1.0
) -> None:
    ts = datetime.now(UTC) - timedelta(seconds=age_s)
    await redis_client.hset(
        keys.ticker(exchange, symbol),
        mapping={
            "last": "50000.5",
            "bid": "50000",
            "ask": "50001",
            "volume_24h": "1234.5",
            "quote_volume_24h": "61725000",
            "change_24h_pct": "0.0123",
            "ts": ts.isoformat(),
        },
    )


async def _write_deriv(
    redis_client: redis_asyncio.Redis, exchange: str, symbol: str, *, mark_age_s: float = 1.0
) -> None:
    now = datetime.now(UTC)
    mark_ts = now - timedelta(seconds=mark_age_s)
    await redis_client.hset(
        keys.derivatives(exchange, symbol),
        mapping={
            "open_interest": "100",
            "open_interest_value": "5000000",
            "oi_ts": now.isoformat(),
            "funding_rate": "0.0001",
            "funding_kind": "estimated",
            "funding_ts": now.isoformat(),
            "mark_price": "50000.6",
            "mark_ts": mark_ts.isoformat(),
        },
    )


async def _write_mark_only(
    redis_client: redis_asyncio.Redis, exchange: str, symbol: str, *, age_s: float = 1.0
) -> None:
    """A deriv hash with only ``mark_price``/``mark_ts`` — the shape a market
    with no funding/OI events yet (a fresh listing) would have.
    """
    mark_ts = datetime.now(UTC) - timedelta(seconds=age_s)
    await redis_client.hset(
        keys.derivatives(exchange, symbol),
        mapping={"mark_price": "50000.6", "mark_ts": mark_ts.isoformat()},
    )


async def _write_book_and_trades(
    redis_client: redis_asyncio.Redis, exchange: str, symbol: str
) -> None:
    book_payload = {
        "ts": datetime.now(UTC).isoformat(),
        "bids": [["50000", "1.5"]],
        "asks": [["50001", "0.5"]],
    }
    book = cast(bytes, msgpack.packb(book_payload))  # type: ignore[reportUnknownMemberType]
    await redis_client.set(keys.book(exchange, symbol), book)
    trade_payload = {
        "ts": datetime.now(UTC).isoformat(),
        "price": "50000.5",
        "qty": "0.01",
        "side": "buy",
        "trade_id": "1",
    }
    trade = cast(bytes, msgpack.packb(trade_payload))  # type: ignore[reportUnknownMemberType]
    await redis_client.lpush(keys.trades(exchange, symbol), trade)


async def _push_trade(
    redis_client: redis_asyncio.Redis, exchange: str, symbol: str, *, trade_id: str, ts: datetime
) -> None:
    """One more trade, ``LPUSH``ed exactly as the market worker does — index 0
    ends up as the newest.
    """
    payload = {
        "ts": ts.isoformat(),
        "price": "50000.5",
        "qty": "0.01",
        "side": "buy",
        "trade_id": trade_id,
    }
    packed = cast(bytes, msgpack.packb(payload))  # type: ignore[reportUnknownMemberType]
    await redis_client.lpush(keys.trades(exchange, symbol), packed)


async def _seed_candle(
    session_factory: async_sessionmaker[AsyncSession],
    market_id: uuid.UUID,
    *,
    open_time: datetime,
    is_final: bool = True,
    timeframe: Timeframe = Timeframe.M1,
) -> None:
    async with session_factory() as session:
        session.add(
            Candle(
                market_id=market_id,
                timeframe=timeframe,
                open_time=open_time,
                open=Decimal("100"),
                high=Decimal("101"),
                low=Decimal("99"),
                close=Decimal("100.5"),
                volume=Decimal("10"),
                is_final=is_final,
            )
        )
        await session.commit()


async def test_list_markets_requires_authentication(client: httpx.AsyncClient) -> None:
    response = await client.get("/api/v1/markets")
    assert response.status_code == 401


async def test_list_markets_ok_row_and_summary(
    client: httpx.AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    redis_client: redis_asyncio.Redis,
    make_actor: Callable[[str], Actor],
) -> None:
    exchange, symbol, _market_id = await _seed_market(session_factory)
    await _write_ticker(redis_client, exchange, symbol)
    await _write_deriv(redis_client, exchange, symbol)
    await _write_book_and_trades(redis_client, exchange, symbol)
    actor: Actor = make_actor("markets-reader")

    response = await client.get(f"/api/v1/markets?exchange={exchange}", headers=actor.headers)

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["summary"] == {
        "markets_total": 1,
        "markets_monitored": 1,
        "markets_ok": 1,
        "markets_stale": 0,
        "markets_degraded": 0,
        "markets_unavailable": 0,
    }
    row = body["items"][0]
    assert row["exchange"] == exchange
    assert row["symbol"] == symbol
    assert row["data_quality"] == "ok"
    assert row["has_open_gap"] is False
    assert row["last_price"] == "50000.5"
    assert isinstance(row["last_price"], str)
    assert row["open_interest"] == "100"
    assert row["mark_price"] == "50000.6"
    assert row["funding_kind"] == "estimated"
    assert row["spread_pct"] is not None
    components = row["components"]
    assert components["ticker"]["quality"] == "ok"
    assert components["book"]["quality"] == "ok"
    assert components["mark"]["quality"] == "ok"
    assert components["open_interest"]["age_ms"] is not None
    assert components["funding"]["kind"] == "estimated"


async def test_list_markets_unavailable_with_no_redis_data(
    client: httpx.AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    make_actor: Callable[[str], Actor],
) -> None:
    exchange, symbol, _market_id = await _seed_market(session_factory)
    actor: Actor = make_actor("markets-reader-2")

    response = await client.get(f"/api/v1/markets?exchange={exchange}", headers=actor.headers)

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["summary"]["markets_unavailable"] == 1
    row = body["items"][0]
    assert row["symbol"] == symbol
    assert row["data_quality"] == "unavailable"
    assert row["last_price"] is None
    assert row["last_update"] is None
    assert row["components"]["ticker"]["quality"] == "absent"
    assert row["components"]["book"]["quality"] == "absent"
    assert row["components"]["mark"]["quality"] == "absent"


async def test_list_markets_degraded_when_book_is_missing(
    client: httpx.AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    redis_client: redis_asyncio.Redis,
    make_actor: Callable[[str], Actor],
) -> None:
    """Ticker and mark fresh, book never written — one required component
    absent is ``degraded``, not ``unavailable`` (not every component is gone)
    and not ``ok`` (one required component is missing).
    """
    exchange, symbol, _market_id = await _seed_market(session_factory)
    await _write_ticker(redis_client, exchange, symbol)
    await _write_mark_only(redis_client, exchange, symbol)
    actor: Actor = make_actor("markets-reader-degraded-book")

    response = await client.get(f"/api/v1/markets?exchange={exchange}", headers=actor.headers)

    assert response.status_code == 200, response.text
    row = response.json()["items"][0]
    assert row["symbol"] == symbol
    assert row["data_quality"] == "degraded"
    assert row["components"]["book"]["quality"] == "absent"
    assert row["components"]["ticker"]["quality"] == "ok"


@pytest.mark.parametrize("gap_status", ["open", "failed"])
async def test_list_markets_degraded_with_an_open_or_failed_ingestion_gap(
    client: httpx.AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    redis_client: redis_asyncio.Redis,
    make_actor: Callable[[str], Actor],
    gap_status: str,
) -> None:
    """A gap that is still open — or one that exhausted its retries and gave
    up (``failed``) — both degrade the market even with every component
    fresh, and the response's own ``has_open_gap`` flag says why.
    """
    exchange, symbol, market_id = await _seed_market(session_factory)
    await _write_ticker(redis_client, exchange, symbol)
    await _write_deriv(redis_client, exchange, symbol)
    await _write_book_and_trades(redis_client, exchange, symbol)
    async with session_factory() as session:
        session.add(
            IngestionGap(
                market_id=market_id,
                timeframe=Timeframe.M1,
                gap_start=datetime.now(UTC) - timedelta(hours=1),
                gap_end=datetime.now(UTC),
                status=gap_status,
                attempts=5 if gap_status == "failed" else 1,
            )
        )
        await session.commit()
    actor: Actor = make_actor(f"markets-reader-gap-{gap_status}")

    response = await client.get(f"/api/v1/markets?exchange={exchange}", headers=actor.headers)

    assert response.status_code == 200, response.text
    row = response.json()["items"][0]
    assert row["symbol"] == symbol
    assert row["data_quality"] == "degraded"
    assert row["has_open_gap"] is True
    assert row["components"]["ticker"]["quality"] == "ok"


async def test_list_markets_monitored_filter(
    client: httpx.AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    make_actor: Callable[[str], Actor],
) -> None:
    exchange, _symbol, _market_id = await _seed_market(session_factory, is_monitored=True)
    _exchange2, symbol2, _market_id2 = await _seed_market(session_factory, is_monitored=False)
    actor: Actor = make_actor("markets-reader-3")

    response = await client.get(
        f"/api/v1/markets?exchange={exchange}&monitored=true", headers=actor.headers
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert all(row["is_monitored"] for row in body["items"])
    assert all(row["symbol"] != symbol2 for row in body["items"])


async def test_get_market_detail_includes_book_and_trades(
    client: httpx.AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    redis_client: redis_asyncio.Redis,
    make_actor: Callable[[str], Actor],
) -> None:
    exchange, symbol, _market_id = await _seed_market(session_factory)
    await _write_ticker(redis_client, exchange, symbol)
    await _write_deriv(redis_client, exchange, symbol)
    await _write_book_and_trades(redis_client, exchange, symbol)
    actor: Actor = make_actor("markets-detail-reader")

    response = await client.get(f"/api/v1/markets/{exchange}/{symbol}", headers=actor.headers)

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["book"]["bids"][0]["price"] == "50000"
    assert body["book"]["asks"][0]["price"] == "50001"
    assert body["book"]["kind"] == "snapshot"
    assert body["book"]["depth"] == 20
    assert len(body["recent_trades"]) == 1
    assert body["recent_trades"][0]["trade_id"] == "1"
    assert body["recent_trades"][0]["side"] == "buy"
    assert body["data_quality"] == "ok"
    assert body["has_open_gap"] is False
    assert body["components"]["mark"]["quality"] == "ok"


async def test_get_market_detail_recent_trades_are_newest_first(
    client: httpx.AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    redis_client: redis_asyncio.Redis,
    make_actor: Callable[[str], Actor],
) -> None:
    """The worker ``LPUSH``es each new trade — index 0 is the newest — so the
    API must read the head of the list, not the tail, and must not reverse.
    """
    exchange, symbol, _market_id = await _seed_market(session_factory)
    await _write_ticker(redis_client, exchange, symbol)
    await _write_deriv(redis_client, exchange, symbol)
    now = datetime.now(UTC)
    # Pushed oldest-first, exactly as the worker appends them one at a time:
    # each LPUSH puts its trade at index 0, so "third" ends up newest.
    await _push_trade(
        redis_client, exchange, symbol, trade_id="first", ts=now - timedelta(seconds=3)
    )
    await _push_trade(
        redis_client, exchange, symbol, trade_id="second", ts=now - timedelta(seconds=2)
    )
    await _push_trade(
        redis_client, exchange, symbol, trade_id="third", ts=now - timedelta(seconds=1)
    )
    actor: Actor = make_actor("markets-detail-trade-order")

    response = await client.get(f"/api/v1/markets/{exchange}/{symbol}", headers=actor.headers)

    assert response.status_code == 200, response.text
    trade_ids = [t["trade_id"] for t in response.json()["recent_trades"]]
    assert trade_ids == ["third", "second", "first"]


async def test_get_market_detail_no_book_or_trades_ever_written_reads_empty_not_null(
    client: httpx.AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    redis_client: redis_asyncio.Redis,
    make_actor: Callable[[str], Actor],
) -> None:
    """(G9) A healthy Redis read that simply finds nothing at ``mkt:*:book``/
    ``mkt:*:trades`` (never written) is the honest "empty" state, not the
    "could not read" state -- ``hot_state_ok`` is ``true`` and
    ``recent_trades`` is ``[]``, never ``null``.
    """
    exchange, symbol, _market_id = await _seed_market(session_factory)
    await _write_ticker(redis_client, exchange, symbol)
    await _write_deriv(redis_client, exchange, symbol)
    actor: Actor = make_actor("markets-detail-empty-hot-state")

    response = await client.get(f"/api/v1/markets/{exchange}/{symbol}", headers=actor.headers)

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["hot_state_ok"] is True
    assert body["book"] is None
    assert body["recent_trades"] == []


async def test_get_market_detail_redis_failure_reads_null_not_empty(
    client: httpx.AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    redis_client: redis_asyncio.Redis,
    make_actor: Callable[[str], Actor],
) -> None:
    """(G9) A real Redis read failure (``WRONGTYPE`` on the trades key,
    which aborts the whole pipeline the same way as the list endpoint's F2
    case) must not be served as "there is nothing" -- ``hot_state_ok`` is
    ``false`` and both ``book`` and ``recent_trades`` come back ``null``,
    never ``[]``/an empty book, so the client can tell a genuine outage from
    genuinely no data.
    """
    exchange, symbol, _market_id = await _seed_market(session_factory)
    await _write_ticker(redis_client, exchange, symbol)
    await _write_deriv(redis_client, exchange, symbol)
    await redis_client.set(keys.trades(exchange, symbol), "not-a-list")
    actor: Actor = make_actor("markets-detail-redis-failure")

    response = await client.get(f"/api/v1/markets/{exchange}/{symbol}", headers=actor.headers)

    assert response.status_code == 200, response.text
    assert "not-a-list" not in response.text
    assert keys.trades(exchange, symbol) not in response.text
    body = response.json()
    assert body["hot_state_ok"] is False
    assert body["book"] is None
    assert body["recent_trades"] is None


async def test_get_market_404_for_unknown_symbol(
    client: httpx.AsyncClient, make_actor: Callable[[str], Actor]
) -> None:
    actor: Actor = make_actor("markets-404-reader")

    response = await client.get("/api/v1/markets/binance/DOES-NOT-EXIST", headers=actor.headers)

    assert response.status_code == 404
    assert response.headers["content-type"].startswith("application/problem+json")


async def test_get_candles_returns_only_final_candles_as_decimal_strings(
    client: httpx.AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    make_actor: Callable[[str], Actor],
) -> None:
    exchange, symbol, market_id = await _seed_market(session_factory)
    base_time = datetime(2026, 9, 5, 12, 0, tzinfo=UTC)
    await _seed_candle(session_factory, market_id, open_time=base_time, is_final=True)
    await _seed_candle(
        session_factory, market_id, open_time=base_time + timedelta(minutes=1), is_final=False
    )
    actor: Actor = make_actor("candles-reader")

    response = await client.get(
        f"/api/v1/markets/{exchange}/{symbol}/candles?timeframe=1m", headers=actor.headers
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert len(body) == 1
    candle = body[0]
    # NUMERIC(28,10): the column pads to full precision, so compare
    # numerically rather than expecting the exact literal back.
    assert isinstance(candle["open"], str)
    assert Decimal(candle["open"]) == Decimal("100")
    assert candle["close_time"] > candle["open_time"]


async def test_get_candles_422_for_an_invalid_timeframe(
    client: httpx.AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    make_actor: Callable[[str], Actor],
) -> None:
    exchange, symbol, _market_id = await _seed_market(session_factory)
    actor: Actor = make_actor("candles-422-reader")

    response = await client.get(
        f"/api/v1/markets/{exchange}/{symbol}/candles?timeframe=3m", headers=actor.headers
    )

    assert response.status_code == 422
    assert response.headers["content-type"].startswith("application/problem+json")


async def test_get_candles_422_for_a_naive_before_datetime(
    client: httpx.AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    make_actor: Callable[[str], Actor],
) -> None:
    """(F4) A naive ``before`` (no UTC offset) must be rejected -- asyncpg
    would otherwise interpret it in the *process*'s timezone, silently
    changing the cut point depending on where the container happens to run.
    """
    exchange, symbol, _market_id = await _seed_market(session_factory)
    actor: Actor = make_actor("candles-naive-before")

    response = await client.get(
        f"/api/v1/markets/{exchange}/{symbol}/candles",
        params={"before": "2026-09-05T12:00:00"},
        headers=actor.headers,
    )

    assert response.status_code == 422, response.text
    assert response.headers["content-type"].startswith("application/problem+json")


async def test_get_candles_before_normalizes_an_explicit_offset_to_utc(
    client: httpx.AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    make_actor: Callable[[str], Actor],
) -> None:
    """(F4) ``before`` sent with a non-UTC offset must cut at the same
    instant as the equivalent UTC timestamp -- proving the value is
    normalized by its own offset arithmetic, not passed through naively
    (which would silently shift the cut point by the process's local zone).
    """
    exchange, symbol, market_id = await _seed_market(session_factory)
    base_time = datetime(2026, 9, 5, 12, 0, tzinfo=UTC)
    await _seed_candle(session_factory, market_id, open_time=base_time)
    await _seed_candle(session_factory, market_id, open_time=base_time + timedelta(minutes=1))
    actor: Actor = make_actor("candles-offset-before")
    # 12:01:00 UTC, expressed as 14:01:00+02:00 -- an implementation that
    # dropped the offset and treated this as a naive UTC value would cut at
    # the wrong instant.
    offset_before = "2026-09-05T14:01:00+02:00"

    response = await client.get(
        f"/api/v1/markets/{exchange}/{symbol}/candles",
        params={"before": offset_before},
        headers=actor.headers,
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert len(body) == 1
    # ARCHITECTURE.md: UTC serialized with a literal "Z", not "+00:00".
    assert datetime.fromisoformat(body[0]["open_time"].replace("Z", "+00:00")) == base_time


async def test_list_markets_stale_after_ms_matches_the_configured_setting(
    client: httpx.AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    make_actor: Callable[[str], Actor],
    api_settings: ApiSettings,
) -> None:
    """(F8) The client must not have to hardcode the staleness threshold --
    it is sourced from the same setting the aggregate/component qualities
    were computed with.
    """
    exchange, _symbol, _market_id = await _seed_market(session_factory)
    actor: Actor = make_actor("markets-stale-after-ms")

    response = await client.get(f"/api/v1/markets?exchange={exchange}", headers=actor.headers)

    assert response.status_code == 200, response.text
    assert response.json()["stale_after_ms"] == int(api_settings.market_stale_after_s * 1000)


async def test_get_market_detail_stale_after_ms_matches_the_configured_setting(
    client: httpx.AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    make_actor: Callable[[str], Actor],
    api_settings: ApiSettings,
) -> None:
    exchange, symbol, _market_id = await _seed_market(session_factory)
    actor: Actor = make_actor("markets-detail-stale-after-ms")

    response = await client.get(f"/api/v1/markets/{exchange}/{symbol}", headers=actor.headers)

    assert response.status_code == 200, response.text
    assert response.json()["stale_after_ms"] == int(api_settings.market_stale_after_s * 1000)


async def _seed_exchange_with_markets(
    session_factory: async_sessionmaker[AsyncSession], count: int
) -> tuple[str, list[str]]:
    """One fresh exchange plus ``count`` markets on it, ordered ``symbol``."""
    suffix = uuid.uuid4().hex[:10]
    exchange_code = f"testex{suffix}"
    symbols = [f"PG{index}{suffix.upper()}USDT" for index in range(count)]
    async with session_factory() as session:
        exchange = Exchange(code=exchange_code, name=exchange_code)
        session.add(exchange)
        await session.flush()
        for index, symbol in enumerate(symbols):
            session.add(
                Market(
                    exchange_id=exchange.id,
                    symbol=symbol,
                    market_type=MarketType.PERPETUAL,
                    is_monitored=True,
                    monitor_rank=index,
                )
            )
        await session.commit()
    return exchange_code, symbols


async def test_list_markets_pagination_round_trip_has_no_duplicate_or_skipped_rows(
    client: httpx.AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    make_actor: Callable[[str], Actor],
) -> None:
    """(F9) ``limit=2`` then following ``next_cursor`` must visit every row
    exactly once, and the last page must end the pagination (``next_cursor``
    ``null``).
    """
    exchange_code, symbols = await _seed_exchange_with_markets(session_factory, 3)
    actor: Actor = make_actor(f"markets-pagination-{exchange_code}")

    first = await client.get(
        f"/api/v1/markets?exchange={exchange_code}&limit=2", headers=actor.headers
    )
    assert first.status_code == 200, first.text
    first_body = first.json()
    assert len(first_body["items"]) == 2
    assert first_body["next_cursor"] is not None

    second = await client.get(
        f"/api/v1/markets?exchange={exchange_code}&limit=2&cursor={first_body['next_cursor']}",
        headers=actor.headers,
    )
    assert second.status_code == 200, second.text
    second_body = second.json()
    assert len(second_body["items"]) == 1
    assert second_body["next_cursor"] is None

    seen_symbols = [row["symbol"] for row in first_body["items"]] + [
        row["symbol"] for row in second_body["items"]
    ]
    assert sorted(seen_symbols) == sorted(symbols)
    assert len(seen_symbols) == len(set(seen_symbols))


async def test_list_markets_garbage_cursor_returns_422_problem_json(
    client: httpx.AsyncClient, make_actor: Callable[[str], Actor]
) -> None:
    """(F9) A hostile/garbage ``cursor`` must be rejected as a validation
    error, never a 500."""
    actor: Actor = make_actor("markets-garbage-cursor")

    response = await client.get(
        "/api/v1/markets?cursor=!!!not-a-valid-cursor!!!", headers=actor.headers
    )

    assert response.status_code == 422, response.text
    assert response.headers["content-type"].startswith("application/problem+json")
    assert response.json()["type"].endswith("invalid-cursor")


async def test_list_markets_stale_when_book_is_present_but_aged(
    client: httpx.AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    redis_client: redis_asyncio.Redis,
    make_actor: Callable[[str], Actor],
) -> None:
    """(F9) "book parado, resto ativo" as a *present but aged* timestamp
    (``STALE``), not merely an absent key -- today only ``mark`` exercised
    this branch in the suite.
    """
    exchange, symbol, _market_id = await _seed_market(session_factory)
    await _write_ticker(redis_client, exchange, symbol)
    await _write_deriv(redis_client, exchange, symbol)
    stale_book_payload = {
        "ts": (datetime.now(UTC) - timedelta(seconds=30)).isoformat(),
        "bids": [["50000", "1.5"]],
        "asks": [["50001", "0.5"]],
    }
    packed = cast(bytes, msgpack.packb(stale_book_payload))  # type: ignore[reportUnknownMemberType]
    await redis_client.set(keys.book(exchange, symbol), packed)
    actor: Actor = make_actor("markets-book-stale")

    response = await client.get(f"/api/v1/markets?exchange={exchange}", headers=actor.headers)

    assert response.status_code == 200, response.text
    row = response.json()["items"][0]
    assert row["components"]["book"]["quality"] == "stale"
    assert row["components"]["ticker"]["quality"] == "ok"
    assert row["data_quality"] == "stale"


async def test_list_markets_corrupted_book_degrades_only_that_market(
    client: httpx.AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    redis_client: redis_asyncio.Redis,
    make_actor: Callable[[str], Actor],
) -> None:
    """(F1) A corrupted ``mkt:*:book`` value (not a msgpack map at all) must
    not 500 the whole list -- even with ``limit=1``, which today decodes
    every filtered row before windowing -- only the market it belongs to
    degrades.
    """
    exchange_code, symbols = await _seed_exchange_with_markets(session_factory, 3)
    for symbol in symbols:
        await _write_ticker(redis_client, exchange_code, symbol)
        await _write_deriv(redis_client, exchange_code, symbol)
    await _write_book_and_trades(redis_client, exchange_code, symbols[0])
    await _write_book_and_trades(redis_client, exchange_code, symbols[1])
    garbage = cast(bytes, msgpack.packb("not-a-book"))  # type: ignore[reportUnknownMemberType]
    await redis_client.set(keys.book(exchange_code, symbols[2]), garbage)
    actor: Actor = make_actor(f"markets-corrupt-{exchange_code}")

    limited = await client.get(
        f"/api/v1/markets?exchange={exchange_code}&limit=1", headers=actor.headers
    )
    assert limited.status_code == 200, limited.text
    assert limited.json()["summary"]["markets_total"] == 3

    full = await client.get(f"/api/v1/markets?exchange={exchange_code}", headers=actor.headers)
    assert full.status_code == 200, full.text
    rows = {row["symbol"]: row for row in full.json()["items"]}
    assert rows[symbols[0]]["data_quality"] == "ok"
    assert rows[symbols[1]]["data_quality"] == "ok"
    assert rows[symbols[2]]["data_quality"] == "degraded"
    assert rows[symbols[2]]["components"]["book"]["quality"] == "absent"


async def test_get_market_detail_drops_a_trade_missing_a_required_field(
    client: httpx.AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    redis_client: redis_asyncio.Redis,
    make_actor: Callable[[str], Actor],
) -> None:
    """(F1) A trade entry with a valid ``ts`` but no ``price`` is dropped
    individually -- the rest of the recent trades still come back."""
    exchange, symbol, _market_id = await _seed_market(session_factory)
    await _write_ticker(redis_client, exchange, symbol)
    await _write_deriv(redis_client, exchange, symbol)
    now = datetime.now(UTC)
    good_payload = {
        "ts": now.isoformat(),
        "price": "1",
        "qty": "1",
        "side": "buy",
        "trade_id": "good",
    }
    broken_payload = {"ts": now.isoformat(), "qty": "1", "side": "buy", "trade_id": "bad"}
    await redis_client.lpush(
        keys.trades(exchange, symbol),
        cast(bytes, msgpack.packb(broken_payload)),  # type: ignore[reportUnknownMemberType]
    )
    await redis_client.lpush(
        keys.trades(exchange, symbol),
        cast(bytes, msgpack.packb(good_payload)),  # type: ignore[reportUnknownMemberType]
    )
    actor: Actor = make_actor("markets-detail-bad-trade")

    response = await client.get(f"/api/v1/markets/{exchange}/{symbol}", headers=actor.headers)

    assert response.status_code == 200, response.text
    trade_ids = [t["trade_id"] for t in response.json()["recent_trades"]]
    assert trade_ids == ["good"]


async def test_list_markets_degrades_honestly_when_a_ticker_key_has_the_wrong_redis_type(
    client: httpx.AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    redis_client: redis_asyncio.Redis,
    make_actor: Callable[[str], Actor],
) -> None:
    """(F2/G3) A real ``WRONGTYPE`` (ticker key set as a STRING instead of a
    HASH) fails that one Redis command -- with a single market in the
    request, that means the market degrades to ``unavailable`` rather than
    500ing, and redis-py's ``WRONGTYPE`` message (which can embed the key)
    never reaches the response body. See
    ``test_list_markets_isolates_a_single_markets_wrongtype_ticker_from_the_rest``
    below for the multi-market case (G3): a bad command must not degrade
    *every* market in the same request, only the one it belongs to.
    """
    exchange, symbol, _market_id = await _seed_market(session_factory)
    await redis_client.set(keys.ticker(exchange, symbol), "not-a-hash")

    actor: Actor = make_actor("markets-wrongtype")

    response = await client.get(f"/api/v1/markets?exchange={exchange}", headers=actor.headers)

    assert response.status_code == 200, response.text
    assert "not-a-hash" not in response.text
    assert keys.ticker(exchange, symbol) not in response.text
    row = response.json()["items"][0]
    assert row["symbol"] == symbol
    assert row["data_quality"] == "unavailable"


async def test_list_markets_isolates_a_single_markets_wrongtype_ticker_from_the_rest(
    client: httpx.AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    redis_client: redis_asyncio.Redis,
    make_actor: Callable[[str], Actor],
) -> None:
    """(G3) A single market's ticker key holding the wrong Redis type must
    not poison every market in the same request -- the previous fix pass
    wrapped the whole ``pipeline.execute()`` in one handler that degraded
    *every* market in the page to absent hot state on any command failure,
    which is the opposite of per-market isolation. The other two markets
    here must still render their real prices; only the broken one degrades.
    """
    exchange_code, symbols = await _seed_exchange_with_markets(session_factory, 3)
    for symbol in symbols:
        await _write_ticker(redis_client, exchange_code, symbol)
        await _write_deriv(redis_client, exchange_code, symbol)
        await _write_book_and_trades(redis_client, exchange_code, symbol)
    await redis_client.set(keys.ticker(exchange_code, symbols[1]), "not-a-hash")
    actor: Actor = make_actor(f"markets-wrongtype-isolated-{exchange_code}")

    response = await client.get(f"/api/v1/markets?exchange={exchange_code}", headers=actor.headers)

    assert response.status_code == 200, response.text
    assert "not-a-hash" not in response.text
    assert keys.ticker(exchange_code, symbols[1]) not in response.text
    rows = {row["symbol"]: row for row in response.json()["items"]}
    assert rows[symbols[0]]["data_quality"] == "ok"
    assert rows[symbols[0]]["last_price"] == "50000.5"
    assert rows[symbols[2]]["data_quality"] == "ok"
    assert rows[symbols[2]]["last_price"] == "50000.5"
    assert rows[symbols[1]]["components"]["ticker"]["quality"] == "absent"
    assert rows[symbols[1]]["data_quality"] in ("degraded", "unavailable")


async def test_gapped_market_ids_handles_more_ids_than_the_postgres_bind_parameter_limit(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """(F6) ``.in_()`` binds one parameter per id and would 500 once the
    list exceeds asyncpg's ~65535 bind-parameter ceiling -- this exercises a
    list well past that, proving the ``= ANY(:ids)`` array-parameter form
    used instead has no such ceiling.
    """
    market_ids = [uuid.uuid4() for _ in range(70_000)]

    async with session_factory() as session:
        gapped = await MarketRepository(session).gapped_market_ids(market_ids)

    assert gapped == set()
