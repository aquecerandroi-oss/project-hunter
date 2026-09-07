"""The tradable **SPOT** universe — a floor, not a top-N (T3.0c, D1).

The perpetual universe (``universe.py``) keeps the top ``MARKET_UNIVERSE_SIZE``
markets by volume: it exists so the scanner has *something* to look at, and the
number is a capacity decision. The spot universe answers a different question —
"where may the wallet actually execute?" — and its rule is the one Everton
wrote: **24h quote volume of at least 50M USDT, measured on spot itself**
(``.claude/state/decisions-M3-delegated-2026-09-06.md`` D1). Nineteen pairs
cleared it when T3.0a measured, against the ~50 the decision had estimated; the
rule is the floor, never the count.

Three things follow from that and are enforced here rather than assumed:

- **the volume is read on the execution venue.** A perpetual's 24h volume says
  nothing about the depth of the spot book the simulated fill walks;
- **a pair with no ticker is out.** Not "assume it is liquid until we know
  otherwise" — the floor is a permission, and a permission is never granted by
  a failed read;
- **the quote must be USDT.** The wallet is denominated in USDT; a BTC-quoted
  pair of the same base is a different instrument with a different numeraire.

Everything else — the ``markets`` rows, the delisting sweep, the durable
``market.universe.changed`` — is the perpetual path's machinery reused with
``market_type=SPOT``, which is exactly what T3.0b made possible.
"""

from __future__ import annotations

import asyncio
import random
from decimal import Decimal
from typing import TYPE_CHECKING, Any

from sqlalchemy import select

from hunter_core.db.models.markets import Exchange, Market
from hunter_core.db.session import role_session
from hunter_core.domain.enums import MarketStatus, MarketType
from hunter_core.domain.types import utcnow
from hunter_core.logging import get_logger
from hunter_core.observability import market_spot_universe_size
from hunter_market_worker.durable import enqueue_universe_changed
from hunter_market_worker.hot_state import write_ticker
from hunter_market_worker.universe import MonitoredUniverse, retry_delay
from hunter_market_worker.universe_repo import (
    mark_delisted,
    monitor_by_floor,
    upsert_assets,
    upsert_exchange,
    upsert_markets,
)

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable, Collection, Iterable

    import redis.asyncio as redis_asyncio
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    from hunter_core.domain.market import NormalizedMarket, NormalizedTicker
    from hunter_core.runtime import WorkerRuntime
    from hunter_core.settings import Settings
    from hunter_exchanges.base import ExchangeAdapter

logger = get_logger(__name__)

SPOT_QUOTE = "USDT"
"""The wallet's numeraire. A BTC-quoted pair is a different instrument."""

SPOT_VOLUME_FLOOR_USDT = Decimal("50000000")
"""D1: 50M USDT of 24h quote volume, **on spot**. Everton's number; changing it
is his call, so it is a constant with a name and not an environment knob."""


def tradable_symbols(
    markets: Iterable[NormalizedMarket],
    tickers: dict[str, NormalizedTicker],
    *,
    floor: Decimal = SPOT_VOLUME_FLOOR_USDT,
    blocklist: Collection[str] = (),
) -> set[str]:
    """Which spot pairs the wallet may execute on, right now.

    Pure so the rule that decides where real (simulated) money goes is pinned
    by a test against a recorded snapshot of the exchange, not observed on a
    running worker. ``>=`` on purpose: a pair exactly on the floor is in.
    """
    blocked = {symbol.upper() for symbol in blocklist}
    eligible: set[str] = set()
    for market in markets:
        if market.market_type is not MarketType.SPOT:
            continue
        if market.quote != SPOT_QUOTE or market.status is not MarketStatus.ACTIVE:
            continue
        if market.symbol.upper() in blocked:
            continue
        ticker = tickers.get(market.symbol)
        if ticker is None or ticker.quote_volume_24h is None:
            continue
        if ticker.quote_volume_24h >= floor:
            eligible.add(market.symbol)
    return eligible


async def _spot_tickers(adapter: ExchangeAdapter) -> dict[str, NormalizedTicker]:
    """One bulk ``ticker/24hr`` (weight 80 on spot), never 740 single calls.

    A spot adapter without the bulk endpoint is a programming error, not a
    degradation to work around: 740 weight-2 calls would be 1480 of the
    6000/min budget every refresh, and the floor would still be measured
    from a partial answer.
    """
    bulk = getattr(adapter, "fetch_tickers_24h", None)
    if bulk is None:
        raise RuntimeError(f"{adapter.code}: spot universe needs fetch_tickers_24h")
    return {ticker.symbol: ticker for ticker in await bulk()}


async def refresh_spot_universe(
    session_factory: async_sessionmaker[AsyncSession],
    adapter: ExchangeAdapter,
    redis: redis_asyncio.Redis,
    settings: Settings,
    *,
    producer: str,
) -> list[str]:
    """One spot universe cycle. Returns the sorted tradable symbol list."""
    markets = await adapter.list_markets(MarketType.SPOT)
    tickers = await _spot_tickers(adapter)
    eligible = tradable_symbols(markets, tickers, blocklist=settings.market_universe_blocklist)
    asset_symbols = {m.base for m in markets} | {m.quote for m in markets}
    refreshed_at = utcnow()

    payload: dict[str, Any] | None = None
    async with role_session(session_factory, db_role="hunter_worker") as session:
        exchange_id = await upsert_exchange(session, adapter.code)
        asset_ids = await upsert_assets(session, asset_symbols)
        # ``write_metadata``: the spot MARKET-order filters have no column of
        # their own and must survive into ``markets.metadata`` for T3.4. The
        # perpetual path leaves the column alone, so its rows do not change
        # under this release.
        await upsert_markets(session, exchange_id, markets, asset_ids, tickers, write_metadata=True)
        await mark_delisted(session, exchange_id, MarketType.SPOT, {m.symbol for m in markets})
        old_monitored, new_monitored = await monitor_by_floor(
            session, exchange_id, MarketType.SPOT, eligible
        )
        if old_monitored != new_monitored:
            payload = await enqueue_universe_changed(
                session,
                exchange=adapter.code,
                old_monitored=old_monitored,
                new_monitored=new_monitored,
                at=refreshed_at,
                producer=producer,
                market_type=MarketType.SPOT,
            )

    for symbol in sorted(new_monitored):
        ticker = tickers.get(symbol)
        if ticker is not None:
            # KB-0044: the REST 24h ticker owns its own fields only — the WS
            # ``bookTicker`` of the same spot pair owns bid/ask.
            await write_ticker(redis, ticker, source="rest")

    market_spot_universe_size.labels(exchange=adapter.code).set(len(new_monitored))
    if payload is not None:
        logger.info("market_spot_universe_changed", exchange=adapter.code, **payload)
    return sorted(new_monitored)


async def run_spot_universe(
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
    """Refresh the spot universe forever, on the perpetual's cadence.

    No leader election and no shard slice, unlike :func:`universe.run_universe`:
    there is exactly one spot collector per venue (``spot.collects_spot``), so
    it is the only writer by construction. A failed refresh backs off with the
    same jittered curve and **keeps the previous universe subscribed** — the
    tradable set changing is a fifteen-minute decision, and a REST hiccup is no
    reason to stop collecting the pairs the wallet is holding.
    """
    producer = f"market-worker@{runtime.instance}"
    consecutive_failures = 0
    while True:
        try:
            monitored = await refresh_spot_universe(
                session_factory, adapter, redis, settings, producer=producer
            )
            universe.set(monitored)
            runtime.mark_success()
            consecutive_failures = 0
            delay: float = settings.market_universe_refresh_s
        except Exception:
            logger.exception("market_spot_universe_refresh_failed", exchange=adapter.code)
            runtime.mark_error()
            consecutive_failures += 1
            delay = retry_delay(consecutive_failures, settings.market_universe_refresh_s, rand=rand)
        await sleep(delay)


async def monitored_spot_symbols(
    session_factory: async_sessionmaker[AsyncSession], exchange_code: str
) -> list[str]:
    """What Postgres says the spot universe is — the restart path.

    A worker that comes back before its first successful refresh must not
    collect nothing for 15 minutes; the last committed universe is the honest
    answer until the exchange is asked again.
    """
    async with role_session(session_factory, db_role="hunter_worker") as session:
        rows = await session.scalars(
            select(Market.symbol)
            .join(Exchange, Exchange.id == Market.exchange_id)
            .where(
                Exchange.code == exchange_code,
                Market.market_type == MarketType.SPOT,
                Market.is_monitored.is_(True),
            )
        )
        return sorted(rows)
