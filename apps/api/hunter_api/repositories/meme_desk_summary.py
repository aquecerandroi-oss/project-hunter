"""The desk's overview reads (T4.7): paper balance per rule set and the last
SOL/USD quote the loop observed — split out of ``repositories/meme_desk.py``
for the 350-line budget (``repositories/lab_summary.py`` is the precedent).

"Today" is the Brasília day of ``exit_at`` (contract §Tabelas,
``meme_lab_scoreboard_v1``'s own rule), computed in SQL with explicit casts so
asyncpg never has to guess a parameter's type: ``timezone(CAST($1 AS TEXT),
timestamptz)`` and ``CAST($2 AS TIMESTAMPTZ)``.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Any

from sqlalchemy import Date, DateTime, Numeric, Text, and_, case, func, literal, select, text
from sqlalchemy import cast as sql_cast

from hunter_api.repositories.meme_desk_rows import (
    RuleSetBalanceRow,
    SolUsdQuoteRow,
    rule_set_from_mapping,
)
from hunter_api.repositories.meme_desk_tables import meme_paper_bets, meme_rule_sets
from hunter_core.domain.types import ensure_utc

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

__all__ = ["BRASILIA_TZ", "latest_sol_usd_quote", "rule_set_balances"]

BRASILIA_TZ = "America/Sao_Paulo"

_b = meme_paper_bets

_LATEST_SOL_USD = text(
    "SELECT rate, observed_at, source FROM ("
    "  SELECT sol_usd_at_exit AS rate, exit_at AS observed_at, exit->>'sol_usd_source' AS source"
    "    FROM meme_paper_bets WHERE sol_usd_at_exit IS NOT NULL AND exit_at IS NOT NULL"
    "  UNION ALL"
    "  SELECT sol_usd_at_entry, entry_at, entry->>'sol_usd_source'"
    "    FROM meme_paper_bets WHERE sol_usd_at_entry IS NOT NULL"
    ") q ORDER BY observed_at DESC LIMIT 1"
)
"""The most recent quote on any bet, entry or exit — the loop's own observed
number with the instant it belongs to, never a live feed this API lacks."""


def _brasilia_day(column: Any) -> Any:
    return sql_cast(func.timezone(sql_cast(literal(BRASILIA_TZ), Text), column), Date)


async def rule_set_balances(session: AsyncSession, now: datetime) -> list[RuleSetBalanceRow]:
    """Per active rule set: SOL committed to open bets (``entry.sol_spent``),
    realized PnL today (Brasília day of ``exit_at``) and overall. The initial
    paper balance lives in ``params.wallet_max_sol`` and is read by the
    caller, never assumed here."""
    r = meme_rule_sets
    today = _brasilia_day(sql_cast(literal(now), DateTime(timezone=True)))
    closed_today = and_(_b.c.status == "closed", _brasilia_day(_b.c.exit_at) == today)
    spent = sql_cast(_b.c.entry["sol_spent"].astext, Numeric())
    stmt = (
        select(
            r,
            func.coalesce(func.sum(case((_b.c.status == "open", spent))), 0).label("open_sol"),
            func.coalesce(func.sum(case((closed_today, _b.c.pnl_sol))), 0).label("today"),
            func.coalesce(func.sum(case((_b.c.status == "closed", _b.c.pnl_sol))), 0).label(
                "total"
            ),
            func.count(_b.c.id).filter(_b.c.status == "open").label("open_bets"),
            func.count(_b.c.id).filter(closed_today).label("closed_today"),
        )
        .select_from(r.outerjoin(_b, _b.c.rule_set_id == r.c.id))
        .where(r.c.status == "active")
        .group_by(*r.c)
        .order_by(r.c.created_at.asc(), r.c.id.asc())
    )
    rows = (await session.execute(stmt)).mappings().all()
    return [
        RuleSetBalanceRow(
            rule_set=rule_set_from_mapping(row),
            open_sol=Decimal(row["open_sol"]),
            realized_today_sol=Decimal(row["today"]),
            realized_total_sol=Decimal(row["total"]),
            open_bets=int(row["open_bets"]),
            closed_today=int(row["closed_today"]),
        )
        for row in rows
    ]


async def latest_sol_usd_quote(session: AsyncSession) -> SolUsdQuoteRow | None:
    row = (await session.execute(_LATEST_SOL_USD)).first()
    if row is None:
        return None
    return SolUsdQuoteRow(
        rate=Decimal(row.rate), observed_at=ensure_utc(row.observed_at), source=row.source
    )
