"""The monitored market universe â€” docs/plans/M1.md T1.3, PIPELINE.md Â§1.1.

Every ``market_universe_refresh_s``: list perpetuals from the exchange, fetch
24h tickers, upsert ``assets``/``markets``, rank by ``volume_24h_usd`` desc
into ``monitor_rank``, and derive ``is_monitored`` (top
``MARKET_UNIVERSE_SIZE`` with the allowlist always in and the blocklist never
in). Publishes ``market.universe.changed`` only when the monitored set
actually changes, and shares that set with ``ingest.py`` through
:class:`MonitoredUniverse`.
"""

from __future__ import annotations

import asyncio
import dataclasses
from typing import TYPE_CHECKING, Any

from sqlalchemy import Boolean, Integer, column, func, select, update
from sqlalchemy import values as sa_values
from sqlalchemy.dialects import postgresql
from sqlalchemy.dialects.postgresql import insert as pg_insert

from hunter_core.db.models.markets import Asset, Exchange, Market
from hunter_core.db.session import role_session
from hunter_core.domain.enums import MarketStatus, MarketType
from hunter_core.domain.types import utcnow
from hunter_core.events.envelope import EventEnvelope
from hunter_core.events.streams import DEFAULT_MAXLEN, Streams
from hunter_core.logging import get_logger
from hunter_exchanges.base import ExchangeError
from hunter_market_worker.hot_state import write_ticker
from hunter_market_worker.publication import publish

if TYPE_CHECKING:
    import redis.asyncio as redis_asyncio
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    from hunter_core.domain.market import NormalizedMarket, NormalizedTicker
    from hunter_core.runtime import WorkerRuntime
    from hunter_core.settings import Settings
    from hunter_exchanges.base import ExchangeAdapter

logger = get_logger(__name__)

TICKER_FETCH_CAP = 300
"""Cap on individual ``fetch_ticker`` calls when the adapter has no bulk
``fetch_tickers_24h`` â€” keeps a universe refresh from hammering REST for an
exchange with thousands of symbols."""


@dataclasses.dataclass
class MonitoredUniverse:
    """Shared, mutable view of the monitored symbol set.

    ``ingest.py`` watches :attr:`changed` to know when to restart its WS
    subscription with a new symbol set.
    """

    symbols: list[str] = dataclasses.field(default_factory=lambda: list[str]())
    initialized: bool = False
    changed: asyncio.Event = dataclasses.field(default_factory=asyncio.Event)

    def set(self, symbols: list[str]) -> None:
        self.initialized = True
        if set(self.symbols) == set(symbols):
            return
        self.symbols = symbols
        self.changed.set()


async def _fetch_tickers(
    adapter: ExchangeAdapter, symbols: list[str]
) -> dict[str, NormalizedTicker]:
    bulk = getattr(adapter, "fetch_tickers_24h", None)
    if bulk is not None:
        try:
            tickers = await bulk()
        except ExchangeError as exc:
            logger.warning("market_universe_bulk_ticker_failed", error=str(exc))
            return {}
        return {t.symbol: t for t in tickers}
    result: dict[str, NormalizedTicker] = {}
    for symbol in symbols[:TICKER_FETCH_CAP]:
        try:
            result[symbol] = await adapter.fetch_ticker(symbol)
        except ExchangeError as exc:
            logger.warning("market_universe_ticker_failed", symbol=symbol, error=str(exc))
    return result


async def _upsert_exchange(session: AsyncSession, code: str) -> Any:
    exchange_id = await session.scalar(select(Exchange.id).where(Exchange.code == code))
    if exchange_id is not None:
        return exchange_id
    stmt = (
        pg_insert(Exchange)
        .values(code=code, name=code.capitalize())
        .on_conflict_do_update(index_elements=["code"], set_={"code": code})
        .returning(Exchange.id)
    )
    return await session.scalar(stmt)


async def _upsert_assets(session: AsyncSession, symbols: set[str]) -> dict[str, Any]:
    if not symbols:
        return {}
    stmt = (
        pg_insert(Asset)
        .values([{"symbol": s} for s in sorted(symbols)])
        .on_conflict_do_update(index_elements=["symbol"], set_={"symbol": Asset.symbol})
        .returning(Asset.id, Asset.symbol)
    )
    rows = (await session.execute(stmt)).all()
    return {row.symbol: row.id for row in rows}


async def _upsert_markets(
    session: AsyncSession,
    exchange_id: Any,
    markets: list[NormalizedMarket],
    asset_ids: dict[str, Any],
    tickers: dict[str, NormalizedTicker],
) -> None:
    now = utcnow()
    values = [
        {
            "exchange_id": exchange_id,
            "symbol": m.symbol,
            "market_type": m.market_type,
            "base_asset_id": asset_ids.get(m.base),
            "quote_asset_id": asset_ids.get(m.quote),
            "status": m.status,
            "delisted_at": now if m.status == MarketStatus.DELISTED else None,
            "tick_size": m.tick_size,
            "step_size": m.step_size,
            "min_notional": m.min_notional,
            "contract_size": m.contract_size,
            "max_leverage": m.max_leverage,
            "volume_24h_usd": (tickers[m.symbol].quote_volume_24h if m.symbol in tickers else None),
            "last_seen_at": now,
        }
        for m in markets
    ]
    if not values:
        return
    stmt = pg_insert(Market).values(values)
    excluded = stmt.excluded
    stmt = stmt.on_conflict_do_update(
        index_elements=["exchange_id", "symbol", "market_type"],
        set_={
            "status": excluded.status,
            "tick_size": excluded.tick_size,
            "step_size": excluded.step_size,
            "min_notional": excluded.min_notional,
            "contract_size": excluded.contract_size,
            "max_leverage": excluded.max_leverage,
            "base_asset_id": excluded.base_asset_id,
            "quote_asset_id": excluded.quote_asset_id,
            "volume_24h_usd": func.coalesce(excluded.volume_24h_usd, Market.volume_24h_usd),
            "last_seen_at": excluded.last_seen_at,
            "delisted_at": excluded.delisted_at,
        },
    )
    await session.execute(stmt)


async def _mark_delisted(
    session: AsyncSession, exchange_id: Any, market_type: MarketType, live_symbols: set[str]
) -> None:
    stmt = (
        select(Market.id)
        .where(Market.exchange_id == exchange_id)
        .where(Market.market_type == market_type)
        .where(Market.status != MarketStatus.DELISTED)
    )
    if live_symbols:
        stmt = stmt.where(Market.symbol.notin_(live_symbols))
    stale_ids = (await session.scalars(stmt)).all()
    if not stale_ids:
        return
    now = utcnow()
    await session.execute(
        update(Market)
        .where(Market.id.in_(stale_ids))
        .values(
            status=MarketStatus.DELISTED, delisted_at=now, is_monitored=False, monitor_rank=None
        )
    )


async def _apply_ranks(session: AsyncSession, rows: list[tuple[Any, int, bool]]) -> None:
    """HIGH-4: one ``UPDATE ... FROM (VALUES ...)`` for the whole ranking
    pass instead of one row-locking ``UPDATE`` per market — ~500 individual
    exclusive locks held for seconds, blocking every concurrent writer."""
    if not rows:
        return
    v = sa_values(
        column("id", postgresql.UUID(as_uuid=True)),
        column("rank", Integer()),
        column("monitored", Boolean()),
        name="v",
    ).data(rows)
    await session.execute(
        update(Market)
        .where(Market.id == v.c.id)
        .values(monitor_rank=v.c.rank, is_monitored=v.c.monitored)
    )


async def _rank_and_monitor(
    session: AsyncSession,
    exchange_id: Any,
    market_type: MarketType,
    settings: Settings,
) -> tuple[set[str], set[str]]:
    """Rank active markets by volume, apply allow/blocklist, write ranks back.

    Returns ``(old_monitored, new_monitored)`` symbol sets.
    """
    rows = (
        await session.execute(
            select(Market.id, Market.symbol, Market.is_monitored)
            .where(Market.exchange_id == exchange_id)
            .where(Market.market_type == market_type)
            .where(Market.status == MarketStatus.ACTIVE)
            .order_by(Market.volume_24h_usd.desc().nulls_last())
        )
    ).all()
    old_monitored = {row.symbol for row in rows if row.is_monitored}
    allowlist = {s.upper() for s in settings.market_universe_allowlist}
    blocklist = {s.upper() for s in settings.market_universe_blocklist}

    new_monitored: set[str] = set()
    eligible_rank = 0
    updates: list[tuple[Any, int, bool]] = []
    for rank, row in enumerate(rows, start=1):
        if row.symbol not in blocklist:
            eligible_rank += 1
        in_top = eligible_rank <= settings.market_universe_size
        is_monitored = (row.symbol in allowlist or in_top) and row.symbol not in blocklist
        if is_monitored:
            new_monitored.add(row.symbol)
        updates.append((row.id, rank, is_monitored))
    await _apply_ranks(session, updates)
    return old_monitored, new_monitored


async def refresh_universe(
    session_factory: async_sessionmaker[AsyncSession],
    adapter: ExchangeAdapter,
    redis: redis_asyncio.Redis,
    settings: Settings,
    *,
    producer: str,
) -> list[str]:
    """One universe refresh cycle. Returns the sorted monitored symbol list."""
    markets = await adapter.list_markets(MarketType.PERPETUAL)
    tickers = await _fetch_tickers(adapter, [m.symbol for m in markets])
    asset_symbols = {m.base for m in markets} | {m.quote for m in markets}

    async with role_session(session_factory, db_role="hunter_worker") as session:
        exchange_id = await _upsert_exchange(session, adapter.code)
        old_monitored = set(
            await session.scalars(
                select(Market.symbol).where(
                    Market.exchange_id == exchange_id,
                    Market.market_type == MarketType.PERPETUAL,
                    Market.is_monitored.is_(True),
                )
            )
        )
        await session.execute(
            update(Market)
            .where(Market.exchange_id == exchange_id, Market.market_type == MarketType.PERPETUAL)
            .values(is_monitored=False, monitor_rank=None)
        )
        asset_ids = await _upsert_assets(session, asset_symbols)
        await _upsert_markets(session, exchange_id, markets, asset_ids, tickers)
        await _mark_delisted(
            session, exchange_id, MarketType.PERPETUAL, {m.symbol for m in markets}
        )
        _, new_monitored = await _rank_and_monitor(
            session, exchange_id, MarketType.PERPETUAL, settings
        )

    for symbol in new_monitored:
        if symbol in tickers:
            await write_ticker(redis, tickers[symbol])

    if old_monitored != new_monitored:
        payload = {
            "added": sorted(new_monitored - old_monitored),
            "removed": sorted(old_monitored - new_monitored),
            "total": len(new_monitored),
        }
        envelope = EventEnvelope(
            type=Streams.MARKET_UNIVERSE_CHANGED,
            producer=producer,
            key=adapter.code,
            payload=payload,
        )
        await publish(
            redis,
            Streams.MARKET_UNIVERSE_CHANGED,
            envelope,
            DEFAULT_MAXLEN[Streams.MARKET_UNIVERSE_CHANGED],
        )
        logger.info("market_universe_changed", **payload)

    return sorted(new_monitored)


async def run_universe(
    session_factory: async_sessionmaker[AsyncSession],
    adapter: ExchangeAdapter,
    redis: redis_asyncio.Redis,
    settings: Settings,
    universe: MonitoredUniverse,
    runtime: WorkerRuntime,
) -> None:
    """Refresh the universe immediately, then every ``market_universe_refresh_s``."""
    producer = f"market-worker@{runtime.instance}"
    while True:
        try:
            monitored = await refresh_universe(
                session_factory, adapter, redis, settings, producer=producer
            )
            universe.set(monitored)
            runtime.mark_success()
        except Exception:
            logger.exception("market_universe_refresh_failed")
            runtime.mark_error()
        await asyncio.sleep(settings.market_universe_refresh_s)
