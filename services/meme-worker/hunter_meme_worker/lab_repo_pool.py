"""The pool-side reads of the Lab loop (T4.11) — as ``hunter_worker``, never
as owner (``lab_repo.py``'s discipline): the PumpSwap pool's trades of a mint
and the creator's sells on the whole tape.

**Non-anticipation is in the predicate**, not in the caller's good will:
every read is bounded by ``received_at <= :until`` (the tick), so a trade the
tape delivered after the instant being judged cannot reach a mark, a rule or
a sale — the same rule ``repo_tape.load_tape`` applies to the fold.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import text

from hunter_indicators.meme.pool import PoolTrade

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

__all__ = ["creator_sold_on_tape", "pool_trades"]

LAMPORTS_PER_SOL = Decimal(1_000_000_000)

_POOL_TRADES = text(
    "SELECT block_time, received_at, side, sol_lamports, token_amount FROM meme_trades "
    "WHERE mint = :mint AND source = 'swap_api' AND program = 'pump_amm' "
    "  AND block_time > :since AND received_at <= :until "
    "ORDER BY block_time, signature, event_index LIMIT :limit"
)
"""Tape order is the primary key's order; ``since`` is the caller's window
start (five minutes before the last mark, so the first walked trade has its
volume), ``until`` the tick."""

_CREATOR_FLOW = text(
    "SELECT coalesce(sum(sol_lamports) FILTER (WHERE side = 'sell'), 0) AS sold, "
    "       coalesce(sum(sol_lamports) FILTER (WHERE side = 'buy'), 0) AS bought "
    "FROM meme_trades WHERE mint = :mint AND source = 'swap_api' AND trader = :creator "
    "  AND received_at <= :until"
)
"""Curve **and** pool: a creator who sells on the pool after the migration is
the same creator dump the curve rule watches for."""


async def pool_trades(
    session: AsyncSession, *, mint: str, since: datetime, until: datetime, limit: int = 2000
) -> list[PoolTrade]:
    """The pool trades known by ``until`` with ``block_time > since``, in tape order."""
    rows = (
        await session.execute(
            _POOL_TRADES, {"mint": mint, "since": since, "until": until, "limit": limit}
        )
    ).mappings()
    return [
        PoolTrade(
            block_time=r["block_time"],
            received_at=r["received_at"],
            side=str(r["side"]),
            sol=Decimal(int(r["sol_lamports"])) / LAMPORTS_PER_SOL,
            tokens=Decimal(r["token_amount"]),
        )
        for r in rows
    ]


async def creator_sold_on_tape(
    session: AsyncSession, *, mint: str, creator: str | None, until: datetime
) -> bool | None:
    """Whether the creator sold anything on the tape known by ``until`` — the
    input the curve path reads from ``meme_features_1m.creator_sold`` (T4.6),
    re-read from the tape because no minute is folded after the migration.
    ``None`` when the creator is unknown: refused as unknown, never as "no"."""
    if creator is None:
        return None
    row = (
        (await session.execute(_CREATOR_FLOW, {"mint": mint, "creator": creator, "until": until}))
        .mappings()
        .one()
    )
    return int(row["sold"]) > 0
