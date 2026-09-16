"""T4.28g — which of this tick's candidate mints already have the rug read the
admission needs, so stage 1 can **wait** for it instead of burning the proposal.

**Measured (R5, 16/09/2026, ``obsidian/03-TRADING/Meme/Estudo-2026-09-16-admissao-real-o-que-recusa.md``):**
13 of the day's 16 real orders were refused ``bundled_share_unmeasurable``, and for
6 of the 7 mints the ``meme_risk_snapshots`` row landed **after** the order — a
median of 103 s after. The desk files the proposal, the executor auto-opens it 3–10 s
later, and the answer to check 11 arrives a minute and a half afterwards.

Opening the proposal in that window is strictly worse than not opening it: the row is
``rejected`` by the robot (gone for the human's click too, ``auto_approve.reject_if_auto``),
one RPC curve read and one ``refused`` order are written, and the coin is spent for a
number that was seconds away. So the planner skips it — ``risk_snapshot_pending``,
named in the heartbeat's ``auto_skipped`` — the row stays ``proposed``, and the next
tick (or the human) sees it exactly as before.

**This loosens nothing.** ``bundled_share`` still refuses when it is unmeasured
(``docs/RISK_ENGINE_MEME.md`` §4, check 11), the freshness window is the admission's
own :data:`~hunter_meme_executor.repo.RISK_SNAPSHOT_MAX_AGE_S`, and a mint whose read
never comes is never bought. The pair to this is the worker's side of T4.28g
(``hunter_meme_worker.repo_tape.pending_operator_mints``), which is what makes the read
arrive at all: without it the wait would simply time out on every coin.
"""

from __future__ import annotations

from datetime import timedelta
from typing import TYPE_CHECKING

from sqlalchemy import text

from hunter_meme_executor.repo import RISK_SNAPSHOT_MAX_AGE_S

if TYPE_CHECKING:
    from collections.abc import Collection
    from datetime import datetime

    from sqlalchemy.ext.asyncio import AsyncSession

__all__ = ["SNAPSHOT_MAX_AGE_S", "mints_with_snapshot", "risk_snapshot_sql"]

SNAPSHOT_MAX_AGE_S = RISK_SNAPSHOT_MAX_AGE_S
"""One home for the 600 s: the planner waits for exactly the row
``repo.token_context`` would accept as ``bundled_share_pct``. A looser window here
would make the robot open a proposal the admission then refuses as stale — the
failure this module exists to remove."""


def risk_snapshot_sql() -> str:
    """The text of :data:`_MEASURED`, exposed so its shape is testable without a
    database.

    Bounded twice and index-friendly: ``mint = ANY(:mints)`` is this tick's short
    candidate list and ``observed_at >= :since`` prunes the partitions of
    ``meme_risk_snapshots`` (RANGE on ``observed_at``) before
    ``ix_meme_risk_snapshots_mint_observed`` (``mint``, ``observed_at``) is walked.
    ``bundled_share IS NOT NULL`` is part of the predicate, not a post-filter: a read
    that answered without the share is not the input check 11 needs, and reporting it
    as measured would put back the very refusal this removes."""
    return (
        "SELECT DISTINCT mint FROM meme_risk_snapshots "
        "WHERE mint = ANY(:mints) AND bundled_share IS NOT NULL AND observed_at >= :since"
    )


_MEASURED = text(risk_snapshot_sql())


async def mints_with_snapshot(
    session: AsyncSession, mints: Collection[str], *, now: datetime
) -> frozenset[str]:
    """Of ``mints``, the ones with a usable ``bundled_share`` inside the window.

    No candidates ⇒ no query: a quiet tick must not touch a partitioned table."""
    if not mints:
        return frozenset()
    rows = await session.execute(
        _MEASURED,
        {"mints": list(mints), "since": now - timedelta(seconds=SNAPSHOT_MAX_AGE_S)},
    )
    return frozenset(str(mint) for mint in rows.scalars().all())
