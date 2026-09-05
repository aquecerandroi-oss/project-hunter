"""Natural-key idempotent inserts. Source timestamps are preserved.

Every ``upsert_*`` here builds **one** multi-row ``INSERT ... ON CONFLICT DO
NOTHING`` per table per flush (CRITICAL-1/H6). A single-statement ``DO
NOTHING`` never raises on duplicate rows within the same statement (only
``DO UPDATE`` does) — it silently keeps the *first* occurrence and drops the
rest (D10). That is the wrong row when a batch carries more than one reading
for the same natural key: the later one is the newer one. So every batch is
deduplicated in Python first, keeping the **last** occurrence per conflict
key, before it ever reaches Postgres.
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from hunter_core.db.models.market_data import (
    Candle,
    FundingRate,
    Liquidation,
    MarketSnapshot,
    OpenInterestHistory,
)
from hunter_core.db.models.markets import Exchange, Market
from hunter_core.db.session import role_session
from hunter_core.domain.market import (
    NormalizedCandle,
    NormalizedFunding,
    NormalizedLiquidation,
    NormalizedOpenInterest,
)
from hunter_core.observability import market_liquidation_duplicates_total
from hunter_market_worker.publication import liquidation_id
from hunter_market_worker.queues import (
    OpenInterestSample,
    PersistItem,
    RealizedFunding,
    Snapshot,
    losses_total,
)

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker


OI_BUCKET_MINUTES = 5


def oi_bucket(ts: datetime) -> datetime:
    """The 5-minute UTC grid slot ``open_interest_history.ts`` stores (DATABASE.md §4).

    Idempotent: an already aligned timestamp maps to itself. Callers that poll a
    whole universe in one round pass the *cycle* timestamp, so every market lands
    on the same slot even when the round straddles a boundary.
    """
    return ts.replace(minute=ts.minute - ts.minute % OI_BUCKET_MINUTES, second=0, microsecond=0)


def _dedupe_last(rows: dict[Any, dict[str, Any]]) -> list[dict[str, Any]]:
    """The values already collapsed by conflict key, keeping insertion order
    of last-write-wins (D10) — see the module docstring."""
    return list(rows.values())


async def load_market_ids(
    session: AsyncSession, exchange_code: str, symbols: set[str]
) -> dict[str, Any]:
    if not symbols:
        return {}
    rows = (
        await session.execute(
            select(Market.id, Market.symbol)
            .join(Exchange, Exchange.id == Market.exchange_id)
            .where(Exchange.code == exchange_code)
            .where(Market.symbol.in_(symbols))
        )
    ).all()
    return {row.symbol: row.id for row in rows}


async def upsert_candles(
    session: AsyncSession,
    candles: list[NormalizedCandle],
    market_ids: dict[str, Any],
    *,
    source: str,
) -> int:
    """``INSERT ... ON CONFLICT (market_id, timeframe, open_time) DO NOTHING``."""
    rows: dict[tuple[Any, Any, datetime], dict[str, Any]] = {}
    for c in candles:
        if not c.is_final:
            continue
        market_id = market_ids.get(c.symbol)
        if market_id is None:
            losses_total.labels(kind=c.kind, reason="unknown_market").inc()
            continue
        rows[(market_id, c.timeframe, c.open_time)] = {
            "market_id": market_id,
            "timeframe": c.timeframe,
            "open_time": c.open_time,
            "open": c.open,
            "high": c.high,
            "low": c.low,
            "close": c.close,
            "volume": c.volume,
            "quote_volume": c.quote_volume,
            "trade_count": c.trade_count,
            "taker_buy_volume": c.taker_buy_volume,
            "is_final": True,
            "source": source,
        }
    if not rows:
        return 0
    stmt = (
        pg_insert(Candle)
        .values(_dedupe_last(rows))
        .on_conflict_do_nothing(index_elements=["market_id", "timeframe", "open_time"])
    )
    result = await session.execute(stmt.returning(Candle.open_time))
    return len(result.all())


async def upsert_funding(
    session: AsyncSession, items: list[NormalizedFunding], market_ids: dict[str, Any]
) -> None:
    rows: dict[tuple[Any, datetime], dict[str, Any]] = {}
    for f in items:
        if not isinstance(f, RealizedFunding):
            continue
        market_id = market_ids.get(f.symbol)
        if market_id is None:
            losses_total.labels(kind=f.kind, reason="unknown_market").inc()
            continue
        rows[(market_id, f.ts)] = {
            "market_id": market_id,
            "funding_time": f.ts,
            "rate": f.funding_rate,
            "mark_price": f.mark_price,
        }
    if not rows:
        return
    stmt = (
        pg_insert(FundingRate)
        .values(_dedupe_last(rows))
        .on_conflict_do_nothing(index_elements=["market_id", "funding_time"])
    )
    await session.execute(stmt)


async def upsert_liquidations(
    session: AsyncSession, items: list[NormalizedLiquidation], market_ids: dict[str, Any]
) -> set[Any]:
    """``INSERT ... ON CONFLICT (id, ts) DO NOTHING``, returning the ids actually
    inserted (M1/D7) so callers only republish what is newly durable.

    ``ts`` is truncated to the millisecond before it is stored (D11):
    :func:`hunter_market_worker.publication.liquidation_id` hashes the
    timestamp at millisecond precision, but the primary key is ``(id, ts)`` —
    storing the untruncated microsecond value would let the same logical
    liquidation, redelivered with a different sub-millisecond ``ts``, collide
    on ``id`` without matching on ``ts`` and be inserted twice.
    """
    rows: dict[tuple[Any, datetime], dict[str, Any]] = {}
    attempted = 0
    for liq in items:
        market_id = market_ids.get(liq.symbol)
        if market_id is None:
            losses_total.labels(kind=liq.kind, reason="unknown_market").inc()
            continue
        attempted += 1
        liq_id = liquidation_id(liq)
        ts = liq.ts.replace(microsecond=(liq.ts.microsecond // 1000) * 1000)
        rows[(liq_id, ts)] = {
            "id": liq_id,
            "ts": ts,
            "market_id": market_id,
            "side": liq.side,
            "qty": liq.qty,
            "price": liq.price,
            "notional": liq.notional,
            "source": "ws",
        }
    if not rows:
        return set()
    stmt = (
        pg_insert(Liquidation)
        .values(_dedupe_last(rows))
        .on_conflict_do_nothing(index_elements=["id", "ts"])
        .returning(Liquidation.id)
    )
    result = await session.execute(stmt)
    inserted_ids = {row[0] for row in result.all()}
    duplicates = attempted - len(inserted_ids)
    if duplicates > 0:
        market_liquidation_duplicates_total.inc(duplicates)
    return inserted_ids


async def upsert_snapshots(
    session: AsyncSession, snapshots: list[Snapshot], market_ids: dict[str, Any]
) -> None:
    rows: dict[tuple[Any, datetime], dict[str, Any]] = {}
    for snapshot in snapshots:
        market_id = market_ids.get(snapshot.symbol)
        if market_id is None:
            losses_total.labels(kind=snapshot.kind, reason="unknown_market").inc()
            continue
        row = {"market_id": market_id, **snapshot.values}
        rows[(market_id, row["ts"])] = row
    if not rows:
        return
    stmt = (
        pg_insert(MarketSnapshot)
        .values(_dedupe_last(rows))
        .on_conflict_do_nothing(index_elements=["market_id", "ts"])
    )
    await session.execute(stmt)


async def upsert_open_interest(
    session: AsyncSession,
    interests: list[NormalizedOpenInterest | OpenInterestSample],
    market_ids: dict[str, Any],
) -> None:
    """Both shapes of an open-interest reading land here (D8).

    An :class:`OpenInterestSample` carries the bucket of its polling round and
    that bucket is used verbatim, so every market of one round shares a slot.
    A bare :class:`NormalizedOpenInterest` comes from the WS path, which has no
    round, and keeps deriving its bucket from its own ``ts``.
    """
    rows: dict[tuple[Any, datetime], dict[str, Any]] = {}
    for item in interests:
        oi = item.reading if isinstance(item, OpenInterestSample) else item
        market_id = market_ids.get(oi.symbol)
        if market_id is None:
            losses_total.labels(kind=oi.kind, reason="unknown_market").inc()
            continue
        bucket = item.bucket_ts if isinstance(item, OpenInterestSample) else oi_bucket(oi.ts)
        rows[(market_id, bucket)] = {
            "market_id": market_id,
            "ts": bucket,
            "open_interest": oi.open_interest,
            "open_interest_value": oi.open_interest_value,
        }
    if not rows:
        return
    stmt = (
        pg_insert(OpenInterestHistory)
        .values(_dedupe_last(rows))
        .on_conflict_do_nothing(index_elements=["market_id", "ts"])
    )
    await session.execute(stmt)


async def flush_batch(
    session_factory: async_sessionmaker[AsyncSession], exchange_code: str, batch: list[PersistItem]
) -> set[Any]:
    """Persist one drained batch. Returns the ids of liquidations actually
    inserted (M1/D7) — callers must only republish those."""
    candles = [i for i in batch if isinstance(i, NormalizedCandle)]
    fundings = [i for i in batch if isinstance(i, NormalizedFunding)]
    liquidations = [i for i in batch if isinstance(i, NormalizedLiquidation)]
    snapshots = [i for i in batch if isinstance(i, Snapshot)]
    interests = [i for i in batch if isinstance(i, NormalizedOpenInterest | OpenInterestSample)]
    symbols = {i.symbol for i in batch}
    async with role_session(session_factory, db_role="hunter_worker") as session:
        market_ids = await load_market_ids(session, exchange_code, symbols)
        await upsert_candles(session, candles, market_ids, source="ws")
        await upsert_funding(session, fundings, market_ids)
        inserted_liquidation_ids = await upsert_liquidations(session, liquidations, market_ids)
        await upsert_snapshots(session, snapshots, market_ids)
        await upsert_open_interest(session, interests, market_ids)
    return inserted_liquidation_ids
