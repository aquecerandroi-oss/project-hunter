"""The program-identity check (T4.8b): at boot, the pump program's two reads; at every
kill-switch tick, the 45-byte ``ProgramData`` headers.

``hunter_exchanges.pumpfun.program_identity`` compares what the chain says
(IDL hash, last deploy slot) with what the fixtures this executor's builder was
proven against were captured from. A difference is ``program_upgraded``:

- **at boot, live (T4.8f F3: exits-only)** — the process **does not die**: a position open
  at that moment needs its exits and its reconciliation, and a process that never starts has
  neither. The divergence is recorded (``program_divergence``, sticky) or the identity is left
  unverified (``program_identity_verified`` is born ``False`` and only a complete compatible
  read sets it), ``meme_executor_boot_exits_only`` is logged at ERROR, and every entry is
  refused by name (``program_upgraded`` / ``program_identity_unverified``) — never "assume
  unchanged". Every loop that sells or reconciles runs as usual;
- **at boot, inert** — logged as an error and kept in the heartbeat; there is no
  key to sign with anyway;
- **at runtime** — ``ExecutorState.program_divergence`` is set and every entry is
  refused by name (``entries.py``). Exits keep the §9.2 simulation as their guard:
  a sell the cluster still accepts is the one way out of a position.

**T4.8f scope.** The watch is not only the pump program: PumpSwap (the ``sell`` of a migrated
position) and the pump fee program (both builders pass it) are watched by deploy slot
(``program_watch.WATCHED_PROGRAMS``) — the three were redeployed together on 2026-10-02, and
PumpSwap's ``sell`` changed shape with nothing announced. The runtime tick is **one**
``getMultipleAccounts``.

**An unreadable identity is not "unchanged" (T4.8f).** After ``PROGRAM_READ_FAILURES_MAX``
consecutive failed runtime reads ``ExecutorState.program_unreadable`` is set and every entry is
refused ``program_identity_unreadable`` until a read succeeds again; one or two bad ticks (a
single 429) do not stop the desk. Exits are never gated by it, and an upgrade already detected
is never cleared by a good read.

**Verification needs the complete read (T4.8f F3).** While the identity is not verified the
tick does the *full* read (``read_program_identity`` + ``read_deploy_slots``); only if both
succeed and match is it marked verified. Once verified the tick is the single cheap
``getMultipleAccounts``. A slots-only read never validates an IDL hash it did not read.
"""

from __future__ import annotations

import asyncio
from collections.abc import Iterable

from hunter_core.logging import get_logger
from hunter_exchanges.pumpfun.decode import PUMP_PROGRAM_ID
from hunter_exchanges.pumpfun.program_identity import (
    EXPECTED_PUMP_PROGRAM,
    UPGRADE_MESSAGE,
    program_divergence,
    read_program_identity,
)
from hunter_exchanges.pumpfun.program_watch import (
    WATCHED_PROGRAMS,
    read_deploy_slots,
    watched_divergence,
)
from hunter_meme_executor.context import ExecutorContext, ExecutorState

__all__ = [
    "PROGRAM_READ_FAILURES_MAX",
    "check_program_at_boot",
    "program_check_once",
]

logger = get_logger(__name__)

PROGRAM_READ_FAILURES_MAX = 3
"""Consecutive failed runtime identity reads after which entries are refused."""


def _watched_divergences(slots: dict[str, int]) -> list[str]:
    found: list[str] = []
    for watch in WATCHED_PROGRAMS:
        text = watched_divergence(watch, slots[watch.program_id])
        if text is not None:
            found.append(text)
    return found


def _remember(state: ExecutorState, found: Iterable[str | None]) -> bool:
    """Records every divergence seen, **at once**, even from a partial read (Astra, T4.8f): a
    divergence observed is sticky; the complete read is required to *release* the block, never
    to *raise* it. ``True`` when something new was recorded."""
    fresh = [r for r in found if r is not None and (state.program_divergence or "").find(r) < 0]
    if not fresh:
        return False
    old = [state.program_divergence] if state.program_divergence else []
    state.program_divergence = "; ".join([*old, *fresh])
    return True


def _boot_unreadable(ctx: ExecutorContext, exc: Exception) -> None:
    ctx.state.rpc_errors += 1
    if ctx.config.live:  # exits-only: the identity stays unverified, entries stay refused
        logger.error(
            "meme_executor_boot_exits_only",
            reason="program_upgraded"
            if ctx.state.program_divergence
            else "program_identity_unreadable",
            detail=ctx.state.program_divergence,
            error_type=type(exc).__name__,
        )
    else:
        logger.warning("meme_executor_program_identity_unreadable", error_type=type(exc).__name__)


async def check_program_at_boot(ctx: ExecutorContext) -> None:
    state = ctx.state
    try:
        identity = await asyncio.to_thread(read_program_identity, ctx.chain.rpc)
    except Exception as exc:
        _boot_unreadable(ctx, exc)
        return
    state.program_idl_hash = identity.idl_sha256
    state.program_last_deploy_slot = identity.last_deploy_slot
    _remember(state, [program_divergence(identity)])  # at once: the next read may fail
    try:
        watched = await asyncio.to_thread(
            read_deploy_slots, ctx.chain.rpc, [w.program_id for w in WATCHED_PROGRAMS]
        )
    except Exception as exc:
        _boot_unreadable(ctx, exc)
        return
    _remember(state, _watched_divergences(watched))
    divergence = state.program_divergence
    state.program_identity_verified = divergence is None  # a COMPLETE compatible read
    if divergence is None:
        logger.info(
            "meme_executor_program_identity_ok",
            idl_sha256=identity.idl_sha256[:16],
            last_deploy_slot=identity.last_deploy_slot,
            expected_task=EXPECTED_PUMP_PROGRAM.task,
            watched=sorted(w.label for w in WATCHED_PROGRAMS),
        )
        return
    if ctx.config.live:  # exits-only (T4.8f F3): never die — a position needs its exits
        logger.error("meme_executor_boot_exits_only", reason="program_upgraded", detail=divergence)
        return
    logger.error("meme_executor_program_upgraded", detail=divergence, live=False)


async def program_check_once(ctx: ExecutorContext) -> None:
    """Runtime detector: the deploy slots only (one 45-byte-per-program read per tick)."""
    state = ctx.state
    # Unverified (born so, or a boot read that failed) the tick does the COMPLETE read; verified,
    # the single cheap one. A slots-only read never validates an IDL hash it did not read.
    full = not state.program_identity_verified and state.program_divergence is None
    identity = None
    try:
        if full:
            identity = await asyncio.to_thread(read_program_identity, ctx.chain.rpc)
            state.program_idl_hash = identity.idl_sha256
            if _remember(state, [program_divergence(identity)]):  # at once, even if slots fail
                logger.error(
                    "meme_executor_program_upgraded",
                    detail=state.program_divergence,
                    live=ctx.config.live,
                )
        slots = await asyncio.to_thread(
            read_deploy_slots,
            ctx.chain.rpc,
            [PUMP_PROGRAM_ID, *(w.program_id for w in WATCHED_PROGRAMS)],
        )
    except Exception as exc:
        state.rpc_errors += 1
        state.program_read_failures += 1
        logger.warning(
            "meme_executor_program_check_unreadable",
            error_type=type(exc).__name__,
            consecutive=state.program_read_failures,
        )
        if state.program_read_failures >= PROGRAM_READ_FAILURES_MAX and (
            state.program_unreadable is None
        ):
            state.program_unreadable = (
                f"{state.program_read_failures} consecutive program identity reads failed "
                f"({type(exc).__name__}); entries are refused until one succeeds"
            )
            logger.error(
                "meme_executor_program_identity_unreadable_runtime", detail=state.program_unreadable
            )
        return
    state.program_read_failures = 0
    if state.program_unreadable is not None:
        state.program_unreadable = None
        logger.warning("meme_executor_program_identity_readable_again")
    slot = slots[PUMP_PROGRAM_ID]
    state.program_last_deploy_slot = slot
    reasons: list[str | None] = []
    if slot != EXPECTED_PUMP_PROGRAM.last_deploy_slot:
        reasons.append(
            f"last_deploy_slot {slot} != {EXPECTED_PUMP_PROGRAM.last_deploy_slot} "
            f"({UPGRADE_MESSAGE}; fixtures {EXPECTED_PUMP_PROGRAM.task} "
            f"{EXPECTED_PUMP_PROGRAM.captured_at})"
        )
    reasons += _watched_divergences(slots)
    if _remember(state, reasons):
        logger.error(
            "meme_executor_program_upgraded", detail=state.program_divergence, live=ctx.config.live
        )
    if state.program_divergence is None and identity is not None:  # complete and compatible
        state.program_identity_verified = True
        logger.warning("meme_executor_program_identity_verified", slot=slot)
