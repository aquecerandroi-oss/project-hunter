"""The tracking-slot state machine — SHADOW-LAB.md "Decisão conjunta" §4.

One slot is one ``(strategy_version_id, market_id, cohort)`` row of
``shadow_episodes``. This module is the *pure* half: given what the slot holds
and what the strategy said about one bar, what happens. The transaction, the
row lock and the writes live in :mod:`.slots`.

The whole point is that ``decision is None`` is not one thing. S1 splits it
(``EvaluationState``) and the slot reads it as:

- ``triggered`` — decide, but only if the slot is armed *and* not already
  tracking. One tracking per slot, ever;
- ``not_triggered`` — the only proof that the entry condition was false, and
  therefore the only thing that re-arms a slot whose previous tracking ended;
- ``rejected`` — the condition held and the decision was refused (geometry).
  Not a false condition: it must not re-arm;
- ``unavailable`` / ``ineligible`` — nothing was proven either way. No re-arm,
  no decision, and the checkpoint does not move: a bar this worker could not
  evaluate is not a bar it evaluated.
"""

from __future__ import annotations

from dataclasses import dataclass

from hunter_core.strategies.base import EvaluationState

__all__ = ["SlotState", "SlotTransition", "next_slot"]

_EVALUATED = frozenset(
    {EvaluationState.TRIGGERED, EvaluationState.NOT_TRIGGERED, EvaluationState.REJECTED}
)


@dataclass(frozen=True, slots=True)
class SlotState:
    """What the durable slot holds right now."""

    armed: bool
    tracking_open: bool
    """``shadow_episodes.open_outcome_signal_id IS NOT NULL``."""


@dataclass(frozen=True, slots=True)
class SlotTransition:
    """What the worker must do with this bar."""

    decide: bool
    armed: bool
    advance_checkpoint: bool


def next_slot(slot: SlotState, state: EvaluationState) -> SlotTransition:
    """The slot after one evaluated bar."""
    if state not in _EVALUATED:
        return SlotTransition(decide=False, armed=slot.armed, advance_checkpoint=False)
    if state is EvaluationState.NOT_TRIGGERED:
        rearmed = slot.armed or not slot.tracking_open
        return SlotTransition(decide=False, armed=rearmed, advance_checkpoint=True)
    if state is EvaluationState.REJECTED:
        return SlotTransition(decide=False, armed=slot.armed, advance_checkpoint=True)
    decide = slot.armed and not slot.tracking_open
    return SlotTransition(
        decide=decide, armed=False if decide else slot.armed, advance_checkpoint=True
    )
