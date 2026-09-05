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
import random
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
"""Cap on individual ``fetch_ticker`` calls when the adapter has no bulk
``fetch_tickers_24h`` â€” keeps a universe refresh from hammering REST for an
exchange with thousands of symbols."""

UNIVERSE_RETRY_BASE_S = 5.0
"""HIGH-3: first retry delay after a failed refresh."""
UNIVERSE_RETRY_MAX_S = 120.0
"""Hard cap on the retry backoff, well below any realistic
``market_universe_refresh_s`` (900s default) so a persistent failure keeps
retrying every couple of minutes instead of sliding back to the full
success interval."""
UNIVERSE_RETRY_JITTER_FRACTION = 0.2
"""Up to +20% jitter on top of the backoff, so several instances that failed
at the same moment (e.g. a shared Postgres restart) do not retry in lockstep."""


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
    exponential from :data:`UNIVERSE_RETRY_BASE_S`, capped well below the
    normal success interval, plus jitter. A single failed refresh must never
    cost the worker a full ``market_universe_refresh_s`` (900s default) of
    blindness — Postgres restarts, brief exchange 5xxs, etc. are routine."""
    cap = min(UNIVERSE_RETRY_MAX_S, max(UNIVERSE_RETRY_BASE_S, refresh_s / 3))
    # Clamp the exponent before raising it, not after: ``2 ** (attempt - 1)``
    # is computed in full before ``min`` sees it, so an outage lasting long
    # enough for ``attempt`` to reach ~1024 (about 41h at the capped delay)
    # would raise ``OverflowError: int too large to convert to float`` inside
    # this helper — killing ``run_universe`` and the whole TaskGroup for a
    # reason unrelated to the outage. 64 doublings already exceed any cap.
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
    """Refresh the universe immediately, then every ``market_universe_refresh_s``
    on success -- or on a short, capped, jittered backoff after a failure
    (HIGH-3, see :func:`_retry_delay`). ``runtime.mark_error()``/
    ``mark_success()`` semantics, and "log and keep going" on failure, are
    unchanged; only the delay before the next attempt differs."""
    producer = f"market-worker@{runtime.instance}"
    consecutive_failures = 0
    while True:
        try:
            monitored = await refresh_universe(
                session_factory, adapter, redis, settings, producer=producer
            )
            universe.set(monitored)
            runtime.mark_success()
            consecutive_failures = 0
            delay: float = settings.market_universe_refresh_s
        except Exception:
            logger.exception("market_universe_refresh_failed")
            runtime.mark_error()
            consecutive_failures += 1
            delay = _retry_delay(
                consecutive_failures, settings.market_universe_refresh_s, rand=rand
            )
        await sleep(delay)
