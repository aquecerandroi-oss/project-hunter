"""Market read payloads — ARCHITECTURE.md §5.3, DATABASE.md §3/§4.

This module is the authoritative field contract for the Redis hot-state keys
``hunter_market_worker`` (T1.3) writes and this API (T1.4) reads, per
``docs/plans/M1.md``'s "Decisões deste plano" staleness section and the joint
Claude<->Astra decision (``.claude/state/dialogue-M1.md``, rodada 3/4).

**``mkt:{exchange}:{symbol}:ticker`` — HASH (``keys.ticker``)**
Every field is a UTF-8-encoded string (the Redis client here uses
``decode_responses=False``, so callers decode bytes themselves):
``last, bid, ask, bid_qty, ask_qty, volume_24h, quote_volume_24h, high_24h,
low_24h, change_24h_pct, ts``. ``ts`` is the exchange event time of the last
accepted tick (ISO-8601 UTC), never the local flush time.

**``mkt:{exchange}:{symbol}:deriv`` — HASH (``keys.derivatives``)**
``open_interest, open_interest_value, oi_ts, funding_rate, funding_kind,
next_funding_time, funding_ts, mark_price, index_price, mark_ts``. Each
producer (funding, open interest, mark) writes only its own fields and its own
timestamp, so one never rejuvenates another's half of the hash — an OI update
must never make ``mark`` look fresh. Key TTL is not a freshness signal; only
the per-field ``*_ts`` values are.

**``mkt:{exchange}:{symbol}:book`` — STRING, msgpack (``keys.book``)**
``{"ts", "bids": [[price, qty], ...], "asks": [...], "depth": 20, "kind":
"snapshot"}``. Each snapshot replaces the previous one wholesale (no local
book, no delta accumulation). ``kind="snapshot"`` and ``depth=20`` are this
API's own projection of the payload — the internal normalized-domain
discriminator stays ``kind="book"`` (``hunter_core.domain.market
.NormalizedOrderBook``); this module always emits the literal projection
values rather than trusting whatever the payload happens to carry.

**``mkt:{exchange}:{symbol}:trades`` — LIST ring buffer (``keys.trades``)**
The worker ``LPUSH``es each new trade, so index 0 is always the newest and
the list is already newest-first. This API reads the head (``LRANGE 0 49``)
and returns it as-is — reading the tail or reversing it would both silently
invert the order.

**Staleness — the aggregate ``data_quality`` rule (binding, M1.md +
dialogue-M1.md rodada 4).** Required components are ``ticker``, ``book`` and
``mark``; precedence, evaluated in order:

1. all three absent -> ``unavailable``
2. an open/failed ``ingestion_gaps`` row for the market, or any required
   component absent -> ``degraded``
3. any required component older than ``market_stale_after_s`` -> ``stale``
4. otherwise -> ``ok``

Individual component qualities are always reported as computed (never
overridden by the aggregate — a ``degraded`` market can still show its ticker
as ``ok``). ``age_ms`` is always ``now - <component ts>`` (the exchange event
time of the last accepted event for that component), never the flush time.
Open interest and funding expose their own age only; they are not part of the
required set and carry no ``quality``. ``has_open_gap`` is reported
independently of ``components`` so a ``degraded`` market whose three required
components all read ``ok`` — the "gap with fresh ticks" scenario — is still
distinguishable from a ``degraded`` caused by an absent component.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta
from decimal import Decimal
from enum import StrEnum
from typing import TYPE_CHECKING, Annotated, Literal

from pydantic import BaseModel, PlainSerializer

from hunter_core.domain.enums import MarketStatus, MarketType, OrderSide, Timeframe
from hunter_core.domain.market import DataQuality, timeframe_seconds

if TYPE_CHECKING:
    from collections.abc import Sequence

    from hunter_core.db.models.market_data import Candle

DecimalStr = Annotated[
    Decimal, PlainSerializer(lambda v: str(v), return_type=str, when_used="json")
]
"""``Decimal`` fields serialize as JSON strings, never floats/numbers — CLAUDE.md's
"money and quantities are Decimal" would otherwise be undone the moment a
response leaves Python, since JSON has no arbitrary-precision number type and
``float(Decimal("0.1"))`` is exactly the precision loss the rule exists to
prevent."""


class ComponentQuality(StrEnum):
    """Freshness of a single hot-state component — narrower than the
    market-level :class:`~hunter_core.domain.market.DataQuality`, which also
    knows ``degraded``/``unavailable`` (market-wide concepts, not a single
    component's).
    """

    OK = "ok"
    STALE = "stale"
    ABSENT = "absent"


class ComponentStatusOut(BaseModel):
    """A required component's freshness: ``ticker``, ``book``, ``mark``."""

    ts: datetime | None = None
    age_ms: int | None = None
    quality: ComponentQuality


class OptionalComponentStatusOut(BaseModel):
    """A non-required component that only exposes its own age: open interest."""

    ts: datetime | None = None
    age_ms: int | None = None


FundingKind = Literal["estimated", "realized"]
"""(G10) The only two values ``mkt:*:deriv``'s ``funding_kind`` field may
carry (dialogue-M1.md rodada 3/4): ``estimated`` is a live mark/index-price
reading, not yet settled; ``realized`` is settled funding read back from the
exchange's funding-rate history endpoint. A value read from Redis that is
neither is dropped to ``None`` by ``services.markets_codec.to_funding_kind``
rather than passed through as an unconstrained string — ``None`` here means
"unknown", the same honest meaning it already carries when ``funding_kind``
was never written at all."""


class FundingComponentStatusOut(OptionalComponentStatusOut):
    """Funding additionally reports whether the rate is ``estimated`` or
    ``realized`` (``mkt:*:deriv``'s ``funding_kind``) — see ``FundingKind``
    for what happens to a value that is neither."""

    kind: FundingKind | None = None


class MarketComponentsOut(BaseModel):
    ticker: ComponentStatusOut
    book: ComponentStatusOut
    mark: ComponentStatusOut
    open_interest: OptionalComponentStatusOut
    funding: FundingComponentStatusOut


class MarketOut(BaseModel):
    """One row of ``GET /api/v1/markets`` or the base of the detail response.

    ``markets``/``exchanges``/``assets`` (Postgres, global/no-RLS tables) give
    the identity and configuration columns; every other field comes from
    Redis hot state and is ``null`` whenever its source component is absent —
    this endpoint never invents a number.
    """

    id: uuid.UUID
    exchange: str
    symbol: str
    base_asset: str | None = None
    quote_asset: str | None = None
    market_type: MarketType
    status: MarketStatus
    is_monitored: bool
    monitor_rank: int | None = None
    last_price: DecimalStr | None = None
    bid: DecimalStr | None = None
    ask: DecimalStr | None = None
    spread_pct: DecimalStr | None = None
    volume_24h: DecimalStr | None = None
    quote_volume_24h: DecimalStr | None = None
    price_change_24h_pct: DecimalStr | None = None
    mark_price: DecimalStr | None = None
    open_interest: DecimalStr | None = None
    funding_rate: DecimalStr | None = None
    funding_kind: FundingKind | None = None
    last_update: datetime | None = None
    data_quality: DataQuality
    has_open_gap: bool
    components: MarketComponentsOut


class MarketsSummary(BaseModel):
    """Counts over every market matching the request's filters (not just the
    page returned) — cheap at M1 scale (``MARKET_UNIVERSE_SIZE`` default 200)
    and what a status header needs ("187 of 200 monitored, 3 stale").
    """

    markets_total: int
    markets_monitored: int
    markets_ok: int
    markets_stale: int
    markets_degraded: int
    markets_unavailable: int


class MarketListPage(BaseModel):
    """``GET /api/v1/markets`` — ``schemas.common.CursorPage`` shape plus the
    top-level ``summary`` the brief asks for (a bare ``CursorPage[MarketOut]``
    has no place for it).
    """

    items: list[MarketOut]
    next_cursor: str | None = None
    summary: MarketsSummary
    stale_after_ms: int
    """(F8) The same ``settings.market_stale_after_s`` (converted to
    milliseconds) the aggregate/component ``quality`` fields above were
    computed with — so a client ages a badge locally using the threshold this
    API actually used, instead of a hardcoded value that silently drifts out
    of sync with it."""


class BookLevelOut(BaseModel):
    price: DecimalStr
    qty: DecimalStr


class OrderBookOut(BaseModel):
    """The API's fixed projection of ``mkt:*:book`` — see the module
    docstring: ``kind`` and ``depth`` are always these literal values, never
    read off the payload.
    """

    ts: datetime | None = None
    depth: Literal[20] = 20
    kind: Literal["snapshot"] = "snapshot"
    bids: list[BookLevelOut] = []
    asks: list[BookLevelOut] = []


class TradeOut(BaseModel):
    ts: datetime
    price: DecimalStr
    qty: DecimalStr
    side: OrderSide
    trade_id: str


class MarketDetailOut(MarketOut):
    """``GET /api/v1/markets/{exchange}/{symbol}`` — the list row plus book and
    recent trades.

    (G9) ``hot_state_ok`` is the one explicit, machine-readable signal for
    whether this request's Redis hot-state read succeeded — ``ticker``,
    ``deriv``, ``book`` and ``trades`` share a single pipeline read in
    ``services.markets.build_market_detail``, so they either all come back
    real or none do; one flag covers all four. Read ``book``/``recent_trades``
    together with it, never on their own:

    * ``hot_state_ok is False`` — the read itself failed (Redis down, or a
      ``WRONGTYPE`` on one of the keys). ``book`` is ``null`` and
      ``recent_trades`` is ``null`` because this API *could not ask*, not
      because there is no book/no trades. Render an outage state, never
      "no book"/"no recent trades".
    * ``hot_state_ok is True`` — the read succeeded; ``book``/``recent_trades``
      are the honest state. ``book`` is ``null`` only when ``mkt:*:book`` has
      expired or was never written; ``recent_trades`` is ``[]`` only when
      there is genuinely nothing recent.
    """

    stale_after_ms: int
    """(F8) See ``MarketListPage.stale_after_ms`` — the same value, repeated
    here because a detail response is not paged through ``MarketListPage``."""
    hot_state_ok: bool
    book: OrderBookOut | None = None
    recent_trades: list[TradeOut] | None = None


class CandleOut(BaseModel):
    """One ``candles`` row (``is_final = true`` only — DATABASE.md §4's
    anti-look-ahead gate). ``close_time`` is derived (``open_time`` + the
    timeframe's duration), not a stored column.
    """

    open_time: datetime
    close_time: datetime
    open: DecimalStr
    high: DecimalStr
    low: DecimalStr
    close: DecimalStr
    volume: DecimalStr
    quote_volume: DecimalStr | None = None
    trade_count: int | None = None
    taker_buy_volume: DecimalStr | None = None

    @classmethod
    def from_candle(cls, candle: Candle, timeframe: Timeframe) -> CandleOut:
        return cls(
            open_time=candle.open_time,
            close_time=candle.open_time + timedelta(seconds=timeframe_seconds(timeframe)),
            open=candle.open,
            high=candle.high,
            low=candle.low,
            close=candle.close,
            volume=candle.volume,
            quote_volume=candle.quote_volume,
            trade_count=candle.trade_count,
            taker_buy_volume=candle.taker_buy_volume,
        )

    @classmethod
    def from_candles(cls, candles: Sequence[Candle], timeframe: Timeframe) -> list[CandleOut]:
        return [cls.from_candle(candle, timeframe) for candle in candles]
