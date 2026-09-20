"""T4.74-4 — the entries loop of the ``spot/1`` desk (design §2, §3, §6, §8):
a Lab ``mean_reversion`` signal → the parity/geometry readings
(``spot_entry_reads``) → the pure ``evaluate_spot_entry`` → one ``spot_orders``
row **whatever the verdict** → only an ``approved`` decision reaches
``spot_leg`` → a ``confirmed`` buy opens the position with the signal's geometry.

Inert without ``config.spot.enabled`` (flag + live + signer): not one query.
The lane state (``refuted``/``cooldown``, §8) is re-read from the closed
positions on every tick and refuses before any candidate is fetched. At most
**one** buy per tick; the newest signal first; a signal that got a row is
never picked again (``NOT EXISTS spot_orders … side = 'buy'``). A tick that
raises is logged and counted, never propagated: this lane must not take the
meme loops down with it.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Any

from hunter_core.db.session import role_session
from hunter_core.domain.types import utcnow
from hunter_core.logging import get_logger
from hunter_exchanges.jupiter import WRAPPED_SOL_MINT
from hunter_meme_executor.admission import wallet_from
from hunter_meme_executor.journal_db import WORKER_ROLE
from hunter_meme_executor.spot_config import SPOT_DECIDED_BY, SpotConfig
from hunter_meme_executor.spot_entry_reads import ENTRY_SLIPPAGE_BPS, ReadRefusal, gather_reads
from hunter_meme_executor.spot_entry_writes import open_position, refuse_row
from hunter_meme_executor.spot_exit_rules import lane_state
from hunter_meme_executor.spot_repo import (
    SpotCandidate,
    candidate_signals,
    closed_stats,
    insert_order,
    mark_refused,
)
from hunter_meme_executor.spot_send import spot_leg
from hunter_meme_executor.spot_send_rules import spot_client_order_id
from hunter_meme_executor.spot_signals import signal_inputs
from hunter_meme_executor.spot_stats import SpotStats
from hunter_meme_executor.treasury_inflow import ensure_anchor
from hunter_risk_meme import evaluate_spot_entry
from hunter_risk_meme.spot_profile import SPOT_LANE

if TYPE_CHECKING:
    from hunter_meme_executor.context import ExecutorContext

__all__ = ["handle_spot_candidate", "spot_config_of", "spot_entries_once", "spot_stats_of"]

logger = get_logger(__name__)
LAMPORTS = Decimal(1_000_000_000)
_EPOCH = datetime(1970, 1, 1, tzinfo=UTC)


def spot_config_of(ctx: ExecutorContext) -> SpotConfig:
    """``config.spot`` once T4.74-5 wires it; an inert default before that."""
    spot = getattr(ctx.config, "spot", None)
    return spot if isinstance(spot, SpotConfig) else SpotConfig()


def spot_stats_of(ctx: ExecutorContext) -> SpotStats:
    stats = getattr(ctx, "spot", None)
    return stats if isinstance(stats, SpotStats) else SpotStats()


async def spot_entries_once(ctx: ExecutorContext) -> None:
    """One pass (``main.py``, 15 s). Nothing runs — no query, no quote — unless
    the lane is enabled; a failure inside is counted, never raised."""
    cfg = spot_config_of(ctx)
    if not cfg.enabled:
        return
    stats = spot_stats_of(ctx)
    now = utcnow()
    stats.last_entries_tick_at = now
    try:
        await _tick(ctx, cfg, stats, now)
    except Exception as exc:
        stats.tick_failures += 1
        ctx.state.rpc_errors += 1
        logger.exception("meme_spot_entries_tick_failed", error_type=type(exc).__name__)


async def _tick(ctx: ExecutorContext, cfg: SpotConfig, stats: SpotStats, now: datetime) -> None:
    await ctx.kill.refresh()
    async with role_session(ctx.session_factory, db_role=WORKER_ROLE) as session:
        closed = await closed_stats(session, since=cfg.refutation_reset_at or _EPOCH)
    state = lane_state(
        closed,
        now=now,
        refute_min_trades=cfg.refute_min_trades,
        refute_max_loss_sol=cfg.refute_max_loss_sol,
        consecutive_stops_pause_s=cfg.consecutive_stops_pause_s,
    )
    stats.closed, stats.lane = closed, state
    if state.refusal is not None:
        stats.last_refusal = state.refusal
        logger.warning("meme_spot_lane_closed", state=state.state, reason=state.reason)
        return
    async with role_session(ctx.session_factory, db_role=WORKER_ROLE) as session:
        candidates = await candidate_signals(
            session, version=cfg.strategy_version, max_age_s=cfg.max_signal_age_s, now=now, limit=1
        )
    for candidate in candidates[:1]:
        stats.signals_seen += 1
        await handle_spot_candidate(ctx, cfg, stats, candidate, now=utcnow())


def _record_refusal(ctx: ExecutorContext, stats: SpotStats, reason: str) -> None:
    stats.record_refusal(reason)
    ctx.state.entries_refused += 1
    ctx.state.last_refusal = reason


async def handle_spot_candidate(
    ctx: ExecutorContext,
    cfg: SpotConfig,
    stats: SpotStats,
    candidate: SpotCandidate,
    *,
    now: datetime,
) -> None:
    if ctx.signer is None or not ctx.mode.live:
        return  # inert by construction (``SpotConfig.enabled`` already said so)
    limits = ctx.config.limits
    ticket = cfg.ticket(limits)
    ticket_lamports = int(ticket * LAMPORTS)
    intent: dict[str, Any] = {
        "lane": SPOT_LANE,
        "side": "buy",
        "input_mint": WRAPPED_SOL_MINT,
        "output_mint": candidate.mint,
        "amount_atoms": ticket_lamports,
        "slippage_bps": ENTRY_SLIPPAGE_BPS,
        "max_priority_fee_lamports": cfg.priority_fee_max_lamports,
        "max_sol_cost_sol": str(ticket),
        "ticket_sol": str(ticket),
        "market_symbol": candidate.market_symbol,
        "strategy_version": cfg.strategy_version,
    }
    if ctx.kill.blocks_entries:
        admission = dict(ctx.kill.describe())
        await refuse_row(
            ctx,
            stats,
            candidate,
            "kill_switch_blocked",
            admission,
            intent=intent,
            quote=None,
            now=now,
        )
        return
    reads = await gather_reads(
        ctx, cfg, candidate, ticket=ticket, ticket_lamports=ticket_lamports, now=now
    )
    if reads is None:
        return  # transient: no row, the signal is retried next tick while it is fresh
    if isinstance(reads, ReadRefusal):
        await refuse_row(
            ctx, stats, candidate, reads.reason, reads.detail, intent=intent, quote=None, now=now
        )
        return
    readings = reads.readings(cfg, limits)
    signal = signal_inputs(
        candidate,
        parity=reads.parity,
        quote_impact_pct=max(Decimal(0), reads.quote.price_impact_pct),
        priority_fee_sol=Decimal(cfg.priority_fee_max_lamports) / LAMPORTS,
        open_spot_markets=reads.open_spot_markets,
        pending_spot_markets=reads.pending_spot_markets,
    )
    if signal is None or not reads.geometry_complete:
        reason = f"geometry_unavailable:{reads.geo.reason or 'incomplete'}"
        await refuse_row(
            ctx, stats, candidate, reason, readings, intent=intent, quote=reads.quote, now=now
        )
        return
    equity = Decimal(reads.balance.lamports) / LAMPORTS + reads.marks_sol
    anchor = await ensure_anchor(ctx, now, equity)
    inflow = ctx.treasury_inflow.inflow_sol
    if anchor is None or inflow is None:
        admission = {**readings, **ctx.treasury_inflow.describe()}
        await refuse_row(
            ctx,
            stats,
            candidate,
            "day_anchor_unavailable",
            admission,
            intent=intent,
            quote=reads.quote,
            now=now,
        )
        return
    wallet = wallet_from(
        wallet_id=ctx.signer.pubkey,
        now=now,
        balance=reads.balance,
        positions=reads.positions,
        pending=reads.pending,
        anchor=anchor,
        limits=limits,
        treasury_inflow_today_sol=inflow,
    )
    decision = evaluate_spot_entry(
        wallet, limits, cfg.profile(limits), signal, ctx.kill.inputs(), now
    )
    if any(c.refusal == "daily_loss_cap_reached" for c in decision.checks):
        await ctx.kill.latch("daily_loss_cap_reached")
    admission = decision.to_jsonable()
    admission["decided_by"] = SPOT_DECIDED_BY
    admission["spot1"] = readings
    # The gate is ``approved`` — the sizing is published on refusals too (T4.74-2).
    approved = decision.approved and decision.sizing is not None
    reason = None if approved else (decision.first_refusal or "refused")
    if decision.sizing is not None and approved:
        intent["max_sol_cost_sol"] = str(decision.sizing.max_sol_cost_sol or ticket)
        intent["sol_final"] = str(decision.sizing.sol_final)
    async with role_session(ctx.session_factory, db_role=WORKER_ROLE) as session:
        order_id = await insert_order(
            session,
            signal_id=candidate.signal_id,
            market_symbol=candidate.market_symbol,
            mint=candidate.mint,
            side="buy",
            client_order_id=spot_client_order_id(candidate.signal_id, side="buy"),
            attempt=1,
            status="admitted" if approved else "refused",
            reason=reason,
            intent=intent,
            admission=admission,
            quote=dict(reads.quote.raw),
            now=now,
        )
    if order_id is None:
        return  # another pass owns this key (idempotent on the signal)
    if not approved:
        _record_refusal(ctx, stats, reason or "refused")
        logger.warning("meme_spot_entry_refused", signal_id=candidate.signal_id, reason=reason)
        return
    stats.admitted += 1
    await ctx.kill.refresh()
    if ctx.kill.blocks_entries:
        blocked = "kill_switch_blocked_before_signing"
        async with role_session(ctx.session_factory, db_role=WORKER_ROLE) as session:
            await mark_refused(session, order_id, reason=blocked, now=utcnow())
        _record_refusal(ctx, stats, blocked)
        return
    result = await spot_leg(
        ctx,
        order_id=order_id,
        input_mint=WRAPPED_SOL_MINT,
        output_mint=candidate.mint,
        amount_atoms=ticket_lamports,
        slippage_bps=ENTRY_SLIPPAGE_BPS,
        max_priority_fee_lamports=cfg.priority_fee_max_lamports,
        quote=reads.quote,
    )
    if result.signature:
        stats.last_signature = result.signature
    if result.status == "submitted_unconfirmed":
        stats.buys_unconfirmed += 1  # no position yet: the reconcile (T4.74-5) settles it
        return
    if result.status != "confirmed":
        _record_refusal(ctx, stats, result.reason or result.status)
        return
    await open_position(
        ctx,
        stats,
        candidate,
        order_id,
        result,
        reads,
        ticket=ticket,
        cfg=cfg,
    )
