"""``hb:meme:executor`` — what the desk and the API read about the executor.

Fields: the flag and the gates (dates, or the small-test scope), the wallet's
**public** key and its balance as last read by RPC (never the secret, never a
prefix of it), orders by state, open positions, blocked exits, the last
signature, the kill switch with its four sources, the day anchor and the loss
so far. Written every ``heartbeat_s`` onto the hash the runtime keeps alive.
T4.28 adds the stage-1 mode (``auto_approve``, ``auto_approved_1h``,
``auto_refused_1h`` by reason, ``auto_skipped`` by reason) and the written
scope's counters (``small_test_used_sol``, ``small_test_trades_done``,
``small_test_remaining_sol``, ``small_test_exhausted``) — what the desk shows as
"modo sozinho — estágio 1: n/5 compras, x/0,25 SOL".
"""

from __future__ import annotations

import json
import statistics
from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from hunter_core.db.session import role_session
from hunter_core.domain.types import utcnow
from hunter_core.logging import get_logger
from hunter_meme_executor.auto_approve import auto_approved_last_hour, auto_refused_last_hour
from hunter_meme_executor.context import ExecutorContext
from hunter_meme_executor.journal_db import WORKER_ROLE
from hunter_meme_executor.repo import open_positions, orders_by_state
from hunter_meme_executor.scope import read_scope_use
from hunter_meme_executor.send_tuning import SendTuning

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from hunter_meme_executor.conviction import ConvictionConfig
    from hunter_meme_executor.kill_switch import DayAnchor
    from hunter_risk_meme import MemeLimits

__all__ = [
    "daily_loss_fields",
    "gates_fields",
    "heartbeat_fields",
    "heartbeat_once",
    "policy_fields",
]

logger = get_logger(__name__)
LAMPORTS = Decimal(1_000_000_000)


def gates_fields(ctx: ExecutorContext) -> dict[str, str]:
    """The gates as published, plus (T4.28d) when the file was last written and
    when this process last swapped its policy from it — so the desk and ops can
    see a hot reload happened without reading the container's log."""
    state = ctx.state
    return {
        "gates": _gates(ctx),
        "gates_mtime": "" if state.gates_mtime is None else state.gates_mtime.isoformat(),
        "gates_reloaded_at": ""
        if state.gates_reloaded_at is None
        else state.gates_reloaded_at.isoformat(),
        "gates_reload_error": _reload_error(ctx),
    }


def _reload_error(ctx: ExecutorContext) -> str:
    """The latched reason, or (T4.28f) the parse failure this process is still
    giving one tick of grace — ``deferred:<reason>``. Empty means the last read
    of the file was a good one."""
    state = ctx.state
    if state.gates_invalid is not None:
        return state.gates_invalid
    if state.gates_deferred_failure is not None:
        return f"deferred:{state.gates_deferred_failure}"
    return ""


def _gates(ctx: ExecutorContext) -> str:
    gates = ctx.mode.gates
    if gates is None:
        return json.dumps({"live": False})
    payload: dict[str, object] = {
        "live": True,
        "engineering": gates.engineering_date.isoformat(),
        "evidence": gates.evidence_date.isoformat(),
        "owner": gates.owner_date.isoformat(),
        "signed_by": gates.signed_by,
        "valid_until": gates.valid_until.isoformat(),
    }
    if gates.small_test is not None:
        payload["small_test"] = {
            "authorized_by": gates.small_test.authorized_by,
            "max_sol_per_trade": str(gates.small_test.max_sol_per_trade),
            "max_total_sol": str(gates.small_test.max_total_sol),
            "max_trades": gates.small_test.max_trades,
            "expires_at": gates.small_test.expires_at.isoformat(),
            "decision_note": gates.small_test.decision_note,
        }
    return json.dumps(payload)


async def _auto_fields(
    ctx: ExecutorContext, session: AsyncSession, now: datetime
) -> dict[str, str]:
    """T4.28: the stage-1 mode and the scope counters, read from the rows."""
    cfg, state = ctx.config, ctx.state
    small = ctx.mode.gates.small_test if ctx.mode.gates is not None else None
    fields = {
        "auto_approve": str(cfg.auto_approve).lower(),
        "auto_approve_max_per_hour": str(cfg.auto_approve_max_per_hour),
        "auto_approved_1h": str(await auto_approved_last_hour(session, now=now)),
        "auto_refused_1h": json.dumps(await auto_refused_last_hour(session, now=now)),
        "auto_skipped": json.dumps(state.auto_skipped),
        "auto_rejected_total": str(state.auto_rejected),
    }
    if small is None:
        return fields
    scope = await read_scope_use(session, small, requested_sol=small.max_sol_per_trade)
    fields["small_test_used_sol"] = str(scope.used_sol)
    fields["small_test_trades_done"] = str(scope.trades_done)
    fields["small_test_remaining_sol"] = str(scope.remaining_sol)
    fields["small_test_exhausted"] = scope.exhausted or ""
    return fields


def _pickup_lag_fields(ctx: ExecutorContext) -> dict[str, str]:
    """T4.52a: p50/max of ``ctx.state.pickup_lags`` — the number R55 measured
    as "Proposal->Received" (4.8s p50 before the wake-up in ``wake.py``).
    Empty until the entries loop has seen its first candidate."""
    lags = ctx.state.pickup_lags
    if not lags:
        return {"proposal_pickup_lag_s_p50": "", "proposal_pickup_lag_s_max": ""}
    return {
        "proposal_pickup_lag_s_p50": f"{statistics.median(lags):.3f}",
        "proposal_pickup_lag_s_max": f"{max(lags):.3f}",
    }


def policy_fields(
    limits: MemeLimits, send: SendTuning | None = None, conviction: ConvictionConfig | None = None
) -> dict[str, object]:
    """The ``policy`` blob: the five the owner writes, the check-10 allowance,
    (T4.58) the curve-progress window this process admits with — published so the
    desk can see that its ``max_progress_pct`` gate cannot exceed it in practice —
    and (T4.59) the buy tolerance the instruction is built with (``send``; the
    profile's 1 % when absent, which is what the buy used before T4.59)."""
    buy_pct = (send or SendTuning()).buy_max_slippage_pct
    return {
        "profile": limits.profile,
        "wallet_max_sol": str(limits.wallet_max_sol),
        "max_sol_per_trade": str(limits.max_sol_per_trade),
        "daily_loss_cap_sol": str(limits.daily_loss_cap_sol),
        "max_open_positions": limits.max_open_positions,
        "rug_cooldown_s": limits.rug_cooldown_s,
        # T4.28h: an allowance on check 10 the owner turned on is a fact
        # about how this process admits, so it is published, not implied.
        "creator_unknown_allowed_if_dev_measured": limits.creator_unknown_allowed_if_dev_measured,
        "creator_unknown_max_dev_share_pct": str(limits.creator_unknown_max_dev_share_pct),
        "curve_progress_min_pct": str(limits.curve_progress_min_pct),
        "curve_progress_max_pct": str(limits.curve_progress_max_pct),
        "buy_max_slippage_pct": str(buy_pct),
        # T4.61b: whether the buy is sized by the conviction ladder or flat.
        "conviction_sizing": "on" if conviction is not None and conviction.enabled else "off",
    }


async def heartbeat_fields(ctx: ExecutorContext) -> dict[str, str]:
    cfg, state = ctx.config, ctx.state
    now = utcnow()
    async with role_session(ctx.session_factory, db_role=WORKER_ROLE) as session:
        by_state = await orders_by_state(session)
        positions = await open_positions(session)
        auto = await _auto_fields(ctx, session, now)
    limits = cfg.limits
    anchor = ctx.kill.anchor
    marks = sum((p.mark_sol or Decimal(0) for p in positions), Decimal(0))
    equity = (
        None if state.wallet_lamports is None else Decimal(state.wallet_lamports) / LAMPORTS + marks
    )
    fields: dict[str, str] = {
        "executor_ts": now.isoformat(),
        "label": "REAL",
        "live_enabled": str(cfg.live).lower(),
        "cluster": cfg.cluster,
        "wallet_pubkey": "" if ctx.signer is None else ctx.signer.pubkey,
        "wallet_sol_balance": ""
        if state.wallet_lamports is None
        else str(Decimal(state.wallet_lamports) / LAMPORTS),
        "wallet_read_at": "" if state.wallet_read_at is None else state.wallet_read_at.isoformat(),
        # T4.51: how old the published balance is — always shown, not only on a
        # failed refresh, so a stalled ``wallet_refresh_once`` (or a process that
        # predates it) is visible from the number itself, not inferred.
        "wallet_balance_stale_s": (
            ""
            if state.wallet_read_at is None
            else str((now - state.wallet_read_at).total_seconds())
        ),
        "policy": json.dumps(policy_fields(limits, cfg.send, cfg.conviction)),
        "orders_by_state": json.dumps(by_state),
        "positions_open": str(len(positions)),
        "blocked_exits": json.dumps(state.blocked_exits),
        "last_signature": state.last_signature or "",
        "last_refusal": state.last_refusal or "",
        "entries_seen": str(state.entries_seen),
        "entries_refused": str(state.entries_refused),
        "entries_confirmed": str(state.entries_confirmed),
        "exits_confirmed": str(state.exits_confirmed),
        "ata_closed": str(state.ata_closed),
        "rpc_errors": str(state.rpc_errors),
        # T4.45: how often this process had to read the rug numbers itself
        # because the radar's row had not landed, and how often that read gave
        # nothing usable (the admission refused by name each of those times).
        "risk_reads_on_demand": str(state.risk_reads_on_demand),
        "risk_reads_on_demand_failed": str(state.risk_reads_on_demand_failed),
        "auto_close_on_emergency": str(cfg.auto_close_on_emergency).lower(),
        "program_idl_hash": state.program_idl_hash or "",
        "program_last_deploy_slot": ""
        if state.program_last_deploy_slot is None
        else str(state.program_last_deploy_slot),
        "program_divergence": state.program_divergence or "",
        "last_entries_tick_at": ""
        if state.last_entries_tick_at is None
        else state.last_entries_tick_at.isoformat(),
        "last_exits_tick_at": ""
        if state.last_exits_tick_at is None
        else state.last_exits_tick_at.isoformat(),
    }
    fields.update(daily_loss_fields(anchor, equity, ctx.treasury_inflow.inflow_sol))
    fields.update(ctx.treasury_inflow.describe())
    fields.update(gates_fields(ctx))
    fields.update(auto)
    fields.update(ctx.kill.describe())
    fields.update(_pickup_lag_fields(ctx))
    fields["treasury"] = _treasury_field(ctx)
    fields.update(_send_fields(ctx))
    return fields


def daily_loss_fields(
    anchor: DayAnchor | None, equity: Decimal | None, inflow: Decimal | None
) -> dict[str, str]:
    """T4.60 — ``daily_loss_sol = day_start + treasury_inflow_today − equity``,
    the same arithmetic as ``MemeWalletState.daily_loss_sol``. YOU (18/09/2026):
    day start 0.686, loss 0.0395, a 0.0516 top-up at 13:12:06 — the old
    ``day_start − equity`` published ``0``; this publishes ``0.0395``. An
    inflow never read yet is published as unknown (empty), never as zero."""
    loss = ""
    if anchor is not None and equity is not None and inflow is not None:
        loss = str(max(Decimal(0), anchor.day_start_sol_equity + inflow - equity))
    return {
        "day_start_utc": "" if anchor is None else anchor.day_start_utc.isoformat(),
        "day_start_sol_equity": "" if anchor is None else str(anchor.day_start_sol_equity),
        "equity_sol": "" if equity is None else str(equity),
        "treasury_inflow_today_sol": "" if inflow is None else str(inflow),
        "daily_loss_sol": loss,
    }


def _send_fields(ctx: ExecutorContext) -> dict[str, str]:
    """T4.55 — the re-send loop and the dynamic priority fee, as numbers the desk
    can re-read after the deploy: how many re-sends this process made (and the
    last attempt's), how often the fee read failed (the floor was paid), and the
    last fee choice with every number that made it."""
    state, cfg = ctx.state, ctx.config
    reader = ctx.priority_fees
    return {
        "resends_total": str(state.resends_total),
        "resend_errors_total": str(state.resend_errors_total),
        "last_resends": str(state.last_resends),
        "resend_interval_s": str(cfg.send.resend_interval_s),
        "priority_fee_reads": "" if reader is None else str(reader.reads),
        "priority_fee_read_failures": str(state.priority_fee_read_failures),
        "priority_fee_last": json.dumps(state.last_priority_fee or {}),
        "exit_max_slippage_pct": str(cfg.send.exit_max_slippage_pct),
        "panic_exit_max_slippage_pct": str(cfg.send.panic_exit_max_slippage_pct),
    }


def _treasury_field(ctx: ExecutorContext) -> str:
    """T4.54 — one JSON blob: whether the top-up is on, when it last landed,
    the wallet's USDC as last read, and the last tick's outcome (empty when
    nothing was attempted this tick)."""
    cfg, state = ctx.config, ctx.state
    return json.dumps(
        {
            "enabled": cfg.treasury_enabled,
            "sol_floor": str(cfg.treasury_sol_floor),
            "sol_target": str(cfg.treasury_sol_target),
            "last_swap_at": (
                None
                if state.treasury_last_swap_at is None
                else state.treasury_last_swap_at.isoformat()
            ),
            "last_result": state.treasury_last_attempt_reason or "",
            "wallet_usdc": (
                None if state.treasury_wallet_usdc is None else str(state.treasury_wallet_usdc)
            ),
        }
    )


async def heartbeat_once(ctx: ExecutorContext) -> None:
    try:
        await ctx.heartbeat(await heartbeat_fields(ctx))
    except Exception:
        logger.warning("meme_executor_heartbeat_write_failed")
