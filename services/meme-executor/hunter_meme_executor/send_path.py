"""T4.55 — what the three send sites (``entries``, ``exits``, ``pumpswap_exit``)
share: the submit policy with the re-send cadence, the priority fee chosen for
*this* transaction, and the send statistics written back to the order row and
the heartbeat after the submitter returns.

T4.59 adds the two ends of a buy that ``6002 TooMuchSolRequired`` exposed: the
buy is built with the configured tolerance (``SendTuning.buy_slippage_bps``),
and a transaction that **landed and failed** still paid its network fee — that
fee is read from the transaction's ``meta`` and written to the order's ``fill``
(``network_fee_lamports``, with ``failed_onchain: true``) so the wallet panel's
fee sum counts it. Every consumer of ``fill`` as a trade guards on
``status = confirmed`` **and** the decoded ``FillRecord`` type, never on ``fill
IS NOT NULL``.

Nothing here decides admission or signs; it is the glue between the executor's
config and ``hunter_core.execution.meme.submit``.
"""

from __future__ import annotations

import asyncio
from collections.abc import Mapping, Sequence
from decimal import Decimal
from typing import TYPE_CHECKING, Any, cast

from hunter_core.db.session import role_session
from hunter_core.execution.meme.journal import SubmitState
from hunter_core.execution.meme.submit import SubmitPolicy, SubmitResult
from hunter_core.logging import get_logger
from hunter_exchanges.pumpfun.decode import PUMP_PROGRAM_ID
from hunter_exchanges.pumpfun.tx import bonding_curve_address
from hunter_meme_executor.build import BuiltTrade, build_buy
from hunter_meme_executor.journal_db import WORKER_ROLE
from hunter_meme_executor.priority_fee import PriorityFeeChoice
from hunter_meme_executor.repo import record_failed_fill, record_send_stats

if TYPE_CHECKING:
    from hunter_exchanges.pumpfun.global_state import GlobalAccount
    from hunter_exchanges.pumpfun.tx_rpc import SolanaTxRpcClient
    from hunter_meme_executor.chain import CurveRead
    from hunter_meme_executor.config import ExecutorConfig
    from hunter_meme_executor.context import ExecutorContext

__all__ = [
    "ONCHAIN_ERROR_PREFIX",
    "build_entry_buy",
    "curve_fee_accounts",
    "failed_onchain_fill",
    "priority_fee_for",
    "record_failed_onchain_fee",
    "record_send_result",
    "submit_policy",
]

ONCHAIN_ERROR_PREFIX = "onchain_error:"
"""``confirm.poll_until_settled`` / ``submit.reconcile``: the chain recorded the
transaction **with** an error — it landed, so the payer was charged ``meta.fee``."""

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


def build_entry_buy(
    cfg: ExecutorConfig,
    read: CurveRead,
    global_account: GlobalAccount,
    *,
    user: str,
    budget_sol: Decimal,
    fee: PriorityFeeChoice,
    blockhash: str,
    last_valid_block_height: int,
    creates_ata: bool,
) -> BuiltTrade:
    """The buy of the entries loop: the sized budget (a ceiling), the priority fee
    chosen for this transaction and the **configured** buy tolerance (T4.59,
    ``MEME_BUY_MAX_SLIPPAGE_PCT``) — the ``max_slippage_bps`` used is in the intent."""
    return build_buy(
        read,
        global_account,
        user=user,
        budget_sol=budget_sol,
        max_slippage_bps=cfg.send.buy_slippage_bps(),
        blockhash=blockhash,
        last_valid_block_height=last_valid_block_height,
        compute_unit_limit=cfg.compute_unit_limit,
        compute_unit_price_micro_lamports=fee.micro_lamports,
        creates_ata=creates_ata,
    )


def failed_onchain_fill(
    transaction: Mapping[str, Any] | None, *, signature: str, reason: str
) -> dict[str, Any] | None:
    """What a landed-and-failed transaction cost, as the order's ``fill`` JSON:
    ``network_fee_lamports`` from ``meta.fee`` (the payer's real charge, priority
    included), the program error and the signature. ``None`` when the transaction
    cannot be read or carries no error (then it is not a failed landing)."""
    if not transaction:
        return None
    meta = cast(Mapping[str, Any], transaction.get("meta") or {})
    if meta.get("err") is None:
        return None
    try:
        fee = int(meta.get("fee") or 0)
    except (TypeError, ValueError):
        return None
    return {
        "failed_onchain": True,
        "network_fee_lamports": fee,
        "err": meta.get("err"),
        "reason": reason,
        "signature": signature,
        "slot": transaction.get("slot"),
    }


async def _failed_onchain_fee(ctx: ExecutorContext, result: SubmitResult) -> dict[str, Any] | None:
    if (
        result.state is not SubmitState.FAILED
        or not result.signature
        or not result.reason.startswith(ONCHAIN_ERROR_PREFIX)
    ):
        return None
    try:
        transaction = await asyncio.to_thread(ctx.chain.rpc.get_transaction, result.signature)
    except Exception as exc:  # the fee is bookkeeping; the refusal already stands
        logger.warning(
            "meme_live_failed_fee_read_failed",
            signature=result.signature,
            error_type=type(exc).__name__,
        )
        return None
    return failed_onchain_fill(transaction, signature=result.signature, reason=result.reason)


async def record_failed_onchain_fee(
    ctx: ExecutorContext, key: str, result: SubmitResult | None
) -> None:
    """T4.59: a transaction that landed **with** an error still charged its
    network fee; write it to the order's ``fill`` so the day's fees count it.
    Called after every settlement — the send itself and the two reconciles
    (``main.reconcile_once``, ``exits._reconcile_sell``). Any other result, a
    replay or an unreadable transaction writes nothing."""
    if result is None or result.replayed:
        return
    fee_fill = await _failed_onchain_fee(ctx, result)
    if fee_fill is None:
        return
    try:
        async with role_session(ctx.session_factory, db_role=WORKER_ROLE) as session:
            await record_failed_fill(session, key, fee_fill)
    except Exception as exc:  # bookkeeping must never mask the settled result
        logger.warning(
            "meme_live_failed_fee_write_failed", order=key, error_type=type(exc).__name__
        )


async def record_send_result(ctx: ExecutorContext, key: str, result: SubmitResult) -> None:
    """The re-send count of this attempt, onto the order's ``intent`` and the
    process counters — after the submitter returned, never inside its loop.
    T4.59: a landed-and-failed transaction also writes its paid fee (``fill``)."""
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
    await record_failed_onchain_fee(ctx, key, result)
