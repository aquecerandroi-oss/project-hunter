"""``meme_treasury_swaps`` — one row per attempt, from the first quote to the
confirmed (or refused/failed) end (T4.54, ``0051_meme_treasury_swaps``).

A row is inserted the moment sizing decides an amount worth quoting (or,
for a refusal that never gets that far, at the refusal itself) and updated
in place as the attempt advances — never a second row for the same attempt.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import text

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

__all__ = [
    "SubmittedSwap",
    "insert_refused",
    "insert_quoted",
    "last_attempt_at",
    "mark_confirmed",
    "mark_failed",
    "mark_refused",
    "mark_simulated",
    "mark_submitted",
    "submitted_swaps",
    "usdc_committed_last_24h",
]

_LAST_ATTEMPT = text("SELECT max(requested_at) FROM meme_treasury_swaps")
_USDC_24H = text(
    "SELECT coalesce(sum(usdc_in), 0) FROM meme_treasury_swaps "
    "WHERE status IN ('submitted', 'confirmed') AND requested_at >= :since"
)
_SUBMITTED = text(
    "SELECT id, signature, requested_at, wallet_sol_before FROM meme_treasury_swaps "
    "WHERE status = 'submitted' AND signature IS NOT NULL ORDER BY requested_at"
)
_INSERT = text(
    "INSERT INTO meme_treasury_swaps (id, reason, usdc_in, sol_out_quoted, sol_out_filled, "
    "  price_impact_pct, slippage_bps, signature, status, refusal, wallet_sol_before, "
    "  wallet_sol_after) "
    "VALUES (:id, :reason, :usdc_in, :sol_out_quoted, NULL, :price_impact_pct, :slippage_bps, "
    "  NULL, :status, :refusal, :wallet_sol_before, NULL) RETURNING id"
)
_UPDATE_STATUS = text("UPDATE meme_treasury_swaps SET status = :status WHERE id = :id")
_UPDATE_REFUSED = text(
    "UPDATE meme_treasury_swaps SET status = 'refused', refusal = :refusal WHERE id = :id"
)
_UPDATE_SUBMITTED = text(
    "UPDATE meme_treasury_swaps SET status = 'submitted', signature = :signature WHERE id = :id"
)
_UPDATE_CONFIRMED = text(
    "UPDATE meme_treasury_swaps SET status = 'confirmed', sol_out_filled = :sol_out_filled, "
    "  wallet_sol_after = :wallet_sol_after WHERE id = :id"
)


async def last_attempt_at(session: AsyncSession) -> datetime | None:
    """When any row (quoted, refused, submitted...) was last requested — the
    min-interval gate cares about attempts, not only confirmed ones."""
    return await session.scalar(_LAST_ATTEMPT)


async def usdc_committed_last_24h(session: AsyncSession, *, now: datetime) -> Decimal:
    """T4.54b fix C — what the daily cap counts: every ``confirmed`` swap
    **and every ``submitted`` one** (sent, not yet proven landed or dead). A
    swap that lands after the confirm timeout still spent the USDC; until the
    reconcile (``treasury_reconcile``) settles the row it counts as spent."""
    result = await session.scalar(_USDC_24H, {"since": now - timedelta(hours=24)})
    return Decimal(result or 0)


@dataclass(frozen=True, slots=True)
class SubmittedSwap:
    id: uuid.UUID
    signature: str
    requested_at: datetime
    wallet_sol_before: Decimal


async def submitted_swaps(session: AsyncSession) -> list[SubmittedSwap]:
    """Rows sent but never settled — a confirm timeout, or a crash between
    ``sendTransaction`` and ``mark_*`` — for the reconcile to resolve."""
    rows = (await session.execute(_SUBMITTED)).mappings().all()
    return [
        SubmittedSwap(
            id=row["id"],
            signature=str(row["signature"]),
            requested_at=row["requested_at"],
            wallet_sol_before=Decimal(row["wallet_sol_before"]),
        )
        for row in rows
    ]


async def insert_refused(
    session: AsyncSession,
    *,
    reason: str,
    refusal: str,
    usdc_in: Decimal,
    sol_out_quoted: Decimal,
    price_impact_pct: Decimal,
    slippage_bps: int,
    wallet_sol_before: Decimal,
) -> uuid.UUID:
    return await _insert(
        session,
        reason=reason,
        usdc_in=usdc_in,
        sol_out_quoted=sol_out_quoted,
        price_impact_pct=price_impact_pct,
        slippage_bps=slippage_bps,
        status="refused",
        refusal=refusal,
        wallet_sol_before=wallet_sol_before,
    )


async def insert_quoted(
    session: AsyncSession,
    *,
    reason: str,
    usdc_in: Decimal,
    sol_out_quoted: Decimal,
    price_impact_pct: Decimal,
    slippage_bps: int,
    wallet_sol_before: Decimal,
) -> uuid.UUID:
    return await _insert(
        session,
        reason=reason,
        usdc_in=usdc_in,
        sol_out_quoted=sol_out_quoted,
        price_impact_pct=price_impact_pct,
        slippage_bps=slippage_bps,
        status="quoted",
        refusal=None,
        wallet_sol_before=wallet_sol_before,
    )


async def _insert(
    session: AsyncSession,
    *,
    reason: str,
    usdc_in: Decimal,
    sol_out_quoted: Decimal,
    price_impact_pct: Decimal,
    slippage_bps: int,
    status: str,
    refusal: str | None,
    wallet_sol_before: Decimal,
) -> uuid.UUID:
    swap_id = uuid.uuid4()
    await session.execute(
        _INSERT,
        {
            "id": swap_id,
            "reason": reason,
            "usdc_in": usdc_in,
            "sol_out_quoted": sol_out_quoted,
            "price_impact_pct": price_impact_pct,
            "slippage_bps": slippage_bps,
            "status": status,
            "refusal": refusal,
            "wallet_sol_before": wallet_sol_before,
        },
    )
    return swap_id


async def mark_refused(session: AsyncSession, swap_id: uuid.UUID, *, refusal: str) -> None:
    """A row that had already reached ``quoted`` (or later) but was refused
    before anything was sent — the CHECK still requires ``signature IS NULL``,
    true of every status before ``submitted``."""
    await session.execute(_UPDATE_REFUSED, {"id": swap_id, "refusal": refusal})


async def mark_simulated(session: AsyncSession, swap_id: uuid.UUID) -> None:
    await session.execute(_UPDATE_STATUS, {"id": swap_id, "status": "simulated"})


async def mark_submitted(session: AsyncSession, swap_id: uuid.UUID, *, signature: str) -> None:
    await session.execute(_UPDATE_SUBMITTED, {"id": swap_id, "signature": signature})


async def mark_confirmed(
    session: AsyncSession,
    swap_id: uuid.UUID,
    *,
    sol_out_filled: Decimal,
    wallet_sol_after: Decimal,
) -> None:
    await session.execute(
        _UPDATE_CONFIRMED,
        {"id": swap_id, "sol_out_filled": sol_out_filled, "wallet_sol_after": wallet_sol_after},
    )


async def mark_failed(session: AsyncSession, swap_id: uuid.UUID) -> None:
    """A send that raised, or a submitted swap the chain reports as errored
    or expired unseen (``treasury_reconcile``) — the signature stays as
    evidence; no ``refusal`` (the CHECK reserves that word for
    ``status = 'refused'``, a swap nothing was ever sent for)."""
    await session.execute(_UPDATE_STATUS, {"id": swap_id, "status": "failed"})
