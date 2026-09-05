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

from dataclasses import asdict, dataclass
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


@dataclass(frozen=True, slots=True)
class HotState:
    """One market's Redis snapshot, decoded but not yet interpreted."""

    ticker: dict[str, str]
    deriv: dict[str, str]
    book_ts: datetime | None


_EMPTY_HOT_STATE = HotState(ticker={}, deriv={}, book_ts=None)


async def _pipeline_hot_state(
    redis: redis_asyncio.Redis, rows: list[MarketRow]
) -> dict[str, HotState]:
    """One round trip: ``ticker``/``deriv`` HGETALL and a ``book`` GET (for
    its ``ts`` only) per row, keyed by ``"{exchange}:{symbol}"``.

    (G3) ``execute(raise_on_error=False)``: a per-command failure (a
    ``WRONGTYPE`` on one market's ticker key) then comes back *in place* in
    ``results`` as the exception object, isolated to the one command -- and
    therefore market -- it belongs to, rather than aborting the whole
    pipeline. A failure at ``execute()`` itself (Redis actually down) still
    raises past this ``try`` and degrades every market, correctly: there is
    no per-market data to isolate when the connection itself is gone.
    """
    if not rows:
        return {}
    pipe = redis.pipeline(transaction=False)
    for row in rows:
        pipe.hgetall(keys.ticker(row.exchange, row.symbol))
        pipe.hgetall(keys.derivatives(row.exchange, row.symbol))
        pipe.get(keys.book(row.exchange, row.symbol))
    try:
        results = await pipe.execute(raise_on_error=False)
    except redis_exceptions.RedisError as exc:
        # (F2) Redis itself unreachable -- every market in this page degrades
        # to "no hot state" rather than 500ing the request. Only the error's
        # *type* and how many markets were affected are logged: redis-py
        # appends the failing command and its key to a WRONGTYPE message, and
        # that key name must never reach a log line.
        logger.warning(
            "market_hot_state_redis_error",
            error_type=type(exc).__name__,
            market_count=len(rows),
        )
        return {}
    out: dict[str, HotState] = {}
    command_error_types: set[str] = set()
    for index, row in enumerate(rows):
        raw_ticker, raw_deriv, raw_book = results[index * 3 : index * 3 + 3]
        # Explicit concrete types below (rather than reassigning the
        # `Any`-typed unpacked result in place) keep pyright's strict mode
        # from unioning `Any` with the failure-branch literal.
        ticker_raw: dict[bytes, bytes] = {}
        deriv_raw: dict[bytes, bytes] = {}
        book_raw: bytes | None = None
        if isinstance(raw_ticker, BaseException):
            command_error_types.add(type(raw_ticker).__name__)
        else:
            ticker_raw = raw_ticker
        if isinstance(raw_deriv, BaseException):
            command_error_types.add(type(raw_deriv).__name__)
        else:
            deriv_raw = raw_deriv
        if isinstance(raw_book, BaseException):
            command_error_types.add(type(raw_book).__name__)
        else:
            book_raw = raw_book
        out[f"{row.exchange}:{row.symbol}"] = HotState(
            ticker=decode_hash(ticker_raw),
            deriv=decode_hash(deriv_raw),
            book_ts=parse_book_ts(book_raw),
        )
    if command_error_types:
        # (G3) one or more individual commands failed but the pipeline as a
        # whole still executed -- only error types/count logged, never a key.
        logger.warning(
            "market_hot_state_command_error",
            error_types=sorted(command_error_types),
            market_count=len(rows),
        )
    return out


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
    hot_state = await _pipeline_hot_state(redis, rows)
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
            hot_state.get(f"{row.exchange}:{row.symbol}", _EMPTY_HOT_STATE),
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
    pipe.hgetall(keys.ticker(row.exchange, row.symbol))
    pipe.hgetall(keys.derivatives(row.exchange, row.symbol))
    pipe.get(keys.book(row.exchange, row.symbol))
    pipe.lrange(keys.trades(row.exchange, row.symbol), 0, RECENT_TRADES_LIMIT - 1)
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
