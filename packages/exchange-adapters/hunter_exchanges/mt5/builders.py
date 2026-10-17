"""Builders of the vendor ``MqlTradeRequest`` dicts — the only place a ``Decimal`` becomes a ``float``.

Every price, level and volume goes through :func:`~hunter_exchanges.mt5.convert.to_float_on_grid`:
a value off its grid is refused (:class:`~hunter_exchanges.mt5.errors.Mt5NotSent`), never rounded
on the way out. A SLTP request carries exactly the fields of contract §5.1 and nothing else.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from .constants import OrderType, TimeMode, TradeAction
from .convert import OffGridError, epoch_from_utc, to_float_on_grid
from .errors import Mt5NotSent
from .models import EntryKind, EntryRequest, Mt5SymbolSpec, Side, SltpRequest


def _grid(value: Decimal, step: Decimal, reason: str) -> float:
    try:
        return to_float_on_grid(value, step)
    except OffGridError as exc:
        raise Mt5NotSent(reason, str(exc)) from None


def order_type_for(request: EntryRequest) -> OrderType:
    buy = request.side is Side.BUY
    if request.kind is EntryKind.MARKET:
        return OrderType.BUY if buy else OrderType.SELL
    return OrderType.BUY_LIMIT if buy else OrderType.SELL_LIMIT


def build_entry_request(request: EntryRequest, spec: Mt5SymbolSpec) -> dict[str, Any]:
    """`TRADE_ACTION_DEAL` (market) or `TRADE_ACTION_PENDING` (limit) with `sl`/`tp` attached."""
    tick = spec.trade_tick_size
    if request.volume < spec.volume_min or request.volume > spec.volume_max:
        raise Mt5NotSent("volume_out_of_range", f"{request.volume}")
    body: dict[str, Any] = {
        "action": int(
            TradeAction.DEAL if request.kind is EntryKind.MARKET else TradeAction.PENDING
        ),
        "symbol": request.symbol,
        "volume": _grid(request.volume, spec.volume_step, "volume_off_step"),
        "type": int(order_type_for(request)),
        "price": _grid(request.price, tick, "price_off_tick"),
        "sl": _grid(request.sl, tick, "sl_off_tick"),
        "tp": _grid(request.tp, tick, "tp_off_tick"),
        "magic": request.magic,
        "comment": request.comment,
        "type_filling": int(request.filling),
        "type_time": int(request.time_in_force),
    }
    if request.kind is EntryKind.MARKET:
        body["deviation"] = request.deviation_points
    if request.time_in_force in (TimeMode.SPECIFIED, TimeMode.SPECIFIED_DAY):
        assert request.expiration is not None  # enforced by the model
        body["expiration"] = epoch_from_utc(request.expiration)
    return body


def build_sltp_request(request: SltpRequest, spec: Mt5SymbolSpec) -> dict[str, Any]:
    """`TRADE_ACTION_SLTP`: symbol, position ticket, levels, magic. Nothing else (§5.1)."""
    tick = spec.trade_tick_size
    return {
        "action": int(TradeAction.SLTP),
        "symbol": request.symbol,
        "position": request.position_ticket,
        "sl": _grid(request.sl, tick, "sl_off_tick"),
        "tp": _grid(request.tp, tick, "tp_off_tick"),
        "magic": request.magic,
    }


def build_cancel_request(ticket: int) -> dict[str, Any]:
    """`TRADE_ACTION_REMOVE` needs only the order ticket."""
    return {"action": int(TradeAction.REMOVE), "order": ticket}
