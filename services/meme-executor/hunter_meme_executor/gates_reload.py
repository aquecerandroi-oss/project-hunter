"""T4.28d — ``meme_gates.json`` re-read at runtime, on the kill-switch tick.

Measured on 16/09/2026 (11:3x BRT): the owner widened
``small_test_authorization.scope.max_total_sol`` from 0,25 to 0,72 on the VPS and
``hb:meme:executor`` kept publishing ``wallet_max_sol 0.25`` until
``docker restart hunter-meme-executor-1``. Restarting the one process that holds
the signing key, the in-flight submissions and the open positions is a cost we
should not pay to change a number the owner wrote. ``meme.kill`` is already
re-read every tick (``kill_switch.py``); the gates now follow the same pattern:

- **cheap**: one ``stat`` per kill-switch tick (``ExecutorConfig.kill_switch_poll_s``,
  10 s); the file is parsed only when ``st_mtime_ns`` moved;
- **valid ⇒ swapped atomically**: the effective policy is recomposed by
  ``config.effective_limits`` from the **owner's env policy** (never from the
  already-tightened one, or a widened scope could never widen anything) and the
  new ``ExecutorConfig``/``MemeExecutionMode`` are bound to the context in two
  assignments the loops read at decision time (``entries``, ``auto_approve`` and
  ``heartbeat`` all read ``ctx.config``/``ctx.mode`` per pass, never at boot);
- **invalid ⇒ latched, never crashed**: a file that stopped parsing, expired, had
  gate C turned off, or dropped the written scope while the robot is armed,
  latches the kill switch ``gates_invalid:<reason>`` (``kill_switch.latch`` — the
  same row, released only by the owner's ``UPDATE``) and keeps the **previous**
  policy in memory for the heartbeat to report. The loop returns normally: the
  entries are already stopped by the latch, and a raise here would take the
  process down while positions are open;
- **one tick of grace before latching a parse failure** (T4.28f): the owner edits
  the file with ``nano`` on the VPS — a non-atomic, in-place rewrite — so a tick
  can stat and read a **half-written** file and latch a process holding real
  money, with resume manual by contract (§7). A parse failure
  (:data:`GRACE_REASONS`: ``gates_file_invalid``, ``gates_file_missing``) is
  therefore *deferred* on its first sighting: nothing is latched, nothing is
  swapped, the previous policy stays in force and
  ``meme_executor_gates_reload_deferred`` is logged. The **next** tick decides —
  parses (reload, no latch) or fails again, same mtime or not (latch). A
  **semantic** refusal (expired, gate C off, the scope gone while armed) is a
  complete file saying no and still latches on the first tick;
- **counters are never reset**: the written scope's two counters (trades sent,
  SOL spent) are read from ``meme_live_orders`` on every pass (``scope.py``), so a
  reload cannot forget what the scope already used. A scope that shrank below what
  was spent clamps ``remaining_sol`` at 0 and the admission refuses new entries
  with the existing ``small_test_scope_exhausted``.
"""

from __future__ import annotations

import asyncio
import os
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Final

from hunter_core.domain.types import utcnow
from hunter_core.execution.meme.gates import (
    MemeExecutionMode,
    MemeLiveTradingRefused,
    load_gates,
)
from hunter_core.logging import get_logger
from hunter_meme_executor.config import with_gates

if TYPE_CHECKING:
    from hunter_meme_executor.context import ExecutorContext

__all__ = ["GATES_LATCH_PREFIX", "GRACE_REASONS", "GatesReload", "gates_reload_once", "prime_gates"]

logger = get_logger(__name__)

GATES_LATCH_PREFIX = "gates_invalid:"
"""The latch reason written to ``meme_live_kill_switch.reason``; the suffix is the
named refusal from ``hunter_core.execution.meme.gates`` (``gates_expired``,
``gate_c_owner_not_enabled``, ``gates_file_invalid``, ``gates_file_missing``,
``small_test_expired``, …) or ``auto_approve_needs_small_test``."""

GRACE_REASONS: Final[frozenset[str]] = frozenset({"gates_file_invalid", "gates_file_missing"})
"""T4.28f — the two refusals that mean *these bytes are not a file yet*, and are
therefore given one tick before they latch. Everything else named in
:data:`GATES_LATCH_PREFIX` is a file that parsed and said no; waiting a tick on
those would only keep the robot trading under a policy the owner already
withdrew."""


@dataclass(frozen=True, slots=True)
class GatesReload:
    reloaded: bool = False
    """The effective policy was recomposed and swapped on this pass."""
    refusal: str | None = None
    """``gates_invalid:<reason>`` when the file on disk is not one this process
    may trade under; the previous policy is kept and the switch is latched."""
    deferred: str | None = None
    """T4.28f — a parse failure seen for the first time: **not** latched, the
    previous policy stays in force and the next tick decides. The heartbeat
    publishes it as ``gates_reload_error = "deferred:<reason>"``."""


def _stat_ns(path: str) -> int | None:
    try:
        return os.stat(path).st_mtime_ns
    except OSError:
        return None


def prime_gates(ctx: ExecutorContext, *, now: datetime | None = None) -> None:
    """Record the mtime of the file the **boot** already parsed, so the first tick
    is not a spurious reload — and so an edit between boot and first tick is."""
    del now  # the mtime comes from the file, not from our clock
    path = ctx.config.gates_file
    if path is None:
        return
    mtime_ns = _stat_ns(path)
    ctx.state.gates_mtime_ns = mtime_ns
    ctx.state.gates_mtime = None if mtime_ns is None else _as_utc(mtime_ns)


def _as_utc(mtime_ns: int) -> datetime:
    return datetime.fromtimestamp(mtime_ns / 1_000_000_000, tz=UTC)


def _clear_deferred(ctx: ExecutorContext) -> None:
    ctx.state.gates_deferred_failure = None
    ctx.state.gates_deferred_mtime_ns = None


async def _failed(
    ctx: ExecutorContext, reason: str, detail: str, *, mtime_ns: int | None, deferred: str | None
) -> GatesReload:
    """One tick of grace for a parse failure, then the latch (T4.28f).

    ``deferred`` is what the **previous** tick left: ``None`` means this is the
    first failure in a row, and a parse failure then only remembers itself. A
    semantic refusal never waits — the file is complete and says no."""
    if reason in GRACE_REASONS and deferred is None:
        ctx.state.gates_deferred_failure = reason
        ctx.state.gates_deferred_mtime_ns = mtime_ns
        logger.warning(
            "meme_executor_gates_reload_deferred",
            reason=reason,
            detail=detail,
            mtime_ns=mtime_ns,
            note="not latched: the next tick decides (a half-written file is not a red gate)",
        )
        return GatesReload(deferred=reason)
    _clear_deferred(ctx)
    return GatesReload(refusal=await _latch(ctx, reason, detail))


async def _latch(ctx: ExecutorContext, reason: str, detail: str) -> str:
    """Stop this process by name. The memory latch first (it needs nothing that
    can fail), the durable row second (it is what survives a restart)."""
    latch_reason = f"{GATES_LATCH_PREFIX}{reason}"
    ctx.state.gates_invalid = reason
    ctx.kill.local_latch_reason = latch_reason
    logger.error("meme_executor_gates_reload_failed", reason=reason, detail=detail)
    try:
        await ctx.kill.latch(latch_reason, event="meme_executor_gates_latched")
    except Exception as exc:  # a Postgres that refuses the write does not unstop us
        logger.error("meme_executor_gates_latch_failed", reason=reason, error=type(exc).__name__)
    return latch_reason


async def gates_reload_once(ctx: ExecutorContext, *, now: datetime | None = None) -> GatesReload:
    """One pass: stat, and parse only if the bytes on disk changed."""
    path = ctx.config.gates_file
    if path is None or not ctx.config.live:
        return GatesReload()  # an inert executor has no gates to re-read
    at = now or utcnow()
    mtime_ns = await asyncio.to_thread(_stat_ns, path)
    deferred = ctx.state.gates_deferred_failure
    if mtime_ns is not None and mtime_ns == ctx.state.gates_mtime_ns and deferred is None:
        return GatesReload()
    # A deferred failure is re-read even under the same mtime: that is exactly the
    # "still failing on the next tick" the grace waits for (T4.28f).
    if mtime_ns is None and ctx.state.gates_invalid is not None:
        # A file that is still gone: already latched and already logged; saying it
        # again every 10 s only buries the first line.
        return GatesReload(refusal=f"{GATES_LATCH_PREFIX}{ctx.state.gates_invalid}")
    ctx.state.gates_mtime_ns = mtime_ns
    ctx.state.gates_mtime = None if mtime_ns is None else _as_utc(mtime_ns)
    try:
        gates = await asyncio.to_thread(load_gates, Path(path), today=at.date())
    except MemeLiveTradingRefused as exc:
        return await _failed(ctx, exc.reason, str(exc), mtime_ns=mtime_ns, deferred=deferred)
    except Exception as exc:  # an unreadable file is a red gate, not a crash
        return await _failed(
            ctx, "gates_file_invalid", type(exc).__name__, mtime_ns=mtime_ns, deferred=deferred
        )
    if ctx.config.auto_approve and gates.small_test is None:
        # The boot's rule (``auto_approve_needs_small_test``) cannot become false
        # at runtime: the robot only decides inside a scope the owner wrote. The
        # file parsed, so there is nothing to wait for: latch now.
        _clear_deferred(ctx)
        return GatesReload(
            refusal=await _latch(
                ctx, "auto_approve_needs_small_test", "the written scope is gone while armed"
            )
        )
    previous, old_small = ctx.config.limits, ctx.config.small_test_max_total_sol
    config = with_gates(ctx.config, gates)
    # Two assignments, no await between them: every loop reads ``ctx.config`` and
    # ``ctx.mode`` at decision time, so a pass sees one policy or the other.
    ctx.config, ctx.mode = config, MemeExecutionMode(live=True, gates=gates)
    ctx.state.gates_reloaded_at = at
    ctx.state.gates_invalid = None
    _clear_deferred(ctx)  # the bytes parse: whatever the last tick saw is history
    logger.warning(
        "meme_executor_gates_reloaded",
        valid_until=gates.valid_until.isoformat(),
        old_wallet_max_sol=str(previous.wallet_max_sol),
        wallet_max_sol=str(config.limits.wallet_max_sol),
        old_max_sol_per_trade=str(previous.max_sol_per_trade),
        max_sol_per_trade=str(config.limits.max_sol_per_trade),
        old_small_test_max_total_sol="" if old_small is None else str(old_small),
        small_test_max_total_sol=""
        if config.small_test_max_total_sol is None
        else str(config.small_test_max_total_sol),
        small_test_max_trades=config.small_test_max_trades,
        mtime="" if ctx.state.gates_mtime is None else ctx.state.gates_mtime.isoformat(),
    )
    return GatesReload(reloaded=True)
