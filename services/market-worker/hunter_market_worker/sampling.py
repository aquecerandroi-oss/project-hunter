"""Minute snapshots and REST open-interest samples feed the bounded persistence queue."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from decimal import Decimal, InvalidOperation
from typing import TYPE_CHECKING, Any

from sqlalchemy.dialects.postgresql import insert as pg_insert

from hunter_core.db.models.market_data import (
    MarketSnapshot,
    OpenInterestHistory,
)
from hunter_core.db.session import role_session
from hunter_core.domain.enums import Timeframe
from hunter_core.domain.market import (
    align_open_time,
)
from hunter_core.domain.types import utcnow
from hunter_core.logging import get_logger
from hunter_core.observability import (
    market_sampling_bucket_skipped_total,
    market_snapshot_skipped_no_data_total,
    market_snapshot_stale_fields_total,
)
from hunter_core.redis import keys
from hunter_exchanges.base import ExchangeError
from hunter_market_worker import hot_state
from hunter_market_worker.persist_rows import oi_bucket
from hunter_market_worker.queues import OpenInterestSample, PersistQueues, Snapshot

if TYPE_CHECKING:
    import redis.asyncio as redis_asyncio
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    from hunter_core.domain.market import NormalizedOpenInterest
    from hunter_core.runtime import WorkerRuntime
    from hunter_core.settings import Settings
    from hunter_exchanges.base import ExchangeAdapter
    from hunter_market_worker.universe import MonitoredUniverse

from hunter_market_worker.persist_rows import load_market_ids

logger = get_logger(__name__)

# H5: which hot-state hash and timestamp gates which snapshot field (hot_state.py
# TICKER_FIELDS/FUNDING_FIELDS/MARK_FIELDS/OI_FIELDS). A field whose owning
# timestamp is missing or older than settings.market_stale_after_s is written as
# NULL rather than republished as if it were a fresh observation. The ticker
# hash owns its six derived fields through its own "ts": its 30 s Redis TTL is
# an eviction policy, not the freshness contract, and the snapshot cadence
# (60 s) is longer than it anyway.
_STALE_OWNERSHIP: tuple[tuple[str, str, tuple[str, ...]], ...] = (
    ("ticker", "ts", ("price", "bid", "ask", "spread_pct", "volume_24h", "quote_volume_24h")),
    ("deriv", "mark_ts", ("mark_price", "index_price")),
    ("deriv", "oi_ts", ("open_interest", "open_interest_value")),
    ("deriv", "funding_ts", ("funding_rate",)),
)


def _decimal(value: str | None) -> Decimal | None:
    if not value:
        return None
    try:
        return Decimal(value)
    except InvalidOperation:
        return None


def _spread_pct(bid: Decimal | None, ask: Decimal | None) -> Decimal | None:
    """A fraction (0.02 == 2%), matching ``market_snapshots.spread_pct``
    ``NUMERIC(9,6)`` (DATABASE.md §4, D1) — never multiplied by 100."""
    if bid is None or ask is None:
        return None
    mid = (bid + ask) / 2
    if mid <= 0:
        return None
    return (ask - bid) / mid


def _apply_staleness(
    row: dict[str, Any],
    ticker: dict[str, str],
    deriv: dict[str, str],
    observed_at: datetime,
    stale_after_s: float,
) -> bool:
    """H5: drop (set to ``None``) every field whose owning timestamp is
    missing or older than ``stale_after_s`` relative to ``observed_at`` --
    the instant the hashes were actually read, never the minute-aligned ``ts``
    the row is keyed on: truncating to the minute would hand a stale value up
    to 59 s of extra slack (and make a negative age look fresh). Each drop is
    counted so the omission is observable.

    Returns whether any observable field survived — D9: a row where nothing
    did is not written at all, because ``ON CONFLICT DO NOTHING`` would make
    the all-NULL row permanent for that minute.
    """
    sources = {"ticker": ticker, "deriv": deriv}
    for source, ts_field, owned_fields in _STALE_OWNERSHIP:
        ts = _parse_ts(sources[source].get(ts_field))
        if ts is not None and (observed_at - ts).total_seconds() <= stale_after_s:
            continue
        for field in owned_fields:
            if row.get(field) is not None:
                row[field] = None
                market_snapshot_stale_fields_total.labels(field=field).inc()
    return any(row.get(f) is not None for _, _, owned in _STALE_OWNERSHIP for f in owned)


def _parse_ts(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def _align_boundary(ts: datetime, interval_s: float) -> datetime:
    epoch = ts.timestamp()
    aligned = (epoch // interval_s) * interval_s
    return datetime.fromtimestamp(aligned, tz=UTC)


def _next_boundary(ts: datetime, interval_s: float) -> datetime:
    return _align_boundary(ts, interval_s) + timedelta(seconds=interval_s)


def _advance_schedule(
    previous_boundary: datetime, finished_at: datetime, interval_s: float, loop: str
) -> datetime:
    """M5: the boundary to sleep until next. Aligned to the UTC grid rather
    than ``interval_s`` after ``finished_at``, so a slow round does not drift
    the whole series. If the round ran long enough to pass the boundary that
    would naturally follow ``previous_boundary``, that boundary was missed —
    count it and jump straight to the next one still ahead of us."""
    following = previous_boundary + timedelta(seconds=interval_s)
    if finished_at >= following:
        market_sampling_bucket_skipped_total.labels(loop=loop).inc()
        logger.warning("market_sampling_bucket_skipped", loop=loop, boundary=following.isoformat())
        following = _next_boundary(finished_at, interval_s)
    return following


async def snapshot_loop(
    session_factory: async_sessionmaker[AsyncSession],
    redis: redis_asyncio.Redis,
    exchange_code: str,
    universe: MonitoredUniverse,
    settings: Settings,
    runtime: WorkerRuntime,
    queues: PersistQueues | None = None,
) -> None:
    interval = settings.market_snapshot_interval_s
    boundary = _next_boundary(utcnow(), interval)
    while True:
        delay = (boundary - utcnow()).total_seconds()
        if delay > 0:
            await asyncio.sleep(delay)
        symbols = list(universe.symbols)
        if symbols:
            try:
                await write_snapshots(
                    session_factory, redis, exchange_code, symbols, settings, queues
                )
                runtime.mark_success()
            except Exception:
                logger.exception("market_snapshot_failed")
                runtime.mark_error()
        boundary = _advance_schedule(boundary, utcnow(), interval, "snapshot")


async def write_snapshots(
    session_factory: async_sessionmaker[AsyncSession],
    redis: redis_asyncio.Redis,
    exchange_code: str,
    symbols: list[str],
    settings: Settings,
    queues: PersistQueues | None = None,
) -> None:
    pipe = redis.pipeline(transaction=False)
    for symbol in symbols:
        pipe.hgetall(keys.ticker(exchange_code, symbol))
        pipe.hgetall(keys.derivatives(exchange_code, symbol))
    raw = await pipe.execute()
    observed_at = utcnow()
    snapshot_ts = align_open_time(observed_at, Timeframe.M1)
    stale_after = settings.market_stale_after_s
    async with role_session(session_factory, db_role="hunter_worker") as session:
        market_ids = await load_market_ids(session, exchange_code, set(symbols))
        values: list[dict[str, Any]] = []
        for index, symbol in enumerate(symbols):
            market_id = market_ids.get(symbol)
            if market_id is None:
                continue
            ticker = {k.decode(): v.decode() for k, v in raw[index * 2].items()}
            deriv = {k.decode(): v.decode() for k, v in raw[index * 2 + 1].items()}
            bid, ask = _decimal(ticker.get("bid")), _decimal(ticker.get("ask"))
            row: dict[str, Any] = {
                "market_id": market_id,
                "ts": snapshot_ts,
                "price": _decimal(ticker.get("last")),
                "bid": bid,
                "ask": ask,
                "spread_pct": _spread_pct(bid, ask),
                "volume_24h": _decimal(ticker.get("volume_24h")),
                "quote_volume_24h": _decimal(ticker.get("quote_volume_24h")),
                "open_interest": _decimal(deriv.get("open_interest")),
                "open_interest_value": _decimal(deriv.get("open_interest_value")),
                "funding_rate": _decimal(deriv.get("funding_rate")),
                "mark_price": _decimal(deriv.get("mark_price")),
                "index_price": _decimal(deriv.get("index_price")),
            }
            if not _apply_staleness(row, ticker, deriv, observed_at, stale_after):
                # D9: nothing fresh to observe -> no row, just a counter.
                market_snapshot_skipped_no_data_total.inc()
                continue
            values.append(row)
        if queues is not None:
            reverse_ids = {value: symbol for symbol, value in market_ids.items()}
            for value in values:
                symbol = reverse_ids[value.pop("market_id")]
                queues.events.put_nowait(Snapshot(symbol=symbol, values=value))
            return
        if values:
            stmt = (
                pg_insert(MarketSnapshot)
                .values(values)
                .on_conflict_do_nothing(index_elements=["market_id", "ts"])
            )
            await session.execute(stmt)


def _oi_rows(
    readings: list[NormalizedOpenInterest], market_ids: dict[str, Any], cycle_bucket: datetime
) -> list[dict[str, Any]]:
    """D8: every reading of one polling round is attributed to the same
    5-minute bucket, computed once at the start of the cycle — never derived
    per reading, or a round that straddles the boundary splits across two
    buckets and the next cycle shifts the split again."""
    return [
        {
            "market_id": market_ids[r.symbol],
            "ts": cycle_bucket,
            "open_interest": r.open_interest,
            "open_interest_value": r.open_interest_value,
        }
        for r in readings
        if r.symbol in market_ids
    ]


async def oi_poll_loop(
    session_factory: async_sessionmaker[AsyncSession],
    redis: redis_asyncio.Redis,
    adapter: ExchangeAdapter,
    universe: MonitoredUniverse,
    settings: Settings,
    runtime: WorkerRuntime,
    queues: PersistQueues | None = None,
) -> None:
    interval = settings.market_oi_poll_s
    boundary = _next_boundary(utcnow(), interval)
    while True:
        delay = (boundary - utcnow()).total_seconds()
        if delay > 0:
            await asyncio.sleep(delay)
        symbols = list(universe.symbols)
        if symbols:
            await _run_oi_cycle(session_factory, redis, adapter, symbols, runtime, queues)
        boundary = _advance_schedule(boundary, utcnow(), interval, "open_interest")


async def _run_oi_cycle(
    session_factory: async_sessionmaker[AsyncSession],
    redis: redis_asyncio.Redis,
    adapter: ExchangeAdapter,
    symbols: list[str],
    runtime: WorkerRuntime,
    queues: PersistQueues | None,
) -> None:
    cycle_bucket = oi_bucket(utcnow())  # D8: one bucket for the whole round
    readings: list[NormalizedOpenInterest] = []
    for symbol in symbols:
        try:
            oi = await adapter.fetch_open_interest(symbol)
        except ExchangeError as exc:
            logger.warning("market_oi_poll_failed", symbol=symbol, error=str(exc))
            continue
        readings.append(oi)
        if await hot_state.write_open_interest(redis, oi):
            from hunter_market_worker.ingest import publish_derivatives

            await publish_derivatives(
                redis,
                f"market-worker@{runtime.instance}",
                adapter.code,
                symbol,
                funding=None,
                oi=oi,
            )
        if queues is not None:
            # D8: the bucket travels with the reading, so a round straddling a
            # 5-minute boundary still lands on one slot (main.py always passes
            # queues -- this, not the branch below, is the production path).
            queues.events.put_nowait(OpenInterestSample(reading=oi, bucket_ts=cycle_bucket))
    if queues is not None or not readings:
        return
    try:
        async with role_session(session_factory, db_role="hunter_worker") as session:
            market_ids = await load_market_ids(session, adapter.code, {r.symbol for r in readings})
            values = _oi_rows(readings, market_ids, cycle_bucket)
            if values:
                stmt = (
                    pg_insert(OpenInterestHistory)
                    .values(values)
                    .on_conflict_do_nothing(index_elements=["market_id", "ts"])
                )
                await session.execute(stmt)
        runtime.mark_success()
    except Exception:
        logger.exception("market_oi_persist_failed")
        runtime.mark_error()
