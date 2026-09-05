"""The monitored market universe â€” docs/plans/M1.md T1.3, PIPELINE.md Â§1.1.

Every ``market_universe_refresh_s``: list perpetuals, fetch 24h tickers,
upsert ``assets``/``markets``, rank by ``volume_24h_usd`` into
``monitor_rank``, derive ``is_monitored``. Publishes ``market.universe.changed``
only when the set changes, and shares it via :class:`MonitoredUniverse`.

T1.6b-C2/C4: with ``MARKET_SHARD=i/N``, one shard per exchange holds a
token-checked lock and is the *leader* refreshing from REST; every other
shard *follows* its versioned snapshot (or Postgres). Both narrow the result
via :func:`shard_symbols` before :meth:`MonitoredUniverse.set` -- the one
place the filter applies, so downstream consumers inherit it for free.
"""

from __future__ import annotations

import asyncio
import dataclasses
import random
import zlib
from typing import TYPE_CHECKING

from sqlalchemy import select, update

from hunter_core.db.models.markets import Market
from hunter_core.db.session import role_session
from hunter_core.domain.enums import MarketType
from hunter_core.events.envelope import EventEnvelope
from hunter_core.events.streams import DEFAULT_MAXLEN, Streams
from hunter_core.logging import get_logger
from hunter_exchanges.base import ExchangeError
from hunter_market_worker.hot_state import write_ticker
from hunter_market_worker.publication import publish
from hunter_market_worker.universe_leader import (
    FOLLOWER_POLL_S,
    LEADER_RENEW_INTERVAL_S,
    SNAPSHOT_TTL_MULTIPLIER,
    extend_leader,
    follower_symbols,
    load_snapshot,
    try_become_leader,
    write_snapshot,
)
from hunter_market_worker.universe_repo import (
    mark_delisted,
    rank_and_monitor,
    upsert_assets,
    upsert_exchange,
    upsert_markets,
)

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    import redis.asyncio as redis_asyncio
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    from hunter_core.domain.market import NormalizedTicker
    from hunter_core.runtime import WorkerRuntime
    from hunter_core.settings import Settings
    from hunter_exchanges.base import ExchangeAdapter

logger = get_logger(__name__)

TICKER_FETCH_CAP = 300
"""Cap on ``fetch_ticker`` calls when the adapter has no bulk endpoint."""

UNIVERSE_RETRY_BASE_S = 5.0
"""HIGH-3: first retry delay after a failed refresh."""
UNIVERSE_RETRY_MAX_S = 120.0
"""Backoff cap, well below ``market_universe_refresh_s`` (900s default)."""
UNIVERSE_RETRY_JITTER_FRACTION = 0.2
"""Up to +20% jitter so instances that failed together do not retry in lockstep."""


def shard_symbols(symbols: list[str], shard_index: int, shard_total: int) -> list[str]:
    """C2: stable slice -- ``crc32(symbol) % total == index``. ``total == 1``
    yields every symbol unchanged (``x % 1`` is always ``0``)."""
    return sorted(s for s in symbols if zlib.crc32(s.encode("ascii")) % shard_total == shard_index)


@dataclasses.dataclass
class MonitoredUniverse:
    """Shared, mutable view of the monitored symbol set; ``ingest.py`` watches
    :attr:`changed` to know when to restart its WS subscription."""

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
        exchange_id = await upsert_exchange(session, adapter.code)
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
        asset_ids = await upsert_assets(session, asset_symbols)
        await upsert_markets(session, exchange_id, markets, asset_ids, tickers)
        await mark_delisted(session, exchange_id, MarketType.PERPETUAL, {m.symbol for m in markets})
        _, new_monitored = await rank_and_monitor(
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


def _retry_delay(
    attempt: int, refresh_s: float, *, rand: Callable[[], float] = random.random
) -> float:
    """Backoff for the ``attempt``-th consecutive failed refresh (HIGH-3):
    exponential, capped well below the normal success interval, plus jitter."""
    cap = min(UNIVERSE_RETRY_MAX_S, max(UNIVERSE_RETRY_BASE_S, refresh_s / 3))
    # Clamp the exponent before raising it (not after): an outage long enough
    # for ``attempt`` to reach ~1024 would otherwise overflow ``2 ** attempt``.
    exponent = min(attempt - 1, 64)
    backoff = min(cap, UNIVERSE_RETRY_BASE_S * (2**exponent))
    return backoff + backoff * UNIVERSE_RETRY_JITTER_FRACTION * rand()


async def run_universe(
    session_factory: async_sessionmaker[AsyncSession],
    adapter: ExchangeAdapter,
    redis: redis_asyncio.Redis,
    settings: Settings,
    universe: MonitoredUniverse,
    runtime: WorkerRuntime,
    *,
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    rand: Callable[[], float] = random.random,
) -> None:
    """C4: the lock holder refreshes from REST and publishes a versioned
    snapshot; every other shard follows it (or Postgres). ``shard_total == 1``
    makes the lone process its own perpetual leader -- unchanged behaviour."""
    producer = f"market-worker@{runtime.instance}"
    consecutive_failures = 0
    token = ""
    # A lone process (``MARKET_SHARD=0/1``, the default) is its own perpetual
    # leader: no lock, no snapshot, no renewal round trips -- exactly the M1
    # behaviour, so single-instance deployments gain no new Redis dependency.
    solo = settings.shard_total == 1
    while True:
        if solo:
            is_leader = True
        else:
            is_leader, token = await try_become_leader(redis, adapter.code, token)
        try:
            if is_leader:
                snapshot = None if solo else await load_snapshot(redis, adapter.code)
                next_version = int(snapshot["version"]) + 1 if snapshot else 1
                monitored = await refresh_universe(
                    session_factory, adapter, redis, settings, producer=producer
                )
                if not solo:
                    await write_snapshot(
                        redis,
                        adapter.code,
                        monitored,
                        next_version,
                        SNAPSHOT_TTL_MULTIPLIER * settings.market_universe_refresh_s,
                    )
                delay: float = settings.market_universe_refresh_s
            else:
                monitored = await follower_symbols(session_factory, redis, adapter.code, settings)
                delay = FOLLOWER_POLL_S
            universe.set(shard_symbols(monitored, settings.shard_index, settings.shard_total))
            runtime.mark_success()
            consecutive_failures = 0
        except Exception:
            logger.exception("market_universe_refresh_failed")
            runtime.mark_error()
            consecutive_failures += 1
            delay = _retry_delay(
                consecutive_failures, settings.market_universe_refresh_s, rand=rand
            )
        if solo or not is_leader:
            await sleep(delay)
            continue
        remaining = delay
        while remaining > 0:
            chunk = min(LEADER_RENEW_INTERVAL_S, remaining)
            await sleep(chunk)
            remaining -= chunk
            # Lost the lock mid-sleep: stop waiting out a delay that can be
            # minutes long and go straight back to the top to reassess.
            if remaining > 0 and not await extend_leader(redis, adapter.code, token):
                break
