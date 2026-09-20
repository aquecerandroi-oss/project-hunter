"""T4.74-4 — the two writes of a ``spot/1`` entry besides the admitted row:
the refused row of a signal that never reached the engine (a named reason,
never picked again) and the position a **confirmed** buy opens with the
signal's geometry (design §4). Nothing here signs or sends.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Any

from hunter_core.db.session import role_session
from hunter_core.domain.types import utcnow
from hunter_core.logging import get_logger
from hunter_meme_executor.journal_db import WORKER_ROLE
from hunter_meme_executor.spot_config import SPOT_DECIDED_BY, SpotConfig
from hunter_meme_executor.spot_entry_reads import EntryReads, text
from hunter_meme_executor.spot_repo import SpotCandidate, insert_order, insert_position
from hunter_meme_executor.spot_send_rules import LegResult, spot_client_order_id

if TYPE_CHECKING:
    from hunter_exchanges.jupiter import JupiterQuote
    from hunter_meme_executor.context import ExecutorContext
    from hunter_meme_executor.spot_stats import SpotStats

__all__ = ["open_position", "refuse_row"]

logger = get_logger(__name__)
LAMPORTS = Decimal(1_000_000_000)


async def refuse_row(
    ctx: ExecutorContext,
    stats: SpotStats,
    candidate: SpotCandidate,
    reason: str,
    admission: dict[str, Any],
    *,
    intent: dict[str, Any],
    quote: JupiterQuote | None,
    now: datetime,
) -> None:
    """A refused row for the signal: the reason is on it, and it is never picked again."""
    async with role_session(ctx.session_factory, db_role=WORKER_ROLE) as session:
        await insert_order(
            session,
            signal_id=candidate.signal_id,
            market_symbol=candidate.market_symbol,
            mint=candidate.mint,
            side="buy",
            client_order_id=spot_client_order_id(candidate.signal_id, side="buy"),
            attempt=1,
            status="refused",
            reason=reason,
            intent=intent,
            admission={"decided_by": SPOT_DECIDED_BY, "refusal": reason, **admission},
            quote=None if quote is None else dict(quote.raw),
            now=now,
        )
    stats.record_refusal(reason)
    ctx.state.entries_refused += 1
    ctx.state.last_refusal = reason
    logger.warning(
        "meme_spot_entry_refused",
        signal_id=candidate.signal_id,
        market=candidate.market_symbol,
        reason=reason,
    )


async def open_position(
    ctx: ExecutorContext,
    stats: SpotStats,
    candidate: SpotCandidate,
    order_id: str,
    result: LegResult,
    reads: EntryReads,
    *,
    ticket: Decimal,
    cfg: SpotConfig,
) -> str | None:
    """The confirmed buy as a position with the signal's geometry (design §4)."""
    tokens = result.filled_atoms
    rent = result.ata_rent_lamports
    spent = -result.sol_delta_lamports - rent
    spent_source = "signature_delta_minus_rent"
    if spent <= 0:
        # The leg only confirms a buy whose signature spent SOL (``sol_delta < 0``);
        # a delta smaller than the rent it says it locked is a contradiction — keep
        # the whole outflow as the cost, rent folded in, and say so. Never the ticket.
        spent, rent, spent_source = -result.sol_delta_lamports, 0, "signature_delta_rent_folded"
        logger.warning("meme_spot_rent_folded_into_spent", order_id=order_id, delta=-spent)
    geo, parity = reads.geo, reads.parity
    stop_frac = geo.stop_frac or Decimal(0)
    r_unit = ticket * stop_frac
    params: dict[str, Any] = {
        "ref": str(candidate.reference_price),
        "stop_price": str(candidate.stop),
        "target1_price": str(candidate.target1),
        "stop_frac": str(stop_frac),
        "target_frac": str(geo.target_frac),
        "horizon_s": geo.horizon_s,
        "entry_sol_per_atom": str(Decimal(spent) / LAMPORTS / Decimal(tokens)),
        "r_unit_sol": str(r_unit),
        "sol_usd_at_entry": text(parity.sol_usd),
        "bin_usd_at_entry": text(parity.bin_usd),
        "jup_usd_at_entry": text(parity.jup_usd),
        "ata_rent_lamports": rent,
        "decimals": reads.decimals,
        "units_per_binance_unit": str(candidate.units_per_binance_unit),
        "strategy_version": cfg.strategy_version,
        "signal_emitted_at": candidate.emitted_at.isoformat(),
        "priority_fee_lamports": result.priority_fee_lamports,
    }
    entry = {
        "order_id": order_id,
        "signature": result.signature,
        "filled_atoms": tokens,
        "sol_delta_lamports": result.sol_delta_lamports,
        "sol_spent_lamports": spent,
        "sol_spent_source": spent_source,
        "ata_rent_lamports": rent,
        "quoted_out_atoms": int(reads.quote.out_amount),
    }
    now = utcnow()
    async with role_session(ctx.session_factory, db_role=WORKER_ROLE) as session:
        position_id = await insert_position(
            session,
            signal_id=candidate.signal_id,
            entry_order_id=order_id,
            market_symbol=candidate.market_symbol,
            mint=candidate.mint,
            entry_at=now,
            entry=entry,
            tokens=tokens,
            sol_spent_lamports=spent,
            initial_risk_sol=r_unit,
            params=params,
            ata_rent_lamports=rent,
            now=now,
        )
    stats.buys_confirmed += 1
    ctx.state.entries_confirmed += 1
    logger.info(
        "meme_spot_position_opened",
        position_id=position_id,
        market=candidate.market_symbol,
        tokens=tokens,
        sol_spent_lamports=spent,
        r_unit_sol=str(r_unit),
        signature=result.signature,
    )
    return position_id
