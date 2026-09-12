"""The pinned set (T4.16b): every mint the tracker's cap and window must not
touch right now — from the durable rows, never from memory, so a restart
rebuilds exactly the same set (``lab.py``'s reload every tick, ``main.py``'s
reload at boot).

Five ``hype_probe_v0`` paper bets closed ``rug_no_snapshot`` on 12/09 with a
last photo 13 minutes before the exit and no coin actually dead
(``docs/RISK_ENGINE_MEME.md`` §10): the tracker's cap evicted them at roughly
one discovery every few seconds, and the chain loop stopped photographing a
mint the instant it left the tracked set. The three facts below are the
brief's own definition of "not optional inventory": an open paper bet, an
open live position (T4.14, ``meme_live_positions`` — read-only here, the
executor owns the writes) and a proposal still waiting on a decision that has
not expired. A ``rejected``/``expired``/``filled``/``unfilled`` proposal
carries no urgency of its own — whatever it produced (a bet, a position) is
already pinned by its own row.
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import text

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

__all__ = ["pinned_mints"]

_PINNED_MINTS = text(
    "SELECT mint FROM meme_paper_bets WHERE status = 'open' "
    "UNION SELECT mint FROM meme_live_positions WHERE status = 'open' "
    "UNION SELECT mint FROM meme_proposals WHERE status = 'proposed' AND expires_at > :now"
)


async def pinned_mints(session: AsyncSession, *, now: datetime) -> frozenset[str]:
    """Every mint the tracker's cap and window may not evict right now."""
    rows = await session.execute(_PINNED_MINTS, {"now": now})
    return frozenset(str(m) for m in rows.scalars().all())
