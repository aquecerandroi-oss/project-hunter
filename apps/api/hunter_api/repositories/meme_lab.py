"""Reads for ``GET /meme/lab`` (T4.6) — global, no-RLS tables of ``0022_meme_lab``,
the same category as ``repositories/meme.py`` (ARCHITECTURE.md §9: global
repositories are read-only for tenants).

Everything here is a ``SELECT`` as ``hunter_app``: the rule sets, the derived
wallet of each one (from ``meme_paper_bets`` alone — the loop keeps no balance
anywhere else), the scoreboard view per Brasília day, the earliest rule set
(the goal clock) and the last quote a bet carried. No ``org_id`` filter: there
is nothing to filter by, and the org path segment only gates *who* may look.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Any

from sqlalchemy import text

from hunter_core.domain.types import ensure_utc

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

__all__ = ["BetQuoteRow", "DayScoreRow", "MemeLabRepository", "RuleSetRow", "WalletRow"]


@dataclass(frozen=True, slots=True)
class RuleSetRow:
    id: str
    name: str
    version: str
    kind: str
    exp_ref: str | None
    status: str
    code_ref: str
    params: dict[str, Any]
    created_at: datetime


@dataclass(frozen=True, slots=True)
class WalletRow:
    realized_total_sol: Decimal
    realized_today_sol: Decimal
    closed_today: int
    open_positions: int
    open_exposure_sol: Decimal
    open_marks_sol: Decimal


@dataclass(frozen=True, slots=True)
class DayScoreRow:
    rule_set_id: str
    day: date
    bets: int
    closed: int
    wins: int
    pnl_sol: Decimal | None
    pnl_usd: Decimal | None
    unpriced_usd: int
    r_sum: Decimal | None
    max_drawdown_sol: Decimal | None
    rugs: int
    indeterminate: int = 0
    """``0030`` (T4.16): closes the instrument could not price, counted apart;
    ``0`` on a database whose board predates the column."""


@dataclass(frozen=True, slots=True)
class BetQuoteRow:
    price_usd: Decimal
    source: str
    observed_at: datetime


_RULE_SETS = text(
    "SELECT id::text AS id, name, version, kind, exp_ref, status, code_ref, params, created_at "
    "FROM meme_rule_sets ORDER BY status, name, version"
)

_WALLET = text(
    "SELECT coalesce(sum(pnl_sol) FILTER (WHERE status = 'closed'), 0) AS realized_total, "
    "       coalesce(sum(pnl_sol) FILTER (WHERE status = 'closed' "
    "                AND exit_at >= :day_start AND exit_at < :day_end), 0) AS realized_today, "
    "       count(*) FILTER (WHERE status = 'closed' "
    "                AND exit_at >= :day_start AND exit_at < :day_end) AS closed_today, "
    "       count(*) FILTER (WHERE status = 'open') AS open_positions, "
    "       coalesce(sum(initial_risk_sol) FILTER (WHERE status = 'open'), 0) AS open_exposure, "
    "       coalesce(sum(mark_sol) FILTER (WHERE status = 'open'), 0) AS open_marks "
    "FROM meme_paper_bets WHERE rule_set_id = :rule_set_id"
)

_SCOREBOARD = text(
    "SELECT rule_set_id::text AS rule_set_id, day_brt, bets, closed, wins, pnl_sol, pnl_usd, "
    "       unpriced_usd, r_sum, max_drawdown_sol, rugs, 0 AS indeterminate "
    "FROM meme_lab_scoreboard_v1 WHERE day_brt >= :since ORDER BY rule_set_id, day_brt DESC"
)
_SCOREBOARD_0030 = text(
    "SELECT rule_set_id::text AS rule_set_id, day_brt, bets, closed, wins, pnl_sol, pnl_usd, "
    "       unpriced_usd, r_sum, max_drawdown_sol, rugs, indeterminate "
    "FROM meme_lab_scoreboard_v1 WHERE day_brt >= :since ORDER BY rule_set_id, day_brt DESC"
)
_SCOREBOARD_PROBE = text(
    "SELECT count(*) FROM information_schema.columns "
    "WHERE table_schema = 'public' AND table_name = 'meme_lab_scoreboard_v1' "
    "  AND column_name = 'indeterminate'"
)
"""T4.16: the board of ``0030`` carries ``indeterminate`` and sums measured
closes only; on a database below it the older board is read with a ``0`` —
the same tolerant probe as ``repositories/meme_desk_marks.py``."""

_LAST_QUOTE = text(
    "SELECT q ->> 'price_usd' AS price_usd, q ->> 'source' AS source, q ->> 'observed_at' AS observed_at "
    "FROM (SELECT coalesce(exit -> 'sol_usd', entry -> 'sol_usd') AS q "
    "      FROM meme_paper_bets ORDER BY coalesce(exit_at, entry_at) DESC LIMIT 1) AS last "
    "WHERE q IS NOT NULL AND q ->> 'price_usd' IS NOT NULL"
)


class MemeLabRepository:
    """No ``org_id``: the Lab's tables carry no ``organization_id`` (§1.1)."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def rule_sets(self) -> list[RuleSetRow]:
        rows = (await self.session.execute(_RULE_SETS)).mappings().all()
        return [
            RuleSetRow(
                id=str(r["id"]),
                name=str(r["name"]),
                version=str(r["version"]),
                kind=str(r["kind"]),
                exp_ref=r["exp_ref"],
                status=str(r["status"]),
                code_ref=str(r["code_ref"]),
                params=dict(r["params"]),
                created_at=ensure_utc(r["created_at"]),
            )
            for r in rows
        ]

    async def wallet(
        self, rule_set_id: str, *, day_start: datetime, day_end: datetime
    ) -> WalletRow:
        r = (
            (
                await self.session.execute(
                    _WALLET,
                    {"rule_set_id": rule_set_id, "day_start": day_start, "day_end": day_end},
                )
            )
            .mappings()
            .one()
        )
        return WalletRow(
            realized_total_sol=Decimal(r["realized_total"]),
            realized_today_sol=Decimal(r["realized_today"]),
            closed_today=int(r["closed_today"]),
            open_positions=int(r["open_positions"]),
            open_exposure_sol=Decimal(r["open_exposure"]),
            open_marks_sol=Decimal(r["open_marks"]),
        )

    async def scoreboard(self, *, since: date) -> list[DayScoreRow]:
        has_quality = int(await self.session.scalar(_SCOREBOARD_PROBE) or 0) == 1
        query = _SCOREBOARD_0030 if has_quality else _SCOREBOARD
        rows = (await self.session.execute(query, {"since": since})).mappings().all()
        return [
            DayScoreRow(
                rule_set_id=str(r["rule_set_id"]),
                day=r["day_brt"],
                bets=int(r["bets"]),
                closed=int(r["closed"]),
                wins=int(r["wins"]),
                pnl_sol=r["pnl_sol"],
                pnl_usd=r["pnl_usd"],
                unpriced_usd=int(r["unpriced_usd"]),
                r_sum=r["r_sum"],
                max_drawdown_sol=r["max_drawdown_sol"],
                rugs=int(r["rugs"]),
                indeterminate=int(r["indeterminate"]),
            )
            for r in rows
        ]

    async def last_bet_quote(self) -> BetQuoteRow | None:
        """The SOL/USD quote the most recent bet carried — the fallback when the
        worker's heartbeat has none (worker down, or never quoted)."""
        r = (await self.session.execute(_LAST_QUOTE)).mappings().first()
        if r is None:
            return None
        return BetQuoteRow(
            price_usd=Decimal(str(r["price_usd"])),
            source=str(r["source"]),
            observed_at=ensure_utc(datetime.fromisoformat(str(r["observed_at"]))),
        )
