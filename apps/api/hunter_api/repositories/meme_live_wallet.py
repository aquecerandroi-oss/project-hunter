"""Bounded aggregates over ``meme_live_positions``/``meme_live_orders``/
``meme_treasury_swaps``/``meme_live_kill_switch`` for T4.57's
``GET /meme/live/wallet-summary`` — split out of ``repositories/meme_live.py``
to stay inside the file-size budget (``infra/scripts/check_file_size.py``).

Every read here is a ``SELECT`` as ``hunter_app`` (DATABASE.md §40.5 grants
it on all four tables) and every query is bounded: an aggregate with a
``FILTER`` clause or a single-row ``ORDER BY ... LIMIT 1``/primary-key lookup
— never a Python loop summing every row a fast-moving wallet has ever
touched.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import text

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

__all__ = ["MemeLiveWalletRepository", "WalletSummaryRow"]


@dataclass(frozen=True, slots=True)
class WalletSummaryRow:
    """Every number the wallet-summary service needs, read as five
    ``SELECT``s: the day's window is a bind parameter, the best/worst trade
    are ``ORDER BY ... LIMIT 1``, and the anchor/first-swap reads are
    single-row lookups."""

    open_positions: int
    open_marked_sol: Decimal
    open_unmarked_positions: int
    open_spent_lamports_marked: int
    bought_today: int
    sold_today: int
    won_today: int
    lost_today: int
    realized_pnl_today_sol: Decimal
    total_bought: int
    total_won: int
    total_lost: int
    total_pnl_sol: Decimal | None
    best_trade_mint: str | None
    best_trade_pnl_sol: Decimal | None
    worst_trade_mint: str | None
    worst_trade_pnl_sol: Decimal | None
    fees_lamports_today: int
    rent_lamports_today: int
    treasury_swaps_today: int
    treasury_usdc_spent_today: Decimal
    treasury_sol_bought_today: Decimal
    kill_switch_day_start_sol_equity: Decimal | None
    kill_switch_day_start_utc: datetime | None
    first_treasury_swap_wallet_sol_before: Decimal | None
    first_treasury_swap_at: datetime | None


_POSITIONS_AGG = text(
    "SELECT "
    "  count(*) FILTER (WHERE status = 'open') AS open_positions, "
    "  coalesce(sum(mark_sol) FILTER (WHERE status = 'open' AND mark_sol IS NOT NULL), 0) AS open_marked_sol, "
    "  count(*) FILTER (WHERE status = 'open' AND mark_sol IS NULL) AS open_unmarked_positions, "
    "  coalesce(sum(sol_spent_lamports) FILTER (WHERE status = 'open' AND mark_sol IS NOT NULL), 0) "
    "    AS open_spent_lamports_marked, "
    "  count(*) FILTER (WHERE entry_at >= :day_start AND entry_at < :day_end) AS bought_today, "
    "  count(*) FILTER (WHERE status = 'closed' AND exit_at >= :day_start AND exit_at < :day_end) AS sold_today, "
    "  count(*) FILTER (WHERE status = 'closed' AND exit_at >= :day_start AND exit_at < :day_end "
    "           AND pnl_sol > 0) AS won_today, "
    "  count(*) FILTER (WHERE status = 'closed' AND exit_at >= :day_start AND exit_at < :day_end "
    "           AND pnl_sol <= 0) AS lost_today, "
    "  coalesce(sum(pnl_sol) FILTER (WHERE status = 'closed' AND exit_at >= :day_start "
    "           AND exit_at < :day_end), 0) AS realized_pnl_today, "
    "  count(*) AS total_bought, "
    "  count(*) FILTER (WHERE status = 'closed' AND pnl_sol > 0) AS total_won, "
    "  count(*) FILTER (WHERE status = 'closed' AND pnl_sol <= 0) AS total_lost, "
    "  sum(pnl_sol) FILTER (WHERE status = 'closed') AS total_pnl_sol "
    "FROM meme_live_positions"
)
_BEST_TRADE = text(
    "SELECT mint, pnl_sol FROM meme_live_positions "
    "WHERE status = 'closed' AND pnl_sol IS NOT NULL ORDER BY pnl_sol DESC LIMIT 1"
)
_WORST_TRADE = text(
    "SELECT mint, pnl_sol FROM meme_live_positions "
    "WHERE status = 'closed' AND pnl_sol IS NOT NULL ORDER BY pnl_sol ASC LIMIT 1"
)
_ORDERS_FEES_TODAY = text(
    "SELECT "
    "  coalesce(sum((fill ->> 'network_fee_lamports')::numeric), 0) AS network_fee_lamports, "
    "  coalesce(sum((fill ->> 'fee')::numeric), 0) AS program_fee_lamports, "
    "  coalesce(sum((fill ->> 'ata_rent_lamports')::numeric), 0) AS ata_rent_lamports, "
    "  coalesce(sum((fill ->> 'account_rent_lamports')::numeric), 0) AS account_rent_lamports, "
    "  coalesce(sum((fill ->> 'ata_rent_refund_lamports')::numeric), 0) AS ata_rent_refund_lamports "
    "FROM meme_live_orders "
    "WHERE fill IS NOT NULL AND settled_at >= :day_start AND settled_at < :day_end"
)
_TREASURY_TODAY = text(
    "SELECT "
    "  count(*) FILTER (WHERE status = 'confirmed') AS swaps_confirmed_today, "
    "  coalesce(sum(usdc_in) FILTER (WHERE status = 'confirmed'), 0) AS usdc_spent_today, "
    "  coalesce(sum(sol_out_filled) FILTER (WHERE status = 'confirmed'), 0) AS sol_bought_today "
    "FROM meme_treasury_swaps WHERE requested_at >= :day_start AND requested_at < :day_end"
)
_KILL_SWITCH_ANCHOR = text(
    "SELECT day_start_sol_equity, day_start_utc FROM meme_live_kill_switch WHERE scope = 'wallet'"
)
_FIRST_TREASURY_SWAP = text(
    "SELECT wallet_sol_before, requested_at FROM meme_treasury_swaps ORDER BY requested_at ASC LIMIT 1"
)


class MemeLiveWalletRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def wallet_summary(self, *, day_start: datetime, day_end: datetime) -> WalletSummaryRow:
        params = {"day_start": day_start, "day_end": day_end}
        pos = (await self.session.execute(_POSITIONS_AGG, params)).mappings().one()
        best = (await self.session.execute(_BEST_TRADE)).mappings().first()
        worst = (await self.session.execute(_WORST_TRADE)).mappings().first()
        fees = (await self.session.execute(_ORDERS_FEES_TODAY, params)).mappings().one()
        treasury = (await self.session.execute(_TREASURY_TODAY, params)).mappings().one()
        anchor = (await self.session.execute(_KILL_SWITCH_ANCHOR)).mappings().first()
        first_swap = (await self.session.execute(_FIRST_TREASURY_SWAP)).mappings().first()
        return WalletSummaryRow(
            open_positions=int(pos["open_positions"]),
            open_marked_sol=Decimal(pos["open_marked_sol"]),
            open_unmarked_positions=int(pos["open_unmarked_positions"]),
            open_spent_lamports_marked=int(pos["open_spent_lamports_marked"]),
            bought_today=int(pos["bought_today"]),
            sold_today=int(pos["sold_today"]),
            won_today=int(pos["won_today"]),
            lost_today=int(pos["lost_today"]),
            realized_pnl_today_sol=Decimal(pos["realized_pnl_today"]),
            total_bought=int(pos["total_bought"]),
            total_won=int(pos["total_won"]),
            total_lost=int(pos["total_lost"]),
            total_pnl_sol=None if pos["total_pnl_sol"] is None else Decimal(pos["total_pnl_sol"]),
            best_trade_mint=None if best is None else str(best["mint"]),
            best_trade_pnl_sol=None if best is None else Decimal(best["pnl_sol"]),
            worst_trade_mint=None if worst is None else str(worst["mint"]),
            worst_trade_pnl_sol=None if worst is None else Decimal(worst["pnl_sol"]),
            fees_lamports_today=int(fees["network_fee_lamports"])
            + int(fees["program_fee_lamports"]),
            rent_lamports_today=(
                int(fees["ata_rent_lamports"])
                + int(fees["account_rent_lamports"])
                - int(fees["ata_rent_refund_lamports"])
            ),
            treasury_swaps_today=int(treasury["swaps_confirmed_today"]),
            treasury_usdc_spent_today=Decimal(treasury["usdc_spent_today"]),
            treasury_sol_bought_today=Decimal(treasury["sol_bought_today"]),
            kill_switch_day_start_sol_equity=(
                None
                if anchor is None or anchor["day_start_sol_equity"] is None
                else Decimal(anchor["day_start_sol_equity"])
            ),
            kill_switch_day_start_utc=None if anchor is None else anchor["day_start_utc"],
            first_treasury_swap_wallet_sol_before=(
                None if first_swap is None else Decimal(first_swap["wallet_sol_before"])
            ),
            first_treasury_swap_at=None if first_swap is None else first_swap["requested_at"],
        )
