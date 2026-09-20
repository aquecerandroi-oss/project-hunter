"""T4.74-5 — what a settled ``spot/1`` leg does to the book, shared by the
exits loop and the reconcile: ``settle_closed`` closes a position with the
chain's lamports (PnL = received − spent, R = pnl ÷ r_unit, ``exit->>'reason'``
set) and re-reads the lane state (design §8); ``open_from_order`` opens the
position of a buy that confirmed late, from the geometry the order's
``admission.spot1``/``intent`` kept (design §4). Nothing here signs or sends.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Any

from hunter_core.db.session import role_session
from hunter_core.logging import get_logger
from hunter_meme_executor.journal_db import WORKER_ROLE
from hunter_meme_executor.spot_exit_rules import lane_state
from hunter_meme_executor.spot_repo import close_position, closed_stats, insert_position

if TYPE_CHECKING:
    from hunter_meme_executor.context import ExecutorContext
    from hunter_meme_executor.spot_config import SpotConfig
    from hunter_meme_executor.spot_exit_repo import SpotOrderRow
    from hunter_meme_executor.spot_repo import SpotPosition
    from hunter_meme_executor.spot_stats import SpotStats

__all__ = ["open_from_order", "refresh_lane", "settle_closed"]

logger = get_logger(__name__)
LAMPORTS = Decimal(1_000_000_000)
_EPOCH = datetime(1970, 1, 1, tzinfo=UTC)


async def settle_closed(
    ctx: ExecutorContext,
    cfg: SpotConfig,
    stats: SpotStats,
    position: SpotPosition,
    *,
    order_id: str,
    exit_payload: dict[str, Any],
    now: datetime,
) -> bool:
    """``close_position`` with the chain's lamports (PnL = received − spent, R =
    pnl ÷ r_unit), then the lane state re-read — shared with the reconcile."""
    received = int(exit_payload["sol_delta_lamports"])
    async with role_session(ctx.session_factory, db_role=WORKER_ROLE) as session:
        closed = await close_position(
            session,
            position.id,
            exit_order_id=order_id,
            exit_at=now,
            exit_payload=exit_payload,
            sol_received_lamports=received,
            sol_spent_lamports=position.sol_spent_lamports,
            initial_risk_sol=position.initial_risk_sol,
            now=now,
        )
    if not closed:
        logger.warning("meme_spot_close_not_open", position_id=position.id, order_id=order_id)
        return False
    reason = str(exit_payload.get("reason") or "unknown")
    stats.record_exit(reason)
    stats.sells_confirmed += 1
    stats.forget_position(position.id)
    ctx.state.exits_confirmed += 1
    pnl = Decimal(received - position.sol_spent_lamports) / LAMPORTS
    logger.info(
        "meme_spot_position_closed",
        position_id=position.id,
        market=position.market_symbol,
        reason=reason,
        sol_received_lamports=received,
        pnl_sol=str(pnl),
        r_multiple=str(pnl / position.initial_risk_sol),
    )
    await refresh_lane(ctx, cfg, stats, now=now)
    return True


async def refresh_lane(
    ctx: ExecutorContext, cfg: SpotConfig, stats: SpotStats, *, now: datetime
) -> None:
    """Design §8, at every close: the refutation/cooldown re-read from the rows."""
    async with role_session(ctx.session_factory, db_role=WORKER_ROLE) as session:
        closed = await closed_stats(
            session, since=cfg.refutation_reset_at or _EPOCH, min_trades=cfg.refute_min_trades
        )
    state = lane_state(
        closed,
        now=now,
        refute_min_trades=cfg.refute_min_trades,
        refute_max_loss_sol=cfg.refute_max_loss_sol,
        consecutive_stops_pause_s=cfg.consecutive_stops_pause_s,
    )
    if stats.lane is None or state.state != stats.lane.state:
        logger.warning("meme_spot_lane_state", state=state.state, reason=state.reason)
    stats.closed, stats.lane = closed, state


async def open_from_order(
    ctx: ExecutorContext,
    cfg: SpotConfig,
    stats: SpotStats,
    row: SpotOrderRow,
    fill: dict[str, Any],
    now: datetime,
) -> str | None:
    """The late-confirmed buy as a position (design §4), from what the order
    kept: ``admission.spot1.geometry`` (``stop_frac``/``target_frac``/
    ``horizon_s``), ``admission.spot1.parity`` and ``intent.ticket_sol``."""
    tokens, rent = int(fill.get("filled_atoms") or 0), int(fill.get("ata_rent_lamports") or 0)
    delta = int(fill.get("sol_delta_lamports") or 0)
    spent, spent_source = -delta - rent, "signature_delta_minus_rent"
    if spent <= 0:
        spent, rent, spent_source = -delta, 0, "signature_delta_rent_folded"
    spot1 = dict(row.admission.get("spot1") or {})
    geometry = dict(spot1.get("geometry") or {})
    parity = dict(spot1.get("parity") or {})
    stop_frac = _decimal(geometry.get("stop_frac"))
    ticket = _decimal(row.intent.get("ticket_sol"))
    if stop_frac is None or stop_frac <= 0 or ticket is None or ticket <= 0:
        logger.error("meme_spot_reconcile_geometry_missing", order_id=row.id, geometry=geometry)
        return None  # confirmed row, no position: named in the log, sold by hand
    if tokens <= 0 or spent <= 0:
        logger.error("meme_spot_reconcile_fill_unusable", order_id=row.id, fill=fill)
        return None
    r_unit = ticket * stop_frac
    params: dict[str, Any] = {
        "stop_frac": str(stop_frac),
        "target_frac": geometry.get("target_frac"),
        "horizon_s": geometry.get("horizon_s"),
        "entry_sol_per_atom": str(Decimal(spent) / LAMPORTS / Decimal(tokens)),
        "r_unit_sol": str(r_unit),
        "sol_usd_at_entry": parity.get("sol_usd"),
        "bin_usd_at_entry": parity.get("bin_usd"),
        "jup_usd_at_entry": parity.get("jup_usd"),
        "ata_rent_lamports": rent,
        "decimals": spot1.get("decimals"),
        "strategy_version": row.intent.get("strategy_version") or cfg.strategy_version,
        "opened_by": "reconcile",
    }
    entry = {
        "order_id": row.id,
        "signature": row.signature,
        "filled_atoms": tokens,
        "sol_delta_lamports": delta,
        "sol_spent_lamports": spent,
        "sol_spent_source": spent_source,
        "ata_rent_lamports": rent,
        "quoted_out_atoms": fill.get("quoted_out_atoms"),
        "opened_by": "reconcile",
    }
    # The horizon runs from when the buy **landed**, never from when this
    # process noticed (Astra): the block time when the meta had it, else the
    # leg's own confirmation instant, else the submission — the earliest it
    # could have landed, so a late repair never grants extra hours.
    entry_at = _stamp(fill.get("landed_at")) or _stamp(fill.get("confirmed_at")) or row.submitted_at
    params["entry_at_source"] = (
        "block_time"
        if fill.get("landed_at")
        else ("leg_confirmed_at" if fill.get("confirmed_at") else "submitted_at")
    )
    async with role_session(ctx.session_factory, db_role=WORKER_ROLE) as session:
        position_id = await insert_position(
            session,
            signal_id=row.signal_id,
            entry_order_id=row.id,
            market_symbol=row.market_symbol,
            mint=row.mint,
            entry_at=entry_at,
            entry=entry,
            tokens=tokens,
            sol_spent_lamports=spent,
            initial_risk_sol=r_unit,
            params=params,
            ata_rent_lamports=rent,
            now=now,
        )
    if position_id is None:
        return None  # the entries loop opened it meanwhile (unique on the signal)
    stats.reconciled_buys += 1
    stats.buys_confirmed += 1
    ctx.state.entries_confirmed += 1
    logger.info(
        "meme_spot_position_opened",
        position_id=position_id,
        market=row.market_symbol,
        tokens=tokens,
        sol_spent_lamports=spent,
        opened_by="reconcile",
    )
    return position_id


def _stamp(value: Any) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    return parsed if parsed.tzinfo is not None else None


def _decimal(value: Any) -> Decimal | None:
    if value is None or value == "":
        return None
    try:
        parsed = Decimal(str(value))
    except ArithmeticError:
        return None
    return parsed if parsed.is_finite() else None
