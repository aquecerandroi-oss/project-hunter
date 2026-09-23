"""T4.90b — a confirmed sell's fill as ``meme_live_orders.fill`` holds it, read
back typed.

``PostgresOrderJournal.record_state`` writes the decoded fill as JSON
(``FillRecord.as_json`` / ``PumpSwapFillRecord.as_json``); a replay, a restart or
the orphan repair gets that JSON back, which ``isinstance(FillRecord)`` rightly
refuses. This is the parse the settlement needs instead of the check: the few
numbers a close uses, each with its type proven, and the venue the payload
names matching the venue of the ORDER it belongs to. Anything else is ``None``
— never a fill guessed from a loose dict.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Any, cast

__all__ = ["CURVE", "PUMPSWAP", "StoredSellFill", "order_venue", "parse_stored_sell_fill"]

CURVE = "curve"
PUMPSWAP = "pumpswap"


def order_venue(intent: Mapping[str, Any]) -> str:
    """The venue an order was SENT to, from its own ``intent``: a PumpSwap sell
    writes ``venue: pumpswap`` (``BuiltPumpSwapSell.intent_json``); a curve one
    writes no venue. Never the position's venue today (T4.90 audit)."""
    return PUMPSWAP if intent.get("venue") == PUMPSWAP else CURVE


@dataclass(frozen=True, slots=True)
class StoredSellFill:
    venue: str
    signature: str
    block_time: datetime | None
    sell_net_lamports: int
    ata_rent_refund_lamports: int | None
    payload: Mapping[str, Any]

    def as_json(self) -> dict[str, Any]:
        return {**self.payload, "settled_from": "stored_fill"}


def _is_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _block_time(value: object) -> tuple[bool, datetime | None]:
    if value is None:
        return True, None
    if not isinstance(value, str):
        return False, None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return False, None
    return parsed.tzinfo is not None, parsed


def parse_stored_sell_fill(raw: object, *, venue: str) -> StoredSellFill | None:
    """``None`` unless ``raw`` is a sell fill of ``venue`` with every number a close uses."""
    if not isinstance(raw, dict):
        return None
    data = cast(dict[str, Any], raw)
    if (PUMPSWAP if data.get("venue") == PUMPSWAP else CURVE) != venue:
        return None
    if venue == CURVE and data.get("is_buy") is not False:
        return None  # a curve fill names its side; a buy is not a sell
    signature, net = data.get("signature"), data.get("sell_net_lamports")
    refund = data.get("ata_rent_refund_lamports")
    if not isinstance(signature, str) or not signature or not _is_int(net):
        return None
    if refund is not None and not _is_int(refund):
        return None
    ok, block_time = _block_time(data.get("block_time"))
    if not ok:
        return None
    return StoredSellFill(
        venue=venue,
        signature=signature,
        block_time=block_time,
        sell_net_lamports=cast(int, net),
        ata_rent_refund_lamports=cast(int | None, refund),
        payload=dict(data),
    )
