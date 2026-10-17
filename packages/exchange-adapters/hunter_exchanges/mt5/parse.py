"""Vendor named tuples (floats) -> ``Decimal``/UTC models. The only place raw objects are read.

Rules, all of them about *not inventing numbers*:

* a missing attribute, a ``NaN`` or a value of the wrong kind is ``Mt5ReadError(malformed:<field>)``
  — never a zero, never a default (the number that hides a loss is the zero);
* prices and volumes snap to the symbol's grid when they are on it (killing float noise exactly)
  and otherwise keep the float's shortest repr — a VWAP ``price_open`` is legitimately off-grid
  and a *report* of the terminal is never refused or rounded for being odd;
* amounts in the account currency are quantized to the account's ``currency_digits``;
* ``login`` and ``server`` are read once, hashed, and dropped (contract §1.1, I-S-1).
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any

from .constants import AccountMarginMode, AccountTradeMode, PositionType
from .convert import (
    OffGridError,
    decimal_from_float,
    decimal_from_number,
    from_float_on_grid,
    money_from_float,
    utc_from_epoch,
    utc_from_msc,
)
from .errors import Mt5ReadError
from .models import (
    AccountMode,
    MarginMode,
    Mt5Account,
    Mt5Deal,
    Mt5Order,
    Mt5Position,
    Mt5SymbolSpec,
    Mt5TerminalInfo,
    Mt5Tick,
    Side,
)


@dataclass(frozen=True)
class Grid:
    """The price and volume grid of one symbol."""

    tick: Decimal
    volume_step: Decimal


def _bad(what: str, field: str) -> Mt5ReadError:
    return Mt5ReadError(what, reason=f"malformed:{field}")


def _attr(obj: Any, name: str, what: str) -> Any:
    try:
        return getattr(obj, name)
    except AttributeError:
        raise _bad(what, name) from None


def _num(obj: Any, name: str, what: str) -> float:
    value = _attr(obj, name, what)
    if isinstance(value, bool) or not isinstance(value, (int, float)) or value != value:
        raise _bad(what, name)
    return float(value)


def _int(obj: Any, name: str, what: str) -> int:
    value = _attr(obj, name, what)
    if isinstance(value, bool) or not isinstance(value, int):
        raise _bad(what, name)
    return value


def _str(obj: Any, name: str, what: str) -> str:
    value = _attr(obj, name, what)
    if not isinstance(value, str):
        raise _bad(what, name)
    return value


def _bool(obj: Any, name: str, what: str) -> bool:
    value = _attr(obj, name, what)
    if not isinstance(value, (bool, int)):
        raise _bad(what, name)
    return bool(value)


def _snap(value: float, step: Decimal, what: str, field: str) -> Decimal:
    try:
        return from_float_on_grid(value, step)
    except OffGridError:
        return decimal_from_float(value)
    except ValueError:
        raise _bad(what, field) from None


def _dec(value: float, what: str, field: str) -> Decimal:
    try:
        return decimal_from_float(value)
    except ValueError:
        raise _bad(what, field) from None


def _price(obj: Any, name: str, grid: Grid, what: str) -> Decimal:
    return _snap(_num(obj, name, what), grid.tick, what, name)


def _volume(obj: Any, name: str, grid: Grid, what: str) -> Decimal:
    return _snap(_num(obj, name, what), grid.volume_step, what, name)


_TRADE_MODES = {
    int(AccountTradeMode.DEMO): AccountMode.DEMO,
    int(AccountTradeMode.REAL): AccountMode.REAL,
    int(AccountTradeMode.CONTEST): AccountMode.CONTEST,
}
_MARGIN_MODES = {
    int(AccountMarginMode.RETAIL_NETTING): MarginMode.NETTING,
    int(AccountMarginMode.EXCHANGE): MarginMode.EXCHANGE,
    int(AccountMarginMode.RETAIL_HEDGING): MarginMode.HEDGING,
}


def account_hash(login: int, server: str) -> str:
    return hashlib.sha256(f"{login}|{server}".encode()).hexdigest()


def parse_terminal(raw: Any, read_at: datetime) -> Mt5TerminalInfo:
    what = "terminal_info"
    ping = _attr(raw, "ping_last", what)
    return Mt5TerminalInfo(
        connected=_bool(raw, "connected", what),
        trade_allowed=_bool(raw, "trade_allowed", what),
        tradeapi_disabled=_bool(raw, "tradeapi_disabled", what),
        build=_int(raw, "build", what),
        ping_last_us=ping if isinstance(ping, int) and not isinstance(ping, bool) else None,
        read_at=read_at,
    )


def parse_account(raw: Any, read_at: datetime) -> Mt5Account:
    what = "account_info"
    digits = _int(raw, "currency_digits", what)
    trade_mode = _TRADE_MODES.get(_int(raw, "trade_mode", what))
    margin_mode = _MARGIN_MODES.get(_int(raw, "margin_mode", what))
    if trade_mode is None or margin_mode is None:
        raise _bad(what, "trade_mode/margin_mode")

    def money(name: str) -> Decimal:
        try:
            return money_from_float(_num(raw, name, what), digits)
        except ValueError:
            raise _bad(what, name) from None

    return Mt5Account(
        account_hash=account_hash(_int(raw, "login", what), _str(raw, "server", what)),
        trade_mode=trade_mode,
        margin_mode=margin_mode,
        currency=_str(raw, "currency", what),
        currency_digits=digits,
        balance=money("balance"),
        equity=money("equity"),
        margin=money("margin"),
        margin_free=money("margin_free"),
        trade_allowed=_bool(raw, "trade_allowed", what),
        trade_expert=_bool(raw, "trade_expert", what),
        read_at=read_at,
    )


def parse_symbol(raw: Any, symbol: str) -> Mt5SymbolSpec:
    what = f"symbol_info({symbol})"

    def positive(name: str) -> Decimal:
        value = _dec(_num(raw, name, what), what, name)
        if value <= 0:
            raise _bad(what, name)
        return value

    return Mt5SymbolSpec(
        symbol=symbol,
        trade_tick_size=positive("trade_tick_size"),
        trade_tick_value=positive("trade_tick_value"),
        point=positive("point"),
        digits=_int(raw, "digits", what),
        volume_min=positive("volume_min"),
        volume_step=positive("volume_step"),
        volume_max=positive("volume_max"),
        trade_mode=_int(raw, "trade_mode", what),
        filling_mode=_int(raw, "filling_mode", what),
        expiration_mode=_int(raw, "expiration_mode", what),
        trade_stops_level=_int(raw, "trade_stops_level", what),
        trade_freeze_level=_int(raw, "trade_freeze_level", what),
        trade_contract_size=positive("trade_contract_size"),
        visible=_bool(raw, "visible", what),
    )


def parse_tick(raw: Any, symbol: str, grid: Grid, received_at: datetime) -> Mt5Tick:
    what = f"symbol_info_tick({symbol})"
    msc = _attr(raw, "time_msc", what)
    server_time = (
        utc_from_msc(msc)
        if isinstance(msc, int) and not isinstance(msc, bool) and msc > 0
        else utc_from_epoch(_num(raw, "time", what))
    )
    return Mt5Tick(
        symbol=symbol,
        server_time=server_time,
        received_at=received_at,
        bid=_price(raw, "bid", grid, what),
        ask=_price(raw, "ask", grid, what),
        last=_price(raw, "last", grid, what),
    )


def parse_position(raw: Any, grid: Grid) -> Mt5Position:
    what = "positions_get"
    kind = _int(raw, "type", what)
    if kind == PositionType.BUY:
        side = Side.BUY
    elif kind == PositionType.SELL:
        side = Side.SELL
    else:
        raise _bad(what, "type")
    return Mt5Position(
        position_id=_int(raw, "identifier", what),
        position_ticket=_int(raw, "ticket", what),
        symbol=_str(raw, "symbol", what),
        side=side,
        volume=_volume(raw, "volume", grid, what),
        price_open=_price(raw, "price_open", grid, what),
        sl=_price(raw, "sl", grid, what),
        tp=_price(raw, "tp", grid, what),
        magic=_int(raw, "magic", what),
        comment=_str(raw, "comment", what),
        opened_at=utc_from_msc(_int(raw, "time_msc", what)),
        reason=_int(raw, "reason", what),
    )


def parse_order(raw: Any, grid: Grid, what: str = "orders_get") -> Mt5Order:
    done_msc = _attr(raw, "time_done_msc", what)
    expiration = _attr(raw, "time_expiration", what)
    return Mt5Order(
        ticket=_int(raw, "ticket", what),
        symbol=_str(raw, "symbol", what),
        order_type=_int(raw, "type", what),
        state=_int(raw, "state", what),
        volume_initial=_volume(raw, "volume_initial", grid, what),
        volume_current=_volume(raw, "volume_current", grid, what),
        price_open=_price(raw, "price_open", grid, what),
        sl=_price(raw, "sl", grid, what),
        tp=_price(raw, "tp", grid, what),
        magic=_int(raw, "magic", what),
        comment=_str(raw, "comment", what),
        position_id=_int(raw, "position_id", what),
        time_setup=utc_from_msc(_int(raw, "time_setup_msc", what)),
        time_done=utc_from_msc(done_msc) if isinstance(done_msc, int) and done_msc > 0 else None,
        expiration=(
            utc_from_epoch(expiration) if isinstance(expiration, int) and expiration > 0 else None
        ),
    )


def parse_deal(raw: Any, grid: Grid) -> Mt5Deal:
    what = "history_deals_get"
    return Mt5Deal(
        ticket=_int(raw, "ticket", what),
        order_ticket=_int(raw, "order", what),
        position_id=_int(raw, "position_id", what),
        symbol=_str(raw, "symbol", what),
        deal_type=_int(raw, "type", what),
        entry=_int(raw, "entry", what),
        volume=_volume(raw, "volume", grid, what),
        price=_price(raw, "price", grid, what),
        commission=_dec(_num(raw, "commission", what), what, "commission"),
        fee=_dec(_num(raw, "fee", what), what, "fee"),
        swap=_dec(_num(raw, "swap", what), what, "swap"),
        profit=_dec(_num(raw, "profit", what), what, "profit"),
        magic=_int(raw, "magic", what),
        reason=_int(raw, "reason", what),
        comment=_str(raw, "comment", what),
        time=utc_from_msc(_int(raw, "time_msc", what)),
    )


def parse_margin(raw: Any, what: str) -> Decimal:
    """`order_calc_margin` answer: a real, finite, positive number or a read error."""
    value = decimal_from_number(raw)
    if value is None or value <= 0:
        raise _bad(what, "margin")
    return value


def parse_check(raw: Any) -> tuple[int, str, Decimal, Decimal]:
    """`order_check` answer: ``(retcode, comment, margin, margin_free)``; any field wrong is an error."""
    what = "order_check"
    retcode = _int(raw, "retcode", what)
    margin = decimal_from_number(_attr(raw, "margin", what))
    free = decimal_from_number(_attr(raw, "margin_free", what))
    if margin is None:
        raise _bad(what, "margin")
    if free is None:
        raise _bad(what, "margin_free")
    return retcode, _str(raw, "comment", what), margin, free
