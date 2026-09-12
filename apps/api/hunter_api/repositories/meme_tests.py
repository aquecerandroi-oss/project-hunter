"""Reads of the test record (T4.13): the paper bets of a Brasília day with
their proposal, token and rule set; the day's totals in SQL; the Lab's
minute (``meme_features_1m``) for a page of proposals; the curve between two
instants; and the observed wallet's positions (T4.12) when their table exists.

Global, no-RLS tables, read-only — same category as ``repositories/meme_desk.py``,
whose row shapes and mappers (``meme_desk_rows.py``) are reused verbatim, so
a column the loop writes is read exactly once in this codebase. Row shapes
of this module live in ``meme_tests_rows.py`` (350-line budget).

**The day is the Brasília day of ``entry_at``** (``meme_lab_scoreboard_v1``'s
own rule); the caller hands UTC bounds computed by ``services/meme_tests.py``.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Any

from sqlalchemy import Numeric, and_, case, func, or_, select, text
from sqlalchemy import cast as sql_cast
from sqlalchemy.exc import DBAPIError, SQLAlchemyError

from hunter_api.repositories.meme_desk_rows import (
    BetRow,
    bet_from_mapping,
    proposal_from_mapping,
    rule_set_from_mapping,
    token_from_mapping,
)
from hunter_api.repositories.meme_desk_tables import (
    meme_paper_bets,
    meme_proposals,
    meme_rule_sets,
)
from hunter_api.repositories.meme_tables import (
    meme_curve_snapshots,
    meme_features_1m,
    meme_tokens,
)
from hunter_api.repositories.meme_tests_rows import (
    PREFERRED_FEATURES_VERSION,
    BetRecord,
    CurvePointRow,
    DayTotalsRow,
    FeaturesAtMinute,
    WalletPositionsRead,
    features_from_mapping,
    prefer_version,
)
from hunter_core.domain.types import ensure_utc
from hunter_core.logging import get_logger

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

__all__ = [
    "PREFERRED_FEATURES_VERSION",
    "WALLET_POSITIONS_TABLE",
    "BetRecord",
    "CurvePointRow",
    "DayTotalsRow",
    "FeaturesAtMinute",
    "MemeTestsRepository",
    "WalletPositionsRead",
]

logger = get_logger(__name__)

WALLET_POSITIONS_TABLE = "meme_wallet_positions"
"""T4.12's table, built in parallel: read by name through ``to_regclass`` so
this API neither depends on its migration nor pretends it is there."""

_b = meme_paper_bets
_p = meme_proposals
_r = meme_rule_sets
_f = meme_features_1m


class MemeTestsRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    def _day_scope(self, day_start: datetime, day_end: datetime, rule_set: str | None) -> Any:
        stmt = select(_b).select_from(_b.outerjoin(_r, _r.c.id == _b.c.rule_set_id))
        stmt = stmt.where(_b.c.entry_at >= day_start, _b.c.entry_at < day_end)
        if rule_set is not None:
            stmt = stmt.where(_r.c.name == rule_set)
        return stmt

    async def list_day_bets(
        self,
        *,
        day_start: datetime,
        day_end: datetime,
        rule_set: str | None,
        limit: int,
        cursor: tuple[datetime, uuid.UUID] | None,
    ) -> list[BetRecord]:
        stmt = self._day_scope(day_start, day_end, rule_set)
        if cursor is not None:
            entry_at, bet_id = cursor
            stmt = stmt.where(
                or_(
                    _b.c.entry_at < entry_at,
                    and_(_b.c.entry_at == entry_at, _b.c.id < bet_id),
                )
            )
        stmt = stmt.order_by(_b.c.entry_at.desc(), _b.c.id.desc()).limit(limit)
        rows = (await self.session.execute(stmt)).mappings().all()
        return await self._assemble([bet_from_mapping(r) for r in rows])

    async def get_bet(self, bet_id: uuid.UUID) -> BetRecord | None:
        row = (await self.session.execute(select(_b).where(_b.c.id == bet_id))).mappings().first()
        if row is None:
            return None
        return (await self._assemble([bet_from_mapping(row)]))[0]

    async def _assemble(self, bets: list[BetRow]) -> list[BetRecord]:
        if not bets:
            return []
        proposal_ids = {b.proposal_id for b in bets}
        mints = {b.mint for b in bets}
        rule_set_ids = {b.rule_set_id for b in bets}
        proposals = {
            r["id"]: proposal_from_mapping(r)
            for r in (
                await self.session.execute(select(_p).where(_p.c.id.in_(proposal_ids)))
            ).mappings()
        }
        tokens = {
            r["mint"]: token_from_mapping(r)
            for r in (
                await self.session.execute(select(meme_tokens).where(meme_tokens.c.mint.in_(mints)))
            ).mappings()
        }
        rule_sets = {
            r["id"]: rule_set_from_mapping(r)
            for r in (
                await self.session.execute(select(_r).where(_r.c.id.in_(rule_set_ids)))
            ).mappings()
        }
        return [
            BetRecord(
                bet=b,
                proposal=proposals.get(b.proposal_id),
                token=tokens.get(b.mint),
                rule_set=rule_sets.get(b.rule_set_id),
            )
            for b in bets
        ]

    async def day_totals(
        self, *, day_start: datetime, day_end: datetime, rule_set: str | None
    ) -> DayTotalsRow:
        closed = _b.c.status == "closed"
        is_open = _b.c.status == "open"
        spent = sql_cast(_b.c.entry["sol_spent"].astext, Numeric())
        provisional = case((and_(is_open, _b.c.mark_sol.isnot(None)), _b.c.mark_sol - spent))
        priced = and_(closed, _b.c.sol_usd_at_exit.isnot(None))
        stmt = (
            select(
                func.count(_b.c.id).label("bets"),
                func.count(_b.c.id).filter(closed).label("closed"),
                func.count(_b.c.id).filter(is_open).label("open"),
                func.count(_b.c.id).filter(and_(closed, _b.c.pnl_sol > 0)).label("wins"),
                func.count(_b.c.id).filter(and_(closed, _b.c.pnl_sol <= 0)).label("losses"),
                func.coalesce(func.sum(case((closed, _b.c.pnl_sol))), 0).label("pnl_sol"),
                func.coalesce(func.sum(provisional), 0).label("provisional_pnl_sol"),
                func.sum(case((priced, _b.c.pnl_sol * _b.c.sol_usd_at_exit))).label("pnl_usd"),
                func.count(_b.c.id)
                .filter(and_(closed, _b.c.sol_usd_at_exit.is_(None)))
                .label("unpriced_usd"),
                func.coalesce(func.sum(case((closed, _b.c.r_multiple))), 0).label("r_sum"),
            )
            .select_from(_b.outerjoin(_r, _r.c.id == _b.c.rule_set_id))
            .where(_b.c.entry_at >= day_start, _b.c.entry_at < day_end)
        )
        if rule_set is not None:
            stmt = stmt.where(_r.c.name == rule_set)
        row = (await self.session.execute(stmt)).mappings().one()
        return DayTotalsRow(
            bets=int(row["bets"]),
            closed=int(row["closed"]),
            open=int(row["open"]),
            wins=int(row["wins"]),
            losses=int(row["losses"]),
            pnl_sol=Decimal(row["pnl_sol"]),
            provisional_pnl_sol=Decimal(row["provisional_pnl_sol"]),
            pnl_usd=None if row["pnl_usd"] is None else Decimal(row["pnl_usd"]),
            unpriced_usd=int(row["unpriced_usd"]),
            r_sum=Decimal(row["r_sum"]),
        )

    async def day_rule_set_names(self, *, day_start: datetime, day_end: datetime) -> list[str]:
        stmt = (
            select(_r.c.name)
            .distinct()
            .select_from(_b.join(_r, _r.c.id == _b.c.rule_set_id))
            .where(_b.c.entry_at >= day_start, _b.c.entry_at < day_end)
            .order_by(_r.c.name.asc())
        )
        return [str(name) for name in (await self.session.scalars(stmt)).all()]

    async def features_at(
        self, pairs: set[tuple[str, datetime]]
    ) -> dict[tuple[str, datetime], FeaturesAtMinute]:
        """The Lab's minute for every ``(mint, features_end_time)`` of a page,
        in one query (a superset by ``mint IN … AND end_time IN …``, narrowed
        to the exact pairs here); per pair the preferred version wins, else
        the newest version name."""
        if not pairs:
            return {}
        mints = {mint for mint, _ in pairs}
        end_times = {at for _, at in pairs}
        stmt = select(_f).where(_f.c.mint.in_(mints), _f.c.end_time.in_(end_times))
        found: dict[tuple[str, datetime], FeaturesAtMinute] = {}
        for r in (await self.session.execute(stmt)).mappings():
            row = features_from_mapping(r)
            key = (row.mint, row.end_time)
            if key not in pairs:
                continue
            current = found.get(key)
            if current is None or prefer_version(row.features_version, current.features_version):
                found[key] = row
        return found

    async def curve_between(
        self, mint: str, *, start: datetime, end: datetime, limit: int
    ) -> list[CurvePointRow]:
        s = meme_curve_snapshots
        stmt = (
            select(s.c.observed_at, s.c.source, s.c.mcap_sol, s.c.complete)
            .where(s.c.mint == mint, s.c.observed_at >= start, s.c.observed_at <= end)
            .order_by(s.c.observed_at.asc())
            .limit(limit)
        )
        return [
            CurvePointRow(
                observed_at=ensure_utc(r.observed_at),
                source=r.source,
                mcap_sol=r.mcap_sol,
                complete=bool(r.complete),
            )
            for r in (await self.session.execute(stmt)).all()
        ]

    async def wallet_positions(
        self, *, day_start: datetime, day_end: datetime, limit: int
    ) -> WalletPositionsRead:
        """T4.12's ``meme_wallet_positions`` of the day (by ``first_buy_at``),
        or the honest reason there are none. Under a SAVEPOINT: a table whose
        columns differ from the brief's must not poison the request's
        transaction."""
        exists = await self.session.scalar(
            text("SELECT to_regclass(:name)"), {"name": f"public.{WALLET_POSITIONS_TABLE}"}
        )
        if exists is None:
            return WalletPositionsRead(rows=[], source="não observada")
        query = text(
            f"SELECT * FROM {WALLET_POSITIONS_TABLE} "  # noqa: S608 — constant identifier
            "WHERE first_buy_at >= CAST(:start AS TIMESTAMPTZ) "
            "AND first_buy_at < CAST(:end AS TIMESTAMPTZ) "
            "ORDER BY first_buy_at DESC LIMIT :limit"
        )
        try:
            async with self.session.begin_nested():
                rows = (
                    await self.session.execute(
                        query, {"start": day_start, "end": day_end, "limit": limit}
                    )
                ).mappings()
                return WalletPositionsRead(rows=[dict(r) for r in rows], source="observada")
        except (DBAPIError, SQLAlchemyError) as exc:
            logger.warning("meme_tests_wallet_positions_unreadable", error_type=type(exc).__name__)
            return WalletPositionsRead(rows=[], source="leitura indisponível")
