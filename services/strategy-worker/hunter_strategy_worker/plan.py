"""Choosing the entry bar — SHADOW-LAB.md "Decisão conjunta" §3.

The hypothetical entry is the open of the **first 1-minute bar whose open is
strictly after** ``decision_at``, and both the chosen bar and the decision must
be persisted *before* that open. Two independent ways to fail that contract,
each producing ``no_entry: late`` and never a retroactive entry:

- the reference bar is too far behind (``entry_bar_open - source_bar_close >
  max_entry_delay_s``): 12:00 / 12:05:02 / 12:06 is late at 360 s;
- the clock is already at or past the chosen open when the row is about to be
  written (the "commit that misses the open").

The bar is never re-chosen with a later clock: that would be look-ahead with
extra steps, since by then the outcome of the first minute is already known.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum
from typing import TYPE_CHECKING

from hunter_core.domain.types import ensure_utc

if TYPE_CHECKING:
    from hunter_core.strategies.envelope import AssumedCosts

_MINUTE = timedelta(minutes=1)

__all__ = ["EntryPlan", "LateReason", "next_minute_open", "plan_entry"]


class LateReason(StrEnum):
    """Why an entry never happened. Persisted verbatim in ``no_entry_reason``."""

    DELAY = "late:delay"
    """The chosen open is further from the reference close than the frozen
    ``max_entry_delay_s`` allows."""
    MISSED_OPEN = "late:missed_open"
    """The decision was not durable before the open it had chosen."""
    UNCONFIRMED = "late:unconfirmed"
    """The row is durable, but nothing proves it was durable *before* the open
    (the process died between the commit and its confirmation). Conservative on
    purpose: a lost entry is a countable loss, a retroactive one is a lie."""


def next_minute_open(after: datetime) -> datetime:
    """The first 1m bar open strictly after ``after`` (UTC)."""
    aware = ensure_utc(after)
    floored = aware.replace(second=0, microsecond=0)
    return floored + _MINUTE


@dataclass(frozen=True, slots=True)
class EntryPlan:
    """The frozen entry intent, written to ``signal_outcomes.meta.entry_plan``."""

    source_bar_close: datetime
    decision_at: datetime
    entry_bar_open: datetime
    delay_s: int
    max_entry_delay_s: int
    late_reason: LateReason | None

    @property
    def deadline(self) -> datetime:
        """The instant the decision must already be durable by."""
        return self.entry_bar_open

    def to_jsonable(self) -> dict[str, str | int | None]:
        """The plan as it is persisted — timestamps ISO-8601 UTC."""
        return {
            "source_bar_close": self.source_bar_close.isoformat(),
            "decision_at": self.decision_at.isoformat(),
            "entry_bar_open": self.entry_bar_open.isoformat(),
            "delay_s": self.delay_s,
            "max_entry_delay_s": self.max_entry_delay_s,
            "late_reason": self.late_reason.value if self.late_reason else None,
        }


def plan_entry(
    *,
    source_bar_close: datetime,
    decision_at: datetime,
    costs: AssumedCosts,
    now: datetime,
) -> EntryPlan:
    """Pick the entry bar and say, already, whether it can still be honoured."""
    reference = ensure_utc(source_bar_close)
    decided = ensure_utc(decision_at)
    clock = ensure_utc(now)
    entry_bar_open = next_minute_open(decided)
    delay_s = int((entry_bar_open - reference).total_seconds())
    reason: LateReason | None = None
    if delay_s > costs.max_entry_delay_s:
        reason = LateReason.DELAY
    elif clock >= entry_bar_open:
        reason = LateReason.MISSED_OPEN
    return EntryPlan(
        source_bar_close=reference,
        decision_at=decided,
        entry_bar_open=entry_bar_open,
        delay_s=delay_s,
        max_entry_delay_s=costs.max_entry_delay_s,
        late_reason=reason,
    )
