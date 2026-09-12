"""The ``0030`` columns of ``meme_paper_bets`` — ``outcome_quality``,
``outcome_quality_reason`` (T4.16) — read **tolerantly**, the way
``repositories/meme_desk_marks.py`` reads ``0029``'s: one catalogue probe,
then a second read by id folded into the :class:`BetRow`s. Below ``0030`` the
rows keep ``None``: "the quality is not known", never a fabricated
``measured``.

The same probe guards the day's **indeterminate totals** for ``/meme/tests``:
the count, PnL and R of the closes the instrument could not price, which the
service subtracts from the day's sums and shows apart ("indeterminado (sem
fotografia)"). Below ``0030`` there are none to subtract.
"""

from __future__ import annotations

import uuid
from collections.abc import Mapping
from dataclasses import dataclass, replace
from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Final

from sqlalchemy import Column, MetaData, Table, Text, select, text
from sqlalchemy.dialects.postgresql import UUID

from hunter_api.repositories.meme_desk_rows import BetRow

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

__all__ = [
    "QUALITY_COLUMNS_0030",
    "IndeterminateTotals",
    "indeterminate_day_totals",
    "quality_0030_present",
    "with_quality_0030",
]

QUALITY_COLUMNS_0030: Final[tuple[str, ...]] = ("outcome_quality", "outcome_quality_reason")

_PROBE = text(
    "SELECT count(*) FROM information_schema.columns "
    "WHERE table_schema = 'public' AND table_name = 'meme_paper_bets' "
    "  AND column_name IN ('outcome_quality', 'outcome_quality_reason')"
)

_quality_0030 = Table(
    "meme_paper_bets",
    MetaData(),
    Column("id", UUID(as_uuid=True), primary_key=True),
    Column("outcome_quality", Text),
    Column("outcome_quality_reason", Text),
)

_INDETERMINATE_TOTALS = text(
    "SELECT count(*) AS bets, "
    "       count(*) FILTER (WHERE b.pnl_sol > 0) AS wins, "
    "       count(*) FILTER (WHERE b.pnl_sol <= 0) AS losses, "
    "       coalesce(sum(b.pnl_sol), 0) AS pnl_sol, "
    "       coalesce(sum(b.r_multiple), 0) AS r_sum, "
    "       sum(b.pnl_sol * b.sol_usd_at_exit) FILTER (WHERE b.sol_usd_at_exit IS NOT NULL) "
    "         AS pnl_usd, "
    "       count(*) FILTER (WHERE b.sol_usd_at_exit IS NULL) AS unpriced_usd "
    "FROM meme_paper_bets b LEFT JOIN meme_rule_sets r ON r.id = b.rule_set_id "
    "WHERE b.status = 'closed' AND b.outcome_quality = 'indeterminate' "
    "  AND b.entry_at >= :day_start AND b.entry_at < :day_end "
    "  AND (CAST(:rule_set AS text) IS NULL OR r.name = :rule_set)"
)


@dataclass(frozen=True, slots=True)
class IndeterminateTotals:
    """The day's closes the instrument could not price — what the sums leave out."""

    bets: int
    wins: int
    losses: int
    pnl_sol: Decimal
    r_sum: Decimal
    pnl_usd: Decimal | None
    unpriced_usd: int


async def quality_0030_present(session: AsyncSession) -> bool:
    count = await session.scalar(_PROBE)
    return int(count or 0) == len(QUALITY_COLUMNS_0030)


async def with_quality_0030(
    session: AsyncSession, bets: Mapping[uuid.UUID, BetRow]
) -> dict[uuid.UUID, BetRow]:
    """The same rows with ``outcome_quality``/``outcome_quality_reason`` filled
    in when the database has them; untouched (``None``) when it does not."""
    out = dict(bets)
    if not out or not await quality_0030_present(session):
        return out
    rows = (
        await session.execute(select(_quality_0030).where(_quality_0030.c.id.in_(list(out))))
    ).mappings()
    for r in rows:
        bet = out.get(r["id"])
        if bet is None:
            continue
        out[r["id"]] = replace(
            bet,
            outcome_quality=None if r["outcome_quality"] is None else str(r["outcome_quality"]),
            outcome_quality_reason=(
                None if r["outcome_quality_reason"] is None else str(r["outcome_quality_reason"])
            ),
        )
    return out


async def indeterminate_day_totals(
    session: AsyncSession, *, day_start: datetime, day_end: datetime, rule_set: str | None
) -> IndeterminateTotals | None:
    """The indeterminate closes of the day (by ``entry_at``, the scoreboard's
    own rule); ``None`` on a database below ``0030``."""
    if not await quality_0030_present(session):
        return None
    r = (
        (
            await session.execute(
                _INDETERMINATE_TOTALS,
                {"day_start": day_start, "day_end": day_end, "rule_set": rule_set},
            )
        )
        .mappings()
        .one()
    )
    return IndeterminateTotals(
        bets=int(r["bets"]),
        wins=int(r["wins"]),
        losses=int(r["losses"]),
        pnl_sol=Decimal(r["pnl_sol"]),
        r_sum=Decimal(r["r_sum"]),
        pnl_usd=None if r["pnl_usd"] is None else Decimal(r["pnl_usd"]),
        unpriced_usd=int(r["unpriced_usd"]),
    )
