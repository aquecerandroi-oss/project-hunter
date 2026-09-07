"""Reading a position's protections: the watermark, the geometry, what is due.

Split out of :mod:`hunter_execution_worker.protection` along the line the T3.4
notes already drew between ``tape`` and ``triggers``: this module answers *what
the protections of this position look like and which of them get an attempt*;
``protection`` answers *what an attempt does*.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field

from hunter_core.domain.enums import ExitIntentState
from hunter_core.execution.intents import ExitIntent
from hunter_core.execution.triggers import ProtectedPosition, TriggerEvaluation
from hunter_execution_worker.positions import OpenPositionRow

__all__ = ["MANUAL_KEY", "STOP_KEY", "TriggerWatermarks", "due", "fired_key", "protected"]

MANUAL_KEY = "manual"
STOP_KEY = "stop"


@dataclass
class TriggerWatermarks:
    """The last trade id already reported per market, kept in memory.

    Deliberately **not** durable: losing it on a restart can only cause a
    crossing to be evaluated again, and an extra evaluation cannot sell an extra
    unit — the quantity is allocated under the lock from what the position and
    the intention still hold (notes-T3.4.md §10.1). A durable watermark would be
    a second source of truth about a protection, and the first time it disagreed
    with the intention nobody would know which one to believe.
    """

    seen: dict[uuid.UUID, int] = field(default_factory=lambda: {})

    def get(self, market_id: uuid.UUID) -> int | None:
        return self.seen.get(market_id)

    def advance(self, market_id: uuid.UUID, accepted: int | None) -> None:
        if accepted is None:
            return
        current = self.seen.get(market_id)
        if current is None or accepted > current:
            self.seen[market_id] = accepted


def protected(position: OpenPositionRow, intents: tuple[ExitIntent, ...]) -> ProtectedPosition:
    """The position as the trigger reader sees it: one stop, N targets."""
    stop = next(
        (i.trigger_price for i in intents if i.protection_key == STOP_KEY and i.trigger_price),
        None,
    )
    targets = tuple(
        sorted(
            i.trigger_price
            for i in intents
            if i.protection_key.startswith("target") and i.trigger_price is not None
        )
    )
    return ProtectedPosition(
        position_id=position.position_id, qty=position.qty, stop_price=stop, target_prices=targets
    )


def fired_key(evaluation: TriggerEvaluation) -> str | None:
    if evaluation.state != "triggered":
        return None
    if evaluation.kind == "stop":
        return STOP_KEY
    return f"target:{(evaluation.target_index or 0) + 1}"


def due(intent: ExitIntent, fired: str | None, pending_stop: bool) -> bool:
    """Does this intention get an attempt in this cycle?

    An intention is attempted when its protection just fired, when it is a
    manual close (which *is* the decision), when it fired earlier and is still
    degraded, or when the verdict carries a stop seen behind the one published.

    **Never when what is left is untradable dust.** ``blocked_residual`` is the
    schema's word for "the exchange will not take this quantity" (DATABASE.md
    §18.4): retrying it produces one rejected ``orders`` row per cycle, for ever,
    for a quantity that cannot be sold at any price. The residual stays
    accounted and visible on the position; it is simply not attempted again
    until something makes it sellable.
    """
    if intent.state is ExitIntentState.BLOCKED_RESIDUAL:
        return False
    if intent.protection_key == fired:
        return True
    if intent.protection_key == MANUAL_KEY:
        return True
    if intent.degraded_since is not None:
        return True
    return pending_stop and intent.protection_key == STOP_KEY
