"""Reserve-then-insert for meme proposals (T4.52b-4, fix "Race entre pistas",
review-T4.52b.md §2): the 15-second lane and the event lane each read
``already_open`` (``EventGateCaches.open_mints`` ∪ ``recently_proposed_mints``)
and then ``await insert_proposals`` — a coroutine of the other lane can run in
that gap and write its own proposal for the same mint before this one marks
its guard, so both land. Marking the guard *before* the ``await`` closes that
window; an insert that finds the row already there (0 rows: the unique index
already had it, most likely the other lane's) releases the reservation again
so the mint is not blocked for the rest of its TTL over a proposal that never
became this lane's own.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from hunter_meme_worker.lab_repo import insert_proposals

if TYPE_CHECKING:
    from collections.abc import Sequence
    from datetime import datetime

    from sqlalchemy.ext.asyncio import AsyncSession

    from hunter_meme_worker.event_gate_caches import EventGateCaches
    from hunter_meme_worker.proposals import ProposalDraft

__all__ = ["insert_proposals_reserved", "reserve_all"]


def reserve_all(
    caches: EventGateCaches | None,
    rule_set_id: str,
    drafts: Sequence[ProposalDraft],
    *,
    now: datetime,
    ttl_s: int,
) -> None:
    """Re-review 9d3c72a1: reserve every draft of the batch *synchronously*,
    before the caller's first ``await`` (a session open, an earlier draft's
    insert). Until then the other lane only sees what is marked, so a batch
    of two drafts left the second one open while the first one inserted.
    ``insert_proposals_reserved`` re-marks (idempotent) and releases a draft
    that inserted nothing, exactly as before."""
    if caches is None:
        return
    for draft in drafts:
        caches.mark_proposed(draft.mint, rule_set_id, now=now, ttl_s=ttl_s)


async def insert_proposals_reserved(
    session: AsyncSession,
    caches: EventGateCaches | None,
    rule_set_id: str,
    drafts: Sequence[ProposalDraft],
    *,
    now: datetime,
    ttl_s: int,
) -> int:
    """Insert every draft one at a time (``insert_proposals`` already does —
    this only moves the reservation to straddle each ``await``), reserving
    its mint in ``caches`` immediately before the insert and releasing it
    again if that insert inserted nothing. ``caches=None`` (the event gate
    disabled) inserts with no reservation at all — there is only one lane."""
    inserted_total = 0
    for draft in drafts:
        if caches is not None:
            caches.mark_proposed(draft.mint, rule_set_id, now=now, ttl_s=ttl_s)
        inserted = await insert_proposals(session, [draft])
        if inserted:
            inserted_total += inserted
        elif caches is not None:
            caches.unmark_proposed(draft.mint, rule_set_id)
    return inserted_total
