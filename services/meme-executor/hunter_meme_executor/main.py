"""``HUNTER_ROLE=meme_executor`` — boot refusals first, then five loops.

The shape of the meme-worker: a thin entrypoint, a ``WorkerRuntime`` for
logging, Sentry, the heartbeat key and ``/health``·``/ready``·``/metrics``, and
the work as supervised tasks. A loop that raises takes the process down (a
green ``/ready`` over a stopped executor would be the worst of both worlds).

Boot (``config.boot``): with ``ENABLE_MEME_LIVE_TRADING`` off the process runs
**paper-inert** — nothing to sign with, ``allow_send=False`` on the RPC client,
every live proposal refused ``meme_live_disabled`` and recorded as such. With it
on, the gates, the policy, the RPC URL and the key are required in that order,
and the first missing one ends the process with a named ``MemeLiveTradingRefused``.

Loops: ``entries`` (1 s), ``exits`` (mark cadence), ``kill_switch`` (10 s, with
or without events), ``reconcile`` (30 s: every ``submitted_unconfirmed`` row is
settled by ``getSignatureStatuses``, never re-sent), ``heartbeat`` (10 s).
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from hunter_core.db.session import create_session_factory, role_session
from hunter_core.domain.types import utcnow
from hunter_core.execution.meme.gates import MemeLiveTradingRefused
from hunter_core.execution.meme.submit import MemeSubmitter, SubmitPolicy
from hunter_core.logging import get_logger
from hunter_core.redis import keys
from hunter_exchanges.pumpfun.tx_rpc import SolanaTxRpcClient
from hunter_meme_executor.build import decode_fills
from hunter_meme_executor.chain import ChainReader
from hunter_meme_executor.config import ExecutorConfig, boot, process_environment
from hunter_meme_executor.context import ExecutorContext
from hunter_meme_executor.entries import entries_once
from hunter_meme_executor.exits import exits_once
from hunter_meme_executor.heartbeat import heartbeat_once
from hunter_meme_executor.journal_db import WORKER_ROLE, PostgresOrderJournal
from hunter_meme_executor.kill_switch import KillSwitchReader
from hunter_meme_executor.program_check import check_program_at_boot, program_check_once
from hunter_meme_executor.repo import unconfirmed_orders

if TYPE_CHECKING:
    from hunter_core.runtime import WorkerRuntime

__all__ = ["build_context", "forever", "reconcile_once", "run_meme_executor"]

logger = get_logger(__name__)


async def forever[ContextT](
    name: str, interval_s: float, step: Callable[[ContextT], Awaitable[object]], ctx: ContextT
) -> None:
    """One step per cadence until cancelled; a failure is logged and re-raised."""
    while True:
        try:
            await step(ctx)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("meme_executor_loop_failed", loop=name)
            raise
        await asyncio.sleep(interval_s)


async def reconcile_once(ctx: ExecutorContext) -> None:
    """Settle every ``submitted_unconfirmed`` row — a restart or a timeout never re-sends."""
    async with role_session(ctx.session_factory, db_role=WORKER_ROLE) as session:
        pending = await unconfirmed_orders(session)
    if not pending:
        return
    submitter = MemeSubmitter(
        rpc=ctx.chain.rpc,
        signer=None,
        journal=ctx.journal,
        verify=lambda _raw: None,
        decode_fill=decode_fills,
        policy=SubmitPolicy(allow_send=False, cluster=ctx.config.cluster),
        now=utcnow,
    )
    for key in pending:
        try:
            result = await asyncio.to_thread(submitter.reconcile, key)
        except Exception as exc:
            # One row that cannot be read must not stop the others from settling.
            ctx.state.rpc_errors += 1
            logger.warning("meme_live_reconcile_failed", order=key, error_type=type(exc).__name__)
            continue
        if result is not None:
            logger.info("meme_live_reconciled", order=key, state=result.state, reason=result.reason)


async def kill_switch_once(ctx: ExecutorContext) -> None:
    await ctx.kill.refresh()
    await program_check_once(ctx)


def build_context(
    runtime: WorkerRuntime, config: ExecutorConfig, mode: object, signer: object
) -> ExecutorContext:
    from hunter_core.execution.meme.gates import MemeExecutionMode
    from hunter_core.execution.meme.signer import MemeSigner

    assert isinstance(mode, MemeExecutionMode)
    assert signer is None or isinstance(signer, MemeSigner)
    loop = asyncio.get_running_loop()
    session_factory = create_session_factory(runtime.engine)
    rpc = SolanaTxRpcClient(config.rpc_url, allow_send=config.live)
    key = keys.heartbeat(runtime.role, runtime.instance)

    async def write_fields(mapping: dict[str, str]) -> None:
        await runtime.redis.hset(key, mapping=mapping)  # type: ignore[reportUnknownMemberType]

    return ExecutorContext(
        config=config,
        mode=mode,
        signer=signer,
        session_factory=session_factory,
        chain=ChainReader(rpc),
        journal=PostgresOrderJournal(session_factory, loop),
        kill=KillSwitchReader(
            redis=runtime.redis,
            session_factory=session_factory,
            system=config.system_kill_switch,
            kill_file=config.kill_file,
        ),
        heartbeat=write_fields,
        loop=loop,
    )


def _register_health(runtime: WorkerRuntime, ctx: ExecutorContext) -> None:
    async def kill_switch_legible() -> bool:
        return ctx.kill.legible

    runtime.readiness_checks.append(kill_switch_legible)
    runtime.status_details["live"] = lambda: (
        "REAL (live flag on)" if ctx.config.live else "inert (live flag off)"
    )
    runtime.status_details["cluster"] = lambda: ctx.config.cluster
    runtime.status_details["wallet_pubkey"] = lambda: (
        "" if ctx.signer is None else ctx.signer.pubkey
    )
    runtime.status_details["kill_switch"] = lambda: ctx.kill.effective.value
    runtime.status_details["blocked_exits"] = lambda: str(len(ctx.state.blocked_exits))


async def run_meme_executor(runtime: WorkerRuntime) -> None:
    """The entrypoint ``RoleRegistry['meme_executor']`` points at."""
    try:
        config, mode, signer = boot(
            process_environment(),
            today=datetime.now(UTC).date(),
            system_kill_switch=runtime.settings.system_kill_switch,
        )
    except MemeLiveTradingRefused as exc:
        logger.error("meme_executor_boot_refused", reason=exc.reason, detail=str(exc))
        raise
    ctx = build_context(runtime, config, mode, signer)
    _register_health(runtime, ctx)
    try:
        # T4.8b: the chain's program must be the one the builder was proven against.
        await check_program_at_boot(ctx)
    except MemeLiveTradingRefused as exc:
        ctx.chain.rpc.close()
        logger.error("meme_executor_boot_refused", reason=exc.reason, detail=str(exc))
        raise
    await ctx.kill.refresh()
    logger.info(
        "meme_executor_starting",
        live=config.live,
        cluster=config.cluster,
        wallet_pubkey="" if signer is None else signer.pubkey,
        profile=config.limits.profile,
        approval_ttl_s=config.approval_ttl_s,
        auto_close_on_emergency=config.auto_close_on_emergency,
        small_test=config.small_test_max_trades,
    )
    try:
        async with asyncio.TaskGroup() as group:
            group.create_task(
                forever("entries", config.loop_s, entries_once, ctx), name="meme-entries"
            )
            group.create_task(forever("exits", config.mark_s, exits_once, ctx), name="meme-exits")
            group.create_task(
                forever("kill_switch", config.kill_switch_poll_s, kill_switch_once, ctx),
                name="meme-kill-switch",
            )
            group.create_task(
                forever("reconcile", config.reconcile_s, reconcile_once, ctx), name="meme-reconcile"
            )
            group.create_task(
                forever("heartbeat", 10.0, heartbeat_once, ctx), name="meme-heartbeat"
            )
    finally:
        ctx.chain.rpc.close()
