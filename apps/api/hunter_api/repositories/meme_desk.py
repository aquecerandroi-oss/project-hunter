"""Reads and the three permitted writes of the operator desk (T4.7).

Global, no-RLS tables (same category as ``repositories/meme.py``); the org
path segment only gates *who* may see or operate the desk. Schema is the
frozen contract (``.claude/state/contrato-T4.6-T4.7-mesa-meme.md``), table
metadata in ``repositories/meme_desk_tables.py``; the overview aggregates
(balances, SOL/USD quote) are ``repositories/meme_desk_summary.py``.

**Reads the base tables, not ``meme_desk_v1``** (contract "Emendas", T4.7):
the contract names the view but not its column list, and the desk needs more
of ``meme_paper_bets`` than the view's four columns (``entry``/``params``/
``exit_at``/``exit`` for remaining hold and exit reason). The base tables'
columns *are* frozen, so joining them here is the reading that cannot drift.

**Writes** are exactly the contract's — and exactly what ``0022_meme_lab``
grants ``hunter_app``: ``UPDATE meme_proposals`` on the four decision columns
(``status``/``decision``/``decided_by``/``decided_at``), guarded by ``WHERE
status = 'proposed'`` so a concurrent decision (or the loop's own ``expired``
stamp) wins by rowcount, never by overwrite; ``INSERT`` into
``meme_proposals`` (manual) and into ``meme_operator_commands``. Nothing here
touches ``meme_paper_bets``.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any, cast

from sqlalchemy import and_, case, func, or_, select, update

from hunter_api.repositories.meme_desk_marks import with_marks_0029
from hunter_api.repositories.meme_desk_rows import (
    BetRow,
    CommandRow,
    CurveQuoteRow,
    DeskRow,
    ProposalRow,
    RuleSetBalanceRow,
    RuleSetRow,
    SolUsdQuoteRow,
    TokenIdentity,
    bet_from_mapping,
    command_from_mapping,
    proposal_from_mapping,
    rule_set_from_mapping,
    token_from_mapping,
)
from hunter_api.repositories.meme_desk_summary import latest_sol_usd_quote, rule_set_balances
from hunter_api.repositories.meme_desk_tables import (
    meme_operator_commands,
    meme_paper_bets,
    meme_proposals,
    meme_rule_sets,
)
from hunter_api.repositories.meme_tables import (
    meme_curve_snapshots,
    meme_features_1m,
    meme_tokens,
)
from hunter_core.domain.types import ensure_utc

if TYPE_CHECKING:
    from sqlalchemy.engine import CursorResult
    from sqlalchemy.ext.asyncio import AsyncSession

__all__ = ["OPERATOR_RULE_SET", "MemeDeskRepository"]

OPERATOR_RULE_SET = ("operator", "2")
"""``meme_rule_sets (name, version)`` a manual proposal is filed under at
``head`` (contract §Rotas): ``0029_meme_moonshot`` (T4.11) retired ``0022``'s
``operator/1`` and seeded ``operator/2`` (the moonshot ``suggested``, sheet
still editable). The read is by **name and status** — the active ``operator``
set of the highest version — so a database still at ``0028`` files under
``operator/1`` instead of refusing ``operator_rule_set_missing``."""

_p = meme_proposals
_b = meme_paper_bets
_rank = case(
    (_p.c.status == "proposed", 0),
    (_p.c.status == "approved", 1),
    (and_(_p.c.status == "filled", _b.c.status == "open"), 2),
    else_=3,
).label("rank")
"""Contract §Rotas: "propostas abertas primeiro, depois apostas abertas,
depois histórico" — derived at read time, never stored."""


class MemeDeskRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    # ---- reads ----------------------------------------------------------

    async def list_desk(
        self,
        *,
        status: str | None,
        limit: int,
        cursor: tuple[int, datetime, uuid.UUID] | None,
    ) -> list[DeskRow]:
        stmt = select(_p, _rank).select_from(_p.outerjoin(_b, _b.c.id == _p.c.bet_id))
        if status is not None:
            stmt = stmt.where(_p.c.status == status)
        if cursor is not None:
            rank, proposed_at, proposal_id = cursor
            stmt = stmt.where(
                or_(
                    _rank > rank,
                    and_(_rank == rank, _p.c.proposed_at < proposed_at),
                    and_(_rank == rank, _p.c.proposed_at == proposed_at, _p.c.id < proposal_id),
                )
            )
        stmt = stmt.order_by(_rank.asc(), _p.c.proposed_at.desc(), _p.c.id.desc()).limit(limit)
        rows = (await self.session.execute(stmt)).mappings().all()
        proposals = [(proposal_from_mapping(r), int(r["rank"])) for r in rows]
        return await self._assemble(proposals)

    async def desk_row(self, proposal_id: uuid.UUID) -> DeskRow | None:
        stmt = (
            select(_p, _rank)
            .select_from(_p.outerjoin(_b, _b.c.id == _p.c.bet_id))
            .where(_p.c.id == proposal_id)
        )
        row = (await self.session.execute(stmt)).mappings().first()
        if row is None:
            return None
        assembled = await self._assemble([(proposal_from_mapping(row), int(row["rank"]))])
        return assembled[0]

    async def _assemble(self, proposals: list[tuple[ProposalRow, int]]) -> list[DeskRow]:
        if not proposals:
            return []
        mints = {p.mint for p, _ in proposals}
        bet_ids = {p.bet_id for p, _ in proposals if p.bet_id is not None}
        rule_set_ids = {p.rule_set_id for p, _ in proposals}
        tokens = {
            r["mint"]: token_from_mapping(r)
            for r in (
                await self.session.execute(select(meme_tokens).where(meme_tokens.c.mint.in_(mints)))
            ).mappings()
        }
        bets: dict[uuid.UUID, BetRow] = {}
        if bet_ids:
            bets = {
                r["id"]: bet_from_mapping(r)
                for r in (
                    await self.session.execute(select(_b).where(_b.c.id.in_(bet_ids)))
                ).mappings()
            }
            bets = await with_marks_0029(self.session, bets)  # 0029's columns, if present
        rule_sets = {
            r["id"]: rule_set_from_mapping(r)
            for r in (
                await self.session.execute(
                    select(meme_rule_sets).where(meme_rule_sets.c.id.in_(rule_set_ids))
                )
            ).mappings()
        }
        return [
            DeskRow(
                proposal=p,
                token=tokens.get(p.mint),
                bet=bets.get(p.bet_id) if p.bet_id is not None else None,
                rule_set=rule_sets.get(p.rule_set_id),
                rank=rank,
            )
            for p, rank in proposals
        ]

    async def get_proposal(self, proposal_id: uuid.UUID) -> ProposalRow | None:
        row = (
            (await self.session.execute(select(_p).where(_p.c.id == proposal_id)))
            .mappings()
            .first()
        )
        return None if row is None else proposal_from_mapping(row)

    async def get_rule_set(self, rule_set_id: uuid.UUID) -> RuleSetRow | None:
        row = (
            (
                await self.session.execute(
                    select(meme_rule_sets).where(meme_rule_sets.c.id == rule_set_id)
                )
            )
            .mappings()
            .first()
        )
        return None if row is None else rule_set_from_mapping(row)

    async def get_operator_rule_set(self) -> RuleSetRow | None:
        name, _version = OPERATOR_RULE_SET
        row = (
            (
                await self.session.execute(
                    select(meme_rule_sets)
                    .where(meme_rule_sets.c.name == name, meme_rule_sets.c.status == "active")
                    .order_by(
                        func.length(meme_rule_sets.c.version).desc(),
                        meme_rule_sets.c.version.desc(),
                    )
                    .limit(1)
                )
            )
            .mappings()
            .first()
        )
        return None if row is None else rule_set_from_mapping(row)

    async def get_bet(self, bet_id: uuid.UUID) -> BetRow | None:
        row = (await self.session.execute(select(_b).where(_b.c.id == bet_id))).mappings().first()
        if row is None:
            return None
        bet = bet_from_mapping(row)
        return (await with_marks_0029(self.session, {bet.id: bet}))[bet.id]

    async def get_token(self, mint: str) -> TokenIdentity | None:
        row = (
            (await self.session.execute(select(meme_tokens).where(meme_tokens.c.mint == mint)))
            .mappings()
            .first()
        )
        return None if row is None else token_from_mapping(row)

    async def latest_curve_quote(self, mint: str) -> CurveQuoteRow | None:
        s = meme_curve_snapshots
        row = (
            await self.session.execute(
                select(s).where(s.c.mint == mint).order_by(s.c.observed_at.desc()).limit(1)
            )
        ).first()
        if row is None:
            return None
        return CurveQuoteRow(
            observed_at=ensure_utc(row.observed_at),
            source=row.source,
            virtual_sol_reserves=row.virtual_sol_reserves,
            virtual_token_reserves=row.virtual_token_reserves,
            real_token_reserves=row.real_token_reserves,
            mcap_sol=row.mcap_sol,
            complete=row.complete,
        )

    async def latest_features_end_time(self, mint: str) -> datetime | None:
        value = await self.session.scalar(
            select(func.max(meme_features_1m.c.end_time)).where(meme_features_1m.c.mint == mint)
        )
        return ensure_utc(value) if value is not None else None

    async def get_command(self, command_id: uuid.UUID) -> CommandRow | None:
        c = meme_operator_commands
        row = (await self.session.execute(select(c).where(c.c.id == command_id))).mappings().first()
        return None if row is None else command_from_mapping(row)

    async def pending_command(self, *, bet_id: uuid.UUID, command: str) -> CommandRow | None:
        """A not-yet-applied command of this kind on this bet, if one exists —
        the loop sells on the next snapshot, and a second ``sell_now`` queued
        behind the first would only ever be refused by it."""
        c = meme_operator_commands
        row = (
            (
                await self.session.execute(
                    select(c)
                    .where(c.c.bet_id == bet_id, c.c.command == command, c.c.applied_at.is_(None))
                    .order_by(c.c.issued_at.desc())
                    .limit(1)
                )
            )
            .mappings()
            .first()
        )
        return None if row is None else command_from_mapping(row)

    async def rule_set_balances(self, now: datetime) -> list[RuleSetBalanceRow]:
        return await rule_set_balances(self.session, now)

    async def latest_sol_usd_quote(self) -> SolUsdQuoteRow | None:
        return await latest_sol_usd_quote(self.session)

    # ---- writes (contract §Papéis: the only three) ----------------------

    async def decide_proposal(
        self,
        proposal_id: uuid.UUID,
        *,
        status: str,
        decision: dict[str, Any] | None,
        decided_by: str,
        decided_at: datetime,
        mode: str = "paper",
    ) -> bool:
        """``True`` when this call moved the row out of ``proposed``; ``False``
        when something else (another operator, the loop's ``expired`` stamp)
        already had — the caller turns that into a 409, never a retry."""
        result = cast(
            "CursorResult[Any]",
            await self.session.execute(
                update(_p)
                .where(_p.c.id == proposal_id, _p.c.status == "proposed")
                .values(
                    status=status,
                    decision=decision,
                    decided_by=decided_by,
                    decided_at=decided_at,
                    mode=mode,
                )
            ),
        )
        return result.rowcount == 1

    async def insert_proposal(self, row: ProposalRow) -> None:
        await self.session.execute(
            _p.insert().values(
                id=row.id,
                mint=row.mint,
                rule_set_id=row.rule_set_id,
                origin=row.origin,
                status=row.status,
                proposed_at=row.proposed_at,
                expires_at=row.expires_at,
                features_end_time=row.features_end_time,
                quote=row.quote,
                reasons=row.reasons,
                suggested=row.suggested,
                decision=row.decision,
                decided_by=row.decided_by,
                decided_at=row.decided_at,
                bet_id=row.bet_id,
                refusal=row.refusal,
                mode=row.mode,
            )
        )

    async def insert_command(self, row: CommandRow) -> None:
        await self.session.execute(
            meme_operator_commands.insert().values(
                id=row.id,
                bet_id=row.bet_id,
                command=row.command,
                proposal_id=row.proposal_id,
                issued_by=row.issued_by,
                issued_at=row.issued_at,
                applied_at=row.applied_at,
                result=row.result,
            )
        )
