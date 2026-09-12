"""Reads for the "Reais — carteira observada" section of ``GET /meme/lab`` and
``GET /meme/desk`` (T4.12): the observed wallets' positions, their ledger and
one summary per wallet — global, no-RLS tables of ``0027_meme_wallets``, every
statement a ``SELECT`` as ``hunter_app``.

No ``org_id`` filter (there is nothing to filter by; the org path segment
gates *who* may look), and no number this module makes up: a position's mark
is the loop's, a wallet without a trade yet is absent from the summary (the
count of *watched* wallets is the worker's heartbeat's to state).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Any

from sqlalchemy import text

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

__all__ = ["MemeWalletsRepository", "WalletPositionRow", "WalletSummaryRow", "WalletTradeRow"]


@dataclass(frozen=True, slots=True)
class WalletPositionRow:
    wallet: str
    mint: str
    status: str
    tokens_held: Decimal
    sol_spent: Decimal
    sol_received: Decimal
    open_cost_sol: Decimal
    avg_cost_sol_per_token: Decimal | None
    realized_pnl_sol: Decimal
    unrealized_pnl_sol: Decimal | None
    unmatched_sell_tokens: Decimal
    buys: int
    sells: int
    first_buy_at: datetime | None
    last_trade_at: datetime
    mark_sol: Decimal | None
    mark_at: datetime | None
    mark_source: str | None
    mark_reason: str | None
    r_multiple: Decimal | None
    updated_at: datetime
    name: str | None
    symbol: str | None
    lab_context: dict[str, Any] | None
    """Of the position's **first** buy — what the Lab said when it opened."""
    hype_score: Decimal | None
    line_reason: str | None


@dataclass(frozen=True, slots=True)
class WalletTradeRow:
    wallet: str
    signature: str
    event_index: int
    slot: int
    block_time: datetime | None
    received_at: datetime
    mint: str | None
    side: str
    venue: str | None
    sol_lamports: int | None
    fee_lamports: int | None
    token_amount: Decimal | None
    decode: str
    reason: str | None
    """``raw ->> 'reason'`` of an ``unknown`` row."""
    lab_context: dict[str, Any] | None
    hype_score: Decimal | None
    line_reason: str | None


@dataclass(frozen=True, slots=True)
class WalletSummaryRow:
    wallet: str
    trades: int
    fills: int
    unknown: int
    first_seen_at: datetime
    last_trade_at: datetime | None
    realized_total_sol: Decimal
    realized_today_sol: Decimal
    """Σ realized PnL of the positions whose last trade fell in today (Brasília)
    — a position is the unit, so a day's partial sells count with their
    position, not alone."""
    open_positions: int
    closed_positions: int
    open_cost_sol: Decimal
    open_marks_sol: Decimal
    unmarked_open: int


_POSITIONS = text(
    "SELECT p.wallet, p.mint, p.status, p.tokens_held, p.sol_spent, p.sol_received, "
    "       p.open_cost_sol, p.avg_cost_sol_per_token, p.realized_pnl_sol, p.unrealized_pnl_sol, "
    "       p.unmatched_sell_tokens, p.buys, p.sells, p.first_buy_at, p.last_trade_at, "
    "       p.mark_sol, p.mark_at, p.mark_source, p.mark_reason, p.r_multiple, p.updated_at, "
    "       t.name, t.symbol, fb.lab_context, fb.hype_score, fb.line_reason "
    "FROM meme_wallet_positions p "
    "LEFT JOIN meme_tokens t ON t.mint = p.mint "
    "LEFT JOIN LATERAL ("
    "    SELECT w.lab_context, w.hype_score, w.line_reason FROM meme_wallet_trades w "
    "    WHERE w.wallet = p.wallet AND w.mint = p.mint AND w.side = 'buy' "
    "    ORDER BY w.block_time, w.slot, w.event_index LIMIT 1) fb ON true "
    "ORDER BY (p.status = 'open') DESC, p.last_trade_at DESC LIMIT :limit"
)

_TRADES = text(
    "SELECT wallet, signature, event_index, slot, block_time, received_at, mint, side, venue, "
    "       sol_lamports, fee_lamports, token_amount, decode, raw ->> 'reason' AS reason, "
    "       lab_context, hype_score, line_reason "
    "FROM meme_wallet_trades ORDER BY block_time DESC NULLS LAST, slot DESC, event_index DESC "
    "LIMIT :limit"
)

_SUMMARIES = text(
    "WITH t AS ("
    "    SELECT wallet, count(*) AS trades, "
    "           count(*) FILTER (WHERE side IN ('buy', 'sell')) AS fills, "
    "           count(*) FILTER (WHERE side = 'unknown') AS unknown, "
    "           min(received_at) AS first_seen_at, "
    "           max(block_time) FILTER (WHERE side IN ('buy', 'sell')) AS last_trade_at "
    "    FROM meme_wallet_trades GROUP BY wallet"
    "), p AS ("
    "    SELECT wallet, coalesce(sum(realized_pnl_sol), 0) AS realized_total, "
    "           coalesce(sum(realized_pnl_sol) FILTER (WHERE last_trade_at >= :day_start "
    "                    AND last_trade_at < :day_end), 0) AS realized_today, "
    "           count(*) FILTER (WHERE status = 'open') AS open_positions, "
    "           count(*) FILTER (WHERE status = 'closed') AS closed_positions, "
    "           coalesce(sum(open_cost_sol) FILTER (WHERE status = 'open'), 0) AS open_cost, "
    "           coalesce(sum(mark_sol) FILTER (WHERE status = 'open'), 0) AS open_marks, "
    "           count(*) FILTER (WHERE status = 'open' AND mark_sol IS NULL) AS unmarked_open "
    "    FROM meme_wallet_positions GROUP BY wallet"
    ") "
    "SELECT t.wallet, t.trades, t.fills, t.unknown, t.first_seen_at, t.last_trade_at, "
    "       coalesce(p.realized_total, 0) AS realized_total, "
    "       coalesce(p.realized_today, 0) AS realized_today, "
    "       coalesce(p.open_positions, 0) AS open_positions, "
    "       coalesce(p.closed_positions, 0) AS closed_positions, "
    "       coalesce(p.open_cost, 0) AS open_cost, coalesce(p.open_marks, 0) AS open_marks, "
    "       coalesce(p.unmarked_open, 0) AS unmarked_open "
    "FROM t LEFT JOIN p ON p.wallet = t.wallet ORDER BY t.wallet"
)


def _decimal(value: Any) -> Decimal | None:
    return None if value is None else Decimal(str(value))


class MemeWalletsRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def positions(self, *, limit: int = 200) -> list[WalletPositionRow]:
        rows = (await self.session.execute(_POSITIONS, {"limit": limit})).mappings().all()
        return [
            WalletPositionRow(
                wallet=str(r["wallet"]),
                mint=str(r["mint"]),
                status=str(r["status"]),
                tokens_held=Decimal(r["tokens_held"]),
                sol_spent=Decimal(r["sol_spent"]),
                sol_received=Decimal(r["sol_received"]),
                open_cost_sol=Decimal(r["open_cost_sol"]),
                avg_cost_sol_per_token=_decimal(r["avg_cost_sol_per_token"]),
                realized_pnl_sol=Decimal(r["realized_pnl_sol"]),
                unrealized_pnl_sol=_decimal(r["unrealized_pnl_sol"]),
                unmatched_sell_tokens=Decimal(r["unmatched_sell_tokens"]),
                buys=int(r["buys"]),
                sells=int(r["sells"]),
                first_buy_at=r["first_buy_at"],
                last_trade_at=r["last_trade_at"],
                mark_sol=_decimal(r["mark_sol"]),
                mark_at=r["mark_at"],
                mark_source=r["mark_source"],
                mark_reason=r["mark_reason"],
                r_multiple=_decimal(r["r_multiple"]),
                updated_at=r["updated_at"],
                name=r["name"],
                symbol=r["symbol"],
                lab_context=r["lab_context"],
                hype_score=_decimal(r["hype_score"]),
                line_reason=r["line_reason"],
            )
            for r in rows
        ]

    async def trades(self, *, limit: int = 100) -> list[WalletTradeRow]:
        rows = (await self.session.execute(_TRADES, {"limit": limit})).mappings().all()
        return [
            WalletTradeRow(
                wallet=str(r["wallet"]),
                signature=str(r["signature"]),
                event_index=int(r["event_index"]),
                slot=int(r["slot"]),
                block_time=r["block_time"],
                received_at=r["received_at"],
                mint=r["mint"],
                side=str(r["side"]),
                venue=r["venue"],
                sol_lamports=None if r["sol_lamports"] is None else int(r["sol_lamports"]),
                fee_lamports=None if r["fee_lamports"] is None else int(r["fee_lamports"]),
                token_amount=_decimal(r["token_amount"]),
                decode=str(r["decode"]),
                reason=r["reason"],
                lab_context=r["lab_context"],
                hype_score=_decimal(r["hype_score"]),
                line_reason=r["line_reason"],
            )
            for r in rows
        ]

    async def summaries(self, *, day_start: datetime, day_end: datetime) -> list[WalletSummaryRow]:
        rows = (
            (await self.session.execute(_SUMMARIES, {"day_start": day_start, "day_end": day_end}))
            .mappings()
            .all()
        )
        return [
            WalletSummaryRow(
                wallet=str(r["wallet"]),
                trades=int(r["trades"]),
                fills=int(r["fills"]),
                unknown=int(r["unknown"]),
                first_seen_at=r["first_seen_at"],
                last_trade_at=r["last_trade_at"],
                realized_total_sol=Decimal(r["realized_total"]),
                realized_today_sol=Decimal(r["realized_today"]),
                open_positions=int(r["open_positions"]),
                closed_positions=int(r["closed_positions"]),
                open_cost_sol=Decimal(r["open_cost"]),
                open_marks_sol=Decimal(r["open_marks"]),
                unmarked_open=int(r["unmarked_open"]),
            )
            for r in rows
        ]
