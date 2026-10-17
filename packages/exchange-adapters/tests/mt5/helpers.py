"""Helpers for the contract suite: requests built from the live quote, so they fit any symbol."""

from __future__ import annotations

import uuid
from decimal import Decimal
from typing import Any

from hunter_exchanges.mt5.constants import Filling, TimeMode
from hunter_exchanges.mt5.models import (
    EntryKind,
    EntryRequest,
    Mt5Position,
    SendOutcome,
    Side,
    SltpRequest,
)
from hunter_exchanges.mt5.retcodes import Verdict

from .conftest import Env
from .factories import MAGIC


def comment_for(n: int) -> str:
    return "HB" + str(n).zfill(16)


async def touch(env: Env) -> tuple[Decimal, Decimal]:
    tick = await env.port.tick(env.symbol)
    return tick.bid, tick.ask


def entry_request(env: Env, price: Decimal, sl: Decimal, **over: Any) -> EntryRequest:
    base: dict[str, Any] = {
        "symbol": env.symbol,
        "side": Side.BUY,
        "kind": EntryKind.LIMIT,
        "volume": Decimal(1),
        "price": price,
        "sl": sl,
        "tp": Decimal(0),
        "magic": MAGIC,
        "comment": comment_for(1),
        "filling": Filling.IOC,
        "time_in_force": TimeMode.DAY,
    }
    return EntryRequest(**{**base, **over})


def sltp_request(env: Env, position: Mt5Position, sl: Decimal, **over: Any) -> SltpRequest:
    base: dict[str, Any] = {
        "sltp_request_id": uuid.uuid4(),
        "symbol": env.symbol,
        "position_ticket": position.position_ticket,
        "sl": sl,
        "tp": Decimal(0),
        "magic": MAGIC,
        "floor_sl": position.sl if position.sl != 0 else sl,
    }
    return SltpRequest(**{**base, **over})


async def open_long(env: Env, *, volume: int = 1, stop_ticks: int = 100) -> Mt5Position:
    """A marketable limit buy at the ask: fills at once on the fake (and on a demo in session)."""
    bid, ask = await touch(env)
    request = entry_request(env, ask, bid - stop_ticks * env.tick_size, volume=Decimal(volume))
    outcome: SendOutcome = await env.port.send_entry(request)
    assert outcome.verdict in (Verdict.DONE, Verdict.PARTIAL), outcome
    positions = await env.port.positions(env.symbol)
    assert len(positions) == 1
    return positions[0]
