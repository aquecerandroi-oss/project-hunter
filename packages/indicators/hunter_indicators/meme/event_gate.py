"""The event gate (T4.26, EXP-M8): refuse a mint with no confirmed "may pump"
announcement behind it — the one criterion ``event_v0/1`` exists to test.

Cross-cutting like :mod:`hunter_indicators.meme.pedigree` and
:mod:`hunter_indicators.meme.identity`: a set opts in with
``require_event: true`` (``lab_models.RuleSetSpec``); every other set never
asks, so it never refuses over an event.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Final

__all__ = ["ALLOWED_EVENT_KINDS", "NO_EVENT", "EventFeatures", "evaluate_event_gate"]

NO_EVENT: Final = "no_event"

ALLOWED_EVENT_KINDS: Final = ("public_figure_launch", "exchange_listing", "brand_launch")
"""EXP-M8's own three: the announcement kinds the $TRUMP case's shape names —
a public figure, an exchange or a brand naming a coin. ``viral_post``,
``narrative`` and ``incident`` (``meme_events.kind``'s other three) do not
qualify a proposal here; they are still recorded and still visible in
``reasons``, just not enough for ``event_v0/1`` to buy on."""


@dataclass(frozen=True, slots=True)
class EventFeatures:
    """The matched event at proposal time, if any. ``None`` on every field
    means no ``meme_events`` row named this mint — the overwhelming majority."""

    kind: str | None
    confidence: str | None
    title: str | None = None
    source: str | None = None
    observed_at: datetime | None = None


def evaluate_event_gate(features: EventFeatures, *, require_event: bool) -> tuple[str, ...]:
    """Off by default. On, refuses :data:`NO_EVENT` unless the matched event is
    ``confirmed`` and one of :data:`ALLOWED_EVENT_KINDS` — a ``rumor`` or a
    ``reported`` mirror is not enough, and neither is a ``viral_post``."""
    if not require_event:
        return ()
    if features.confidence == "confirmed" and features.kind in ALLOWED_EVENT_KINDS:
        return ()
    return (NO_EVENT,)
