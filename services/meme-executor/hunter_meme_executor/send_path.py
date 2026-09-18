"""T4.55 — what the three send sites (``entries``, ``exits``, ``pumpswap_exit``)
share: the submit policy with the re-send cadence, the priority fee chosen for
*this* transaction, and the send statistics written back to the order row and
the heartbeat after the submitter returns.

Nothing here decides admission or signs; it is the glue between the executor's
config and ``hunter_core.execution.meme.submit``.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import TYPE_CHECKING, Any

from hunter_core.db.session import role_session
from hunter_core.execution.meme.submit import SubmitPolicy, SubmitResult
from hunter_core.logging import get_logger
from hunter_exchanges.pumpfun.decode import PUMP_PROGRAM_ID
from hunter_exchanges.pumpfun.tx import bonding_curve_address
from hunter_meme_executor.journal_db import WORKER_ROLE
from hunter_meme_executor.priority_fee import PriorityFeeChoice
from hunter_meme_executor.repo import record_send_stats

if TYPE_CHECKING:
    from hunter_exchanges.pumpfun.tx_rpc import SolanaTxRpcClient
    from hunter_meme_executor.config import ExecutorConfig
    from hunter_meme_executor.context import ExecutorContext

__all__ = ["curve_fee_accounts", "priority_fee_for", "record_send_result", "submit_policy"]

logger = get_logger(__name__)


def submit_policy(cfg: ExecutorConfig, rpc: SolanaTxRpcClient) -> SubmitPolicy:
    return SubmitPolicy(
        allow_send=cfg.live and rpc.allow_send,
        cluster=cfg.cluster,
        confirm_timeout_s=cfg.confirm_timeout_s,
        resend_interval_s=cfg.send.resend_interval_s,
    )


def curve_fee_accounts(mint: str) -> tuple[str, str]:
    """The accounts whose recent fees price a trade on this curve: the pump
    program and the mint's bonding curve (the RPC answers per slot the fee to
    lock *all* of them — contention on this coin, not the cluster's average)."""
    return (PUMP_PROGRAM_ID, bonding_curve_address(mint))


async def priority_fee_for(ctx: ExecutorContext, addresses: Sequence[str]) -> PriorityFeeChoice:
    """The per-CU price this transaction is built with. Without a reader (a
    context built before T4.55, tests) the configured static price."""
    reader = ctx.priority_fees
    if reader is None:
        return PriorityFeeChoice.static(ctx.config.compute_unit_price_micro_lamports)
    choice = await reader.choose(addresses, compute_unit_limit=ctx.config.compute_unit_limit)
    ctx.state.last_priority_fee = choice.as_json(ctx.config.compute_unit_limit)
    if choice.source.startswith("floor:") and choice.source != "floor:throttled":
        ctx.state.priority_fee_read_failures += 1
    return choice


async def record_send_result(ctx: ExecutorContext, key: str, result: SubmitResult) -> None:
    """The re-send count of this attempt, onto the order's ``intent`` and the
    process counters — after the submitter returned, never inside its loop."""
    ctx.state.resends_total += result.resends
    ctx.state.resend_errors_total += result.resend_errors
    ctx.state.last_resends = result.resends
    if result.replayed:
        return
    patch: dict[str, Any] = {"resends": result.resends, "resend_errors": result.resend_errors}
    try:
        async with role_session(ctx.session_factory, db_role=WORKER_ROLE) as session:
            await record_send_stats(session, key, patch)
    except Exception as exc:  # a statistic must never mask the settled result
        logger.warning(
            "meme_live_send_stats_write_failed", order=key, error_type=type(exc).__name__
        )
