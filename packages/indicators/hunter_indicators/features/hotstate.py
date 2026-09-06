"""Hot state -> :class:`MarketContext`: one thin IO function, one pure loader.

:func:`read_hot_state` is the only part that touches Redis, and it does nothing
but read the four documented keys in one pipeline. Everything that can be wrong
— ordering, the cut, decoding, availability — happens in :func:`load_context`,
a pure function over the bytes, so the tests exercise the real payload contract
(``packages/indicators/tests/factories.py`` mirrors the writers in
``services/market-worker/hunter_market_worker/hot_state*.py``) instead of a
mocked client.

The scanner never calls the exchange (``docs/plans/M2.md`` §REST): what the hot
state does not have is *unavailable with a reason*, never fetched and never
guessed.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, InvalidOperation
from types import MappingProxyType
from typing import Any, cast

import msgpack

from hunter_core.domain.enums import OrderSide
from hunter_core.domain.market import NormalizedCandle, from_wire
from hunter_core.domain.types import ensure_utc
from hunter_core.redis import keys
from hunter_indicators.features.context import (
    INPUT_BOOK,
    INPUT_DERIV_HISTORY,
    INPUT_OI,
    INPUT_TRADES,
    BookSnapshot,
    DerivObservation,
    DerivSnapshot,
    MarketContext,
    SourceEntry,
    TapeTrade,
    build_context,
    missing,
)

CANDLES_MAXLEN = 1500
"""Mirrors ``hunter_market_worker.hot_state_candles.CANDLES_MAXLEN`` (25 h of minutes)."""
TRADES_MAXLEN = 2000
"""Mirrors ``hunter_market_worker.hot_state.TRADES_MAXLEN``."""

EMPTY_HASH: Mapping[bytes | str, bytes | str] = MappingProxyType({})
"""An immutable empty hash — a frozen dataclass default that cannot be shared."""

AFTER_CUT = "after_cut"
"""The payload exists but was observed after ``as_of`` — dropped, not used."""
EMPTY = "empty"
CORRUPT = "corrupt"
"""A field could not be parsed; the whole snapshot is refused, never patched."""
CROSSED = "crossed"
"""Best ask at or below best bid — a quote no exchange published, so no book."""


@dataclass(frozen=True, slots=True)
class HotStateRaw:
    """Exactly what the four Redis keys returned, undecoded."""

    candles: Sequence[bytes] = ()
    book: bytes | None = None
    trades: Sequence[bytes] = ()
    deriv: Mapping[bytes | str, bytes | str] = EMPTY_HASH
    candles_limit: int = CANDLES_MAXLEN
    trades_limit: int = TRADES_MAXLEN
    """How many rows were asked for: ``len(rows) >= limit`` means possibly truncated."""


async def read_hot_state(
    redis: Any,
    exchange: str,
    symbol: str,
    *,
    candles: int = CANDLES_MAXLEN,
    trades: int = TRADES_MAXLEN,
) -> HotStateRaw:
    """Read the four hot-state keys of one market in a single pipeline."""
    async with redis.pipeline(transaction=False) as pipe:
        pipe.lrange(keys.candles_1m(exchange, symbol), 0, candles - 1)
        pipe.get(keys.book(exchange, symbol))
        pipe.lrange(keys.trades(exchange, symbol), 0, trades - 1)
        pipe.hgetall(keys.derivatives(exchange, symbol))
        candle_rows, book, trade_rows, deriv = await pipe.execute()
    return HotStateRaw(
        candles=list(candle_rows or ()),
        book=book,
        trades=list(trade_rows or ()),
        deriv=dict(deriv or {}),
        candles_limit=candles,
        trades_limit=trades,
    )


def _text(value: bytes | str) -> str:
    return value.decode() if isinstance(value, bytes) else value


def _decimal(value: object) -> Decimal | None:
    """A **finite** ``Decimal``, or ``None``.

    ``Decimal("NaN")`` and ``Decimal("Infinity")`` parse happily, and either
    would poison every comparison downstream: a corrupted field is no field
    (Astra, T2.2 diff review).
    """
    if value is None:
        return None
    try:
        parsed = Decimal(_text(value) if isinstance(value, (bytes, str)) else str(value))
    except (InvalidOperation, ValueError):
        return None
    return parsed if parsed.is_finite() else None


def _instant(value: object) -> datetime | None:
    if value is None:
        return None
    try:
        return ensure_utc(
            datetime.fromisoformat(_text(value) if isinstance(value, (bytes, str)) else str(value))
        )
    except ValueError:
        return None


_codec: Any = msgpack
"""Typed boundary for msgpack's untyped API, like ``hunter_market_worker.wire``."""


def _unpack(row: bytes) -> dict[str, Any]:
    value: Any = _codec.unpackb(row, raw=False)
    if not isinstance(value, dict):
        raise ValueError(f"hot-state row is not a mapping: {type(value).__name__}")
    items: list[tuple[Any, Any]] = list(cast("dict[Any, Any]", value).items())
    return {str(key): item for key, item in items}


def decode_candles(
    rows: Sequence[bytes], limit: int = CANDLES_MAXLEN
) -> SourceEntry[tuple[NormalizedCandle, ...]]:
    """Decode ``mkt:*:candles:1m`` rows (newest-first) into candles, oldest-first.

    The writer stores ``to_wire(candle)`` **plus** a ``ts`` key holding the
    exchange push time (``hot_state_candles.push_candle``); the model forbids
    extra fields, so ``ts`` is folded back into ``event_ts`` — which is what
    orders two updates of the same forming minute.

    ``len(rows) >= limit`` marks the entry ``truncated``: the buffer returned
    everything that was asked for, so the history may have been cut and
    ``covers_from`` is the oldest minute *available*, not the oldest that
    happened (same rule as :func:`decode_trades`).
    """
    candles: list[NormalizedCandle] = []
    for row in reversed(list(rows)):
        payload = _unpack(row)
        push_ts = payload.pop("ts", None)
        if payload.get("event_ts") is None and push_ts is not None:
            payload["event_ts"] = push_ts
        candles.append(from_wire(NormalizedCandle, payload))
    truncated = len(rows) >= limit
    if not candles:
        return SourceEntry(reason=EMPTY, truncated=truncated)
    return SourceEntry(
        value=tuple(candles),
        ts=candles[-1].close_time,
        covers_from=candles[0].open_time,
        truncated=truncated,
    )


def decode_book(payload: bytes | None, as_of: datetime) -> SourceEntry[BookSnapshot]:
    """Decode ``mkt:*:book``. A level that does not parse invalidates the snapshot.

    Dropping the bad level instead would promote the next one to best bid and
    publish a spread the exchange never quoted (Astra, T2.2 round 2): corruption
    must look like an absent book, not like a different book.
    """
    if payload is None:
        return missing(INPUT_BOOK)
    raw = _unpack(payload)
    ts = _instant(raw.get("ts"))
    if ts is None:
        return SourceEntry(reason=EMPTY)
    if ts > as_of:
        return SourceEntry(reason=AFTER_CUT, ts=None)
    levels: dict[str, tuple[tuple[Decimal, Decimal], ...]] = {}
    for side in ("bids", "asks"):
        rows: Any = raw.get(side) or []
        parsed: list[tuple[Decimal, Decimal]] = []
        for level in rows:  # pyright: ignore[reportUnknownVariableType]
            price, qty = _decimal(level[0]), _decimal(level[1])  # pyright: ignore[reportUnknownArgumentType]
            if price is None or qty is None:
                return SourceEntry(reason=CORRUPT, ts=None)
            parsed.append((price, qty))
        levels[side] = tuple(parsed)
    bids, asks = levels["bids"], levels["asks"]
    if bids and asks and asks[0][0] <= bids[0][0]:
        # A crossed (or locked) top of book is the same class of fact as an
        # unparsable level: the snapshot cannot describe a market, so it is
        # refused whole (cross review, must-fix 3). Keeping it would publish a
        # negative spread as `ok`, and repairing it would invent a quote.
        return SourceEntry(reason=CROSSED, ts=None)
    depth = int(raw.get("depth") or 20)
    book = BookSnapshot(ts=ts, depth=depth, bids=bids, asks=asks)
    return SourceEntry(value=book, ts=ts)


def decode_trades(
    rows: Sequence[bytes], as_of: datetime, limit: int
) -> SourceEntry[tuple[TapeTrade, ...]]:
    """Decode ``mkt:*:trades`` (newest-first) into an oldest-first tape.

    ``truncated`` says the ring buffer was full, so ``covers_from`` is the
    oldest trade *available*, not the oldest that happened: a calculator that
    needs a full 60 s window must refuse rather than divide by a window it
    cannot prove it saw (Astra, T2.2 design review, must-fix 1c).
    """
    if not rows:
        return missing(INPUT_TRADES)
    tape: list[TapeTrade] = []
    for row in reversed(list(rows)):
        payload = _unpack(row)
        ts = _instant(payload.get("ts"))
        price, qty = _decimal(payload.get("price")), _decimal(payload.get("qty"))
        if ts is None or price is None or qty is None or ts > as_of:
            continue
        tape.append(
            TapeTrade(
                ts=ts,
                price=price,
                qty=qty,
                side=OrderSide(_text(payload["side"])),
                trade_id=_text(payload.get("trade_id") or ""),
            )
        )
    if not tape:
        return SourceEntry(reason=EMPTY, truncated=len(rows) >= limit)
    return SourceEntry(
        value=tuple(tape),
        ts=tape[-1].ts,
        covers_from=tape[0].ts,
        truncated=len(rows) >= limit,
    )


def decode_deriv(
    fields: Mapping[bytes | str, bytes | str], as_of: datetime
) -> SourceEntry[DerivSnapshot]:
    """Decode the ``deriv`` hash, keeping ``funding_ts``/``mark_ts``/``oi_ts`` apart.

    A group whose own timestamp is after the cut is dropped on its own: a mark
    price from the future must not take the open interest with it, and it must
    not be presented as current either.

    ``next_funding_time`` belongs to the funding group and travels with it, but
    it is never compared against the cut: it is the scheduled settlement, which
    is *supposed* to be in the future (cross review, nice-to-have f).
    """
    if not fields:
        return missing(INPUT_OI)
    plain = {
        _text(key): _text(value) for key, value in fields.items() if not _text(key).startswith("_")
    }
    funding_ts = _instant(plain.get("funding_ts"))
    mark_ts = _instant(plain.get("mark_ts"))
    oi_ts = _instant(plain.get("oi_ts"))
    funding_ok = funding_ts is not None and funding_ts <= as_of
    mark_ok = mark_ts is not None and mark_ts <= as_of
    oi_ok = oi_ts is not None and oi_ts <= as_of
    snapshot = DerivSnapshot(
        funding_rate=_decimal(plain.get("funding_rate")) if funding_ok else None,
        funding_kind=plain.get("funding_kind") if funding_ok else None,
        funding_ts=funding_ts if funding_ok else None,
        next_funding_time=_instant(plain.get("next_funding_time")) if funding_ok else None,
        mark_price=_decimal(plain.get("mark_price")) if mark_ok else None,
        index_price=_decimal(plain.get("index_price")) if mark_ok else None,
        mark_ts=mark_ts if mark_ok else None,
        open_interest=_decimal(plain.get("open_interest")) if oi_ok else None,
        open_interest_value=_decimal(plain.get("open_interest_value")) if oi_ok else None,
        oi_ts=oi_ts if oi_ok else None,
    )
    stamps = snapshot.timestamps()
    if not stamps:
        return SourceEntry(reason=AFTER_CUT if (funding_ts or mark_ts or oi_ts) else EMPTY)
    return SourceEntry(value=snapshot, ts=max(stamps), covers_from=min(stamps))


def load_context(
    raw: HotStateRaw,
    *,
    exchange: str,
    symbol: str,
    as_of: datetime,
    deriv_history: Sequence[DerivObservation] | None = None,
    btc: MarketContext | None = None,
) -> MarketContext:
    """Build the context of one market from its raw hot state, cut at ``as_of``.

    ``deriv_history`` is not in the hot state (the ``deriv`` hash holds only the
    current reading): the caller supplies it from the durable tables, and
    without it every "change over N hours" feature is ``unavailable``.
    """
    as_of = ensure_utc(as_of)
    history: SourceEntry[tuple[DerivObservation, ...]] = missing(INPUT_DERIV_HISTORY)
    if deriv_history is not None:
        kept = tuple(sorted((o for o in deriv_history if o.ts <= as_of), key=lambda o: o.ts))
        history = (
            SourceEntry(value=kept, ts=kept[-1].ts, covers_from=kept[0].ts)
            if kept
            else SourceEntry(reason=EMPTY)
        )
    candles = decode_candles(raw.candles, raw.candles_limit)
    return build_context(
        exchange=exchange,
        symbol=symbol,
        as_of=as_of,
        candles=candles.value or (),
        candles_truncated=candles.truncated,
        book=decode_book(raw.book, as_of),
        trades=decode_trades(raw.trades, as_of, raw.trades_limit),
        deriv=decode_deriv(raw.deriv, as_of),
        deriv_history=history,
        btc=btc,
    )


__all__ = [
    "AFTER_CUT",
    "CORRUPT",
    "CROSSED",
    "CANDLES_MAXLEN",
    "EMPTY",
    "TRADES_MAXLEN",
    "HotStateRaw",
    "decode_book",
    "decode_candles",
    "decode_deriv",
    "decode_trades",
    "load_context",
    "read_hot_state",
]
