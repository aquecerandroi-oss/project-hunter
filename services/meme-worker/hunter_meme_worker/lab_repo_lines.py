"""The T4.10 reads of the Lab loop — as ``hunter_worker``, never as owner
(``lab_repo.py``'s discipline): the open probes a rule set may scale, the
probes already scaled (or queued to be), the support lines of a mint and the
snapshot at one instant.

Every read is bounded by an instant the caller names (``until``), so a line
folded after the snapshot being judged can never reach the exit rule.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from functools import partial
from typing import TYPE_CHECKING

from sqlalchemy import text

from hunter_meme_worker.lab_models import Snapshot
from hunter_meme_worker.lab_rows import snapshot_from_row
from hunter_meme_worker.lines_exit import SupportLine, below_support, next_streak, support_at

if TYPE_CHECKING:
    from collections.abc import Callable
    from decimal import Decimal

    from sqlalchemy.ext.asyncio import AsyncSession

    from hunter_meme_worker.lab_models import BetState

__all__ = [
    "line_state",
    "open_probes_for",
    "scaled_parent_ids",
    "snapshot_at",
    "support_lines_for",
]

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
    "SELECT end_time, computed_at, support_line_sol, support_line_slope FROM meme_features_1m "
    "WHERE mint = :mint AND features_version = :version "
    "  AND end_time >= :since AND end_time <= :until ORDER BY end_time DESC"
)
"""T4.98: minutes **without** a line come back too (``support_at`` needs the
newest minute to know a ``flat`` one hides every older line), with the
``computed_at`` that says which snapshot could have seen each. Read by range,
not ``LIMIT``: 30 rows would be only 30 minutes, and a Lab back from a longer
pause would judge the old photos with no line (Astra's review)."""
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
    since: datetime,
    until: datetime,
) -> list[SupportLine]:
    """The minutes closed in ``[since, until]``, newest first, with or without a line."""
    params = {"mint": mint, "version": features_version, "since": since, "until": until}
    return [
        SupportLine(
            end_time=r["end_time"],
            computed_at=r["computed_at"],
            support_sol=r["support_line_sol"],
            slope_per_min=r["support_line_slope"],
        )
        for r in (await session.execute(_SUPPORT_LINES, params)).mappings()
    ]


async def snapshot_at(session: AsyncSession, *, mint: str, at: datetime) -> Snapshot | None:
    """The snapshot observed exactly at ``at`` (the one a mark was written on)."""
    row = (await session.execute(_SNAPSHOT_AT, {"mint": mint, "at": at})).mappings().first()
    return None if row is None else snapshot_from_row(row)


async def line_state(
    session: AsyncSession,
    state: BetState,
    *,
    features_version: str,
    after: datetime,
    now: datetime,
) -> tuple[Callable[[datetime], Decimal | None], int | None]:
    """T4.10: the support a bet that watches the line reads at a photo's instant
    — under the bet's own ``line_support_causal``/``line_support_max_age_s``
    (T4.98) — and the streak rebuilt from the snapshot the last mark was written
    on: one back, which is all a two-snapshot rule needs and never lets a
    restart fire it early. Moved here from ``lab_bets`` (T4.98, 350-line budget)."""
    params = state.params
    if not params.exit_on_line_break:
        return (lambda _at: None), None
    # A minute closed before ``after − bound`` is stale for every photo from
    # ``after`` on, so it can never be the one ``support_at`` projects.
    since = after - timedelta(seconds=params.line_support_max_age_s)
    lines = await support_lines_for(
        session, mint=state.mint, features_version=features_version, since=since, until=now
    )
    support = partial(
        support_at,
        lines,
        causal=params.line_support_causal,
        max_age_s=params.line_support_max_age_s,
    )
    seed = await snapshot_at(session, mint=state.mint, at=after)
    if seed is None:
        return support, None
    return support, next_streak(None, below_support(seed.mcap_sol, support(after)))
