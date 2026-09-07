"""Reading one page of markets out of the Redis hot state, in one round trip.

Split out of :mod:`.markets` (T3.0b) for the same 350-line reason
``markets_codec`` and ``markets_quality`` were: this is the *fetch*, and what
is left there is the merge into the API row. ``markets`` re-exports
:class:`HotState`, which its own tests import from it.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import TYPE_CHECKING

import redis.exceptions as redis_exceptions

from hunter_api.services.markets_codec import (
    book_ts as parse_book_ts,
)
from hunter_api.services.markets_codec import (
    decode_hash,
)
from hunter_core.logging import get_logger
from hunter_core.redis import keys

if TYPE_CHECKING:
    from datetime import datetime

    import redis.asyncio as redis_asyncio

    from hunter_api.repositories.markets import MarketRow

__all__ = ["EMPTY_HOT_STATE", "HotState", "pipeline_hot_state"]

logger = get_logger(__name__)


@dataclass(frozen=True, slots=True)
class HotState:
    """One market's Redis snapshot, decoded but not yet interpreted."""

    ticker: dict[str, str]
    deriv: dict[str, str]
    book_ts: datetime | None


EMPTY_HOT_STATE = HotState(ticker={}, deriv={}, book_ts=None)


async def pipeline_hot_state(
    redis: redis_asyncio.Redis, rows: list[MarketRow]
) -> dict[uuid.UUID, HotState]:
    """One round trip: ``ticker``/``deriv`` HGETALL and a ``book`` GET (for
    its ``ts`` only) per row, keyed by ``markets.id``: keyed by exchange and
    symbol, one page holding both listings of ``BTCUSDT`` had one entry for
    the two of them, and each was shown the other's price (T3.0b).

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
        pipe.hgetall(keys.ticker(row.exchange, row.symbol, row.market_type))
        pipe.hgetall(keys.derivatives(row.exchange, row.symbol, row.market_type))
        pipe.get(keys.book(row.exchange, row.symbol, row.market_type))
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
    out: dict[uuid.UUID, HotState] = {}
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
        out[row.id] = HotState(
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
