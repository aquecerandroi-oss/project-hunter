"""Normalized market domain types shared by every exchange adapter and worker.

``docs/EXCHANGE_INTEGRATION.md`` §2-3 — the adapter contract: an
``ExchangeAdapter`` speaks only its exchange's dialect internally and returns
these ``Normalized*`` models; no raw field crosses the ``hunter_exchanges``
boundary except inside an explicitly labelled ``metadata`` dict.

All models are ``frozen=True, extra="forbid"``: prices/quantities are
``Decimal`` (never ``float``), every timestamp is timezone-aware UTC (naive
datetimes are rejected), and each event model carries a fixed ``kind``
discriminator so ``TypeAdapter(NormalizedEvent)`` can parse a dict back into
the right class.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal
from enum import StrEnum
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, computed_field, field_validator, model_validator

from hunter_core.domain.enums import MarketStatus, MarketType, OrderSide, Timeframe
from hunter_core.domain.types import ensure_utc, utcnow

_TIMEFRAME_SECONDS: dict[Timeframe, int] = {
    Timeframe.M1: 60,
    Timeframe.M5: 5 * 60,
    Timeframe.M15: 15 * 60,
    Timeframe.H1: 60 * 60,
    Timeframe.H4: 4 * 60 * 60,
    Timeframe.D1: 24 * 60 * 60,
}


class DataQuality(StrEnum):
    """Freshness of a market's hot state — ``docs/plans/M1.md`` staleness rule."""

    OK = "ok"
    STALE = "stale"
    DEGRADED = "degraded"
    UNAVAILABLE = "unavailable"


def timeframe_seconds(tf: Timeframe) -> int:
    """Duration of one candle of timeframe ``tf``, in seconds."""
    return _TIMEFRAME_SECONDS[tf]


def align_open_time(ts: datetime, tf: Timeframe) -> datetime:
    """Floor ``ts`` to the start of the ``tf`` bucket it falls in, in UTC.

    Buckets are aligned to the Unix epoch (as Binance klines are), so this
    works uniformly for every timeframe in :class:`Timeframe`.
    """
    aware = ensure_utc(ts)
    seconds = timeframe_seconds(tf)
    epoch = int(aware.timestamp())
    floored = epoch - (epoch % seconds)
    return datetime.fromtimestamp(floored, tz=aware.tzinfo)


def close_time_for(open_time: datetime, tf: Timeframe) -> datetime:
    """End of the candle starting at ``open_time`` (exclusive)."""
    return ensure_utc(open_time) + timedelta(seconds=timeframe_seconds(tf))


def is_aligned(ts: datetime, tf: Timeframe) -> bool:
    """Whether ``ts`` already sits on a ``tf`` bucket boundary."""
    return align_open_time(ts, tf) == ensure_utc(ts)


def data_quality(
    last_event_at: datetime | None,
    *,
    now: datetime,
    stale_after_s: int,
    has_open_gap: bool,
) -> DataQuality:
    """Classify a market's data freshness for the API/UI staleness badge."""
    if last_event_at is None:
        return DataQuality.UNAVAILABLE
    if has_open_gap:
        return DataQuality.DEGRADED
    age_s = (ensure_utc(now) - ensure_utc(last_event_at)).total_seconds()
    if age_s > stale_after_s:
        return DataQuality.STALE
    return DataQuality.OK


def to_wire(model: BaseModel) -> dict[str, Any]:
    """Serialize ``model`` for Redis/wire transport: ``Decimal`` -> str, ``datetime`` -> ISO 8601.

    Computed fields (e.g. ``spread_pct``) are derived, not stored state, and
    every model here forbids extra fields — so they are excluded here to keep
    :func:`from_wire` a lossless inverse.
    """
    computed = set(type(model).model_computed_fields)
    return model.model_dump(mode="json", exclude=computed)


def from_wire[ModelT: BaseModel](cls: type[ModelT], data: dict[str, Any]) -> ModelT:
    """Inverse of :func:`to_wire`."""
    return cls.model_validate(data)


class NormalizedModel(BaseModel):
    """Shared config for every model in this module."""

    model_config = ConfigDict(frozen=True, extra="forbid")


class _TsUtcMixin(NormalizedModel):
    """Adds an ``ts`` (exchange event time) field, enforced UTC-aware."""

    ts: datetime

    @field_validator("ts", mode="after")
    @classmethod
    def _ts_is_utc(cls, v: datetime) -> datetime:
        return ensure_utc(v)


class _ReceivedAtMixin(NormalizedModel):
    """Adds ``received_at`` (local receive time), defaulting to ``utcnow()``."""

    received_at: datetime = Field(default_factory=utcnow)

    @field_validator("received_at", mode="after")
    @classmethod
    def _received_at_is_utc(cls, v: datetime) -> datetime:
        return ensure_utc(v)


class NormalizedMarket(NormalizedModel):
    """A tradable instrument as listed by an exchange (``exchangeInfo``/``instruments-info``)."""

    exchange: str
    symbol: str
    market_type: MarketType
    base: str
    quote: str
    status: MarketStatus
    tick_size: Decimal
    step_size: Decimal
    min_notional: Decimal
    contract_size: Decimal | None = None
    max_leverage: int | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class NormalizedTicker(_TsUtcMixin, _ReceivedAtMixin):
    kind: Literal["ticker"] = "ticker"
    exchange: str
    symbol: str
    last: Decimal
    bid: Decimal | None = None
    ask: Decimal | None = None
    bid_qty: Decimal | None = None
    ask_qty: Decimal | None = None
    volume_24h: Decimal | None = None
    quote_volume_24h: Decimal | None = None
    high_24h: Decimal | None = None
    low_24h: Decimal | None = None
    change_24h_pct: Decimal | None = None

    @computed_field  # type: ignore[prop-decorator]
    @property
    def spread_pct(self) -> Decimal | None:
        if self.bid is None or self.ask is None:
            return None
        mid = (self.bid + self.ask) / 2
        if mid == 0:
            return None
        return (self.ask - self.bid) / mid * 100


class NormalizedTrade(_TsUtcMixin, _ReceivedAtMixin):
    kind: Literal["trade"] = "trade"
    exchange: str
    symbol: str
    trade_id: str
    price: Decimal
    qty: Decimal
    side: OrderSide
    is_block: bool = False


class BookLevel(NormalizedModel):
    price: Decimal
    qty: Decimal = Field(ge=0)


class NormalizedOrderBook(_TsUtcMixin, _ReceivedAtMixin):
    kind: Literal["book"] = "book"
    exchange: str
    symbol: str
    bids: list[BookLevel]
    asks: list[BookLevel]
    sequence: int | None = None
    is_snapshot: bool

    @field_validator("bids", mode="after")
    @classmethod
    def _bids_sorted_desc(cls, v: list[BookLevel]) -> list[BookLevel]:
        if any(a.price < b.price for a, b in zip(v, v[1:], strict=False)):
            raise ValueError("bids must be sorted descending by price")
        return v

    @field_validator("asks", mode="after")
    @classmethod
    def _asks_sorted_asc(cls, v: list[BookLevel]) -> list[BookLevel]:
        if any(a.price > b.price for a, b in zip(v, v[1:], strict=False)):
            raise ValueError("asks must be sorted ascending by price")
        return v

    @computed_field  # type: ignore[prop-decorator]
    @property
    def best_bid(self) -> Decimal | None:
        return self.bids[0].price if self.bids else None

    @computed_field  # type: ignore[prop-decorator]
    @property
    def best_ask(self) -> Decimal | None:
        return self.asks[0].price if self.asks else None

    @computed_field  # type: ignore[prop-decorator]
    @property
    def mid(self) -> Decimal | None:
        if self.best_bid is None or self.best_ask is None:
            return None
        return (self.best_bid + self.best_ask) / 2

    @computed_field  # type: ignore[prop-decorator]
    @property
    def spread_pct(self) -> Decimal | None:
        if self.best_bid is None or self.best_ask is None or not self.mid:
            return None
        return (self.best_ask - self.best_bid) / self.mid * 100

    def imbalance(self, depth: int) -> Decimal | None:
        """(sum bid qty - sum ask qty) / (sum bid qty + sum ask qty) over the top ``depth`` levels."""
        bid_qty = sum((lvl.qty for lvl in self.bids[:depth]), start=Decimal(0))
        ask_qty = sum((lvl.qty for lvl in self.asks[:depth]), start=Decimal(0))
        total = bid_qty + ask_qty
        if total == 0:
            return None
        return (bid_qty - ask_qty) / total


class NormalizedCandle(_ReceivedAtMixin):
    kind: Literal["candle"] = "candle"
    exchange: str
    symbol: str
    timeframe: Timeframe
    open_time: datetime
    close_time: datetime
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Decimal
    quote_volume: Decimal | None = None
    trade_count: int | None = None
    taker_buy_volume: Decimal | None = None
    is_final: bool

    @field_validator("open_time", "close_time", mode="after")
    @classmethod
    def _times_are_utc(cls, v: datetime) -> datetime:
        return ensure_utc(v)

    @model_validator(mode="after")
    def _check_invariants(self) -> NormalizedCandle:
        if self.close_time <= self.open_time:
            raise ValueError("close_time must be after open_time")
        if self.high < max(self.open, self.close):
            raise ValueError("high must be >= max(open, close)")
        if self.low > min(self.open, self.close):
            raise ValueError("low must be <= min(open, close)")
        if not is_aligned(self.open_time, self.timeframe):
            raise ValueError("open_time must be aligned to the timeframe boundary")
        return self


class NormalizedFunding(_TsUtcMixin, _ReceivedAtMixin):
    kind: Literal["funding"] = "funding"
    exchange: str
    symbol: str
    funding_rate: Decimal
    next_funding_time: datetime | None = None
    mark_price: Decimal
    index_price: Decimal | None = None

    @field_validator("next_funding_time", mode="after")
    @classmethod
    def _next_funding_time_is_utc(cls, v: datetime | None) -> datetime | None:
        return None if v is None else ensure_utc(v)


class NormalizedOpenInterest(_TsUtcMixin, _ReceivedAtMixin):
    kind: Literal["open_interest"] = "open_interest"
    exchange: str
    symbol: str
    open_interest: Decimal
    open_interest_value: Decimal | None = None


class NormalizedLiquidation(_TsUtcMixin, _ReceivedAtMixin):
    kind: Literal["liquidation"] = "liquidation"
    exchange: str
    symbol: str
    side: OrderSide
    qty: Decimal
    price: Decimal
    notional: Decimal | None = None

    @model_validator(mode="after")
    def _default_notional(self) -> NormalizedLiquidation:
        if self.notional is None:
            object.__setattr__(self, "notional", self.qty * self.price)
        return self


NormalizedEvent = Annotated[
    NormalizedTicker
    | NormalizedTrade
    | NormalizedOrderBook
    | NormalizedCandle
    | NormalizedFunding
    | NormalizedOpenInterest
    | NormalizedLiquidation,
    Field(discriminator="kind"),
]
