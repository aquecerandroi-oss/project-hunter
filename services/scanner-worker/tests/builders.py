"""Synthetic hot state, in exactly the bytes the market-worker writes.

The scanner reads Redis, not objects, so a test that handed it decoded candles
would prove nothing about the path that runs in production. These builders write
the same msgpack rows ``hunter_market_worker.hot_state`` writes, which is why the
pipeline test can claim to exercise ``read_hot_state -> decode_* ->
build_context`` and not a convenient shortcut around them.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any
from uuid import UUID

import msgpack

from hunter_core.domain.enums import OrderSide, Timeframe
from hunter_core.domain.market import NormalizedCandle, to_wire
from hunter_core.redis import keys
from hunter_scanner_worker.registry import MarketRef

ORIGIN = datetime(2026, 9, 1, 0, 0, tzinfo=UTC)
EXCHANGE = "binance"
SYMBOL = "BTCUSDT"
MARKET_ID = UUID("11111111-1111-7111-8111-111111111111")

REF = MarketRef(market_id=MARKET_ID, exchange=EXCHANGE, symbol=SYMBOL)


_codec: Any = msgpack
"""msgpack's extension functions are untyped; same narrowing the collector uses
(``hunter_market_worker.wire``), kept local so the tests do not import a private
module of another service."""


def _packb(value: Any) -> bytes:
    packed: Any = _codec.packb(value, use_bin_type=True, datetime=True)
    assert isinstance(packed, bytes)
    return packed


def candle(
    open_time: datetime,
    *,
    close: Decimal = Decimal("100"),
    volume: Decimal = Decimal("10"),
    high: Decimal | None = None,
    low: Decimal | None = None,
    trades: int = 50,
    is_final: bool = True,
    event_ts: datetime | None = None,
) -> NormalizedCandle:
    return NormalizedCandle(
        exchange=EXCHANGE,
        symbol=SYMBOL,
        timeframe=Timeframe.M1,
        open_time=open_time,
        close_time=open_time + timedelta(minutes=1),
        open=close,
        high=high if high is not None else close,
        low=low if low is not None else close,
        close=close,
        volume=volume,
        quote_volume=volume * close,
        trade_count=trades,
        taker_buy_volume=volume / 2,
        is_final=is_final,
        event_ts=event_ts,
    )


def series(
    minutes: int,
    *,
    start: datetime = ORIGIN,
    close: Decimal = Decimal("100"),
    volume: Decimal = Decimal("10"),
) -> list[NormalizedCandle]:
    """``minutes`` contiguous closed candles, oldest first."""
    return [
        candle(start + timedelta(minutes=index), close=close, volume=volume)
        for index in range(minutes)
    ]


def candle_rows(candles: list[NormalizedCandle]) -> list[bytes]:
    """Newest-first rows, as the hot-state list holds them."""
    rows: list[bytes] = []
    for item in reversed(candles):
        payload = to_wire(item)
        payload["ts"] = item.close_time.isoformat()
        rows.append(_packb(payload))
    return rows


def book_payload(
    *,
    bid: Decimal = Decimal("99.9"),
    ask: Decimal = Decimal("100.1"),
    ts: datetime,
    depth: int = 20,
) -> bytes:
    return _packb(
        {
            "ts": ts.isoformat(),
            "depth": depth,
            "bids": [[str(bid - Decimal(index) / 100), "1"] for index in range(depth)],
            "asks": [[str(ask + Decimal(index) / 100), "1"] for index in range(depth)],
        }
    )


def trade_rows(count: int, *, until: datetime, buy_ratio: Decimal = Decimal("0.6")) -> list[bytes]:
    """``count`` trades in the minute before ``until``, newest first."""
    rows: list[bytes] = []
    buys = int(count * float(buy_ratio))
    for index in range(count):
        ts = until - timedelta(seconds=index * 0.5)
        rows.append(
            _packb(
                {
                    "ts": ts.isoformat(),
                    "price": "100",
                    "qty": "1",
                    "side": (OrderSide.BUY if index < buys else OrderSide.SELL).value,
                    "trade_id": str(index),
                }
            )
        )
    return rows


def deriv_hash(*, ts: datetime) -> dict[str, str]:
    return {
        "funding_rate": "0.0001",
        "funding_ts": ts.isoformat(),
        "next_funding_time": (ts + timedelta(hours=4)).isoformat(),
        "mark_price": "100",
        "mark_ts": ts.isoformat(),
        "open_interest": "1000",
        "open_interest_value": "100000",
        "oi_ts": ts.isoformat(),
    }


class FakeHotState:
    """Only the four reads ``read_hot_state`` issues, plus the writes we assert on."""

    def __init__(self) -> None:
        self.lists: dict[str, list[bytes]] = {}
        self.strings: dict[str, bytes] = {}
        self.hashes: dict[str, dict[str, str]] = {}
        self.zsets: dict[str, dict[str, float]] = {}
        self.published: list[tuple[str, bytes]] = []
        self.streams: dict[str, list[dict[bytes, bytes]]] = {}

    def load(
        self,
        *,
        candles: list[NormalizedCandle],
        as_of: datetime,
        trades: int = 120,
        with_book: bool = True,
        with_deriv: bool = True,
    ) -> None:
        self.lists[keys.candles_1m(EXCHANGE, SYMBOL)] = candle_rows(candles)
        self.lists[keys.trades(EXCHANGE, SYMBOL)] = trade_rows(trades, until=as_of)
        if with_book:
            self.strings[keys.book(EXCHANGE, SYMBOL)] = book_payload(ts=as_of)
        if with_deriv:
            self.hashes[keys.derivatives(EXCHANGE, SYMBOL)] = deriv_hash(ts=as_of)

    def publish_coverage(self, *, session_since: datetime, covered_until: datetime) -> None:
        self.hashes[keys.tape_coverage(EXCHANGE)] = {
            "session_since": session_since.isoformat(),
            "covered_until": covered_until.isoformat(),
            f"sym:{SYMBOL}": session_since.isoformat(),
        }

    # --- the redis surface -------------------------------------------------

    def pipeline(self, transaction: bool = False) -> FakePipeline:
        del transaction
        return FakePipeline(self)

    async def lrange(self, key: str, start: int, end: int) -> list[bytes]:
        rows = self.lists.get(key, [])
        return rows[start : end + 1] if end >= 0 else rows[start:]

    async def get(self, key: str) -> bytes | None:
        return self.strings.get(key)

    async def hgetall(self, key: str) -> dict[str, str]:
        return dict(self.hashes.get(key, {}))

    async def set(self, key: str, value: bytes, ex: int | None = None) -> bool:
        del ex
        self.strings[key] = value
        return True

    async def hset(self, key: str, *, mapping: dict[str, str]) -> int:
        self.hashes.setdefault(key, {}).update(mapping)
        return len(mapping)

    async def expire(self, key: str, ttl: int) -> bool:
        del key, ttl
        return True

    async def zadd(self, key: str, mapping: dict[str, float]) -> int:
        self.zsets.setdefault(key, {}).update(mapping)
        return len(mapping)

    async def zrem(self, key: str, *members: str) -> int:
        entry = self.zsets.get(key, {})
        return sum(1 for member in members if entry.pop(member, None) is not None)

    async def delete(self, *keys_: str) -> int:
        return sum(1 for key in keys_ if self.strings.pop(key, None) is not None)

    async def publish(self, channel: str, payload: bytes) -> int:
        self.published.append((channel, payload))
        return 1

    async def xadd(self, stream: str, fields: dict[bytes, bytes], **kwargs: Any) -> str:
        del kwargs
        self.streams.setdefault(stream, []).append(fields)
        return f"{len(self.streams[stream])}-0"


class FakePipeline:
    def __init__(self, state: FakeHotState) -> None:
        self.state = state
        self.calls: list[tuple[str, tuple[Any, ...]]] = []

    async def __aenter__(self) -> FakePipeline:
        return self

    async def __aexit__(self, *args: Any) -> None:
        return None

    def lrange(self, key: str, start: int, end: int) -> None:
        self.calls.append(("lrange", (key, start, end)))

    def get(self, key: str) -> None:
        self.calls.append(("get", (key,)))

    def hgetall(self, key: str) -> None:
        self.calls.append(("hgetall", (key,)))

    async def execute(self) -> list[Any]:
        out: list[Any] = []
        for name, args in self.calls:
            method = getattr(self.state, name)
            out.append(await method(*args))
        self.calls = []
        return out
