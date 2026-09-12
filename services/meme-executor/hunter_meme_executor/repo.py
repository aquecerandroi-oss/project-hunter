"""Every read and write of the executor's loops — as ``hunter_worker``, one
transaction per call, no balance kept in memory.

The proposals and the desk's decision are T4.6/T4.7's rows, read only; the
executor's own ledger is ``0028_meme_live``. A restart is not a reset: open
positions, pending attempts and the day anchor are all rebuilt from here. The
positions live in ``repo_positions.py`` and are re-exported here.
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from typing import TYPE_CHECKING, Any

from sqlalchemy import text

from hunter_core.domain.types import uuid7
from hunter_meme_executor.repo_positions import (
    OpenPosition,
    close_position,
    insert_position,
    open_positions,
    set_exit_intent,
    update_mark,
)

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

__all__ = [
    "Candidate",
    "OpenPosition",
    "OrderRow",
    "PendingAttempt",
    "TokenContext",
    "close_position",
    "count_live_buys",
    "insert_order",
    "insert_position",
    "latest_sell_order",
    "live_candidates",
    "open_positions",
    "order_key",
    "orders_by_state",
    "participation_used_sol",
    "pending_attempts",
    "refuse_admitted_order",
    "set_exit_intent",
    "token_context",
    "unconfirmed_orders",
    "update_mark",
]


@dataclass(frozen=True, slots=True)
class Candidate:
    id: str
    mint: str
    decision: dict[str, Any]
    decided_at: datetime
    decided_by: str
    status: str


@dataclass(frozen=True, slots=True)
class TokenContext:
    created_at: datetime | None
    creator: str | None
    initial_real_token_reserves: int | None
    completed_at: datetime | None
    migrated_at: datetime | None
    curve_volume_1m_sol: Decimal | None
    features_end_time: datetime | None
    creator_sold: bool | None
    top10_share: Decimal | None
    bundled_share: Decimal | None


@dataclass(frozen=True, slots=True)
class OrderRow:
    id: str
    proposal_id: str
    side: str
    client_order_id: str
    attempt: int
    status: str
    reason: str | None
    intent: dict[str, Any]
    admission: dict[str, Any]


@dataclass(frozen=True, slots=True)
class PendingAttempt:
    proposal_id: str
    mint: str
    reserved_sol: Decimal


_CANDIDATES = text(
    "SELECT p.id, p.mint, p.decision, p.decided_at, p.decided_by, p.status "
    "FROM meme_proposals p "
    "WHERE p.mode = 'live' AND p.status IN ('approved', 'filled', 'unfilled') "
    "  AND p.decided_at IS NOT NULL AND p.decided_at >= :since "
    "  AND NOT EXISTS (SELECT 1 FROM meme_live_orders o "
    "                  WHERE o.proposal_id = p.id AND o.side = 'buy') "
    "ORDER BY p.decided_at"
)
_TOKEN = text(
    "SELECT created_at, creator, initial_real_token_reserves, completed_at, migrated_at "
    "FROM meme_tokens WHERE mint = :mint"
)
_FEATURES = text(
    "SELECT end_time, curve_volume_1m_sol, creator_sold, top10_share, bundled_share "
    "FROM meme_features_1m WHERE mint = :mint ORDER BY end_time DESC LIMIT 1"
)
_INSERT_ORDER = text(
    "INSERT INTO meme_live_orders (id, proposal_id, side, client_order_id, attempt, intent, "
    "  admission, status, reason, received_at, admitted_at, updated_at) "
    "VALUES (:id, :proposal_id, :side, :client_order_id, :attempt, CAST(:intent AS jsonb), "
    "  CAST(:admission AS jsonb), :status, :reason, :now, "
    "  CASE WHEN :status = 'admitted' THEN CAST(:now AS timestamptz) END, :now) "
    "ON CONFLICT (client_order_id) DO NOTHING RETURNING id"
)
_REFUSE_ADMITTED = text(
    "UPDATE meme_live_orders SET status = 'refused', reason = :reason, settled_at = :now, "
    "  updated_at = :now "
    "WHERE client_order_id = :key AND status = 'admitted' AND signing_at IS NULL RETURNING id"
)
_PENDING = text(
    "SELECT o.proposal_id, p.mint, o.intent FROM meme_live_orders o "
    "JOIN meme_proposals p ON p.id = o.proposal_id "
    "WHERE o.side = 'buy' AND o.status IN ('admitted', 'simulated', 'submitted_unconfirmed')"
)
_PARTICIPATION = text(
    "SELECT o.intent FROM meme_live_orders o JOIN meme_proposals p ON p.id = o.proposal_id "
    "WHERE p.mint = :mint AND o.side = 'buy' AND o.received_at >= :since "
    "  AND o.status IN ('simulated', 'submitted_unconfirmed', 'confirmed')"
)
_COUNT_BUYS = text(
    "SELECT count(*) FROM meme_live_orders WHERE side = 'buy' "
    "AND status IN ('submitted_unconfirmed', 'confirmed')"
)
_LATEST_SELL = text(
    "SELECT id, proposal_id, side, client_order_id, attempt, status, reason, intent, admission "
    "FROM meme_live_orders WHERE proposal_id = :proposal_id AND side = 'sell' "
    "ORDER BY attempt DESC LIMIT 1"
)
_UNCONFIRMED = text(
    "SELECT client_order_id FROM meme_live_orders "
    "WHERE tx_signature IS NOT NULL AND status IN ('simulated', 'submitted_unconfirmed') "
    "ORDER BY coalesce(submitted_at, simulated_at)"
)
"""Rows with a signature and no settlement: ``submitted_unconfirmed`` (a timeout after
the send) **and** ``simulated`` (a crash between recording the signature and the send,
or between the send and the state write) — every one is settled by reading the chain,
never by sending again."""
_BY_STATE = text("SELECT status, count(*) FROM meme_live_orders GROUP BY status")


def _decimal(value: Any) -> Decimal | None:
    return None if value is None else Decimal(str(value))


async def live_candidates(
    session: AsyncSession, *, now: datetime, lookback_s: int = 86_400
) -> list[Candidate]:
    """Live proposals decided on the desk that have no buy attempt yet. ``rejected``
    never appears; the TTL that refuses an old approval is the caller's."""
    rows = (
        await session.execute(_CANDIDATES, {"since": now - timedelta(seconds=lookback_s)})
    ).mappings()
    return [
        Candidate(
            id=str(r["id"]),
            mint=str(r["mint"]),
            decision=dict(r["decision"] or {}),
            decided_at=r["decided_at"],
            decided_by=str(r["decided_by"]),
            status=str(r["status"]),
        )
        for r in rows
    ]


async def token_context(session: AsyncSession, mint: str) -> TokenContext:
    token = (await session.execute(_TOKEN, {"mint": mint})).mappings().first()
    features = (await session.execute(_FEATURES, {"mint": mint})).mappings().first()
    initial = None if token is None else token["initial_real_token_reserves"]
    return TokenContext(
        created_at=None if token is None else token["created_at"],
        creator=None if token is None else token["creator"],
        initial_real_token_reserves=None if initial is None else int(Decimal(str(initial))),
        completed_at=None if token is None else token["completed_at"],
        migrated_at=None if token is None else token["migrated_at"],
        curve_volume_1m_sol=None if features is None else _decimal(features["curve_volume_1m_sol"]),
        features_end_time=None if features is None else features["end_time"],
        creator_sold=None if features is None else features["creator_sold"],
        top10_share=None if features is None else _decimal(features["top10_share"]),
        bundled_share=None if features is None else _decimal(features["bundled_share"]),
    )


async def insert_order(
    session: AsyncSession,
    *,
    proposal_id: str,
    side: str,
    client_order_id: str,
    attempt: int,
    status: str,
    reason: str | None,
    intent: dict[str, Any],
    admission: dict[str, Any],
    now: datetime,
) -> str | None:
    """The row the submitter will lock. ``None`` when the key already exists (idempotent)."""
    order_id = str(uuid7())
    inserted = await session.execute(
        _INSERT_ORDER,
        {
            "id": order_id,
            "proposal_id": proposal_id,
            "side": side,
            "client_order_id": client_order_id,
            "attempt": attempt,
            "intent": json.dumps(intent, default=str),
            "admission": json.dumps(admission, default=str),
            "status": status,
            "reason": reason,
            "now": now,
        },
    )
    return None if inserted.scalar() is None else order_id


async def refuse_admitted_order(
    session: AsyncSession, client_order_id: str, *, reason: str, now: datetime
) -> bool:
    """An admitted row the executor decided not to sign after all (the kill switch
    moved between the admission and the signature): ``refused`` by name, only while
    nobody holds its signing lock. ``True`` when this call refused it."""
    refused = await session.execute(
        _REFUSE_ADMITTED, {"key": client_order_id, "reason": reason, "now": now}
    )
    return refused.scalar() is not None


async def pending_attempts(session: AsyncSession) -> list[PendingAttempt]:
    """Buy attempts still in flight — each reserves its ``max_sol_cost`` (§9.5)."""
    out: list[PendingAttempt] = []
    for r in (await session.execute(_PENDING)).mappings():
        intent = dict(r["intent"] or {})
        reserved = _decimal(intent.get("max_sol_cost_sol")) or Decimal(0)
        if reserved > 0:
            out.append(PendingAttempt(str(r["proposal_id"]), str(r["mint"]), reserved))
    return out


async def participation_used_sol(session: AsyncSession, mint: str, *, now: datetime) -> Decimal:
    """SOL this wallet committed to ``mint`` in the moving 60 s window (§5)."""
    total = Decimal(0)
    for r in (
        await session.execute(_PARTICIPATION, {"mint": mint, "since": now - timedelta(seconds=60)})
    ).mappings():
        total += _decimal(dict(r["intent"] or {}).get("sol_final")) or Decimal(0)
    return total


async def count_live_buys(session: AsyncSession) -> int:
    return int((await session.execute(_COUNT_BUYS)).scalar() or 0)


async def latest_sell_order(session: AsyncSession, proposal_id: str) -> OrderRow | None:
    r = (await session.execute(_LATEST_SELL, {"proposal_id": proposal_id})).mappings().first()
    if r is None:
        return None
    return OrderRow(
        id=str(r["id"]),
        proposal_id=str(r["proposal_id"]),
        side=str(r["side"]),
        client_order_id=str(r["client_order_id"]),
        attempt=int(r["attempt"]),
        status=str(r["status"]),
        reason=r["reason"],
        intent=dict(r["intent"] or {}),
        admission=dict(r["admission"] or {}),
    )


async def unconfirmed_orders(session: AsyncSession) -> list[str]:
    return [str(k) for k in (await session.execute(_UNCONFIRMED)).scalars()]


async def orders_by_state(session: AsyncSession) -> dict[str, int]:
    return {str(r[0]): int(r[1]) for r in await session.execute(_BY_STATE)}


def order_key(proposal_id: str, *, side: str, attempt: int = 1) -> str:
    """``meme:{proposal_id}`` for the buy, ``meme:{proposal_id}:exit:{n}`` for a sell."""
    uuid.UUID(proposal_id)
    return f"meme:{proposal_id}" if side == "buy" else f"meme:{proposal_id}:exit:{attempt}"
