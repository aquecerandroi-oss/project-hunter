"""Boot-time warm-up of the tracked set — split out of ``main.py`` for the
350-line budget.

A restart is not a reset (Astra's MUST-FIX 3): the tracked set is rebuilt
from ``meme_tokens`` before any loop starts, capped and windowed the way it
always is (``repo.load_tracked``). Since T4.16b the pinned mints — an open
paper bet, an open live position or a pending proposal — are loaded on top of
that, by identity rather than recency (``repo.load_tracked_by_mint``): a real
position older than ``track_window_minutes`` or simply not among the
youngest ``tracked_max`` is not optional inventory, and a restart must not be
the thing that stops photographing it.
"""

from __future__ import annotations

from datetime import timedelta
from typing import TYPE_CHECKING

from hunter_core.db.session import role_session
from hunter_core.domain.types import utcnow
from hunter_meme_worker.metrics import meme_tracked_mints
from hunter_meme_worker.repo import load_tracked, load_tracked_by_mint
from hunter_meme_worker.tracker_pins import pinned_mints

if TYPE_CHECKING:
    from hunter_meme_worker.context import RadarContext

__all__ = ["warm_tracked_set"]

WORKER_ROLE = "hunter_worker"


async def warm_tracked_set(ctx: RadarContext) -> int:
    """Rebuild the tracked set from the database before any loop starts."""
    now = utcnow()
    cutoff = now - timedelta(minutes=ctx.config.track_window_minutes)
    async with role_session(ctx.session_factory, db_role=WORKER_ROLE) as session:
        tracked = await load_tracked(session, cutoff=cutoff, cap=ctx.config.tracked_max)
        pinned = await pinned_mints(session, now=now)
        missing = sorted(pinned - {t.mint for t in tracked})
        rescued = await load_tracked_by_mint(session, mints=missing)
    for mint in (*tracked, *rescued):
        ctx.tracker.observe(mint)
    ctx.tracker.pin(pinned)
    meme_tracked_mints.set(len(ctx.tracker))
    return len(tracked) + len(rescued)
