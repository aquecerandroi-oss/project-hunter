"""What the copy book holds per copy and returns per event (H-037) — plain data, split out of
``copy_book.py`` for the 350-line budget."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Literal

from hunter_meme_worker.copy_events import Job

if TYPE_CHECKING:
    from datetime import datetime

    from hunter_meme_worker.lab_models import BetState

__all__ = ["Decision", "Live", "Position", "State"]

State = Literal["opening", "open", "closing"]


@dataclass(slots=True)
class Position:
    """One copy the book knows about, from the instant it was decided until it is closed."""

    key: str
    leader: str
    stratum: str
    mint: str
    opened_by: datetime
    """The leader's ``observed_at`` on the buy that opened this copy."""
    decided_at: datetime
    peak_atoms: int
    state: State = "opening"
    entry_at: datetime | None = None
    bet_id: str | None = None
    gap_reason: str | None = None
    """A censor reason once the book can no longer vouch for the leader's exit (a gap, a restart)."""
    was: State = "opening"
    """The state to go back to when a close job is refused by the queue."""


@dataclass(slots=True)
class Decision:
    """What one event produced: jobs for the executor, or the named reason nothing was done."""

    jobs: list[Job] = field(default_factory=list[Job])
    skipped: str | None = None
    wallet_known: bool = True


@dataclass(slots=True)
class Live:
    """A copy open in the database: the row and the state its marks and exits are priced from."""

    bet_id: str
    state: BetState
    leader: str
    last_slot: int
    """The slot of the last chain state this copy accepted (its entry, then every mark): an exit never
    prices a state below it — the design's non-regression rule."""
