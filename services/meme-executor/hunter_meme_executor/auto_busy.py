"""T4.94, guardian review finding 1: "busy" is temporal, not observed.

Stage 1 used to supersede a proposal only when a pass *saw* its mint busy. Two
races slip past that: twins born on the same tape instant (the pass opens one,
the other waits a tick in which the first may buy and exit), and a proposal
born while another position was open that the exit loop closed before any
pass looked. Both open a proposal on a tape older than the mint's own
activity — the 007/BAGI pattern of R78 (``.claude/state/notes-R78.md``).

The rows answer it: proposal ``P`` on mint ``M`` is superseded when ``M`` has a
position that is open, or that the chain (``exit_at``, the sale's
``block_time``) or the executor (``updated_at``, stamped by the close and by
nothing after it — every other update requires ``status = 'open'``) closed at or
after ``P.proposed_at``, or an order of
another proposal — buy **or sell**, any status — received at or after
``P.proposed_at``. The sell matters: ``exit_at`` is the sale's chain
``block_time``, which can precede ``P`` while the executor still held the
position (the sale lands, ``P`` is born, the settlement follows); the sell
order's ``received_at`` is the executor's own record that the mint was held
after ``P``'s tape. And the close's ``updated_at`` covers the sequence where
every other stamp precedes ``P``: sell recorded → sale on chain → ``P`` born →
executor confirms and closes. (The close's ``updated_at`` is normally at or
after ``exit_at``; the ``exit_at`` clause still counts when the chain's clock
runs ahead of the executor's.) A refused buy counts too: somebody acted on the mint after
it. Activity that ended before ``P`` was born does not touch it.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import text

if TYPE_CHECKING:
    from collections.abc import Sequence

    from sqlalchemy.ext.asyncio import AsyncSession

    from hunter_meme_executor.auto_plan import OperatorProposal

__all__ = ["overtaken_proposals"]

_OVERTAKEN = text(
    "SELECT c.id FROM meme_proposals c "
    "WHERE c.id = ANY(CAST(:ids AS uuid[])) AND ("
    "  EXISTS (SELECT 1 FROM meme_live_positions lp WHERE lp.mint = c.mint "
    "          AND (lp.status = 'open' OR lp.exit_at >= c.proposed_at "
    "               OR lp.updated_at >= c.proposed_at)) "
    "  OR EXISTS (SELECT 1 FROM meme_live_orders o "
    "             JOIN meme_proposals op ON op.id = o.proposal_id "
    "             WHERE op.mint = c.mint "
    "               AND o.received_at >= c.proposed_at AND o.proposal_id <> c.id))"
)
"""Indexed both ways: ``ix_meme_live_positions_mint``, and
``ix_meme_proposals_mint_proposed_at`` → ``ix_meme_live_orders_proposal_id_side``."""


async def overtaken_proposals(
    session: AsyncSession, candidates: Sequence[OperatorProposal]
) -> frozenset[str]:
    """Ids of ``candidates`` whose mint's activity overtook them (see module)."""
    if not candidates:
        return frozenset()
    rows = await session.execute(_OVERTAKEN, {"ids": [c.id for c in candidates]})
    return frozenset(str(r[0]) for r in rows)
