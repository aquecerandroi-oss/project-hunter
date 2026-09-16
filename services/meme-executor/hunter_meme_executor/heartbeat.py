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

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

__all__ = ["gates_fields", "heartbeat_fields", "heartbeat_once"]

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
        "gates_reload_error": state.gates_invalid or "",
    }


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
        "policy": json.dumps(
            {
                "profile": limits.profile,
                "wallet_max_sol": str(limits.wallet_max_sol),
                "max_sol_per_trade": str(limits.max_sol_per_trade),
                "daily_loss_cap_sol": str(limits.daily_loss_cap_sol),
                "max_open_positions": limits.max_open_positions,
                "rug_cooldown_s": limits.rug_cooldown_s,
            }
        ),
        "orders_by_state": json.dumps(by_state),
        "positions_open": str(len(positions)),
        "blocked_exits": json.dumps(state.blocked_exits),
        "last_signature": state.last_signature or "",
        "last_refusal": state.last_refusal or "",
        "entries_seen": str(state.entries_seen),
        "entries_refused": str(state.entries_refused),
        "entries_confirmed": str(state.entries_confirmed),
        "exits_confirmed": str(state.exits_confirmed),
        "rpc_errors": str(state.rpc_errors),
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
        "day_start_utc": "" if anchor is None else anchor.day_start_utc.isoformat(),
        "day_start_sol_equity": "" if anchor is None else str(anchor.day_start_sol_equity),
        "equity_sol": "" if equity is None else str(equity),
        "daily_loss_sol": ""
        if anchor is None or equity is None
        else str(max(Decimal(0), anchor.day_start_sol_equity - equity)),
    }
    fields.update(gates_fields(ctx))
    fields.update(auto)
    fields.update(ctx.kill.describe())
    return fields


async def heartbeat_once(ctx: ExecutorContext) -> None:
    try:
        await ctx.heartbeat(await heartbeat_fields(ctx))
    except Exception:
        logger.warning("meme_executor_heartbeat_write_failed")
