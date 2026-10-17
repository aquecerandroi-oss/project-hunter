"""Small builders for the MT5 models used across the MT5 test files (labelled test data)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from hunter_exchanges.mt5.constants import Filling, SymbolTradeMode, TimeMode
from hunter_exchanges.mt5.models import (
    EntryKind,
    EntryRequest,
    Mt5Position,
    Mt5SymbolSpec,
    Side,
    SltpRequest,
)

SYMBOL = "WINZ26"
MAGIC = 7_000_001
T0 = datetime(2026, 11, 4, 13, 0, 0, tzinfo=UTC)


def spec(**over: Any) -> Mt5SymbolSpec:
    base: dict[str, Any] = {
        "symbol": SYMBOL,
        "trade_tick_size": Decimal("5"),
        "trade_tick_value": Decimal("1"),
        "point": Decimal("1"),
        "digits": 0,
        "volume_min": Decimal("1"),
        "volume_step": Decimal("1"),
        "volume_max": Decimal("1000"),
        "trade_mode": int(SymbolTradeMode.FULL),
        "filling_mode": 3,
        "expiration_mode": 15,
        "trade_stops_level": 0,
        "trade_freeze_level": 0,
        "trade_contract_size": Decimal("0.2"),
        "visible": True,
    }
    return Mt5SymbolSpec(**{**base, **over})


def position(**over: Any) -> Mt5Position:
    base: dict[str, Any] = {
        "position_id": 5001,
        "position_ticket": 5001,
        "symbol": SYMBOL,
        "side": Side.BUY,
        "volume": Decimal("1"),
        "price_open": Decimal("130500"),
        "sl": Decimal("130000"),
        "tp": Decimal("0"),
        "magic": MAGIC,
        "comment": "HBTESTTESTTESTTES",
        "opened_at": T0,
        "reason": 3,
    }
    return Mt5Position(**{**base, **over})


def entry(**over: Any) -> EntryRequest:
    base: dict[str, Any] = {
        "symbol": SYMBOL,
        "side": Side.BUY,
        "kind": EntryKind.LIMIT,
        "volume": Decimal("1"),
        "price": Decimal("130505"),
        "sl": Decimal("130000"),
        "tp": Decimal("0"),
        "magic": MAGIC,
        "comment": "HBTESTTESTTESTTES",
        "filling": Filling.IOC,
        "time_in_force": TimeMode.DAY,
    }
    return EntryRequest(**{**base, **over})


def sltp(**over: Any) -> SltpRequest:
    base: dict[str, Any] = {
        "sltp_request_id": uuid.UUID("018f0000-0000-7000-8000-000000000001"),
        "symbol": SYMBOL,
        "position_ticket": 5001,
        "sl": Decimal("130100"),
        "tp": Decimal("0"),
        "magic": MAGIC,
        "floor_sl": Decimal("130000"),
    }
    return SltpRequest(**{**base, **over})
