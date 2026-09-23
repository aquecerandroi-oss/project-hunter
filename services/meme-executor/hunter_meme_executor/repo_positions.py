"""The real positions (``meme_live_positions``): rebuilt from Postgres on every
pass, marked honestly, closed with R where **risk = SOL spent** (§5).

Split from ``repo.py`` (proposals, orders) so each module stays under the
350-line budget; ``repo.py`` re-exports these names, so callers import one place.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from typing import TYPE_CHECKING, Any

from sqlalchemy import text

from hunter_core.domain.types import uuid7

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

__all__ = [
    "ConfirmedSell",
    "OpenPosition",
    "close_position",
    "confirmed_sells",
    "insert_position",
    "open_position",
    "open_positions",
    "positions_with_confirmed_sell",
    "recent_losses",
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


@dataclass(frozen=True, slots=True)
class ConfirmedSell:
    """T4.90b: a ``confirmed`` sell whose position is still ``open`` — the fill
    as the row holds it (JSON; ``stored_fill`` parses it) and the ORDER's intent."""

    order_id: str
    proposal_id: str
    position_id: str
    tx_signature: str | None
    intent: dict[str, Any]
    fill: object


_CONFIRMED_ON_OPEN = (
    "FROM meme_live_orders o JOIN meme_live_positions p ON p.proposal_id = o.proposal_id "
    "WHERE o.side = 'sell' AND o.status = 'confirmed' AND p.status = 'open' "
)
_CONFIRMED_SELLS = text(
    "SELECT o.id, o.proposal_id, p.id AS position_id, o.tx_signature, o.intent, o.fill "
    + _CONFIRMED_ON_OPEN
    + "AND o.proposal_id = :p ORDER BY o.attempt"
)
_WITH_CONFIRMED_SELL = text("SELECT DISTINCT p.id " + _CONFIRMED_ON_OPEN)
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
_RECENT_LOSS = text(
    "SELECT max(exit_at) AS exit_at FROM meme_live_positions "
    "WHERE mint = :mint AND status = 'closed' AND pnl_sol < 0 AND exit_at >= :since"
)
"""T4.78 (check 28): the **newest losing** live close of the candidate's mint
inside the cooldown — ``pnl_sol < 0`` only (a positive close never counts), one
row, keyed by the mint the admission is about. Astra (review T4.78): a global
"last 50 losing mints" read could omit exactly the candidate on a saturated
window and hand the engine an empty map, which reads as "no loss" — so the
read is per mint and cannot lose it. Every lane's rows count: a launch loss
blocks a desk re-entry on the same mint and vice versa."""
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


async def confirmed_sells(session: AsyncSession, proposal_id: str) -> list[ConfirmedSell]:
    """T4.90b: this proposal's confirmed sells while its position is still open, oldest first."""
    rows = await session.execute(_CONFIRMED_SELLS, {"p": proposal_id})
    return [
        ConfirmedSell(
            order_id=str(r["id"]),
            proposal_id=str(r["proposal_id"]),
            position_id=str(r["position_id"]),
            tx_signature=r["tx_signature"],
            intent=dict(r["intent"] or {}),
            fill=r["fill"],
        )
        for r in rows.mappings()
    ]


async def positions_with_confirmed_sell(session: AsyncSession) -> list[str]:
    """T4.90b: every open position that a confirmed sell already emptied."""
    return [str(pid) for pid in (await session.execute(_WITH_CONFIRMED_SELL)).scalars()]


async def recent_losses(
    session: AsyncSession, mint: str, *, now: datetime, cooldown_s: int
) -> dict[str, datetime]:
    """``{mint: exit_at}`` of the newest losing close of ``mint`` inside
    ``cooldown_s`` (empty when none) — the engine's
    ``MemeWalletState.recent_losses``. ``0`` (disabled) runs no query."""
    if cooldown_s <= 0:
        return {}
    stamp = (
        await session.execute(
            _RECENT_LOSS, {"mint": mint, "since": now - timedelta(seconds=cooldown_s)}
        )
    ).scalar()
    return {} if stamp is None else {mint: stamp}


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
