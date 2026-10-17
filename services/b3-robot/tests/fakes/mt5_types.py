"""FAKE MetaTrader 5 value types: the vendor's named tuples (floats), reduced to the fields the
adapter reads, plus the mutable records the fake keeps. TEST CODE ONLY."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import NamedTuple


class TerminalInfo(NamedTuple):
    connected: bool
    trade_allowed: bool
    tradeapi_disabled: bool
    build: int
    ping_last: int
    path: str
    data_path: str


class AccountInfo(NamedTuple):
    login: int
    server: str
    trade_mode: int
    margin_mode: int
    currency: str
    currency_digits: int
    balance: float
    equity: float
    margin: float
    margin_free: float
    trade_allowed: bool
    trade_expert: bool


class SymbolInfo(NamedTuple):
    name: str
    select: bool
    visible: bool
    digits: int
    point: float
    trade_tick_size: float
    trade_tick_value: float
    trade_contract_size: float
    volume_min: float
    volume_max: float
    volume_step: float
    trade_mode: int
    filling_mode: int
    expiration_mode: int
    trade_stops_level: int
    trade_freeze_level: int


class Tick(NamedTuple):
    time: int
    time_msc: int
    bid: float
    ask: float
    last: float
    volume: int
    flags: int


class TradePosition(NamedTuple):
    ticket: int
    identifier: int
    time_msc: int
    type: int
    magic: int
    reason: int
    volume: float
    price_open: float
    sl: float
    tp: float
    symbol: str
    comment: str


class TradeOrder(NamedTuple):
    ticket: int
    time_setup_msc: int
    time_done_msc: int
    time_expiration: int
    type: int
    type_filling: int
    type_time: int
    state: int
    magic: int
    position_id: int
    reason: int
    volume_initial: float
    volume_current: float
    price_open: float
    sl: float
    tp: float
    symbol: str
    comment: str


class TradeDeal(NamedTuple):
    ticket: int
    order: int
    time_msc: int
    type: int
    entry: int
    magic: int
    position_id: int
    reason: int
    volume: float
    price: float
    commission: float
    swap: float
    profit: float
    fee: float
    symbol: str
    comment: str


class OrderSendResult(NamedTuple):
    retcode: int
    deal: int
    order: int
    volume: float
    price: float
    bid: float
    ask: float
    comment: str
    request_id: int


class OrderCheckResult(NamedTuple):
    retcode: int
    balance: float
    equity: float
    margin: float
    margin_free: float
    comment: str


# ---------------------------------------------------------------- the fake's own mutable records


@dataclass
class Pos:
    position_id: int
    ticket: int
    symbol: str
    side: int  # 0 buy / 1 sell
    volume: float
    price_open: float
    sl: float
    tp: float
    magic: int
    comment: str
    time_msc: int
    reason: int


@dataclass
class Ord:
    ticket: int
    symbol: str
    type: int
    state: int
    volume_initial: float
    volume_current: float
    price_open: float
    sl: float
    tp: float
    magic: int
    comment: str
    position_id: int
    time_setup_msc: int
    filling: int
    time_type: int
    expiration: int
    reason: int = 3
    time_done_msc: int = 0


@dataclass
class Deal:
    ticket: int
    order: int
    time_msc: int
    type: int
    entry: int
    magic: int
    position_id: int
    reason: int
    volume: float
    price: float
    commission: float
    profit: float
    symbol: str
    comment: str


@dataclass
class Fault:
    """A scripted misbehaviour of the next matching ``order_send``."""

    kind: str  # reject | none_after_effect | none_no_effect | raise | hang
    action: int | None = None
    retcode: int | None = None


@dataclass
class Hooks:
    drop_comment: bool = False
    drop_magic: bool = False
    float_noise: bool = False
    duplicate_deals: bool = False
    history_unavailable: bool = False
    history_floor_ms: int = 0
    delisted: bool = False
    reversal_new_identifier: bool = False
    faults: list[Fault] = field(default_factory=list[Fault])
