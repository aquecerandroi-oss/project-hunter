"""SQL of the wallet loop (T4.12): the ledger ``meme_wallet_trades`` and the
derived ``meme_wallet_positions``, plus the two reads a mark needs.

Every write is idempotent by key — ``ON CONFLICT (signature, event_index) DO
NOTHING`` on the ledger (dedupe by signature is the schema's, not a memory of
the process) and an upsert on ``(wallet, mint)`` for a position recomputed from
the ledger. ``DELETE`` is granted to nobody and used by nobody.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Any

from sqlalchemy import bindparam, text

from hunter_exchanges.pumpfun.wallet_fills import WalletFill
from hunter_indicators.meme.curve import CurveReserves
from hunter_meme_worker.wallet_positions import (
    Fill,
    Mark,
    Position,
    SnapshotPoint,
    TapePoint,
    fee_pct_from_raw,
)

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

__all__ = [
    "LoadedFills",
    "existing_signatures",
    "insert_fills",
    "latest_snapshot",
    "latest_tape",
    "load_fills",
    "newest_signature",
    "open_positions",
    "set_lab_context",
    "upsert_position",
]

_EXISTING = text(
    "SELECT signature FROM meme_wallet_trades WHERE wallet = :wallet AND signature IN :signatures"
).bindparams(bindparam("signatures", expanding=True))

_NEWEST = text(
    "SELECT signature FROM meme_wallet_trades WHERE wallet = :wallet "
    "ORDER BY slot DESC, block_time DESC NULLS LAST, event_index DESC LIMIT 1"
)

_INSERT = text(
    "INSERT INTO meme_wallet_trades (wallet, signature, event_index, slot, block_time, "
    "  received_at, mint, side, venue, sol_lamports, token_amount, fee_lamports, decode, raw) "
    "VALUES (:wallet, :signature, :event_index, :slot, :block_time, :received_at, :mint, "
    "  :side, :venue, :sol_lamports, :token_amount, :fee_lamports, :decode, "
    "  CAST(:raw AS jsonb)) "
    "ON CONFLICT (signature, event_index) DO NOTHING RETURNING signature"
)

_SET_LAB_CONTEXT = text(
    "UPDATE meme_wallet_trades SET lab_context = CAST(:context AS jsonb), "
    "  hype_score = :hype_score, line_reason = :line_reason "
    "WHERE signature = :signature AND event_index = :event_index"
)

_FILLS = text(
    "SELECT block_time, slot, event_index, side, sol_lamports, fee_lamports, token_amount, "
    "       venue, raw FROM meme_wallet_trades "
    "WHERE wallet = :wallet AND mint = :mint AND side IN ('buy', 'sell') "
    "ORDER BY block_time, slot, event_index"
)

_SNAPSHOT = text(
    "SELECT observed_at, virtual_sol_reserves, virtual_token_reserves, real_token_reserves, "
    "       complete FROM meme_curve_snapshots WHERE mint = :mint "
    "ORDER BY observed_at DESC LIMIT 1"
)

_TAPE = text(
    "SELECT block_time, price FROM meme_trades WHERE mint = :mint ORDER BY block_time DESC LIMIT 1"
)

_UPSERT_POSITION = text(
    "INSERT INTO meme_wallet_positions (wallet, mint, status, tokens_held, sol_spent, "
    "  sol_received, open_cost_sol, avg_cost_sol_per_token, realized_pnl_sol, "
    "  unmatched_sell_tokens, buys, sells, first_buy_at, last_trade_at, mark_sol, mark_at, "
    "  mark_source, mark_reason, unrealized_pnl_sol, r_multiple, updated_at) "
    "VALUES (:wallet, :mint, :status, :tokens_held, :sol_spent, :sol_received, :open_cost_sol, "
    "  :avg_cost, :realized_pnl_sol, :unmatched_sell_tokens, :buys, :sells, :first_buy_at, "
    "  :last_trade_at, :mark_sol, :mark_at, :mark_source, :mark_reason, :unrealized_pnl_sol, "
    "  :r_multiple, :updated_at) "
    "ON CONFLICT (wallet, mint) DO UPDATE SET status = EXCLUDED.status, "
    "  tokens_held = EXCLUDED.tokens_held, sol_spent = EXCLUDED.sol_spent, "
    "  sol_received = EXCLUDED.sol_received, open_cost_sol = EXCLUDED.open_cost_sol, "
    "  avg_cost_sol_per_token = EXCLUDED.avg_cost_sol_per_token, "
    "  realized_pnl_sol = EXCLUDED.realized_pnl_sol, "
    "  unmatched_sell_tokens = EXCLUDED.unmatched_sell_tokens, buys = EXCLUDED.buys, "
    "  sells = EXCLUDED.sells, first_buy_at = EXCLUDED.first_buy_at, "
    "  last_trade_at = EXCLUDED.last_trade_at, mark_sol = EXCLUDED.mark_sol, "
    "  mark_at = EXCLUDED.mark_at, mark_source = EXCLUDED.mark_source, "
    "  mark_reason = EXCLUDED.mark_reason, unrealized_pnl_sol = EXCLUDED.unrealized_pnl_sol, "
    "  r_multiple = EXCLUDED.r_multiple, updated_at = EXCLUDED.updated_at"
)

_OPEN = text(
    "SELECT wallet, mint FROM meme_wallet_positions WHERE status = 'open' AND wallet IN :wallets"
).bindparams(bindparam("wallets", expanding=True))


@dataclass(frozen=True, slots=True)
class LoadedFills:
    fills: list[Fill]
    fee_pct: Decimal | None
    """The fee rate of the newest curve fill (``raw.fee_bps``), the rate the
    mark sells at; ``None`` when the position has no curve fill."""


async def existing_signatures(
    session: AsyncSession, wallet: str, signatures: Sequence[str]
) -> set[str]:
    if not signatures:
        return set()
    rows = await session.execute(_EXISTING, {"wallet": wallet, "signatures": list(signatures)})
    return {str(value) for value in rows.scalars()}


async def newest_signature(session: AsyncSession, wallet: str) -> str | None:
    value = await session.scalar(_NEWEST, {"wallet": wallet})
    return None if value is None else str(value)


async def insert_fills(
    session: AsyncSession, fills: Sequence[WalletFill], *, received_at: datetime
) -> list[WalletFill]:
    """Append; the rows the schema already had are not returned."""
    inserted: list[WalletFill] = []
    for fill in fills:
        result = await session.execute(
            _INSERT,
            {
                "wallet": fill.wallet,
                "signature": fill.signature,
                "event_index": fill.event_index,
                "slot": fill.slot,
                "block_time": fill.block_time,
                "received_at": received_at,
                "mint": fill.mint,
                "side": fill.side,
                "venue": fill.venue,
                "sol_lamports": fill.sol_lamports,
                "token_amount": fill.token_amount,
                "fee_lamports": fill.fee_lamports,
                "decode": fill.decode,
                "raw": json.dumps(fill.raw, default=str, sort_keys=True),
            },
        )
        if result.scalar() is not None:
            inserted.append(fill)
    return inserted


async def set_lab_context(
    session: AsyncSession,
    *,
    signature: str,
    event_index: int,
    context: dict[str, Any],
    hype_score: Decimal | None,
    line_reason: str | None,
) -> None:
    await session.execute(
        _SET_LAB_CONTEXT,
        {
            "signature": signature,
            "event_index": event_index,
            "context": json.dumps(context, default=str, sort_keys=True),
            "hype_score": hype_score,
            "line_reason": line_reason,
        },
    )


async def load_fills(session: AsyncSession, wallet: str, mint: str) -> LoadedFills:
    rows = (await session.execute(_FILLS, {"wallet": wallet, "mint": mint})).mappings().all()
    fills: list[Fill] = []
    fee_pct: Decimal | None = None
    for r in rows:
        fills.append(
            Fill(
                at=r["block_time"],
                slot=int(r["slot"]),
                event_index=int(r["event_index"]),
                side=str(r["side"]),
                sol_lamports=int(r["sol_lamports"]),
                fee_lamports=int(r["fee_lamports"]),
                token_amount=Decimal(r["token_amount"]),
            )
        )
        if r["venue"] == "curve":
            fee_pct = fee_pct_from_raw(r["raw"]) or fee_pct
    return LoadedFills(fills=fills, fee_pct=fee_pct)


async def latest_snapshot(session: AsyncSession, mint: str) -> SnapshotPoint | None:
    r = (await session.execute(_SNAPSHOT, {"mint": mint})).mappings().first()
    if r is None or r["virtual_token_reserves"] is None or r["virtual_token_reserves"] <= 0:
        return None
    return SnapshotPoint(
        reserves=CurveReserves(
            virtual_sol_reserves=Decimal(r["virtual_sol_reserves"]),
            virtual_token_reserves=Decimal(r["virtual_token_reserves"]),
            real_token_reserves=Decimal(r["real_token_reserves"]),
            complete=bool(r["complete"]),
        ),
        observed_at=r["observed_at"],
        complete=bool(r["complete"]),
    )


async def latest_tape(session: AsyncSession, mint: str) -> TapePoint | None:
    r = (await session.execute(_TAPE, {"mint": mint})).mappings().first()
    if r is None:
        return None
    return TapePoint(price_sol_per_token=Decimal(r["price"]), at=r["block_time"])


async def upsert_position(
    session: AsyncSession,
    *,
    wallet: str,
    mint: str,
    position: Position,
    mark: Mark,
    unrealized: Decimal | None,
    r_multiple: Decimal | None,
    now: datetime,
) -> None:
    await session.execute(
        _UPSERT_POSITION,
        {
            "wallet": wallet,
            "mint": mint,
            "status": position.status,
            "tokens_held": position.tokens_held,
            "sol_spent": position.sol_spent,
            "sol_received": position.sol_received,
            "open_cost_sol": position.open_cost_sol,
            "avg_cost": position.avg_cost_sol_per_token,
            "realized_pnl_sol": position.realized_pnl_sol,
            "unmatched_sell_tokens": position.unmatched_sell_tokens,
            "buys": position.buys,
            "sells": position.sells,
            "first_buy_at": position.first_buy_at,
            "last_trade_at": position.last_trade_at,
            "mark_sol": mark.mark_sol,
            "mark_at": mark.mark_at,
            "mark_source": mark.mark_source,
            "mark_reason": mark.mark_reason,
            "unrealized_pnl_sol": unrealized,
            "r_multiple": r_multiple,
            "updated_at": now,
        },
    )


async def open_positions(session: AsyncSession, wallets: Sequence[str]) -> list[tuple[str, str]]:
    if not wallets:
        return []
    rows = await session.execute(_OPEN, {"wallets": list(wallets)})
    return [(str(r[0]), str(r[1])) for r in rows]
