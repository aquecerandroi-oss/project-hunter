"""T4.74-5 — the ``spot1`` JSON field of ``hb:meme:executor`` (design §7):
``mode`` (``on`` / ``inert:<reason>`` / ``refuted`` / ``cooldown``), the
config that decides, the open positions with R now, the counters by reason,
the closed numbers, the refutation meter and the last instants.

Pure over what the caller already holds — no query, no quote: the open
positions come from the heartbeat's own ``brake_positions`` read (the spot
rows are money on the chain and are read in every mode), the counters from
``ctx.spot``. With ``SPOT1_ENABLED=false`` this publishes ``inert:disabled``
(no entries) next to ``exits_active`` (T4.74-7: the exits loop runs on any
live executor with a signer) and touches nothing else. ``stuck_exits`` names
the positions whose sell keeps being refused transiently (A2). T4.86 adds the
reconcile's own named outcome (``last_reconcile_result``) and its pending
meter (``pending_unconfirmed`` / ``oldest_pending_s``) — from the same stats
object, no query. Every ``Decimal`` is a string.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Any

from hunter_meme_executor.spot_entries import spot_stats_of
from hunter_meme_executor.spot_exits import STALE_AFTER_FAILURES, exits_active

if TYPE_CHECKING:
    from hunter_meme_executor.context import ExecutorContext
    from hunter_meme_executor.repo import OpenPosition
    from hunter_meme_executor.spot_config import SpotConfig

__all__ = ["TOP_REFUSALS", "spot1_fields"]

LAMPORTS = Decimal(1_000_000_000)
TOP_REFUSALS = 8


def spot1_fields(
    ctx: ExecutorContext,
    config: SpotConfig,
    now: datetime,
    *,
    positions: Sequence[OpenPosition] = (),
    markets_enabled: int | None = None,
) -> dict[str, Any]:
    """``positions``: the spot rows as ``brake_positions`` maps them
    (``params.lane = spot``); ``markets_enabled``: read by the caller only when
    the lane is on (``None`` is published as ``null``, never as ``0``)."""
    stats = spot_stats_of(ctx)
    lane = stats.lane
    mode = "on" if config.enabled else f"inert:{config.inert_reason}"
    if config.enabled and lane is not None and lane.state != "on":
        mode = lane.state
    closed = stats.closed
    limits = ctx.config.limits
    open_rows = [_open_row(p, stats, now) for p in positions]
    stale = [row["mark_stale_s"] for row in open_rows if row["mark_stale"] is True]
    return {
        "mode": mode,
        "exits_active": exits_active(config),
        "lane_reason": None if lane is None else lane.reason,
        "strategy_version": config.strategy_version,
        "ticket_sol": str(config.ticket(limits)),
        "max_open": config.max_open,
        "markets_enabled": markets_enabled,
        "open": open_rows,
        "mark_stale_s": None if not stale else max(int(s) for s in stale if s is not None),
        "signals_seen": stats.signals_seen,
        "admitted": stats.admitted,
        "buys_confirmed": stats.buys_confirmed,
        "buys_unconfirmed": stats.buys_unconfirmed,
        "reconciled_buys": stats.reconciled_buys,
        "reconciled_expired": stats.reconciled_expired,
        "last_reconcile_result": stats.last_reconcile_result,
        "pending_unconfirmed": stats.pending_unconfirmed,
        "oldest_pending_s": stats.oldest_pending_s,
        "refused_by_reason": _top(stats.refused_by_reason),
        "exits_by_reason": dict(sorted(stats.exits_by_reason.items())),
        "blocked_exits": dict(sorted(stats.blocked_exits.items())),
        "stuck_exits": dict(sorted(stats.stuck_exits.items())),
        "closed": {
            "n": 0 if closed is None else closed.n,
            "sum_r_gross": None,
            "sum_r_net": None if closed is None else str(closed.sum_r_net),
            "sum_pnl_sol": None if closed is None else str(closed.sum_pnl_sol),
            "expectancy_r_net": (
                None
                if closed is None or closed.expectancy_r_net is None
                else str(closed.expectancy_r_net)
            ),
            "consecutive_stops": 0 if closed is None else closed.consecutive_stops,
            "last_exit_at": _stamp(None if closed is None else closed.last_exit_at),
        },
        "refutation": {
            "trades": 0 if closed is None else closed.n,
            "threshold": config.refute_min_trades,
            "max_loss_sol": str(config.refute_max_loss_sol),
            "state": "unknown" if lane is None else lane.state,
            "reset_at": _stamp(config.refutation_reset_at),
        },
        "tick_failures": stats.tick_failures,
        "last_signature": stats.last_signature,
        "last_refusal": stats.last_refusal,
        "last_entries_tick_at": _stamp(stats.last_entries_tick_at),
        "last_exits_tick_at": _stamp(stats.last_exits_tick_at),
    }


def _open_row(p: OpenPosition, stats: Any, now: datetime) -> dict[str, Any]:
    spent = Decimal(p.sol_spent_lamports) / LAMPORTS
    r = None
    if p.mark_sol is not None and p.initial_risk_sol > 0:
        r = (p.mark_sol - spent) / p.initial_risk_sol
    failures = int(stats.mark_failures.get(p.id, 0))
    ok_at = stats.mark_ok_at.get(p.id)
    horizon = p.params.get("horizon_s")
    return {
        "id": p.id,
        "market": p.params.get("market_symbol"),
        "mint8": p.mint[:8],
        "entry_at": p.entry_at.isoformat(),
        "sol_spent": str(spent),
        "mark_sol": None if p.mark_sol is None else str(p.mark_sol),
        "r_now": None if r is None else str(r.quantize(Decimal("0.001"))),
        "age_s": int((now - p.entry_at).total_seconds()),
        "horizon_s": None if horizon is None else int(horizon),
        "mark_failures": failures,
        "mark_stale": failures >= STALE_AFTER_FAILURES,
        "mark_stale_s": None if ok_at is None else int((now - ok_at).total_seconds()),
        "exit_pending": (p.exit_intent or {}).get("status") == "submitted_unconfirmed",
        "blocked": p.id in stats.blocked_exits,
    }


def _top(counts: dict[str, int]) -> dict[str, int]:
    ranked = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))
    return dict(ranked[:TOP_REFUSALS])


def _stamp(value: datetime | None) -> str | None:
    return None if value is None else value.isoformat()
