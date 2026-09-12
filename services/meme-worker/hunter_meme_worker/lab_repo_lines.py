"""The T4.10 reads of the Lab loop — as ``hunter_worker``, never as owner
(``lab_repo.py``'s discipline): the open probes a rule set may scale, the
probes already scaled (or queued to be), the support lines of a mint and the
snapshot at one instant.

Every read is bounded by an instant the caller names (``until``), so a line
folded after the snapshot being judged can never reach the exit rule.
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import text

from hunter_meme_worker.lab_models import Snapshot
from hunter_meme_worker.lab_rows import snapshot_from_row
from hunter_meme_worker.lines_exit import SupportLine

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

__all__ = ["open_probes_for", "scaled_parent_ids", "snapshot_at", "support_lines_for"]

_OPEN_PROBES = text(
    "SELECT mint, id FROM meme_paper_bets "
    "WHERE rule_set_id = :rule_set_id AND status = 'open' AND leg = 'probe' ORDER BY entry_at"
)
_SCALED_PARENTS = text(
    "SELECT parent_bet_id::text AS parent FROM meme_paper_bets "
    "WHERE rule_set_id = :rule_set_id AND parent_bet_id IS NOT NULL "
    "UNION SELECT suggested ->> 'parent_bet_id' FROM meme_proposals "
    "WHERE rule_set_id = :rule_set_id AND status IN ('proposed', 'approved') "
    "  AND suggested ->> 'parent_bet_id' IS NOT NULL"
)
"""A probe scales **once**: a bet already carrying it as parent, or a proposal
still waiting to fill with it in ``suggested``, both count."""

_SUPPORT_LINES = text(
    "SELECT end_time, support_line_sol, support_line_slope FROM meme_features_1m "
    "WHERE mint = :mint AND features_version = :version AND support_line_sol IS NOT NULL "
    "  AND end_time <= :until ORDER BY end_time DESC LIMIT :limit"
)
_SNAPSHOT_AT = text(
    "SELECT observed_at, mint, source, virtual_sol_reserves, virtual_token_reserves, "
    "real_sol_reserves, real_token_reserves, total_supply, complete, mcap_sol "
    "FROM meme_curve_snapshots WHERE mint = :mint AND observed_at = :at ORDER BY source LIMIT 1"
)


async def open_probes_for(session: AsyncSession, rule_set_id: str) -> dict[str, str]:
    """``mint → bet id`` of every open ``probe`` leg of one rule set."""
    rows = (await session.execute(_OPEN_PROBES, {"rule_set_id": rule_set_id})).mappings()
    return {str(r["mint"]): str(r["id"]) for r in rows}


async def scaled_parent_ids(session: AsyncSession, rule_set_id: str) -> frozenset[str]:
    rows = await session.execute(_SCALED_PARENTS, {"rule_set_id": rule_set_id})
    return frozenset(str(p) for p in rows.scalars().all() if p is not None)


async def support_lines_for(
    session: AsyncSession,
    *,
    mint: str,
    features_version: str,
    until: datetime,
    limit: int = 30,
) -> list[SupportLine]:
    """The support lines folded at or before ``until``, newest first."""
    params = {"mint": mint, "version": features_version, "until": until, "limit": limit}
    return [
        SupportLine(
            end_time=r["end_time"],
            support_sol=r["support_line_sol"],
            slope_per_min=r["support_line_slope"],
        )
        for r in (await session.execute(_SUPPORT_LINES, params)).mappings()
    ]


async def snapshot_at(session: AsyncSession, *, mint: str, at: datetime) -> Snapshot | None:
    """The snapshot observed exactly at ``at`` (the one a mark was written on)."""
    row = (await session.execute(_SNAPSHOT_AT, {"mint": mint, "at": at})).mappings().first()
    return None if row is None else snapshot_from_row(row)
