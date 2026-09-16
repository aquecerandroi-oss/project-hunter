"""The per-minute event ↔ mint matching job (T4.26): "who announced it, and
does a coin exist yet" is a fact the worker keeps current, not something a
human has to notice.

One task, ``forever``'s own shape (``main.py``'s wiring), always on while the
radar is — the query is bounded and savepoint-guarded
(``events_repo.match_events_once``), so it costs nothing extra to leave it
running the way ``retention``/``heartbeat`` already do without their own
switch.
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Final

from hunter_core.db.session import role_session
from hunter_core.domain.types import utcnow
from hunter_core.logging import get_logger
from hunter_meme_worker.events_repo import count_events, link_proposals, match_events_once

if TYPE_CHECKING:
    from hunter_meme_worker.context import RadarContext

__all__ = ["EVENTS_MATCH_CYCLE_S", "WORKER_ROLE", "events_match_once", "spawn_events_match"]

logger = get_logger(__name__)

WORKER_ROLE: Final = "hunter_worker"
EVENTS_MATCH_CYCLE_S: Final = 60.0
"""Once a minute (the brief's own cadence) — plenty next to the query's
sub-second plan over a table of a handful of rows a day."""


async def events_match_once(ctx: RadarContext) -> None:
    now = utcnow()
    async with role_session(ctx.session_factory, db_role=WORKER_ROLE) as session:
        matched = await match_events_once(session, now=now)
        linked = await link_proposals(session, matched) if matched else 0
        counts = await count_events(session, now=now)
    if matched:
        logger.info("meme_events_matched", count=len(matched), proposals_linked=linked)
    logger.debug("meme_events_tick", events_open=counts.open, events_matched_1h=counts.matched_1h)


def spawn_events_match(group: asyncio.TaskGroup, ctx: RadarContext) -> None:
    """One task, ``main.py``'s wiring (the ``spawn_creator_watch`` shape)."""
    from hunter_meme_worker.collect import forever

    group.create_task(
        forever("events_match", EVENTS_MATCH_CYCLE_S, events_match_once, ctx),
        name="meme-events-match",
    )
