"""Redis hot state. Source times gate writes; every list has newest at index 0."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Literal

from redis.exceptions import NoScriptError, WatchError

from hunter_core.domain.market import (
    NormalizedFunding,
    NormalizedOpenInterest,
    NormalizedOrderBook,
    NormalizedTicker,
    to_wire,
)
from hunter_core.redis import keys
from hunter_market_worker import wire as msgpack
from hunter_market_worker.hot_state_candles import (
    CANDLE_FAST_WINDOW as CANDLE_FAST_WINDOW,
)
from hunter_market_worker.hot_state_candles import (
    CANDLES_MAXLEN as CANDLES_MAXLEN,
)
from hunter_market_worker.hot_state_candles import (
    is_newer,
)
from hunter_market_worker.hot_state_candles import (
    push_candle as push_candle,
)
from hunter_market_worker.hot_state_trades import (
    TRADE_DEDUPE_WINDOW as TRADE_DEDUPE_WINDOW,
)
from hunter_market_worker.hot_state_trades import (
    TRADES_MAXLEN as TRADES_MAXLEN,
)
from hunter_market_worker.hot_state_trades import (
    TradeMemory as TradeMemory,
)
from hunter_market_worker.hot_state_trades import (
    push_trade as push_trade,
)

TICKER_TTL_S = 30
BOOK_TTL_S = 10
DERIV_TTL_S = 600

# Fields each writer owns in a shared hash. On an accepted write, owned
# fields whose value is None are HDEL'd in the same MULTI as the HSET, so an
# exchange that stops sending an optional field does not leave it stale next
# to a fresh timestamp (H4). A writer must never touch a field it does not
# own — the ticker and deriv hashes are shared by several writers.
#
# KB-0044: the ticker hash has two disjoint writers — the REST 24h-ticker
# refresh (``universe.py``, no bid/ask) and the WS ``bookTicker`` stream
# (``coalesce.py``, no 24h volume). Both used to share ``owned=TICKER_FIELDS``
# (every field), so each accepted write HDEL'd the *other* producer's fields
# as "missing, must be stale": a REST write erased bid/ask, the next
# bookTicker erased volume_24h right back — 6/55,709 populated rows in prod.
# Ownership must be scoped to what each producer actually sends.
TICKER_REST_FIELDS = (
    "last",
    "volume_24h",
    "quote_volume_24h",
    "high_24h",
    "low_24h",
    "change_24h_pct",
    "ts",
)
TICKER_WS_FIELDS = (
    "last",
    "bid",
    "ask",
    "bid_qty",
    "ask_qty",
    "ts",
)
_TICKER_OWNED_FIELDS: dict[str, tuple[str, ...]] = {
    "rest": TICKER_REST_FIELDS,
    "ws": TICKER_WS_FIELDS,
}
FUNDING_FIELDS = ("funding_rate", "funding_kind", "next_funding_time", "funding_ts")
MARK_FIELDS = ("mark_price", "index_price", "mark_ts")
OI_FIELDS = ("open_interest", "open_interest_value", "oi_ts")


def _mapping(**fields: Any) -> dict[str, str]:
    return {name: str(value) for name, value in fields.items() if value is not None}


_EPOCH = datetime(1970, 1, 1, tzinfo=UTC)

# B2 (t16b-profile.md: WATCH+HGET then MULTI/HSET/HDEL/EXPIRE/EXEC cost 10.02%
# of the worker's own CPU at 50 markets, two Redis round trips per accepted
# bookTicker frame). This does the whole compare-and-write atomically in one
# round trip. The compare is on a shadow numeric field (epoch microseconds,
# ``_<ts_field>_us``) so ordering is on the actual instant, never on the ISO
# string's bytes (H-ordering) â€” the human-readable ``ts_field`` keeps its
# exact name/format/meaning for apps/api and the UI.
#
# ARGV: [1]=shadow field name, [2]=new ts_us, [3]=ttl seconds,
#       [4]=N (mapping field count), then N*(name, value) pairs,
#       then M (stale field count), then M stale field names.
_HASH_SCRIPT = """
local shadow = ARGV[1]
local new_ts = tonumber(ARGV[2])
local ttl = tonumber(ARGV[3])
local n = tonumber(ARGV[4])
local previous = redis.call('HGET', KEYS[1], shadow)
if previous and tonumber(previous) and tonumber(previous) >= new_ts then
    return 0
end
local idx = 5
for _ = 1, n do
    redis.call('HSET', KEYS[1], ARGV[idx], ARGV[idx + 1])
    idx = idx + 2
end
local m = tonumber(ARGV[idx])
idx = idx + 1
for _ = 1, m do
    redis.call('HDEL', KEYS[1], ARGV[idx])
    idx = idx + 1
end
redis.call('EXPIRE', KEYS[1], ttl)
return 1
"""

_SCRIPT_SHA_ATTR = "_hunter_hot_state_hash_sha"


def _epoch_us(ts: datetime) -> int:
    """Exact microseconds since epoch â€” integer arithmetic, no float rounding
    (``ts.timestamp()`` loses precision at this magnitude in float64)."""
    delta = ts - _EPOCH
    return (delta.days * 86400 + delta.seconds) * 1_000_000 + delta.microseconds


def _hash_argv(
    fields: dict[str, str], ts_field: str, ts: datetime, ttl: int, owned: tuple[str, ...]
) -> list[str]:
    stale = [name for name in owned if name not in fields]
    shadow = f"_{ts_field}_us"
    mapping = dict(fields)
    mapping[shadow] = str(_epoch_us(ts))
    flat: list[str] = []
    for name, value in mapping.items():
        flat.append(name)
        flat.append(value)
    return [shadow, str(_epoch_us(ts)), str(ttl), str(len(mapping)), *flat, str(len(stale)), *stale]


async def ensure_script_sha(redis: Any) -> str:
    """Cache :data:`_HASH_SCRIPT`'s SHA on the client instance (B2) so the
    hot path never re-sends the script body. Exposed so a caller queuing
    many :func:`queue_ticker_hash` calls onto a shared pipeline (B3) can
    resolve the SHA once, outside the pipeline, before building the batch."""
    sha = getattr(redis, _SCRIPT_SHA_ATTR, None)
    if sha is None:
        sha = await redis.script_load(_HASH_SCRIPT)
        setattr(redis, _SCRIPT_SHA_ATTR, sha)
    return sha


async def _hash(
    redis: Any,
    key: str,
    fields: dict[str, str],
    ts_field: str,
    ts: datetime,
    ttl: int,
    *,
    owned: tuple[str, ...] = (),
) -> bool:
    argv = _hash_argv(fields, ts_field, ts, ttl, owned)
    sha = await ensure_script_sha(redis)
    try:
        result = await redis.evalsha(sha, 1, key, *argv)
    except NoScriptError:
        # A Redis restart flushes the script cache (T1.6 already proved
        # restarts happen) â€” fall back to EVAL once instead of killing the
        # worker, and re-cache the (unchanged) SHA for next time.
        result = await redis.eval(_HASH_SCRIPT, 1, key, *argv)
        setattr(redis, _SCRIPT_SHA_ATTR, await redis.script_load(_HASH_SCRIPT))
    return bool(result)


def queue_ticker_hash(
    pipe: Any, sha: str, ticker: NormalizedTicker, *, source: Literal["rest", "ws"]
) -> None:
    """Queue the same atomic ticker HSET-if-newer onto ``pipe`` (B3's
    per-cycle batch) without awaiting a result â€” the caller has already
    resolved ``sha`` via :func:`ensure_script_sha`. ``source`` picks the
    producer-scoped owned-field set (KB-0044); the coalescer only ever
    queues WS ``bookTicker`` tickers, so it always passes ``"ws"``."""
    fields = _ticker_fields(ticker)
    owned = _TICKER_OWNED_FIELDS[source]
    argv = _hash_argv(fields, "ts", ticker.ts, TICKER_TTL_S, owned)
    pipe.evalsha(sha, 1, keys.ticker(ticker.exchange, ticker.symbol), *argv)


def queue_book_set(pipe: Any, book: NormalizedOrderBook, depth: int = 20) -> None:
    """Queue an unconditional book snapshot ``SET`` onto ``pipe`` (B3).

    No freshness compare here: the coalescer only ever holds the newest
    accepted snapshot per symbol (``AcceptedEvents.accept`` already gated
    ordering in memory before this was buffered), so by the time a cycle
    flushes there is nothing left to compare against â€” unlike
    :func:`write_book`, which a direct caller may invoke without that
    upstream guarantee and therefore still needs to check for itself."""
    payload = _book_payload(book, depth)
    pipe.set(
        keys.book(book.exchange, book.symbol),
        msgpack.packb(payload, use_bin_type=True),
        ex=BOOK_TTL_S,
    )


def _ticker_fields(ticker: NormalizedTicker) -> dict[str, str]:
    fields = to_wire(ticker)
    for field in ("kind", "exchange", "symbol", "received_at"):
        fields.pop(field, None)
    fields["ts"] = ticker.ts.isoformat()
    return _mapping(**fields)


def _book_payload(book: NormalizedOrderBook, depth: int = 20) -> dict[str, Any]:
    if not book.is_snapshot:
        raise ValueError("market worker requires book snapshots")
    depth = 20
    return {
        "ts": book.ts.isoformat(),
        "depth": depth,
        "kind": "snapshot",
        "bids": [[str(level.price), str(level.qty)] for level in book.bids[:depth]],
        "asks": [[str(level.price), str(level.qty)] for level in book.asks[:depth]],
    }


async def write_ticker(
    redis: Any, ticker: NormalizedTicker, *, source: Literal["rest", "ws"]
) -> bool:
    """``source`` picks the producer-scoped owned-field set (KB-0044): the
    universe refresh always passes ``"rest"`` (no bid/ask on that endpoint);
    the coalescer batches WS tickers through :func:`queue_ticker_hash`
    instead, but the parameter is still required so no caller can default
    back into sharing one owned set across producers."""
    return await _hash(
        redis,
        keys.ticker(ticker.exchange, ticker.symbol),
        _ticker_fields(ticker),
        "ts",
        ticker.ts,
        TICKER_TTL_S,
        owned=_TICKER_OWNED_FIELDS[source],
    )


async def write_book(redis: Any, book: NormalizedOrderBook, depth: int = 20) -> bool:
    key = keys.book(book.exchange, book.symbol)
    payload = _book_payload(book, depth)
    while True:
        async with redis.pipeline(transaction=True) as pipe:
            try:
                await pipe.watch(key)
                previous = await pipe.get(key)
                if previous and not is_newer(book.ts, msgpack.unpackb(previous)["ts"]):
                    return False
                pipe.multi()
                pipe.set(key, msgpack.packb(payload, use_bin_type=True), ex=BOOK_TTL_S)
                await pipe.execute()
                return True
            except WatchError:
                continue


async def write_funding(redis: Any, funding: NormalizedFunding, *, realized: bool = False) -> bool:
    key = keys.derivatives(funding.exchange, funding.symbol)
    fields = _mapping(
        funding_rate=funding.funding_rate,
        funding_kind="realized" if realized else "estimated",
        next_funding_time=funding.next_funding_time.isoformat()
        if funding.next_funding_time
        else None,
        funding_ts=funding.ts.isoformat(),
    )
    accepted = await _hash(
        redis, key, fields, "funding_ts", funding.ts, DERIV_TTL_S, owned=FUNDING_FIELDS
    )
    if not realized:
        mark = _mapping(
            mark_price=funding.mark_price,
            index_price=funding.index_price,
            mark_ts=funding.ts.isoformat(),
        )
        accepted = (
            await _hash(redis, key, mark, "mark_ts", funding.ts, DERIV_TTL_S, owned=MARK_FIELDS)
            or accepted
        )
    return accepted


async def write_open_interest(redis: Any, oi: NormalizedOpenInterest) -> bool:
    fields = _mapping(
        open_interest=oi.open_interest,
        open_interest_value=oi.open_interest_value,
        oi_ts=oi.ts.isoformat(),
    )
    return await _hash(
        redis,
        keys.derivatives(oi.exchange, oi.symbol),
        fields,
        "oi_ts",
        oi.ts,
        DERIV_TTL_S,
        owned=OI_FIELDS,
    )
