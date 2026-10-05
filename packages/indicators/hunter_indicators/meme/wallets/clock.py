"""Slot ↔ instant, carried in the context (the engine never reads a wall clock).

:class:`NominalClock` is a **declared nominal clock**, not a guaranteed bound
(Astra, wallets-engine-design): ``block_time`` is whole seconds and real slots
run 0.4–0.5 s, so extrapolating at 0.4 s/slot can land before or after the true
instant. A caller with a measured slot→time map passes its own
:class:`SlotClock`; the nightly job is expected to anchor on the trigger's own
``(slot, block_time)`` as :meth:`NominalClock.anchored_on` does.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import ROUND_CEILING, Decimal, localcontext
from typing import Protocol

from hunter_core.strategies.numeric import CONTEXT

__all__ = ["NominalClock", "SlotClock"]


class SlotClock(Protocol):
    def instant(self, slot: int) -> datetime: ...

    def first_slot_at_or_after(self, instant: datetime) -> int: ...


@dataclass(frozen=True, slots=True)
class NominalClock:
    anchor_slot: int
    anchor_time: datetime
    slot_seconds: Decimal = Decimal("0.4")

    @classmethod
    def anchored_on(cls, slot: int, time: datetime, slot_seconds: Decimal) -> NominalClock:
        return cls(slot, time, slot_seconds)

    def instant(self, slot: int) -> datetime:
        with localcontext(CONTEXT):
            delta = Decimal(slot - self.anchor_slot) * self.slot_seconds
        return self.anchor_time + timedelta(seconds=float(delta))

    def first_slot_at_or_after(self, instant: datetime) -> int:
        seconds = Decimal(str((instant - self.anchor_time).total_seconds()))
        with localcontext(CONTEXT):
            steps = (seconds / self.slot_seconds).to_integral_value(rounding=ROUND_CEILING)
        return self.anchor_slot + int(steps)
