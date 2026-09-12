"""Reads of the executor's ledger (``0028_meme_live``) and the one write the API
is granted on it: asking for a sale (``sell_requested_at``/``sell_requested_by``).

Global, no-RLS tables (the ``repositories/meme.py`` category); the org segment
gates who may look. Declared on T4.3's private ``MEME_METADATA`` like the
desk's tables, columns copied from ``ddl/meme_live.py`` verbatim.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Any, cast

from sqlalchemy import (
    BigInteger,
    Boolean,
    Column,
    DateTime,
    Integer,
    Numeric,
    Table,
    Text,
    select,
    update,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID

from hunter_api.repositories.meme_desk_tables import meme_proposals
from hunter_api.repositories.meme_tables import MEME_METADATA

if TYPE_CHECKING:
    from sqlalchemy.engine import CursorResult
    from sqlalchemy.ext.asyncio import AsyncSession

__all__ = [
    "LiveOrderRow",
    "LivePositionRow",
    "MemeLiveRepository",
    "meme_live_orders",
    "meme_live_positions",
]

meme_live_orders = Table(
    "meme_live_orders",
    MEME_METADATA,
    Column("id", UUID(as_uuid=True), primary_key=True),
    Column("proposal_id", UUID(as_uuid=True), nullable=False),
    Column("side", Text, nullable=False),
    Column("client_order_id", Text, nullable=False),
    Column("attempt", Integer, nullable=False),
    Column("intent", JSONB(none_as_null=True), nullable=False),
    Column("admission", JSONB(none_as_null=True), nullable=False),
    Column("status", Text, nullable=False),
    Column("reason", Text),
    Column("tx_signature", Text),
    Column("signatures", JSONB(none_as_null=True), nullable=False),
    Column("last_valid_block_height", BigInteger),
    Column("signing_at", DateTime(timezone=True)),
    Column("fill", JSONB(none_as_null=True)),
    Column("received_at", DateTime(timezone=True), nullable=False),
    Column("admitted_at", DateTime(timezone=True)),
    Column("simulated_at", DateTime(timezone=True)),
    Column("submitted_at", DateTime(timezone=True)),
    Column("settled_at", DateTime(timezone=True)),
    Column("updated_at", DateTime(timezone=True), nullable=False),
)

meme_live_positions = Table(
    "meme_live_positions",
    MEME_METADATA,
    Column("id", UUID(as_uuid=True), primary_key=True),
    Column("proposal_id", UUID(as_uuid=True), nullable=False),
    Column("entry_order_id", UUID(as_uuid=True), nullable=False),
    Column("mint", Text, nullable=False),
    Column("status", Text, nullable=False),
    Column("entry_at", DateTime(timezone=True), nullable=False),
    Column("entry", JSONB(none_as_null=True), nullable=False),
    Column("tokens", BigInteger, nullable=False),
    Column("sol_spent_lamports", BigInteger, nullable=False),
    Column("initial_risk_sol", Numeric(28, 10), nullable=False),
    Column("params", JSONB(none_as_null=True), nullable=False),
    Column("mark_sol", Numeric(28, 10)),
    Column("mark_at", DateTime(timezone=True)),
    Column("mark_source", Text),
    Column("mark_reason", Text),
    Column("high_water_sol", Numeric(28, 10)),
    Column("exit_intent", JSONB(none_as_null=True)),
    Column("sell_requested_at", DateTime(timezone=True)),
    Column("sell_requested_by", Text),
    Column("exit_order_id", UUID(as_uuid=True)),
    Column("exit_at", DateTime(timezone=True)),
    Column("exit", JSONB(none_as_null=True)),
    Column("sol_received_lamports", BigInteger),
    Column("pnl_sol", Numeric(28, 10)),
    Column("r_multiple", Numeric(28, 10)),
    Column("migrated", Boolean, nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
)

_o, _pos, _p = meme_live_orders, meme_live_positions, meme_proposals


@dataclass(frozen=True, slots=True)
class LiveOrderRow:
    id: uuid.UUID
    proposal_id: uuid.UUID
    mint: str | None
    side: str
    client_order_id: str
    attempt: int
    status: str
    reason: str | None
    tx_signature: str | None
    intent: dict[str, Any]
    admission: dict[str, Any]
    fill: dict[str, Any] | None
    received_at: datetime
    submitted_at: datetime | None
    settled_at: datetime | None


@dataclass(frozen=True, slots=True)
class LivePositionRow:
    id: uuid.UUID
    proposal_id: uuid.UUID
    mint: str
    status: str
    entry_at: datetime
    tokens: int
    sol_spent_lamports: int
    initial_risk_sol: Decimal
    params: dict[str, Any]
    mark_sol: Decimal | None
    mark_at: datetime | None
    mark_source: str | None
    mark_reason: str | None
    high_water_sol: Decimal | None
    exit_intent: dict[str, Any] | None
    sell_requested_at: datetime | None
    sell_requested_by: str | None
    exit_at: datetime | None
    exit: dict[str, Any] | None
    sol_received_lamports: int | None
    pnl_sol: Decimal | None
    r_multiple: Decimal | None
    migrated: bool


def _order(r: Any) -> LiveOrderRow:
    m = cast(dict[str, Any], r)
    return LiveOrderRow(
        id=m["id"],
        proposal_id=m["proposal_id"],
        mint=m.get("mint"),
        side=str(m["side"]),
        client_order_id=str(m["client_order_id"]),
        attempt=int(m["attempt"]),
        status=str(m["status"]),
        reason=m["reason"],
        tx_signature=m["tx_signature"],
        intent=dict(m["intent"] or {}),
        admission=dict(m["admission"] or {}),
        fill=None if m["fill"] is None else dict(m["fill"]),
        received_at=m["received_at"],
        submitted_at=m["submitted_at"],
        settled_at=m["settled_at"],
    )


def _position(r: Any) -> LivePositionRow:
    m = cast(dict[str, Any], r)
    return LivePositionRow(
        id=m["id"],
        proposal_id=m["proposal_id"],
        mint=str(m["mint"]),
        status=str(m["status"]),
        entry_at=m["entry_at"],
        tokens=int(m["tokens"]),
        sol_spent_lamports=int(m["sol_spent_lamports"]),
        initial_risk_sol=Decimal(str(m["initial_risk_sol"])),
        params=dict(m["params"] or {}),
        mark_sol=None if m["mark_sol"] is None else Decimal(str(m["mark_sol"])),
        mark_at=m["mark_at"],
        mark_source=m["mark_source"],
        mark_reason=m["mark_reason"],
        high_water_sol=None if m["high_water_sol"] is None else Decimal(str(m["high_water_sol"])),
        exit_intent=None if m["exit_intent"] is None else dict(m["exit_intent"]),
        sell_requested_at=m["sell_requested_at"],
        sell_requested_by=m["sell_requested_by"],
        exit_at=m["exit_at"],
        exit=None if m["exit"] is None else dict(m["exit"]),
        sol_received_lamports=None
        if m["sol_received_lamports"] is None
        else int(m["sol_received_lamports"]),
        pnl_sol=None if m["pnl_sol"] is None else Decimal(str(m["pnl_sol"])),
        r_multiple=None if m["r_multiple"] is None else Decimal(str(m["r_multiple"])),
        migrated=bool(m["migrated"]),
    )


class MemeLiveRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list_orders(self, *, limit: int) -> list[LiveOrderRow]:
        stmt = (
            select(_o, _p.c.mint)
            .select_from(_o.outerjoin(_p, _p.c.id == _o.c.proposal_id))
            .order_by(_o.c.received_at.desc(), _o.c.id.desc())
            .limit(limit)
        )
        return [_order(r) for r in (await self.session.execute(stmt)).mappings()]

    async def list_positions(self, *, closed_since: datetime) -> list[LivePositionRow]:
        stmt = (
            select(_pos)
            .where((_pos.c.status == "open") | (_pos.c.exit_at >= closed_since))
            .order_by(_pos.c.status.desc(), _pos.c.entry_at.desc())
        )
        return [_position(r) for r in (await self.session.execute(stmt)).mappings()]

    async def get_position(self, position_id: uuid.UUID) -> LivePositionRow | None:
        row = (
            (await self.session.execute(select(_pos).where(_pos.c.id == position_id)))
            .mappings()
            .first()
        )
        return None if row is None else _position(row)

    async def request_sell(self, position_id: uuid.UUID, *, by: str, now: datetime) -> bool:
        """The only write ``hunter_app`` holds on this table: ``True`` when this call set
        the request, ``False`` when it was already set or the position is not open."""
        result = cast(
            "CursorResult[Any]",
            await self.session.execute(
                update(_pos)
                .where(
                    _pos.c.id == position_id,
                    _pos.c.status == "open",
                    _pos.c.sell_requested_at.is_(None),
                )
                .values(sell_requested_at=now, sell_requested_by=by)
            ),
        )
        return result.rowcount == 1
