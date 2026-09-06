"""Persistence helpers for one universe refresh cycle (docs/plans/M1.md T1.3).

Split out of ``universe.py`` to keep that module under the 350-line budget
(CLAUDE.md) once HIGH-3's retry backoff was added: this module owns only the
``assets``/``markets`` upserts, delisting and ranking writes, never the
refresh orchestration or the retry loop.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from sqlalchemy import Boolean, Integer, column, func, select, update
from sqlalchemy import values as sa_values
from sqlalchemy.dialects import postgresql
from sqlalchemy.dialects.postgresql import insert as pg_insert

from hunter_core.db.models.agents_shadow import ShadowEpisode
from hunter_core.db.models.markets import Asset, Exchange, Market
from hunter_core.domain.enums import MarketStatus, MarketType
from hunter_core.domain.types import utcnow

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from hunter_core.domain.market import NormalizedMarket, NormalizedTicker
    from hunter_core.settings import Settings


async def upsert_exchange(session: AsyncSession, code: str) -> Any:
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


async def upsert_assets(session: AsyncSession, symbols: set[str]) -> dict[str, Any]:
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


async def upsert_markets(
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


async def mark_delisted(
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


async def tracking_hold_symbols(session: AsyncSession, exchange_id: Any) -> set[str]:
    """Symbols this exchange must keep collecting for the Shadow Lab.

    docs/plans/SHADOW-LAB.md §8: a market may leave the monitored universe, but
    not while a shadow tracking still needs its 1m candles — losing them would
    turn an outcome that was merely out of the top N into a *censored* one.

    The predicate is ``shadow_episodes.open_outcome_signal_id IS NOT NULL``
    (served by the partial index ``ix_shadow_episodes_hold``), so the hold is
    durable and survives a restart: it is derived from the database, never from
    a worker's memory. Several versions may hold the same market — ending one
    experiment does not release the collection another still depends on, which
    is why this is a set of symbols and not a per-version flag.
    """
    rows = await session.scalars(
        select(Market.symbol)
        .join(ShadowEpisode, ShadowEpisode.market_id == Market.id)
        .where(
            Market.exchange_id == exchange_id,
            ShadowEpisode.open_outcome_signal_id.is_not(None),
        )
        .distinct()
    )
    return set(rows)


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


async def rank_and_monitor(
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
