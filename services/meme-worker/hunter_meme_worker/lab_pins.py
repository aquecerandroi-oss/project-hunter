"""T4.16b: the Lab's own step over the pinned set — reload it every tick and
hand the tracker the whole truth, never a diff kept in memory.

Split out of ``lab.py`` for the 350-line budget: this is one call and one
``if``, but it is a whole reason the file exists (``lab.py``'s step 1).
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from hunter_core.db.session import role_session
from hunter_meme_worker.tracker_pins import pinned_mints

if TYPE_CHECKING:
    from hunter_meme_worker.lab import LabContext

__all__ = ["reload_pinned_mints"]

WORKER_ROLE = "hunter_worker"


async def reload_pinned_mints(ctx: LabContext, *, now: datetime) -> int:
    """Read the durable pinned set and replace the tracker's wholesale.

    ``ctx.tracker`` is ``None`` for a Lab context built without the radar's
    tracker (every unit test in this package, and a heartbeat-only context
    written while the Lab itself is disabled, ``main.py``) — a no-op then,
    never a crash.
    """
    if ctx.tracker is None:
        return 0
    async with role_session(ctx.session_factory, db_role=WORKER_ROLE) as session:
        pinned = await pinned_mints(session, now=now)
    ctx.tracker.set_pinned(pinned)
    return len(pinned)
