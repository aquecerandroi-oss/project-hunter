"""The per-mint gate refusal trail's own state and jobs (T4.43) — split from
:mod:`hunter_meme_worker.lab` for the 350-line budget, the same shape
``lab_bets.py``'s ``FillReport``/``BetsReport`` already established: one
field on ``LabState`` (``trail``), the rest lives here.

Two jobs, two cadences:

- :func:`write_refusal_trail` — every 15-second tick (``lab_fast.py``), one
  batched ``INSERT`` only when the tick produced candidates, capped at
  ``config_trail.trail_max_rows_per_tick`` (default 200). The two counters on
  :class:`RefusalTrailState` are what the heartbeat reports as
  ``lab_refusal_trail_rows`` (rows actually written, since boot) and
  ``lab_refusal_trail_capped`` (rows the cap dropped, since boot — not a
  count of capped ticks: how much the desk is losing to the cap matters more
  than how often it happens).
- :func:`prune_trail_batches` — once a day (``collect.prune_once``, the
  existing retention loop), never every hour like ``meme_tokens`` beside it:
  the table is small by construction (the selector already keeps it so), so
  a daily sweep is plenty. :func:`should_prune_trail_today` is the pure
  decision (a calendar day, UTC) so the day-boundary logic is unit-testable
  without a database.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from typing import TYPE_CHECKING

from hunter_core.db.session import role_session
from hunter_core.domain.types import utcnow
from hunter_meme_worker.config_trail import TRAIL_RETENTION_DAYS, trail_max_rows_per_tick
from hunter_meme_worker.gate_refusal_trail import RefusalTrailRow, cap_trail_rows
from hunter_meme_worker.lab_repo_fast import insert_refusal_trail, prune_refusal_trail

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

__all__ = [
    "RefusalTrailState",
    "maybe_prune_trail",
    "prune_trail_batches",
    "should_prune_trail_today",
    "write_refusal_trail",
]

WORKER_ROLE = "hunter_worker"
"""``lab_repo_fast.py``'s own convention, duplicated here rather than
imported — the existing convention between these modules."""


@dataclass
class RefusalTrailState:
    """Since boot: what ``lab_heartbeat.heartbeat_fields`` reads."""

    rows_total: int = 0
    capped_total: int = 0


async def write_refusal_trail(
    session: AsyncSession, state: RefusalTrailState, candidates: list[RefusalTrailRow]
) -> int:
    """Cap ``candidates``, insert once (batched), count into ``state``.
    Nothing is written for an empty tick — one batched ``INSERT`` only when
    rows exist (the cost rule of ``.claude/state/notes-T4.24b.md``)."""
    if not candidates:
        return 0
    kept, capped = cap_trail_rows(candidates, limit=trail_max_rows_per_tick())
    inserted = await insert_refusal_trail(session, kept)
    state.rows_total += inserted
    if capped:
        state.capped_total += len(candidates) - len(kept)
    return inserted


def should_prune_trail_today(last_prune_day: date | None, today: date) -> bool:
    """Once a day: true only the first time ``today`` is seen."""
    return last_prune_day != today


async def prune_trail_batches(
    session_factory: async_sessionmaker[AsyncSession], *, batch: int
) -> int:
    """Every row of ``meme_gate_refusals_by_mint`` older than
    ``TRAIL_RETENTION_DAYS`` (7 d), in batches — ``repo.prune_tokens``'s own
    loop shape, one call per batch so a sweep never holds the lock over a
    whole week of rows at once."""
    cutoff = utcnow() - timedelta(days=TRAIL_RETENTION_DAYS)
    total = 0
    while True:
        async with role_session(session_factory, db_role=WORKER_ROLE) as session:
            deleted = await prune_refusal_trail(session, cutoff=cutoff, batch=batch)
        total += deleted
        if deleted < batch:
            break
    return total


async def maybe_prune_trail(
    session_factory: async_sessionmaker[AsyncSession], last_prune_day: date | None, *, batch: int
) -> tuple[int, date | None]:
    """``(deleted, day)`` — ``day`` is today's date if this call pruned, else
    ``last_prune_day`` unchanged; the caller (``collect.prune_once``) stores
    it back onto its own state."""
    today = utcnow().date()
    if not should_prune_trail_today(last_prune_day, today):
        return 0, last_prune_day
    return await prune_trail_batches(session_factory, batch=batch), today
