"""T4.67b — the 2 s fallback tick for launch positions.

A launch position lives seconds (``time_stop_s`` 6, EXP-M18). The event path
(``event_exits.py``) judges it on every trade of its curve; but a curve nobody
trades sends no frame, and the time stop still has to fire. The desk's tick
(``exits_once``, ``mark_s``) covers it too, at 5–10 s — too slow for a 6 s
stop. This loop runs :func:`exits.manage_position` for the launch positions
only, every :data:`LAUNCH_EXIT_TICK_S`, through the same per-position lock, so
the three paths (event, this tick, the desk's tick) never both sell.
"""

from __future__ import annotations

from hunter_core.db.session import role_session
from hunter_core.domain.types import utcnow
from hunter_meme_executor.context import ExecutorContext
from hunter_meme_executor.exit_common import is_launch_position
from hunter_meme_executor.exits import manage_position
from hunter_meme_executor.journal_db import WORKER_ROLE
from hunter_meme_executor.repo import OpenPosition, open_positions

__all__ = ["launch_exits_once", "launch_positions"]


def launch_positions(positions: list[OpenPosition]) -> list[OpenPosition]:
    return [p for p in positions if is_launch_position(p.params)]


async def launch_exits_once(ctx: ExecutorContext) -> None:
    """One pass over the open launch positions (nothing to do with none open)."""
    async with role_session(ctx.session_factory, db_role=WORKER_ROLE) as session:
        positions = launch_positions(await open_positions(session))
    now = utcnow()
    for position in positions:
        await manage_position(ctx, position, now=now)
