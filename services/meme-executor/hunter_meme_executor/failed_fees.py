"""T4.96b fix — the durable half of T4.59's failed-landing fee, for buys.

A buy that landed **with an error** paid its network fee (priority included).
``send_path.record_failed_onchain_fee`` writes it right after the settlement,
but that one read can come back empty, time out, or the process can die between
the ``FAILED`` state write and the fee write — and until 27/09 the write itself
never matched (``fill`` is JSON ``null`` after ``submit._fail``, the predicate
wanted SQL NULL; VPS: 13 failed buys since 17/09 without their fee). Without the
fee, the small-test counter (``scope._USED``) undercounts what left the wallet.

Each reconcile tick claims at most :data:`FAILED_FEE_BATCH` failed buys with an
``onchain_error:`` reason, a signature and no fee yet, whose ``updated_at`` is
older than :data:`FAILED_FEE_RETRY_S` (the claim bumps it: an unanswered read
is retried after the backoff, not every tick), and re-reads each through the
same path as the first write. Never raises; runs after the exits' settlement.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Final

from sqlalchemy import text

from hunter_core.db.session import role_session
from hunter_core.execution.meme.journal import SubmitState
from hunter_core.execution.meme.submit import SubmitResult
from hunter_core.logging import get_logger
from hunter_meme_executor.journal_db import WORKER_ROLE
from hunter_meme_executor.send_path import ONCHAIN_ERROR_PREFIX, record_failed_onchain_fee

if TYPE_CHECKING:
    from hunter_meme_executor.context import ExecutorContext

__all__ = ["FAILED_FEE_BATCH", "FAILED_FEE_RETRY_S", "recover_failed_fees"]

logger = get_logger(__name__)

FAILED_FEE_BATCH: Final = 10
FAILED_FEE_RETRY_S: Final = 600

_CLAIM = text(
    "UPDATE meme_live_orders SET updated_at = :now WHERE id IN ("
    "  SELECT id FROM meme_live_orders "
    "  WHERE side = 'buy' AND status = 'failed' AND reason LIKE :prefix "
    "    AND tx_signature IS NOT NULL "
    "    AND (fill IS NULL OR jsonb_typeof(fill) = 'null') "
    "    AND updated_at < :retry_before "
    "  ORDER BY updated_at LIMIT :batch) "
    "RETURNING client_order_id, tx_signature, reason"
)


async def recover_failed_fees(ctx: ExecutorContext, *, now: datetime) -> list[str]:
    """Write the fee of the failed buys that still lack it; returns the keys written."""
    params = {
        "now": now,
        "prefix": ONCHAIN_ERROR_PREFIX + "%",
        "retry_before": now - timedelta(seconds=FAILED_FEE_RETRY_S),
        "batch": FAILED_FEE_BATCH,
    }
    written: list[str] = []
    try:
        async with role_session(ctx.session_factory, db_role=WORKER_ROLE) as session:
            claimed = list((await session.execute(_CLAIM, params)).mappings())
        for row in claimed:
            key = str(row["client_order_id"])
            result = SubmitResult(
                key, SubmitState.FAILED, str(row["reason"]), str(row["tx_signature"]), None
            )
            if await record_failed_onchain_fee(ctx, key, result):
                written.append(key)
    except Exception as exc:
        logger.warning("meme_live_failed_fee_recovery_failed", error_type=type(exc).__name__)
    for key in written:
        logger.info("meme_live_failed_fee_recovered", order=key)
    return written
