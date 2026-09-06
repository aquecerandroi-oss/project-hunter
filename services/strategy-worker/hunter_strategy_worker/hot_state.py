"""Reading the market-worker's hot state: 1m candles and the derivatives hash.

Read-only, and deliberately narrow: for candles, only the **tail**; for
funding/open interest, only the single newest reading of each field
(``mkt:{ex}:{sym}:deriv``, ``DERIV_TTL_S = 600`` in the market-worker). The
durable series/tables are authoritative — Redis is what covers the gap between
an event and the next persistence flush (ARCHITECTURE.md §5.3), which is why
:mod:`.derivatives` reads Postgres first and falls back here only when the
durable side has nothing at or before the cut.

Non-final entries and anything at or after the cut are dropped here rather
than at the context: a partial candle, or a reading from the future, is not an
observation (SHADOW-LAB.md's "nothing from the future" applies to derivatives
exactly as it does to candles).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import TYPE_CHECKING, Any, cast

import msgpack

from hunter_core.domain.market import NormalizedCandle, from_wire
from hunter_core.domain.types import ensure_utc
from hunter_core.logging import get_logger
from hunter_core.redis import keys

if TYPE_CHECKING:
    import redis.asyncio as redis_asyncio

logger = get_logger(__name__)
_codec: Any = msgpack

__all__ = ["DerivRaw", "read_derivatives", "read_tail"]


def _decode(raw: bytes) -> NormalizedCandle | None:
    value: Any = _codec.unpackb(raw, raw=False)
    if not isinstance(value, dict):
        return None
    data: dict[str, Any] = dict(cast("dict[str, Any]", value))
    data.pop("ts", None)  # market-worker's partial-ordering token, not a model field
    try:
        return from_wire(NormalizedCandle, data)
    except Exception:
        logger.warning("shadow_hot_state_candle_unreadable")
        return None


async def read_tail(
    redis: redis_asyncio.Redis, *, exchange: str, symbol: str, count: int, cut: datetime
) -> list[NormalizedCandle]:
    """The newest ``count`` final 1m candles that had closed by ``cut``."""
    if count <= 0:
        return []
    key = keys.candles_1m(exchange, symbol)
    rows: list[bytes] = cast("list[bytes]", await redis.lrange(key, 0, count - 1))
    candles: list[NormalizedCandle] = []
    for raw in rows:
        candle = _decode(raw)
        if candle is None or not candle.is_final or candle.close_time > cut:
            continue
        if candle.exchange != exchange or candle.symbol != symbol:
            continue
        candles.append(candle)
    candles.sort(key=lambda candle: candle.open_time)
    return candles


def _text(value: bytes | str) -> str:
    return value.decode() if isinstance(value, bytes) else value


def _decimal(value: str | None) -> Decimal | None:
    """A **finite** ``Decimal``, or ``None`` (mirrors ``hunter_indicators``'s
    reader for the same hash: a corrupted field is no field, never ``NaN``)."""
    if value is None:
        return None
    try:
        parsed = Decimal(value)
    except InvalidOperation:
        return None
    return parsed if parsed.is_finite() else None


def _instant(value: str | None) -> datetime | None:
    if value is None:
        return None
    try:
        return ensure_utc(datetime.fromisoformat(value))
    except ValueError:
        return None


@dataclass(frozen=True, slots=True)
class DerivRaw:
    """The ``mkt:{ex}:{sym}:deriv`` hash, decoded and cut at ``cut``.

    Funding and mark price are written as two **independently** freshness-gated
    field groups (``hunter_market_worker.hot_state.write_funding``), and a
    realized settlement write touches only the funding group, leaving whatever
    mark price was last written by an unrelated estimated snapshot in place.
    ``funding_ts`` and ``mark_ts`` therefore travel separately so a caller can
    tell "the same write set both" (``funding_ts == mark_ts``, true for every
    ``realized=False`` write) from "these are two unrelated readings that
    happen to both be fresh" (Astra, S2-context review, must-fix 2) — only the
    former is one observation.
    """

    funding_rate: Decimal | None
    funding_kind: str | None
    funding_ts: datetime | None
    mark_price: Decimal | None
    mark_ts: datetime | None
    open_interest: Decimal | None
    open_interest_ts: datetime | None


_EMPTY_DERIV = DerivRaw(
    funding_rate=None,
    funding_kind=None,
    funding_ts=None,
    mark_price=None,
    mark_ts=None,
    open_interest=None,
    open_interest_ts=None,
)


async def read_derivatives(
    redis: redis_asyncio.Redis, *, exchange: str, symbol: str, cut: datetime
) -> DerivRaw:
    """Funding/open-interest fields observed at or before ``cut``.

    ``DERIV_TTL_S = 600`` in the market-worker means the hash holds only the
    single newest reading of each field, never a history: this can only ever
    answer "what is the last known value", not "what was it N minutes ago".
    """
    raw: dict[Any, Any] = await redis.hgetall(keys.derivatives(exchange, symbol))  # type: ignore[misc]
    if not raw:
        return _EMPTY_DERIV
    plain = {_text(k): _text(v) for k, v in raw.items() if not _text(k).startswith("_")}
    funding_ts = _instant(plain.get("funding_ts"))
    mark_ts = _instant(plain.get("mark_ts"))
    oi_ts = _instant(plain.get("oi_ts"))
    funding_ok = funding_ts is not None and funding_ts <= cut
    mark_ok = mark_ts is not None and mark_ts <= cut
    oi_ok = oi_ts is not None and oi_ts <= cut
    return DerivRaw(
        funding_rate=_decimal(plain.get("funding_rate")) if funding_ok else None,
        funding_kind=plain.get("funding_kind") if funding_ok else None,
        funding_ts=funding_ts if funding_ok else None,
        mark_price=_decimal(plain.get("mark_price")) if mark_ok else None,
        mark_ts=mark_ts if mark_ok else None,
        open_interest=_decimal(plain.get("open_interest")) if oi_ok else None,
        open_interest_ts=oi_ts if oi_ok else None,
    )
