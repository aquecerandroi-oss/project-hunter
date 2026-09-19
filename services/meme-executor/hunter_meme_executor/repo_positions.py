"""The real positions (``meme_live_positions``): rebuilt from Postgres on every
pass, marked honestly, closed with R where **risk = SOL spent** (§5).

Split from ``repo.py`` (proposals, orders) so each module stays under the
350-line budget; ``repo.py`` re-exports these names, so callers import one place.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Any

from sqlalchemy import text

from hunter_core.domain.types import uuid7

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

__all__ = [
    "OpenPosition",
    "close_position",
    "insert_position",
    "open_position",
    "open_positions",
    "set_exit_intent",
    "stamp_creator_sold",
    "update_mark",
]

LAMPORTS = Decimal(1_000_000_000)


@dataclass(frozen=True, slots=True)
class OpenPosition:
    id: str
    proposal_id: str
    mint: str
    entry_at: datetime
    tokens: int
    sol_spent_lamports: int
    initial_risk_sol: Decimal
    params: dict[str, Any]
    mark_sol: Decimal | None
    high_water_sol: Decimal | None
    exit_intent: dict[str, Any] | None
    sell_requested_at: datetime | None
    sell_requested_by: str | None
    migrated: bool
    creator_sold_seen_at: datetime | None = None
    """T4.2h-b (``0038``): the instant the radar's creator watch saw this mint's
    creator sell on the chain. Read on the exit loop's own 5 s tick, so a real
    position stops waiting for the minute tape to notice."""

    def creator_dump_seen(self, tape_creator_sold: bool | None) -> bool:
        """``creator_dump`` for this position: the sale **seen on the chain** or
        the tape's own flag — either is enough, and neither is inferred from
        silence (a tape that says ``None`` has not measured anything)."""
        return self.creator_sold_seen_at is not None or tape_creator_sold is True


_POSITION_COLUMNS = (
    "SELECT id, proposal_id, mint, entry_at, tokens, sol_spent_lamports, initial_risk_sol, "
    "       params, mark_sol, high_water_sol, exit_intent, sell_requested_at, "
    "       sell_requested_by, migrated, creator_sold_seen_at "
    "FROM meme_live_positions WHERE status = 'open'"
)
_OPEN_POSITIONS = text(_POSITION_COLUMNS + " ORDER BY entry_at")
_OPEN_POSITION = text(_POSITION_COLUMNS + " AND id = :id")
_CREATOR_SOLD = text(
    "UPDATE meme_live_positions SET creator_sold_seen_at = :at, "
    "  creator_sold_fraction = :fraction, creator_balance_reason = NULL, updated_at = :now "
    "WHERE id = :id AND status = 'open' AND creator_sold_seen_at IS NULL RETURNING id"
)
_INSERT_POSITION = text(
    "INSERT INTO meme_live_positions (id, proposal_id, entry_order_id, mint, status, entry_at, "
    "  entry, tokens, sol_spent_lamports, initial_risk_sol, params, updated_at) "
    "VALUES (:id, :proposal_id, :entry_order_id, :mint, 'open', :entry_at, "
    "  CAST(:entry AS jsonb), :tokens, :sol_spent, :risk, CAST(:params AS jsonb), :now) "
    "ON CONFLICT (proposal_id) DO NOTHING RETURNING id"
)
_MARK = text(
    "UPDATE meme_live_positions SET mark_sol = :mark, mark_at = :now, mark_source = :source, "
    "  mark_reason = :reason, high_water_sol = GREATEST(coalesce(high_water_sol, 0), :mark), "
    "  migrated = :migrated, updated_at = :now WHERE id = :id AND status = 'open'"
)
_MARK_UNAVAILABLE = text(
    "UPDATE meme_live_positions SET mark_sol = NULL, mark_at = NULL, mark_source = NULL, "
    "  mark_reason = :reason, updated_at = :now WHERE id = :id AND status = 'open'"
)
_EXIT_INTENT = text(
    "UPDATE meme_live_positions SET exit_intent = CAST(:intent AS jsonb), updated_at = :now "
    "WHERE id = :id AND status = 'open'"
)
_CLOSE = text(
    "UPDATE meme_live_positions SET status = 'closed', exit_order_id = :order_id, "
    "  exit_at = :exit_at, exit = CAST(:exit AS jsonb), sol_received_lamports = :received, "
    "  pnl_sol = :pnl, r_multiple = :r, tokens = 0, updated_at = :now "
    "WHERE id = :id AND status = 'open' RETURNING id"
)


def _decimal(value: Any) -> Decimal | None:
    return None if value is None else Decimal(str(value))


def _position(r: Any) -> OpenPosition:
    return OpenPosition(
        id=str(r["id"]),
        proposal_id=str(r["proposal_id"]),
        mint=str(r["mint"]),
        entry_at=r["entry_at"],
        tokens=int(r["tokens"]),
        sol_spent_lamports=int(r["sol_spent_lamports"]),
        initial_risk_sol=Decimal(str(r["initial_risk_sol"])),
        params=dict(r["params"] or {}),
        mark_sol=_decimal(r["mark_sol"]),
        high_water_sol=_decimal(r["high_water_sol"]),
        exit_intent=None if r["exit_intent"] is None else dict(r["exit_intent"]),
        sell_requested_at=r["sell_requested_at"],
        sell_requested_by=r["sell_requested_by"],
        migrated=bool(r["migrated"]),
        creator_sold_seen_at=r["creator_sold_seen_at"],
    )


async def open_positions(session: AsyncSession) -> list[OpenPosition]:
    return [_position(r) for r in (await session.execute(_OPEN_POSITIONS)).mappings()]


async def open_position(session: AsyncSession, position_id: str) -> OpenPosition | None:
    """T4.63: the row **now**, or ``None`` once it is no longer open — what the
    tick and the event path re-read under the position's lock before selling."""
    r = (await session.execute(_OPEN_POSITION, {"id": position_id})).mappings().first()
    return None if r is None else _position(r)


async def stamp_creator_sold(
    session: AsyncSession, position_id: str, *, at: datetime, fraction: Decimal, now: datetime
) -> bool:
    """T4.63: the creator's sell seen in a ``TradeEvent`` of the position's own
    curve — the same columns the radar's 15 s watch stamps (``0038``), first
    sighting kept. ``fraction`` is sold ÷ allocation in ``(0, 1]``: the row's
    CHECK ``a_creator_sale_has_its_fraction`` refuses a sighting without one,
    so a caller that cannot measure it keeps the sighting in memory instead.
    ``True`` when this call was the one that stamped it."""
    if not Decimal(0) < fraction <= Decimal(1):
        raise ValueError(f"creator_sold_fraction_out_of_range:{fraction}")
    stamped = await session.execute(
        _CREATOR_SOLD, {"id": position_id, "at": at, "fraction": fraction, "now": now}
    )
    return stamped.scalar() is not None


async def insert_position(
    session: AsyncSession,
    *,
    proposal_id: str,
    entry_order_id: str,
    mint: str,
    entry_at: datetime,
    entry: dict[str, Any],
    tokens: int,
    sol_spent_lamports: int,
    params: dict[str, Any],
    now: datetime,
) -> str | None:
    """One position per proposal; ``initial_risk_sol`` **is** the SOL spent (§5)."""
    position_id = str(uuid7())
    inserted = await session.execute(
        _INSERT_POSITION,
        {
            "id": position_id,
            "proposal_id": proposal_id,
            "entry_order_id": entry_order_id,
            "mint": mint,
            "entry_at": entry_at,
            "entry": json.dumps(entry, default=str),
            "tokens": tokens,
            "sol_spent": sol_spent_lamports,
            "risk": Decimal(sol_spent_lamports) / LAMPORTS,
            "params": json.dumps(params, default=str),
            "now": now,
        },
    )
    return None if inserted.scalar() is None else position_id


async def update_mark(
    session: AsyncSession,
    position_id: str,
    *,
    mark_sol: Decimal | None,
    source: str,
    reason: str | None,
    migrated: bool,
    now: datetime,
) -> None:
    """``None`` keeps the row **unmarked with its reason** — never a fabricated number."""
    if mark_sol is None:
        await session.execute(_MARK_UNAVAILABLE, {"id": position_id, "reason": reason, "now": now})
        return
    await session.execute(
        _MARK,
        {
            "id": position_id,
            "mark": mark_sol,
            "now": now,
            "source": source,
            "reason": reason,
            "migrated": migrated,
        },
    )


async def set_exit_intent(
    session: AsyncSession, position_id: str, intent: dict[str, Any] | None, *, now: datetime
) -> None:
    await session.execute(
        _EXIT_INTENT,
        {"id": position_id, "intent": json.dumps(intent, default=str), "now": now},
    )


async def close_position(
    session: AsyncSession,
    position_id: str,
    *,
    exit_order_id: str,
    exit_at: datetime,
    exit_payload: dict[str, Any],
    sol_received_lamports: int,
    sol_spent_lamports: int,
    initial_risk_sol: Decimal,
    now: datetime,
) -> bool:
    """Close with the chain's numbers: ``pnl = received − spent``, ``R = pnl / risk``."""
    pnl = Decimal(sol_received_lamports - sol_spent_lamports) / LAMPORTS
    closed = await session.execute(
        _CLOSE,
        {
            "id": position_id,
            "order_id": exit_order_id,
            "exit_at": exit_at,
            "exit": json.dumps(exit_payload, default=str),
            "received": sol_received_lamports,
            "pnl": pnl,
            "r": pnl / initial_risk_sol,
            "now": now,
        },
    )
    return closed.scalar() is not None
