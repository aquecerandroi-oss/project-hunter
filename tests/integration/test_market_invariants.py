"""T1.7 item 2: pipeline-wide invariants, proven against real Redis/Postgres
and the real API -- not just the unit test of the task that introduced each
rule. Scenarios are the literal list from ``.claude/state/review-T1.7.md``
(a) and ``docs/plans/M1.md``'s "Decisão conjunta" rodada 4.

Every "time passing" scenario here backdates an event's own ``ts`` at
construction time instead of sleeping -- CLAUDE.md/`review-T1.7.md` (c):
"Tempo controlado explicitamente ..., não sleep longo".

``worker_redis`` is typed ``Any`` throughout (not ``redis.asyncio.Redis``),
matching ``services/market-worker/tests/test_heartbeat.py``'s own convention:
redis-py's stubs leave several members (``pubsub()``, ``xrange`` overloads)
partially unknown under pyright strict.
"""

from __future__ import annotations

import uuid
from datetime import timedelta
from decimal import Decimal
from typing import TYPE_CHECKING, Any

import pytest

from hunter_core.domain.enums import Timeframe
from hunter_core.domain.market import NormalizedCandle, align_open_time
from hunter_core.domain.types import utcnow
from hunter_core.redis import keys
from hunter_market_worker import hot_state
from hunter_market_worker.persist_rows import flush_batch
from hunter_market_worker.publication import liquidation_id
from hunter_market_worker.universe import refresh_universe

from . import pipeline_builders as b

if TYPE_CHECKING:
    import httpx
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    from hunter_core.settings import Settings

pytestmark = pytest.mark.integration


def _candle(
    symbol: str, open_time: Any, *, is_final: bool, close: Decimal, **overrides: object
) -> NormalizedCandle:
    """``pipeline_builders.candle`` with ``open``/``high``/``low`` always
    bracketing ``close`` -- ``NormalizedCandle`` validates ``high >=
    max(open, close)`` and ``low <= min(open, close)``, so a test that only
    cares about ``close`` (most of this file) does not have to compute the
    other three by hand."""
    return b.candle(
        symbol,
        open_time,
        is_final=is_final,
        open=close,
        high=close + Decimal(1),
        low=close - Decimal(1),
        close=close,
        **overrides,
    )


EXCHANGE = b.EXCHANGE
SYMBOL = "ETHUSDT"
PRODUCER = "market-worker@invariants-it:1"


async def _seed_market(
    worker_session_factory: async_sessionmaker[AsyncSession],
    worker_redis: Any,
    worker_settings: Settings,
    symbol: str = SYMBOL,
) -> None:
    from hunter_exchanges.testing.fake_adapter import FakeExchangeAdapter

    adapter = FakeExchangeAdapter(
        code=EXCHANGE,
        markets=[b.market(symbol, symbol.removesuffix("USDT"))],
        ticker=b.ticker(symbol, "1000"),
    )
    await refresh_universe(
        worker_session_factory, adapter, worker_redis, worker_settings, producer=PRODUCER
    )


# ---------------------------------------------------------------------------
# open_time alignment + no duplicate candle
# ---------------------------------------------------------------------------


async def test_open_time_is_always_aligned_to_the_timeframe_boundary() -> None:
    misaligned = utcnow().replace(second=37, microsecond=123456)
    aligned = align_open_time(misaligned, Timeframe.M1)
    assert aligned.second == 0
    assert aligned.microsecond == 0
    assert aligned <= misaligned


async def test_candle_open_conflict_keeps_the_first_committed_row_not_the_last_flushed(
    worker_session_factory: async_sessionmaker[AsyncSession],
    worker_redis: Any,
    worker_settings: Settings,
) -> None:
    """T1.3 decision conjunta: REST ``ON CONFLICT (market_id, timeframe,
    open_time) DO NOTHING`` never overwrites an existing final -- proven here
    across two *separate* ``flush_batch`` calls (not a replay of the same
    batch, which ``test_market_pipeline.py`` already covers) carrying
    different closing prices for the same open_time, simulating a delayed
    REST backfill racing an already-committed WS final."""
    symbol = "GAPUSDT"
    await _seed_market(worker_session_factory, worker_redis, worker_settings, symbol)

    open_time = align_open_time(utcnow(), Timeframe.M1)
    ws_final = _candle(symbol, open_time, is_final=True, close=Decimal("10"))
    rest_final = _candle(symbol, open_time, is_final=True, close=Decimal("999"))

    ids = await flush_batch(worker_session_factory, EXCHANGE, [ws_final])
    assert ids == set()  # candles never appear in the liquidation-id return set
    ids2 = await flush_batch(worker_session_factory, EXCHANGE, [rest_final])
    assert ids2 == set()

    from sqlalchemy import select

    from hunter_core.db.models.market_data import Candle
    from hunter_market_worker.persist_rows import load_market_ids

    async with worker_session_factory() as session:
        market_id = (await load_market_ids(session, EXCHANGE, {symbol}))[symbol]
        rows = (
            (
                await session.execute(
                    select(Candle).where(
                        Candle.market_id == market_id, Candle.open_time == open_time
                    )
                )
            )
            .scalars()
            .all()
        )
        assert len(rows) == 1
        assert rows[0].close == Decimal("10")  # the first commit wins, not "999"


# ---------------------------------------------------------------------------
# Redis candles list: precedence rules (T1.3 decision conjunta)
# ---------------------------------------------------------------------------


async def test_larger_open_time_advances_the_head(worker_redis: Any) -> None:
    open_time = align_open_time(utcnow(), Timeframe.M1)
    first = b.candle(SYMBOL, open_time, is_final=True)
    second_open = open_time + timedelta(minutes=1)
    second = b.candle(SYMBOL, second_open, is_final=True)

    assert await hot_state.push_candle(worker_redis, first)
    assert await hot_state.push_candle(worker_redis, second)

    raw = await worker_redis.lrange(keys.candles_1m(EXCHANGE, SYMBOL), 0, -1)
    from hunter_market_worker import wire as msgpack

    head = msgpack.unpackb(raw[0])
    assert head["open_time"] > msgpack.unpackb(raw[1])["open_time"]


async def test_final_replaces_partial_but_partial_never_replaces_final(worker_redis: Any) -> None:
    open_time = align_open_time(utcnow(), Timeframe.M1)
    t0 = open_time + timedelta(seconds=1)
    partial = _candle(SYMBOL, open_time, is_final=False, close=Decimal("50"), event_ts=t0)
    final = _candle(SYMBOL, open_time, is_final=True, close=Decimal("42"))
    later_partial = _candle(
        SYMBOL, open_time, is_final=False, close=Decimal("1"), event_ts=t0 + timedelta(seconds=10)
    )

    assert await hot_state.push_candle(worker_redis, partial, event_ts=t0)
    assert await hot_state.push_candle(worker_redis, final)
    assert not await hot_state.push_candle(
        worker_redis, later_partial, event_ts=t0 + timedelta(seconds=10)
    )

    raw = await worker_redis.lrange(keys.candles_1m(EXCHANGE, SYMBOL), 0, -1)
    from hunter_market_worker import wire as msgpack

    assert msgpack.unpackb(raw[0])["close"] == "42"


async def test_older_or_duplicate_partial_is_rejected_not_silently_dropped(
    worker_redis: Any,
) -> None:
    open_time = align_open_time(utcnow(), Timeframe.M1)
    t0 = open_time + timedelta(seconds=5)
    growing = _candle(SYMBOL, open_time, is_final=False, close=Decimal("2"), event_ts=t0)
    duplicate = growing.model_copy()  # same event_ts, same open_time

    assert await hot_state.push_candle(worker_redis, growing, event_ts=t0)
    assert not await hot_state.push_candle(worker_redis, duplicate, event_ts=t0)  # not newer

    older = growing.model_copy(
        update={"close": Decimal("999"), "event_ts": t0 - timedelta(seconds=1)}
    )
    assert not await hot_state.push_candle(worker_redis, older, event_ts=t0 - timedelta(seconds=1))

    raw = await worker_redis.lrange(keys.candles_1m(EXCHANGE, SYMBOL), 0, -1)
    from hunter_market_worker import wire as msgpack

    assert msgpack.unpackb(raw[0])["close"] == "2"  # neither rejection mutated the stored value


# ---------------------------------------------------------------------------
# Coalescing: only a new accepted event renews ts/TTL
# ---------------------------------------------------------------------------


async def test_ticker_ttl_counts_down_when_no_new_event_refreshes_it(worker_redis: Any) -> None:
    """Astra's second opinion (T1.7): the previous version of this test never
    ran a coalescer cycle at all -- it wrote directly via
    ``hot_state.write_ticker`` and then just confirmed Redis's own
    ``EXPIRE``/``TTL`` round-trips, which would pass even if a real
    ``flush_ticks`` cycle re-issued the ticker hash script (and therefore
    the TTL) on every tick regardless of new data. This version drives the
    real ``handle_event`` -> ``flush_ticks`` path and forces the SECOND
    cycle to have nothing dirty, then confirms that cycle left the
    (deliberately shrunk) TTL alone.
    """
    from hunter_market_worker.ingest import AcceptedEvents, TickCoalescer, flush_ticks, handle_event
    from hunter_market_worker.persist import PersistQueues

    coalescer = TickCoalescer()
    args = (
        worker_redis,
        PRODUCER,
        PersistQueues(),
        coalescer,
        AcceptedEvents(),
        hot_state.TradeMemory(),
    )
    assert await handle_event(b.ticker(SYMBOL, "1"), *args)
    published = await flush_ticks(coalescer, worker_redis, PRODUCER)
    assert published == [SYMBOL]
    ttl_immediately = await worker_redis.ttl(keys.ticker(EXCHANGE, SYMBOL))
    assert ttl_immediately == hot_state.TICKER_TTL_S

    # Force the clock forward on the key itself (EXPIRE), rather than a
    # `sleep` in wall time, then run a SECOND flush cycle with nothing new
    # dirty (the coalescer already reset itself after the first flush) --
    # the real regression this guards against is `flush_ticks` re-queuing
    # the ticker hash script (and therefore its TTL) every cycle regardless
    # of whether anything actually changed.
    await worker_redis.expire(keys.ticker(EXCHANGE, SYMBOL), 5)
    empty_flush = await flush_ticks(coalescer, worker_redis, PRODUCER)
    assert empty_flush == []  # nothing dirty -> flush_ticks touches nothing
    ttl_after = await worker_redis.ttl(keys.ticker(EXCHANGE, SYMBOL))
    assert ttl_after == 5  # a cycle with no accepted event never re-set it to 30


async def test_late_or_duplicate_ticker_never_rejuvenates_the_hash(worker_redis: Any) -> None:
    fresh = b.ticker(SYMBOL, "100")
    stale = b.ticker(SYMBOL, "1", ts=fresh.ts - timedelta(seconds=1))

    assert await hot_state.write_ticker(worker_redis, fresh, source="rest")
    assert not await hot_state.write_ticker(worker_redis, stale, source="rest")

    raw = await worker_redis.hgetall(keys.ticker(EXCHANGE, SYMBOL))
    assert raw[b"last"] == b"100"  # the older duplicate never overwrote it


async def test_a_second_trade_pushes_the_first_down_not_the_reverse(worker_redis: Any) -> None:
    """Astra's second opinion (T1.7): the pipeline test only ever pushes ONE
    trade, so it cannot tell ``LPUSH`` (newest at index 0) apart from
    ``RPUSH`` (which would put it at the tail). A second trade here makes
    the ordering directional and therefore actually falsified by a
    LPUSH->RPUSH regression."""
    from hunter_market_worker import wire as msgpack

    first = b.trade(SYMBOL, "10", "1", trade_id="first")
    second = b.trade(SYMBOL, "11", "1", trade_id="second")
    assert await hot_state.push_trade(worker_redis, first, hot_state.TradeMemory())
    assert await hot_state.push_trade(worker_redis, second, hot_state.TradeMemory())

    raw = await worker_redis.lrange(keys.trades(EXCHANGE, SYMBOL), 0, -1)
    assert [msgpack.unpackb(r)["trade_id"] for r in raw] == ["second", "first"]


async def test_a_second_book_snapshot_wholesale_replaces_the_first(worker_redis: Any) -> None:
    """Astra's second opinion (T1.7): the pipeline test only ever writes ONE
    book snapshot, so it cannot prove old levels are gone after a second
    one -- only that *a* book exists. A depth-20 `@depth20` update is a full
    snapshot (ARCHITECTURE.md §5.3/schemas/markets.py), never a delta merge."""
    from hunter_market_worker import wire as msgpack

    first = b.order_book(SYMBOL, "100", "100.1")
    # Explicit, strictly-later `ts`: two `utcnow()` calls back-to-back can
    # land in the same microsecond, and `_newer()` (hot_state.py) is a
    # strict `>` -- an equal `ts` would make this test flaky rather than
    # exercising the replacement it is meant to prove.
    second = b.order_book(SYMBOL, "200", "200.1", ts=first.ts + timedelta(milliseconds=1))
    assert await hot_state.write_book(worker_redis, first)
    assert await hot_state.write_book(worker_redis, second)

    raw = await worker_redis.get(keys.book(EXCHANGE, SYMBOL))
    payload = msgpack.unpackb(raw)
    assert payload["bids"] == [["200", "5"]]  # the "100" level is gone, not merged in
    assert payload["asks"] == [["200.1", "2"]]


# ---------------------------------------------------------------------------
# event_id == liquidation row id, consumer dedupe
# ---------------------------------------------------------------------------


async def test_liquidation_event_id_matches_the_deterministic_row_id(
    worker_session_factory: async_sessionmaker[AsyncSession],
    worker_redis: Any,
    worker_settings: Settings,
) -> None:
    """Since T2.9 a liquidation is not published directly: ``flush_batch``
    inserts the row and queues the ``market.liquidations`` event in the same
    transaction (transactional outbox). The identity contract is unchanged —
    the queued ``event_id`` is the row's uuid5 primary key — so a consumer can
    dedupe a redelivery against the row it already has."""
    from sqlalchemy import select

    from hunter_core.db.models.system import OutboxEvent
    from hunter_core.events.streams import Streams

    await _seed_market(worker_session_factory, worker_redis, worker_settings)
    liq = b.liquidation(SYMBOL, price="1234.5", qty="0.02")

    inserted = await flush_batch(worker_session_factory, EXCHANGE, [liq])
    assert inserted == {liquidation_id(liq)}

    async with worker_session_factory() as session:
        rows = (
            await session.execute(
                select(OutboxEvent.event_id, OutboxEvent.stream).where(
                    OutboxEvent.stream == Streams.MARKET_LIQUIDATIONS,
                    OutboxEvent.event_id == liquidation_id(liq),
                )
            )
        ).all()
    assert len(rows) == 1, "one identity end to end: the queued event is the row's id"


# ---------------------------------------------------------------------------
# data_quality precedence at the API (T1.4 decision conjunta rodada 4)
# ---------------------------------------------------------------------------


@pytest.fixture
async def quality_market(
    worker_session_factory: async_sessionmaker[AsyncSession],
    worker_redis: Any,
    worker_settings: Settings,
) -> str:
    """A freshly monitored market with a CLEAN hot-state slate.

    Each call uses a unique symbol (not a shared ``QUALUSDT``): this suite's
    Postgres database is session-scoped and shared across every test in this
    file (see ``test_market_pipeline.py``'s isolation note), so two tests
    reusing one symbol would leak ``ingestion_gaps``/``markets`` rows into
    each other. ``refresh_universe`` itself warms the ticker hash for a newly
    monitored symbol (T1.3), so that key is deleted right back out here —
    every quality test below controls its own hot state from nothing.
    """
    symbol = f"QUAL{uuid.uuid4().hex[:8].upper()}USDT"
    await _seed_market(worker_session_factory, worker_redis, worker_settings, symbol)
    await worker_redis.delete(keys.ticker(EXCHANGE, symbol))
    return symbol


async def _row(
    pipeline_client: httpx.AsyncClient, authed_actor: dict[str, str], symbol: str
) -> Any:
    resp = await pipeline_client.get("/api/v1/markets", headers=authed_actor)
    assert resp.status_code == 200, resp.text
    return next(item for item in resp.json()["items"] if item["symbol"] == symbol)


async def test_no_data_at_all_is_unavailable(
    quality_market: str, pipeline_client: httpx.AsyncClient, authed_actor: dict[str, str]
) -> None:
    row = await _row(pipeline_client, authed_actor, quality_market)
    assert row["data_quality"] == "unavailable"
    assert row["components"]["ticker"]["quality"] == "absent"


async def test_book_stopped_with_ticker_and_mark_active_is_degraded(
    quality_market: str,
    worker_redis: Any,
    pipeline_client: httpx.AsyncClient,
    authed_actor: dict[str, str],
) -> None:
    symbol = quality_market
    await hot_state.write_ticker(worker_redis, b.ticker(symbol, "10"), source="rest")
    await hot_state.write_funding(worker_redis, b.funding(symbol, mark_price=Decimal("10")))
    # book never written for this market -> absent, a required component.
    row = await _row(pipeline_client, authed_actor, symbol)
    assert row["components"]["book"]["quality"] == "absent"
    assert row["data_quality"] == "degraded"


async def test_mark_stopped_with_ticker_and_book_active_is_degraded(
    quality_market: str,
    worker_redis: Any,
    pipeline_client: httpx.AsyncClient,
    authed_actor: dict[str, str],
) -> None:
    symbol = quality_market
    await hot_state.write_ticker(worker_redis, b.ticker(symbol, "10"), source="rest")
    await hot_state.write_book(worker_redis, b.order_book(symbol))
    row = await _row(pipeline_client, authed_actor, symbol)
    assert row["components"]["mark"]["quality"] == "absent"
    assert row["data_quality"] == "degraded"


async def test_open_interest_updates_while_mark_is_stopped_stay_independent(
    quality_market: str,
    worker_redis: Any,
    pipeline_client: httpx.AsyncClient,
    authed_actor: dict[str, str],
) -> None:
    """T1.4 decision conjunta: OI has its own age, never borrows the ``mark``
    component's freshness or vice-versa -- an OI update alone must not make a
    stopped ``mark`` (and therefore the aggregate) look any less degraded."""
    symbol = quality_market
    await hot_state.write_ticker(worker_redis, b.ticker(symbol, "10"), source="rest")
    await hot_state.write_book(worker_redis, b.order_book(symbol))
    await hot_state.write_open_interest(worker_redis, b.open_interest(symbol))
    row = await _row(pipeline_client, authed_actor, symbol)
    assert row["components"]["open_interest"]["age_ms"] is not None
    assert row["components"]["mark"]["quality"] == "absent"
    assert row["data_quality"] == "degraded"


async def test_a_fresh_open_interest_write_never_rejuvenates_a_stale_mark(
    quality_market: str,
    worker_redis: Any,
    pipeline_client: httpx.AsyncClient,
    authed_actor: dict[str, str],
) -> None:
    """Astra's second opinion (T1.7): the sibling test above only proves
    ``mark`` reads ``absent`` when it was NEVER written -- it would still
    pass even if a fresh OI write rejuvenated an EXISTING, aging ``mark``
    (the H4/H5-class bug ``hot_state.write_open_interest`` owning only its
    own ``oi_ts`` field is meant to prevent). Here ``mark`` is genuinely
    written, then ages past ``market_stale_after_s`` while OI keeps
    updating -- ``mark`` must still read ``stale``, not ``ok``.
    """
    symbol = quality_market
    old_ts = utcnow() - timedelta(seconds=11)  # market_stale_after_s=10 in this suite's settings
    await hot_state.write_ticker(worker_redis, b.ticker(symbol, "10"), source="rest")
    await hot_state.write_book(worker_redis, b.order_book(symbol))
    await hot_state.write_funding(
        worker_redis, b.funding(symbol, mark_price=Decimal("10"), ts=old_ts)
    )

    # OI updates repeatedly, in the same `deriv` hash `mark` lives in --
    # each write must touch only its own `oi_ts`/`open_interest*` fields.
    await hot_state.write_open_interest(worker_redis, b.open_interest(symbol, ts=utcnow()))
    row = await _row(pipeline_client, authed_actor, symbol)
    assert row["components"]["mark"]["quality"] == "stale"
    assert row["components"]["mark"]["age_ms"] >= 11_000  # unchanged by the OI write
    assert row["components"]["open_interest"]["age_ms"] < 2_000  # OI itself is fresh
    assert row["data_quality"] == "stale"


async def test_a_required_component_older_than_stale_after_s_is_stale_not_ok(
    quality_market: str,
    worker_redis: Any,
    pipeline_client: httpx.AsyncClient,
    authed_actor: dict[str, str],
) -> None:
    symbol = quality_market
    old_ts = utcnow() - timedelta(seconds=11)  # market_stale_after_s=10 in this suite's settings
    await hot_state.write_ticker(worker_redis, b.ticker(symbol, "10", ts=old_ts), source="rest")
    await hot_state.write_book(worker_redis, b.order_book(symbol, ts=old_ts))
    await hot_state.write_funding(
        worker_redis, b.funding(symbol, mark_price=Decimal("10"), ts=old_ts)
    )
    row = await _row(pipeline_client, authed_actor, symbol)
    assert row["data_quality"] == "stale"
    assert row["components"]["ticker"]["age_ms"] >= 11_000


async def test_all_required_components_fresh_and_no_gap_is_ok(
    quality_market: str,
    worker_redis: Any,
    pipeline_client: httpx.AsyncClient,
    authed_actor: dict[str, str],
) -> None:
    symbol = quality_market
    await hot_state.write_ticker(worker_redis, b.ticker(symbol, "10"), source="rest")
    await hot_state.write_book(worker_redis, b.order_book(symbol))
    await hot_state.write_funding(worker_redis, b.funding(symbol, mark_price=Decimal("10")))
    row = await _row(pipeline_client, authed_actor, symbol)
    assert row["data_quality"] == "ok"


async def test_component_age_ms_is_the_exchange_event_ts_never_the_flush_time(
    quality_market: str,
    worker_redis: Any,
    pipeline_client: httpx.AsyncClient,
    authed_actor: dict[str, str],
) -> None:
    """T1.4: ``age_ms`` must reflect ``now - <exchange ts>``, not ``now -
    <write time>`` -- write a ticker whose own ``ts`` is already 5s old and
    confirm the API reports roughly that age, not ~0."""
    symbol = quality_market
    event_ts = utcnow() - timedelta(seconds=5)
    await hot_state.write_ticker(worker_redis, b.ticker(symbol, "10", ts=event_ts), source="rest")
    row = await _row(pipeline_client, authed_actor, symbol)
    age_ms = row["components"]["ticker"]["age_ms"]
    assert 4500 <= age_ms <= 8000  # generous band for test wall-clock overhead, never ~0


async def test_open_or_failed_gap_degrades_even_with_fresh_ticks(
    quality_market: str,
    worker_redis: Any,
    worker_session_factory: async_sessionmaker[AsyncSession],
    pipeline_client: httpx.AsyncClient,
    authed_actor: dict[str, str],
) -> None:
    """T1.4 decision conjunta: 'gap failed com ticks atuais' -- an ingestion
    gap degrades the market even though every required component is fresh."""
    symbol = quality_market
    await hot_state.write_ticker(worker_redis, b.ticker(symbol, "10"), source="rest")
    await hot_state.write_book(worker_redis, b.order_book(symbol))
    await hot_state.write_funding(worker_redis, b.funding(symbol, mark_price=Decimal("10")))

    from sqlalchemy import select

    from hunter_core.db.models.market_data import IngestionGap
    from hunter_core.db.models.markets import Exchange, Market

    async with worker_session_factory() as session:
        market_id = await session.scalar(
            select(Market.id)
            .join(Exchange, Exchange.id == Market.exchange_id)
            .where(Exchange.code == EXCHANGE, Market.symbol == symbol)
        )
        open_time = align_open_time(utcnow(), Timeframe.M1)
        session.add(
            IngestionGap(
                market_id=market_id,
                timeframe=Timeframe.M1,
                gap_start=open_time,
                gap_end=open_time,
                status="failed",
                attempts=5,
            )
        )
        await session.commit()

    row = await _row(pipeline_client, authed_actor, symbol)
    assert row["has_open_gap"] is True
    assert row["data_quality"] == "degraded"
    assert row["components"]["ticker"]["quality"] == "ok"  # the gap, not a dead component


async def test_time_advancing_with_no_new_publication_eventually_reads_stale(
    quality_market: str,
    worker_redis: Any,
    pipeline_client: httpx.AsyncClient,
    authed_actor: dict[str, str],
) -> None:
    """The literal 'passagem do tempo sem publicações' scenario -- exercised
    via a backdated ``ts`` (clock injetável), not a real sleep."""
    symbol = quality_market
    await hot_state.write_ticker(worker_redis, b.ticker(symbol, "10"), source="rest")
    await hot_state.write_book(worker_redis, b.order_book(symbol))
    await hot_state.write_funding(worker_redis, b.funding(symbol, mark_price=Decimal("10")))
    row = await _row(pipeline_client, authed_actor, symbol)
    assert row["data_quality"] == "ok"

    # No new event arrives; the next read is what "time passing" means here --
    # rewrite only the ticker's ts backwards without ever repeating "fresh".
    stale_ts = utcnow() - timedelta(seconds=30)
    await worker_redis.hset(keys.ticker(EXCHANGE, symbol), mapping={"ts": stale_ts.isoformat()})
    row_after = await _row(pipeline_client, authed_actor, symbol)
    assert row_after["data_quality"] == "stale"
