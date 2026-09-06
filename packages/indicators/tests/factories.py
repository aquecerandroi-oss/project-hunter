"""Synthetic series and *exact* hot-state payloads for the feature tests.

The payloads are byte-for-byte what ``services/market-worker`` writes today —
``hot_state_candles.push_candle`` (msgpack ``to_wire(candle)`` plus a ``ts``
key, newest at index 0), ``hot_state.queue_book_set`` (msgpack snapshot,
top-20), ``hot_state.push_trade`` (msgpack, newest-first) and the ``deriv``
hash (string fields, per-field timestamps). A fake that drifts from those
contracts would let the loader pass its tests and fail against Redis, so the
builders below mirror the writers instead of the reader.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

import msgpack

from hunter_core.domain.enums import OrderSide, Timeframe
from hunter_core.domain.market import NormalizedCandle, to_wire

_codec: Any = msgpack
"""Typed boundary for msgpack (mirrors ``hunter_market_worker.wire``)."""


def _packb(value: Any) -> bytes:
    packed: Any = _codec.packb(value, use_bin_type=True)
    return bytes(packed)


EXCHANGE = "binance"
SYMBOL = "BTCUSDT"
ORIGIN = datetime(2026, 9, 1, 0, 0, tzinfo=UTC)
MINUTE = timedelta(minutes=1)


def candle(
    open_time: datetime,
    *,
    close: Decimal,
    open: Decimal | None = None,
    high: Decimal | None = None,
    low: Decimal | None = None,
    volume: Decimal = Decimal("10"),
    is_final: bool = True,
    trade_count: int | None = None,
    taker_buy_volume: Decimal | None = None,
    event_ts: datetime | None = None,
    exchange: str = EXCHANGE,
    symbol: str = SYMBOL,
) -> NormalizedCandle:
    """One 1-minute candle. ``open`` defaults to ``close``; ``high``/``low`` widen it."""
    open_price = close if open is None else open
    return NormalizedCandle(
        exchange=exchange,
        symbol=symbol,
        timeframe=Timeframe.M1,
        open_time=open_time,
        close_time=open_time + MINUTE,
        open=open_price,
        high=max(open_price, close) if high is None else high,
        low=min(open_price, close) if low is None else low,
        close=close,
        volume=volume,
        quote_volume=None,
        trade_count=trade_count,
        taker_buy_volume=taker_buy_volume,
        is_final=is_final,
        event_ts=event_ts,
    )


def series(
    closes: Sequence[Decimal],
    *,
    start: datetime = ORIGIN,
    volumes: Sequence[Decimal] | None = None,
    highs: Sequence[Decimal] | None = None,
    lows: Sequence[Decimal] | None = None,
) -> list[NormalizedCandle]:
    """``len(closes)`` consecutive final 1-minute candles starting at ``start``."""
    out: list[NormalizedCandle] = []
    for i, close in enumerate(closes):
        out.append(
            candle(
                start + i * MINUTE,
                close=close,
                volume=Decimal("10") if volumes is None else volumes[i],
                high=None if highs is None else highs[i],
                low=None if lows is None else lows[i],
            )
        )
    return out


def flat_series(minutes: int, *, close: Decimal = Decimal("100"), start: datetime = ORIGIN):
    """``minutes`` identical candles — the neutral background a test perturbs."""
    return series([close] * minutes, start=start)


# --- exact hot-state payloads ------------------------------------------------


def candle_rows(candles: Sequence[NormalizedCandle]) -> list[bytes]:
    """``mkt:*:candles:1m`` — newest at index 0, msgpack, ``ts`` next to the model."""
    rows: list[bytes] = []
    for item in sorted(candles, key=lambda c: c.open_time, reverse=True):
        value: dict[str, Any] = to_wire(item)
        if item.event_ts is not None:
            value["ts"] = item.event_ts.isoformat()
        rows.append(_packb(value))
    return rows


def book_payload(
    ts: datetime,
    bids: Sequence[tuple[str, str]],
    asks: Sequence[tuple[str, str]],
    depth: int = 20,
) -> bytes:
    """``mkt:*:book`` — one msgpack snapshot, top-``depth``."""
    return _packb(
        {
            "ts": ts.isoformat(),
            "depth": depth,
            "kind": "snapshot",
            "bids": [[price, qty] for price, qty in bids],
            "asks": [[price, qty] for price, qty in asks],
        }
    )


def trade_rows(
    trades: Sequence[tuple[datetime, str, str, OrderSide]],
    *,
    first_id: int = 1,
) -> list[bytes]:
    """``mkt:*:trades`` — newest at index 0. Input is oldest-first, as it happened."""
    rows: list[bytes] = []
    for offset, (ts, price, qty, side) in enumerate(trades):
        rows.append(
            _packb(
                {
                    "ts": ts.isoformat(),
                    "price": price,
                    "qty": qty,
                    "side": side.value,
                    "trade_id": str(first_id + offset),
                }
            )
        )
    return list(reversed(rows))


def deriv_hash(
    *,
    funding_rate: str | None = None,
    funding_ts: datetime | None = None,
    funding_kind: str = "estimated",
    next_funding_time: datetime | None = None,
    mark_price: str | None = None,
    mark_ts: datetime | None = None,
    open_interest: str | None = None,
    open_interest_value: str | None = None,
    oi_ts: datetime | None = None,
) -> dict[bytes | str, bytes | str]:
    """``mkt:*:deriv`` — a Redis hash: bytes keys, bytes values, per-field ``*_ts``."""
    fields: dict[str, str] = {}
    if funding_rate is not None and funding_ts is not None:
        fields |= {
            "funding_rate": funding_rate,
            "funding_kind": funding_kind,
            "funding_ts": funding_ts.isoformat(),
        }
        if next_funding_time is not None:
            fields["next_funding_time"] = next_funding_time.isoformat()
    if mark_price is not None and mark_ts is not None:
        fields |= {"mark_price": mark_price, "mark_ts": mark_ts.isoformat()}
    if open_interest is not None and oi_ts is not None:
        fields |= {"open_interest": open_interest, "oi_ts": oi_ts.isoformat()}
        if open_interest_value is not None:
            fields["open_interest_value"] = open_interest_value
    encoded: dict[bytes | str, bytes | str] = {
        key.encode(): value.encode() for key, value in fields.items()
    }
    # the writer also keeps shadow ordering fields; the loader must ignore them
    for name in ("funding_ts", "mark_ts", "oi_ts"):
        if name in fields:
            encoded[f"_{name}_us".encode()] = b"0"
    return encoded
