"""Merging Postgres market rows with Redis hot state — the Redis field
contract this module reads is documented verbatim in ``schemas/markets.py``'s
module docstring; keep the two in sync.

Raw Redis value decoding (msgpack, hash-to-str, ``Decimal``/timestamp
coercion) lives in ``services/markets_codec.py``, and component/aggregate
``data_quality`` computation lives in ``services/markets_quality.py`` — both
split out to keep this module under CLAUDE.md's 350-line budget. Their public
names are re-exported here for callers (and this module's own tests) that
already import them from ``services.markets``.
"""

from __future__ import annotations

from dataclasses import asdict
from datetime import datetime
from typing import TYPE_CHECKING

import redis.exceptions as redis_exceptions

from hunter_api.repositories.base import clamp_page_size
from hunter_api.repositories.markets import (
    MarketRepository,
    decode_market_cursor,
    encode_market_cursor,
)
from hunter_api.schemas.markets import (
    FundingComponentStatusOut,
    MarketComponentsOut,
    MarketDetailOut,
    MarketListPage,
    MarketOut,
    MarketsSummary,
    OptionalComponentStatusOut,
)
from hunter_api.services.markets_codec import (
    book_ts as parse_book_ts,
)
from hunter_api.services.markets_codec import (
    decode_hash,
    parse_book,
    parse_trades,
    to_decimal,
    to_funding_kind,
    to_timestamp,
)
from hunter_api.services.markets_hot_state import (
    EMPTY_HOT_STATE,
    pipeline_hot_state,
)
from hunter_api.services.markets_hot_state import (
    HotState as HotState,  # re-exported: callers and tests import it from here
)
from hunter_api.services.markets_quality import (
    CLOCK_SKEW_TOLERANCE_S,
    aggregate_data_quality,
    component_status,
    spread_pct,
)
from hunter_api.services.markets_quality import (
    age_ms as component_age_ms,
)
from hunter_core.domain.market import DataQuality
from hunter_core.domain.types import utcnow
from hunter_core.logging import get_logger
from hunter_core.redis import keys

if TYPE_CHECKING:
    import redis.asyncio as redis_asyncio
    from sqlalchemy.ext.asyncio import AsyncSession

    from hunter_api.repositories.markets import MarketRow

__all__ = [
    "CLOCK_SKEW_TOLERANCE_S",
    "HotState",
    "aggregate_data_quality",
    "build_market_detail",
    "build_market_list_page",
    "build_market_out",
    "parse_book",
    "parse_trades",
    "spread_pct",
]

logger = get_logger(__name__)

RECENT_TRADES_LIMIT = 50


def build_market_out(
    row: MarketRow,
    hot: HotState,
    *,
    has_gap: bool,
    now: datetime,
    stale_after_s: float,
) -> MarketOut:
    ticker, deriv = hot.ticker, hot.deriv
    ticker_ts = to_timestamp(ticker.get("ts"))
    mark_ts = to_timestamp(deriv.get("mark_ts"))
    oi_ts = to_timestamp(deriv.get("oi_ts"))
    funding_ts = to_timestamp(deriv.get("funding_ts"))
    funding_kind = to_funding_kind(deriv.get("funding_kind"))

    ticker_status = component_status(ticker_ts, now=now, stale_after_s=stale_after_s)
    book_status = component_status(hot.book_ts, now=now, stale_after_s=stale_after_s)
    mark_status = component_status(mark_ts, now=now, stale_after_s=stale_after_s)
    oi_status = OptionalComponentStatusOut(ts=oi_ts, age_ms=component_age_ms(oi_ts, now))
    funding_status = FundingComponentStatusOut(
        ts=funding_ts, age_ms=component_age_ms(funding_ts, now), kind=funding_kind
    )

    quality = aggregate_data_quality(
        ticker=ticker_status.quality,
        book=book_status.quality,
        mark=mark_status.quality,
        has_gap=has_gap,
    )
    bid = to_decimal(ticker.get("bid"))
    ask = to_decimal(ticker.get("ask"))
    return MarketOut(
        **asdict(row),  # row's fields are named identically to MarketOut's
        last_price=to_decimal(ticker.get("last")),
        bid=bid,
        ask=ask,
        spread_pct=spread_pct(bid, ask),
        volume_24h=to_decimal(ticker.get("volume_24h")),
        quote_volume_24h=to_decimal(ticker.get("quote_volume_24h")),
        price_change_24h_pct=to_decimal(ticker.get("change_24h_pct")),
        mark_price=to_decimal(deriv.get("mark_price")),
        open_interest=to_decimal(deriv.get("open_interest")),
        funding_rate=to_decimal(deriv.get("funding_rate")),
        funding_kind=funding_kind,
        last_update=ticker_ts,
        data_quality=quality,
        has_open_gap=has_gap,
        components=MarketComponentsOut(
            ticker=ticker_status,
            book=book_status,
            mark=mark_status,
            open_interest=oi_status,
            funding=funding_status,
        ),
    )


def _summarize(items: list[MarketOut]) -> MarketsSummary:
    return MarketsSummary(
        markets_total=len(items),
        markets_monitored=sum(1 for item in items if item.is_monitored),
        markets_ok=sum(1 for item in items if item.data_quality is DataQuality.OK),
        markets_stale=sum(1 for item in items if item.data_quality is DataQuality.STALE),
        markets_degraded=sum(1 for item in items if item.data_quality is DataQuality.DEGRADED),
        markets_unavailable=sum(
            1 for item in items if item.data_quality is DataQuality.UNAVAILABLE
        ),
    )


async def build_market_list_page(
    session: AsyncSession,
    rows: list[MarketRow],
    redis: redis_asyncio.Redis,
    *,
    limit: int | None,
    cursor: str | None,
    stale_after_s: float,
) -> MarketListPage:
    """Merge Redis state into every filtered row, summarize the whole set,
    then window it down to one page — windowing happens here, over the
    already-fetched, already-ordered list, so ``summary`` and the page share
    one consistent snapshot of hot state instead of two ``HGETALL`` rounds
    that could straddle a worker write.
    """
    hot_states = await pipeline_hot_state(redis, rows)
    gapped_ids = await MarketRepository(session).gapped_market_ids([r.id for r in rows])
    # (F3) captured after the Redis and Postgres reads above, not before: ages
    # are `now - <component ts>`, so `now` must reflect the instant those
    # reads actually completed, not the instant the request started -- a
    # component sitting right at the staleness boundary must not read fresher
    # than the read latency itself made it.
    now = utcnow()
    items = [
        build_market_out(
            row,
            hot_states.get(row.id, EMPTY_HOT_STATE),
            has_gap=row.id in gapped_ids,
            now=now,
            stale_after_s=stale_after_s,
        )
        for row in rows
    ]
    summary = _summarize(items)

    after_id = decode_market_cursor(cursor)
    start = 0
    if after_id is not None:
        for index, item in enumerate(items):
            if item.id == after_id:
                start = index + 1
                break
        else:
            start = len(items)
    size = clamp_page_size(limit)
    page = items[start : start + size]
    has_more = start + size < len(items)
    next_cursor = encode_market_cursor(page[-1].id) if has_more else None
    return MarketListPage(
        items=page,
        next_cursor=next_cursor,
        summary=summary,
        stale_after_ms=int(stale_after_s * 1000),
    )


async def build_market_detail(
    session: AsyncSession, row: MarketRow, redis: redis_asyncio.Redis, *, stale_after_s: float
) -> MarketDetailOut:
    pipe = redis.pipeline(transaction=False)
    pipe.hgetall(keys.ticker(row.exchange, row.symbol, row.market_type))
    pipe.hgetall(keys.derivatives(row.exchange, row.symbol, row.market_type))
    pipe.get(keys.book(row.exchange, row.symbol, row.market_type))
    pipe.lrange(keys.trades(row.exchange, row.symbol, row.market_type), 0, RECENT_TRADES_LIMIT - 1)
    # Declared up front so both the happy path (redis-py's `execute()` return
    # type is untyped `Any`) and the except-branch fallback below share one
    # concrete, fully-known type -- otherwise pyright infers a partially
    # unknown union of the two and flags every use of these below.
    ticker_raw: dict[bytes, bytes]
    deriv_raw: dict[bytes, bytes]
    book_raw: bytes | None
    trades_raw: list[bytes]
    hot_state_ok = True
    try:
        ticker_raw, deriv_raw, book_raw, trades_raw = await pipe.execute()
    except redis_exceptions.RedisError as exc:
        # (F2) same degrade-to-absent rule as the list endpoint: never leak
        # the key that failed, never 500 -- this one market reads unavailable.
        # (G9) `hot_state_ok=False` -- see `MarketDetailOut`'s docstring.
        logger.warning(
            "market_detail_redis_error",
            error_type=type(exc).__name__,
            exchange=row.exchange,
            symbol=row.symbol,
        )
        ticker_raw, deriv_raw, book_raw, trades_raw = {}, {}, None, []
        hot_state_ok = False
    gapped_ids = await MarketRepository(session).gapped_market_ids([row.id])
    # (G5) captured after *both* the Redis pipeline and the Postgres gap
    # query above, not just the former: a slow gap query would otherwise
    # leave `now` stale by however long that query took, letting a component
    # sitting right at the staleness boundary read fresher than the combined
    # read latency actually made it -- the same reasoning `build_market_list_page`
    # already applies.
    now = utcnow()
    hot = HotState(
        ticker=decode_hash(ticker_raw),
        deriv=decode_hash(deriv_raw),
        book_ts=parse_book_ts(book_raw),
    )
    base = build_market_out(
        row, hot, has_gap=row.id in gapped_ids, now=now, stale_after_s=stale_after_s
    )
    return MarketDetailOut(
        **base.model_dump(),
        stale_after_ms=int(stale_after_s * 1000),
        hot_state_ok=hot_state_ok,
        # (G9) `None` on a failed read, not a parsed-from-absent value --
        # see `MarketDetailOut`'s docstring for the full contract.
        book=parse_book(book_raw) if hot_state_ok else None,
        recent_trades=parse_trades(trades_raw) if hot_state_ok else None,
    )
