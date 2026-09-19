"""T4.74-3 — the ``spot/1`` desk's positions (``spot_positions``, ``0057``):
rebuilt from Postgres on every pass, marked by the Jupiter quote, closed with
the chain's numbers and **R = pnl ÷ r_unit** (design §4/§5).

Split from ``spot_repo.py`` (orders, candidates, the market map) the way
``repo_positions.py`` is split from ``repo.py``; ``spot_repo`` re-exports these
names so callers import one place. One statement per call, every read limited.

``closed_stats`` reads the exit reason from ``exit->>'reason'`` — the
convention the exits (T4.74-5) write; ``r_multiple`` is R **net** (the chain's
deltas include the fees), so ``sum_r_net`` is the honest number of §7/§8.
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
    "ClosedStats",
    "SpotPosition",
    "close_position",
    "closed_stats",
    "insert_position",
    "open_spot_positions",
    "set_mark",
    "spot_position_from_row",
]

LAMPORTS = Decimal(1_000_000_000)
STREAK_WINDOW = 20
"""The ``[1:20]`` of ``_CLOSED_STATS``: latest exits the stop streak looks at (§8 needs 3)."""


@dataclass(frozen=True, slots=True)
class SpotPosition:
    id: str
    signal_id: str
    market_symbol: str
    mint: str
    entry_at: datetime
    tokens: int
    sol_spent_lamports: int
    initial_risk_sol: Decimal
    params: dict[str, Any]
    ata_rent_lamports: int
    mark_sol: Decimal | None
    high_water_sol: Decimal | None
    exit_intent: dict[str, Any] | None
    sell_requested_at: datetime | None
    sell_requested_by: str | None


@dataclass(frozen=True, slots=True)
class ClosedStats:
    n: int
    sum_pnl_sol: Decimal
    sum_r_net: Decimal
    expectancy_r_net: Decimal | None
    consecutive_stops: int
    last_exit_at: datetime | None


_INSERT = text(
    "INSERT INTO spot_positions (id, signal_id, entry_order_id, market_symbol, mint, status, "
    "  entry_at, entry, tokens, sol_spent_lamports, initial_risk_sol, params, "
    "  ata_rent_lamports, updated_at) "
    "VALUES (:id, :signal_id, :entry_order_id, :market_symbol, :mint, 'open', :entry_at, "
    "  CAST(:entry AS jsonb), :tokens, :sol_spent, :risk, CAST(:params AS jsonb), :ata_rent, "
    "  :now) ON CONFLICT (signal_id) DO NOTHING RETURNING id"
)
_OPEN = text(
    "SELECT id, signal_id, market_symbol, mint, entry_at, tokens, sol_spent_lamports, "
    "  initial_risk_sol, params, ata_rent_lamports, mark_sol, high_water_sol, exit_intent, "
    "  sell_requested_at, sell_requested_by "
    "FROM spot_positions WHERE status = 'open' ORDER BY entry_at LIMIT 100"
)
_MARK = text(
    "UPDATE spot_positions SET mark_sol = :mark, mark_at = :now, mark_source = 'jupiter_quote', "
    "  mark_reason = :reason, high_water_sol = GREATEST(coalesce(high_water_sol, 0), :mark), "
    "  updated_at = :now WHERE id = :id AND status = 'open'"
)
_MARK_UNAVAILABLE = text(
    "UPDATE spot_positions SET mark_reason = :reason, updated_at = :now "
    "WHERE id = :id AND status = 'open'"
)
_CLOSE = text(
    "UPDATE spot_positions SET status = 'closed', exit_order_id = :order_id, exit_at = :exit_at, "
    "  exit = CAST(:exit AS jsonb), sol_received_lamports = :received, pnl_sol = :pnl, "
    "  r_multiple = :r, tokens = 0, updated_at = :now "
    "WHERE id = :id AND status = 'open' RETURNING id"
)
_CLOSED_STATS = text(
    "SELECT count(*) AS n, coalesce(sum(pnl_sol), 0) AS sum_pnl_sol, "
    "  coalesce(sum(r_multiple), 0) AS sum_r_net, "
    "  (array_agg(exit->>'reason' ORDER BY exit_at DESC))[1:20] AS recent_reasons, "
    "  max(exit_at) AS last_exit_at "
    "FROM spot_positions WHERE status = 'closed' AND exit_at >= :since"
)


def _decimal(value: Any) -> Decimal | None:
    return None if value is None else Decimal(str(value))


def spot_position_from_row(r: Any) -> SpotPosition:
    return SpotPosition(
        id=str(r["id"]),
        signal_id=str(r["signal_id"]),
        market_symbol=str(r["market_symbol"]),
        mint=str(r["mint"]),
        entry_at=r["entry_at"],
        tokens=int(r["tokens"]),
        sol_spent_lamports=int(r["sol_spent_lamports"]),
        initial_risk_sol=Decimal(str(r["initial_risk_sol"])),
        params=dict(r["params"] or {}),
        ata_rent_lamports=int(r["ata_rent_lamports"]),
        mark_sol=_decimal(r["mark_sol"]),
        high_water_sol=_decimal(r["high_water_sol"]),
        exit_intent=None if r["exit_intent"] is None else dict(r["exit_intent"]),
        sell_requested_at=r["sell_requested_at"],
        sell_requested_by=r["sell_requested_by"],
    )


async def insert_position(
    session: AsyncSession,
    *,
    signal_id: str,
    entry_order_id: str,
    market_symbol: str,
    mint: str,
    entry_at: datetime,
    entry: dict[str, Any],
    tokens: int,
    sol_spent_lamports: int,
    initial_risk_sol: Decimal,
    params: dict[str, Any],
    ata_rent_lamports: int,
    now: datetime,
) -> str | None:
    """One position per signal; ``initial_risk_sol`` is ``r_unit_sol`` (design §4/§5)."""
    position_id = str(uuid7())
    inserted = await session.execute(
        _INSERT,
        {
            "id": position_id,
            "signal_id": signal_id,
            "entry_order_id": entry_order_id,
            "market_symbol": market_symbol,
            "mint": mint,
            "entry_at": entry_at,
            "entry": json.dumps(entry, default=str),
            "tokens": tokens,
            "sol_spent": sol_spent_lamports,
            "risk": initial_risk_sol,
            "params": json.dumps(params, default=str),
            "ata_rent": ata_rent_lamports,
            "now": now,
        },
    )
    return None if inserted.scalar() is None else position_id


async def open_spot_positions(session: AsyncSession) -> list[SpotPosition]:
    return [spot_position_from_row(r) for r in (await session.execute(_OPEN)).mappings()]


async def set_mark(
    session: AsyncSession,
    position_id: str,
    *,
    mark_sol: Decimal | None,
    reason: str | None,
    now: datetime,
) -> None:
    """``None`` = the quote failed: the **old mark stays** with its instant and source
    (design §4 — the exits read its age as ``mark_stale_s``), only the reason moves.
    Not the meme doctrine (``update_mark`` erases): a Jupiter timeout is not a curve
    that vanished."""
    if mark_sol is None:
        await session.execute(_MARK_UNAVAILABLE, {"id": position_id, "reason": reason, "now": now})
        return
    await session.execute(
        _MARK, {"id": position_id, "mark": mark_sol, "reason": reason, "now": now}
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
    """The chain's numbers: ``pnl = received − spent`` (ATA rent stays out), ``R = pnl ÷ r_unit``."""
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


async def closed_stats(session: AsyncSession, *, since: datetime) -> ClosedStats:
    """§8's numbers over the exits since ``since`` (``SPOT1_REFUTATION_RESET_AT`` or the
    epoch): one aggregate; the stop streak is counted from the latest exit backwards."""
    r = (await session.execute(_CLOSED_STATS, {"since": since})).mappings().one()
    n = int(r["n"] or 0)
    sum_r = Decimal(str(r["sum_r_net"] or 0))
    streak = 0
    for reason in list(r["recent_reasons"] or []):
        if reason != "stop":
            break
        streak += 1
    return ClosedStats(
        n=n,
        sum_pnl_sol=Decimal(str(r["sum_pnl_sol"] or 0)),
        sum_r_net=sum_r,
        expectancy_r_net=None if n == 0 else sum_r / Decimal(n),
        consecutive_stops=streak,
        last_exit_at=r["last_exit_at"],
    )
