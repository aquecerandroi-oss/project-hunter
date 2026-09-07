"""Reading a position's protections: the watermark, the geometry, what is due.

Split out of :mod:`hunter_execution_worker.protection` along the line the T3.4
notes already drew between ``tape`` and ``triggers``: this module answers *what
the protections of this position look like and which of them get an attempt*;
``protection`` answers *what an attempt does*.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from hunter_core.domain.enums import ExitIntentState
from hunter_core.execution.intents import ExitIntent
from hunter_core.execution.triggers import ProtectedPosition, TriggerEvaluation
from hunter_execution_worker.positions import OpenPositionRow

__all__ = [
    "BACKOFF_MAX_S",
    "BACKOFF_START_S",
    "MANUAL_KEY",
    "STOP_KEY",
    "DegradedRetries",
    "TriggerWatermarks",
    "due",
    "fired_key",
    "protected",
]

MANUAL_KEY = "manual"
STOP_KEY = "stop"

BACKOFF_START_S = 1.0
"""The first retry of a degraded protection is one cycle later — no slower.

A stop that fired and found no book is *late*, and being late is the only
failure of a paper wallet that destroys information. The first retry must
therefore be immediate; what may not stay immediate is the thousandth."""

BACKOFF_MAX_S = 60.0
"""The ceiling. Doubling from 1 s reaches it in six refusals (~63 s of tape).

Before this, a degraded protection wrote one refused ``orders`` row **per
second, for ever** — 86.400 a day for one stop the market cannot fill — and
``intents_repo._applied_attempts`` rebuilt a UNION over every one of them on
every cycle, so the cost of being late grew quadratically with how late it was
(review of ``7ecafd2``, item 5). One minute is short enough that a book which
came back is used within a minute, and bounded enough that a market that never
comes back costs 1.440 rows a day instead of 86.400."""


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


@dataclass
class DegradedRetries:
    """When each degraded protection may be attempted again, kept in memory.

    Deliberately **not** durable, for the same reason as
    :class:`TriggerWatermarks`: losing it on a restart can only make a retry
    happen *earlier*, and an early retry cannot sell an extra unit — the
    quantity is allocated under the lock from what the position and the
    intention still hold. A durable backoff would be a second source of truth
    about a protection nobody could reconcile with the intention.
    """

    next_at: dict[uuid.UUID, datetime] = field(default_factory=lambda: {})
    delay_s: dict[uuid.UUID, float] = field(default_factory=lambda: {})

    def ready(self, intent_id: uuid.UUID, now: datetime) -> bool:
        """May this degraded intention be attempted at ``now``?"""
        due_at = self.next_at.get(intent_id)
        return due_at is None or now >= due_at

    def defer(self, intent_id: uuid.UUID, now: datetime) -> float:
        """Record one more refusal and return the delay until the next attempt."""
        current = self.delay_s.get(intent_id)
        delay = BACKOFF_START_S if current is None else min(current * 2, BACKOFF_MAX_S)
        self.delay_s[intent_id] = delay
        self.next_at[intent_id] = now + timedelta(seconds=delay)
        return delay

    def clear(self, intent_id: uuid.UUID) -> None:
        """The protection filled (or is gone): the backoff has nothing to hold."""
        self.next_at.pop(intent_id, None)
        self.delay_s.pop(intent_id, None)


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
