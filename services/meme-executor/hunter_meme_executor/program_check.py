"""The program-identity check (T4.8b): at boot, both reads; at every kill-switch
tick, the 45-byte ``ProgramData`` header.

``hunter_exchanges.pumpfun.program_identity`` compares what the chain says
(IDL hash, last deploy slot) with what the fixtures this executor's builder was
proven against were captured from. A difference is ``program_upgraded``:

- **at boot, live** — ``MemeLiveTradingRefused("program_upgraded")``: the process
  does not exist, nothing is signed (the key was already read by ``boot``; it dies
  with the process). An unreadable identity is ``program_identity_unreadable`` —
  fail closed, never "assume unchanged";
- **at boot, inert** — logged as an error and kept in the heartbeat; there is no
  key to sign with anyway;
- **at runtime** — ``ExecutorState.program_divergence`` is set and every entry is
  refused by name (``entries.py``). Exits keep the §9.2 simulation as their guard:
  a sell the cluster still accepts is the one way out of a position.
"""

from __future__ import annotations

import asyncio

from hunter_core.execution.meme.gates import MemeLiveTradingRefused
from hunter_core.logging import get_logger
from hunter_exchanges.pumpfun.program_identity import (
    EXPECTED_PUMP_PROGRAM,
    program_divergence,
    read_last_deploy_slot,
    read_program_identity,
)
from hunter_meme_executor.context import ExecutorContext

__all__ = ["check_program_at_boot", "program_check_once"]

logger = get_logger(__name__)


async def check_program_at_boot(ctx: ExecutorContext) -> None:
    try:
        identity = await asyncio.to_thread(read_program_identity, ctx.chain.rpc)
    except Exception as exc:
        if ctx.config.live:
            raise MemeLiveTradingRefused("program_identity_unreadable", type(exc).__name__) from exc
        ctx.state.rpc_errors += 1
        logger.warning("meme_executor_program_identity_unreadable", error_type=type(exc).__name__)
        return
    ctx.state.program_idl_hash = identity.idl_sha256
    ctx.state.program_last_deploy_slot = identity.last_deploy_slot
    divergence = program_divergence(identity)
    ctx.state.program_divergence = divergence
    if divergence is None:
        logger.info(
            "meme_executor_program_identity_ok",
            idl_sha256=identity.idl_sha256[:16],
            last_deploy_slot=identity.last_deploy_slot,
            expected_task=EXPECTED_PUMP_PROGRAM.task,
        )
        return
    if ctx.config.live:
        raise MemeLiveTradingRefused("program_upgraded", divergence)
    logger.error("meme_executor_program_upgraded", detail=divergence, live=False)


async def program_check_once(ctx: ExecutorContext) -> None:
    """Runtime detector: the deploy slot only (one 45-byte read per tick)."""
    try:
        slot = await asyncio.to_thread(read_last_deploy_slot, ctx.chain.rpc)
    except Exception as exc:
        ctx.state.rpc_errors += 1
        logger.warning("meme_executor_program_check_unreadable", error_type=type(exc).__name__)
        return
    ctx.state.program_last_deploy_slot = slot
    if slot == EXPECTED_PUMP_PROGRAM.last_deploy_slot:
        return
    detail = (
        f"last_deploy_slot {slot} != {EXPECTED_PUMP_PROGRAM.last_deploy_slot} "
        f"(programa mudou: regravar T4.8b; fixtures {EXPECTED_PUMP_PROGRAM.task} "
        f"{EXPECTED_PUMP_PROGRAM.captured_at})"
    )
    if ctx.state.program_divergence != detail:
        ctx.state.program_divergence = detail
        logger.error("meme_executor_program_upgraded", detail=detail, live=ctx.config.live)
