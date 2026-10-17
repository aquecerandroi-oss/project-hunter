"""What the copy lane needs from chain **history** (H-037, R2 fix B2/F8) — the hook the source side (task
A) is asked to provide. The lane never reads the chain's past itself: it asks this protocol, and treats
"cannot" as the fail-closed answer.

Two questions, both bounded (at most ``limit`` signatures per wallet):

* :meth:`LeaderHistory.window` — *what did this leader buy inside a hole we could not see?* The answer is
  the set of mints whose balance went up in ``[start, end)``. It is what makes the next buy of such a mint
  **not** "the first" (a leader that bought and zeroed a mint during a disconnection must not look fresh
  afterwards).
* :meth:`LeaderHistory.mint_trace` — *where is this leader's position in a mint we hold, and how high did it
  get since ``since``?* It re-reads a surviving copy's leader position and peak after a hole or a restart.

``None`` / ``complete=False`` mean "could not read": the leader stays without new entries (``window``) or
the copy's leader-driven exit stays censored by name (``mint_trace``). Never a guessed answer.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from datetime import datetime

__all__ = ["SIGNATURE_CAP", "LeaderHistory", "MintTrace", "WindowTrace"]

SIGNATURE_CAP = 1000
"""At most this many signatures are read per wallet and window; past it the answer is incomplete."""


@dataclass(frozen=True, slots=True)
class WindowTrace:
    complete: bool
    """``False`` = the cap was hit or the node failed before the window was covered."""
    bought_mints: frozenset[str]
    """Mints whose token balance increased in the window, as far as it was read."""


@dataclass(frozen=True, slots=True)
class MintTrace:
    current_atoms: int
    """The leader's token balance in the mint now."""
    peak_atoms: int
    """The highest balance it showed in the mint since ``since`` (never below ``current_atoms``)."""


class LeaderHistory(Protocol):
    async def window(
        self, wallet: str, start: datetime, end: datetime, *, limit: int = SIGNATURE_CAP
    ) -> WindowTrace: ...

    async def mint_trace(self, wallet: str, mint: str, since: datetime) -> MintTrace | None: ...
