"""Normalized MT5 models: the only shapes that cross out of ``hunter_exchanges.mt5``.

Frozen, ``extra="forbid"``, **no ``float`` anywhere** (refused at construction, as in
``hunter_risk.base``) and every timestamp tz-aware UTC. A terminal ``login``/``server`` never
appears in a model: the account is identified by ``account_hash`` only (contract §1.1, I-S-1).

Absent stop/target levels are ``Decimal(0)`` because that is how the terminal reports them;
:attr:`Mt5Position.has_stop` is the readable form.
"""

from __future__ import annotations

import uuid
from collections.abc import Mapping
from datetime import UTC, datetime
from decimal import Decimal
from enum import StrEnum
from typing import Annotated, Any, cast

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .constants import Filling, TimeMode
from .retcodes import Action, Verdict

NonNegDec = Annotated[Decimal, Field(ge=0)]
PosDec = Annotated[Decimal, Field(gt=0)]


class Mt5Model(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    @model_validator(mode="before")
    @classmethod
    def _refuse_float(cls, data: Any) -> Any:
        untouched: Any = data
        if isinstance(data, Mapping):
            for key, value in cast("Mapping[object, object]", data).items():
                if isinstance(value, float):
                    raise TypeError(f"{cls.__name__}.{key} received a float; use Decimal")
        return untouched

    @field_validator("*", mode="after")
    @classmethod
    def _utc_only(cls, value: Any) -> Any:
        if isinstance(value, datetime):
            if value.tzinfo is None or value.tzinfo.utcoffset(value) is None:
                raise ValueError("naive datetime is not allowed; every timestamp is tz-aware UTC")
            return value.astimezone(UTC)
        return value


class Side(StrEnum):
    BUY = "buy"
    SELL = "sell"

    @property
    def opposite(self) -> Side:
        return Side.SELL if self is Side.BUY else Side.BUY


class AccountMode(StrEnum):
    DEMO = "demo"
    REAL = "real"
    CONTEST = "contest"


class MarginMode(StrEnum):
    NETTING = "netting"  # ACCOUNT_MARGIN_MODE_RETAIL_NETTING
    EXCHANGE = "exchange"  # ACCOUNT_MARGIN_MODE_EXCHANGE (the B3 case)
    HEDGING = "hedging"


# ------------------------------------------------------------------ reads


class Mt5TerminalInfo(Mt5Model):
    connected: bool
    trade_allowed: bool  # the terminal's "Algo Trading" button (K2)
    tradeapi_disabled: bool
    build: int
    ping_last_us: int | None
    read_at: datetime


class Mt5Account(Mt5Model):
    account_hash: Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
    trade_mode: AccountMode
    margin_mode: MarginMode
    currency: str
    currency_digits: int
    balance: Decimal
    equity: Decimal
    margin: Decimal
    margin_free: Decimal
    trade_allowed: bool
    trade_expert: bool
    read_at: datetime


class Mt5SymbolSpec(Mt5Model):
    symbol: str
    trade_tick_size: PosDec
    trade_tick_value: PosDec
    point: PosDec
    digits: int
    volume_min: PosDec
    volume_step: PosDec
    volume_max: PosDec
    trade_mode: int
    filling_mode: int  # SYMBOL_FILLING_* bit mask, kept raw
    expiration_mode: int  # SYMBOL_EXPIRATION_* bit mask, kept raw
    trade_stops_level: int  # in points
    trade_freeze_level: int  # in points
    trade_contract_size: PosDec
    visible: bool


class Mt5Tick(Mt5Model):
    symbol: str
    server_time: datetime  # the broker's clock reading; correcting it is the caller's offset (T11)
    received_at: datetime
    bid: NonNegDec
    ask: NonNegDec
    last: NonNegDec


class Mt5Position(Mt5Model):
    position_id: int  # POSITION_IDENTIFIER: the identity (contract §1.1)
    position_ticket: int  # POSITION_TICKET: the address; may change
    symbol: str
    side: Side
    volume: PosDec
    price_open: PosDec
    sl: NonNegDec  # 0 = no stop
    tp: NonNegDec  # 0 = no target
    magic: int
    comment: str
    opened_at: datetime
    reason: int

    @property
    def has_stop(self) -> bool:
        return self.sl != 0


class Mt5Order(Mt5Model):
    ticket: int
    symbol: str
    order_type: int
    state: int
    volume_initial: NonNegDec
    volume_current: NonNegDec
    price_open: NonNegDec
    sl: NonNegDec
    tp: NonNegDec
    magic: int
    comment: str
    position_id: int
    time_setup: datetime
    time_done: datetime | None = None
    expiration: datetime | None = None


class Mt5Deal(Mt5Model):
    ticket: int
    order_ticket: int
    position_id: int
    symbol: str
    deal_type: int
    entry: int
    volume: NonNegDec
    price: NonNegDec
    commission: Decimal
    fee: Decimal
    swap: Decimal
    profit: Decimal
    magic: int
    reason: int
    comment: str
    time: datetime


# ------------------------------------------------------------------ requests


class EntryKind(StrEnum):
    MARKET = "market"  # TRADE_ACTION_DEAL
    LIMIT = "limit"  # TRADE_ACTION_PENDING, ORDER_TYPE_*_LIMIT


class EntryRequest(Mt5Model):
    """The only DEAL/PENDING request the port sends. ``sl=0`` is representable so the guard
    can refuse it; the engine's check 15 is what stops a naked entry from being proposed."""

    symbol: Annotated[str, Field(min_length=1)]
    side: Side
    kind: EntryKind
    volume: PosDec
    price: PosDec  # limit price, or the reference for `deviation_points` on a market deal
    deviation_points: Annotated[int, Field(ge=0)] = 0
    sl: NonNegDec
    tp: NonNegDec = Decimal(0)
    magic: Annotated[int, Field(ge=0)]
    comment: Annotated[str, Field(max_length=31, pattern=r"^[\x20-\x7e]*$")]
    filling: Filling
    time_in_force: TimeMode = TimeMode.DAY
    expiration: datetime | None = None

    @model_validator(mode="after")
    def _expiration_matches_time_mode(self) -> EntryRequest:
        needs = self.time_in_force in (TimeMode.SPECIFIED, TimeMode.SPECIFIED_DAY)
        if needs != (self.expiration is not None):
            raise ValueError("expiration is required exactly for SPECIFIED time modes")
        return self


class SltpRequest(Mt5Model):
    """A ``TRADE_ACTION_SLTP`` request (contract §4.3, §5.1): nothing but levels."""

    sltp_request_id: uuid.UUID  # minted and recorded by the caller BEFORE sending (I-SL-5)
    symbol: Annotated[str, Field(min_length=1)]
    position_ticket: Annotated[int, Field(gt=0)]  # `request_position_ticket` (I-SL-4)
    sl: NonNegDec
    tp: NonNegDec = Decimal(0)
    magic: Annotated[int, Field(ge=0)]
    floor_sl: PosDec  # the tightest stop known (contract §4.4); never to be widened past


# ------------------------------------------------------------------ results


class Mt5CheckResult(Mt5Model):
    ok: bool
    retcode: int | None
    retcode_name: str
    comment: str
    margin: Decimal | None = None
    margin_free: Decimal | None = None


class SendOutcome(Mt5Model):
    """What ``order_send`` did, or may have done. ``verdict is UNCERTAIN`` means: never resend."""

    action: Action
    verdict: Verdict
    retcode: int | None
    retcode_name: str
    broker_comment: str
    order_ticket: int | None = None
    deal_ticket: int | None = None
    volume: Decimal | None = None
    price: Decimal | None = None
    error: str | None = None  # none_result | ipc_timeout | exception:<Type>
    last_error: tuple[int, str] | None = None
    sltp_request_id: uuid.UUID | None = None
    request_position_ticket: int | None = None
    sent_at: datetime
    received_at: datetime
