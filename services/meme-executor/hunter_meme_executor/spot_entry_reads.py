"""T4.74-4 — what one ``spot/1`` admission reads before it decides (split from
``spot_entries.py`` for the 350-line budget; the writes are in
``spot_entry_writes.py``): the mint's decimals (once, written back to the map), the wallet, the
buy quote of the whole ticket, the two final 1 m closes (``bin_usd``,
``sol_usd``), every open position of every lane and every pending buy — then
the parity and the geometry, pure. Nothing here signs or sends.
"""

from __future__ import annotations

import asyncio
import base64
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Any

from hunter_core.db.session import role_session
from hunter_core.logging import get_logger
from hunter_exchanges.base import ExchangeError
from hunter_exchanges.jupiter import WRAPPED_SOL_MINT
from hunter_meme_executor.journal_db import WORKER_ROLE
from hunter_meme_executor.repo import OpenPosition, PendingAttempt, pending_attempts
from hunter_meme_executor.spot_brake import brake_positions
from hunter_meme_executor.spot_config import SpotConfig
from hunter_meme_executor.spot_repo import (
    PendingSpotIntent,
    SpotCandidate,
    pending_spot_markets,
    set_market_decimals,
)
from hunter_meme_executor.spot_signals import (
    SOL_SYMBOL,
    FinalClose,
    Geometry,
    Parity,
    geometry,
    latest_final_close,
    parity_ratio,
)
from hunter_risk_meme.spot_profile import SPOT_LANE

if TYPE_CHECKING:
    from hunter_exchanges.jupiter import JupiterQuote
    from hunter_meme_executor.chain import WalletRead
    from hunter_meme_executor.context import ExecutorContext
    from hunter_risk_meme import MemeLimits

__all__ = [
    "ENTRY_SLIPPAGE_BPS",
    "PRICE_MAX_AGE_S",
    "EntryReads",
    "ReadRefusal",
    "gather_reads",
    "read_decimals",
    "text",
]

logger = get_logger(__name__)
LAMPORTS = Decimal(1_000_000_000)
ENTRY_SLIPPAGE_BPS = 50
"""The buy's tolerance — the 50 bps the design gives the mark's quote and the exit."""
PRICE_MAX_AGE_S = 180
"""Design §2: ``bin_usd``/``sol_usd`` must have closed within this of the decision."""
_WSOL_DECIMALS = 9


@dataclass(frozen=True, slots=True)
class ReadRefusal:
    reason: str
    detail: dict[str, Any]


@dataclass(frozen=True, slots=True)
class EntryReads:
    decimals: int
    balance: WalletRead
    quote: JupiterQuote
    bin_close: FinalClose | None
    sol_close: FinalClose | None
    positions: list[OpenPosition]
    pending: list[PendingAttempt]
    spot_pending: list[PendingSpotIntent]
    parity: Parity
    geo: Geometry

    @property
    def open_spot_markets(self) -> tuple[str, ...]:
        return tuple(
            str(p.params.get("market_symbol"))
            for p in self.positions
            if p.params.get("lane") == SPOT_LANE and p.params.get("market_symbol")
        )

    @property
    def pending_spot_markets(self) -> tuple[str, ...]:
        return tuple(p.market_symbol for p in self.spot_pending)

    @property
    def marks_sol(self) -> Decimal:
        return sum((p.mark_sol or Decimal(0) for p in self.positions), Decimal(0))

    @property
    def geometry_complete(self) -> bool:
        g = self.geo
        return g.stop_frac is not None and g.target_frac is not None and g.horizon_s is not None

    def readings(self, cfg: SpotConfig, limits: MemeLimits) -> dict[str, Any]:
        """What the row keeps beside the engine's checks: the two prices with their
        candle stamps, the geometry, the decimals and the config that decided."""
        p, g = self.parity, self.geo
        return {
            "parity": {
                "ratio": text(p.ratio),
                "reason": p.reason,
                "jup_usd": text(p.jup_usd),
                "bin_usd": text(p.bin_usd),
                "sol_usd": text(p.sol_usd),
            },
            "candles": {
                "bin_close_time": _stamp(self.bin_close),
                "sol_close_time": _stamp(self.sol_close),
            },
            "geometry": {
                "stop_frac": text(g.stop_frac),
                "target_frac": text(g.target_frac),
                "horizon_s": g.horizon_s,
                "reason": g.reason,
            },
            "decimals": self.decimals,
            "config": cfg.as_json(limits),
        }


def text(value: Decimal | None) -> str | None:
    return None if value is None else str(value)


def _stamp(close: FinalClose | None) -> str | None:
    return None if close is None else close.close_time.isoformat()


def read_decimals(rpc: Any, mint: str) -> int:
    """SPL ``Mint``: ``decimals`` is the byte at offset 44 (Token and Token-2022 alike)."""
    if mint == WRAPPED_SOL_MINT:
        return _WSOL_DECIMALS
    snapshot = rpc.get_account(mint, commitment="confirmed")
    if snapshot is None:
        raise LookupError("mint_not_found")
    raw = base64.b64decode(snapshot.data_base64)
    if len(raw) < 45:
        raise ValueError("mint_account_too_short")
    return raw[44]


async def gather_reads(
    ctx: ExecutorContext,
    cfg: SpotConfig,
    candidate: SpotCandidate,
    *,
    ticket: Decimal,
    ticket_lamports: int,
    now: datetime,
) -> EntryReads | ReadRefusal | None:
    """``None`` = a transient failure (no row; the signal is retried next tick
    while it is fresh); a :class:`ReadRefusal` = a named refusal to write."""
    assert ctx.signer is not None
    decimals = candidate.decimals
    if decimals is None:
        try:
            decimals = await asyncio.to_thread(read_decimals, ctx.chain.rpc, candidate.mint)
        except Exception as exc:
            return ReadRefusal(f"decimals_unavailable:{type(exc).__name__}", {})
        async with role_session(ctx.session_factory, db_role=WORKER_ROLE) as session:
            await set_market_decimals(session, candidate.market_symbol, decimals, now=now)
    try:
        balance = await asyncio.to_thread(ctx.chain.wallet, ctx.signer.pubkey)
    except Exception as exc:
        ctx.state.rpc_errors += 1
        logger.warning("meme_spot_wallet_unreadable", error_type=type(exc).__name__)
        return None
    ctx.state.wallet_lamports, ctx.state.wallet_read_at = balance.lamports, balance.observed_at
    try:
        quote = await asyncio.to_thread(
            ctx.treasury_client.quote,
            input_mint=WRAPPED_SOL_MINT,
            output_mint=candidate.mint,
            amount=ticket_lamports,
            slippage_bps=ENTRY_SLIPPAGE_BPS,
        )
    except ExchangeError as exc:
        if exc.retryable:
            logger.warning("meme_spot_quote_unavailable", error_type=type(exc).__name__)
            return None
        return ReadRefusal(f"quote_refused:{type(exc).__name__}", {"detail": str(exc)[:200]})
    async with role_session(ctx.session_factory, db_role=WORKER_ROLE) as session:
        closes = [
            await latest_final_close(
                session,
                symbol=symbol,
                exchange_id=candidate.exchange_id,
                market_type=candidate.market_type,
                now=now,
                max_age_s=PRICE_MAX_AGE_S,
            )
            for symbol in (candidate.market_symbol, SOL_SYMBOL)
        ]
        positions = await brake_positions(session)
        pending = await pending_attempts(session)
        spot_pending = await pending_spot_markets(session)
    bin_close, sol_close = closes
    pending.extend(
        PendingAttempt(p.signal_id, p.mint, p.reserved_sol, lane=SPOT_LANE) for p in spot_pending
    )
    parity = parity_ratio(
        ticket_sol=ticket,
        sol_usd=None if sol_close is None else sol_close.close,
        out_amount_atoms=int(quote.out_amount),
        decimals=decimals,
        units_per_binance_unit=candidate.units_per_binance_unit,
        bin_usd=None if bin_close is None else bin_close.close,
    )
    geo = geometry(
        reference_price=candidate.reference_price,
        stop=candidate.stop,
        target1=candidate.target1,
        expected_holding_s=candidate.expected_holding_s,
        max_hold_s=cfg.max_hold_s,
    )
    return EntryReads(
        decimals,
        balance,
        quote,
        bin_close,
        sol_close,
        positions,
        pending,
        spot_pending,
        parity,
        geo,
    )
