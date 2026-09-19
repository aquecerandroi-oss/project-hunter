"""``meme_treasury_swaps`` writes for ``meme_spot_swap.py`` (T4.73) — the
generic-mint-pair sibling of ``hunter_meme_executor.treasury_db``'s
USDC->SOL-shaped functions, spelled here because this script connects as the
schema owner (``meme_ops_db.migration_url``, an ``AsyncConnection``) rather
than through ``role_session``'s ``AsyncSession``, and because it always fills
the ``0056`` ``input_mint``/``output_mint`` columns the executor's own rows
leave ``NULL``. Same table, same lifecycle
(``quoted -> simulated -> submitted -> confirmed | failed``, or ``refused``).
"""

from __future__ import annotations

import uuid
from decimal import Decimal
from typing import Any, Protocol

from sqlalchemy import text

__all__ = [
    "Connection",
    "insert_row",
    "mark_confirmed",
    "mark_failed",
    "mark_refused",
    "mark_simulated",
    "mark_submitted",
]


class Connection(Protocol):
    async def execute(self, statement: Any, parameters: Any = None, /) -> Any: ...


_INSERT = text(
    "INSERT INTO meme_treasury_swaps (id, reason, usdc_in, sol_out_quoted, sol_out_filled, "
    "  price_impact_pct, slippage_bps, signature, status, refusal, wallet_sol_before, "
    "  wallet_sol_after, input_mint, output_mint) "
    "VALUES (:id, :reason, :amount_in, :amount_out_quoted, NULL, :price_impact_pct, "
    "  :slippage_bps, NULL, :status, :refusal, :wallet_sol_before, NULL, "
    "  :input_mint, :output_mint)"
)
_UPDATE_STATUS = text("UPDATE meme_treasury_swaps SET status = :status WHERE id = :id")
_UPDATE_REFUSED = text(
    "UPDATE meme_treasury_swaps SET status = 'refused', refusal = :refusal WHERE id = :id"
)
_UPDATE_SUBMITTED = text(
    "UPDATE meme_treasury_swaps SET status = 'submitted', signature = :signature WHERE id = :id"
)
_UPDATE_CONFIRMED = text(
    "UPDATE meme_treasury_swaps SET status = 'confirmed', sol_out_filled = :amount_out_filled, "
    "  wallet_sol_after = :wallet_sol_after WHERE id = :id"
)


async def insert_row(
    conn: Connection,
    *,
    reason: str,
    amount_in: Decimal,
    amount_out_quoted: Decimal,
    price_impact_pct: Decimal,
    slippage_bps: int,
    wallet_sol_before: Decimal,
    input_mint: str,
    output_mint: str,
    status: str,
    refusal: str | None = None,
) -> uuid.UUID:
    swap_id = uuid.uuid4()
    await conn.execute(
        _INSERT,
        {
            "id": swap_id,
            "reason": reason,
            "amount_in": amount_in,
            "amount_out_quoted": amount_out_quoted,
            "price_impact_pct": price_impact_pct,
            "slippage_bps": slippage_bps,
            "status": status,
            "refusal": refusal,
            "wallet_sol_before": wallet_sol_before,
            "input_mint": input_mint,
            "output_mint": output_mint,
        },
    )
    return swap_id


async def mark_refused(conn: Connection, swap_id: uuid.UUID, *, refusal: str) -> None:
    await conn.execute(_UPDATE_REFUSED, {"id": swap_id, "refusal": refusal})


async def mark_simulated(conn: Connection, swap_id: uuid.UUID) -> None:
    await conn.execute(_UPDATE_STATUS, {"id": swap_id, "status": "simulated"})


async def mark_submitted(conn: Connection, swap_id: uuid.UUID, *, signature: str) -> None:
    await conn.execute(_UPDATE_SUBMITTED, {"id": swap_id, "signature": signature})


async def mark_confirmed(
    conn: Connection, swap_id: uuid.UUID, *, amount_out_filled: Decimal, wallet_sol_after: Decimal
) -> None:
    await conn.execute(
        _UPDATE_CONFIRMED,
        {
            "id": swap_id,
            "amount_out_filled": amount_out_filled,
            "wallet_sol_after": wallet_sol_after,
        },
    )


async def mark_failed(conn: Connection, swap_id: uuid.UUID) -> None:
    await conn.execute(_UPDATE_STATUS, {"id": swap_id, "status": "failed"})
