"""T4.96b — an ``admitted`` buy that never got a signature is refused
``admitted_orphan_expired``, so it stops holding the small-test scope forever.

Why refusing it can never refuse a buy that landed: the submitter
(``hunter_core.execution.meme.submit``) takes the signing lock, signs,
**records the signature** (``status = 'simulated'``) and only then sends. A row
still ``admitted`` with no signature never left the process — and none can
leave after the refusal, because the journal (``journal_db``) neither locks nor
records a signature on a row that is not ``admitted`` any more (a submitter
that wakes up late fails closed, before the send). There is no signature to
look up on chain, so the chain's confirm helpers have nothing to answer here;
rows **with** a signature stay the reconcile's (``unconfirmed_orders``).

Two bounds, both far past anything a live submit can take:

- no lock (``signing_at`` NULL — a restart between the commit and
  ``begin_signing``): ``admitted_at`` older than the approval's reservation
  TTL + :data:`ORPHAN_MARGIN_S` (after the TTL the submitter refuses to sign);
- a lock left behind (a journal failure whose ``release_signing`` failed too):
  ``signing_at`` older than TTL + the confirmation window + the margin.

Rides the reconcile loop after the settlements (exits' sells included) and
never raises: a failure is logged and the next tick tries again.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Final

from sqlalchemy import text

from hunter_core.db.session import role_session
from hunter_core.logging import get_logger
from hunter_meme_executor.journal_db import WORKER_ROLE

if TYPE_CHECKING:
    from hunter_meme_executor.context import ExecutorContext

__all__ = ["ADMITTED_ORPHAN_EXPIRED", "ORPHAN_MARGIN_S", "expire_orphan_buys"]

logger = get_logger(__name__)

ADMITTED_ORPHAN_EXPIRED: Final = "admitted_orphan_expired"
ORPHAN_MARGIN_S: Final = 300
"""Seconds on top of the bounds: each journal/RPC call of a submit times out in
15 s, so no live submit holds an unsigned ``admitted`` row for minutes."""

_EXPIRE = text(
    "UPDATE meme_live_orders SET status = 'refused', reason = :reason, "
    "  settled_at = :now, updated_at = :now "
    "WHERE side = 'buy' AND status = 'admitted' AND tx_signature IS NULL "
    "  AND signatures = '[]'::jsonb "
    "  AND ((signing_at IS NULL AND coalesce(admitted_at, received_at) < :unsigned_before) "
    "    OR (signing_at IS NOT NULL AND signing_at < :locked_before)) "
    "RETURNING client_order_id"
)


async def expire_orphan_buys(ctx: ExecutorContext, *, now: datetime) -> list[str]:
    """Refuse the orphans; returns their ``client_order_id`` (empty on failure)."""
    cfg = ctx.config
    unsigned_s = cfg.limits.reservation_ttl_s + ORPHAN_MARGIN_S
    params = {
        "reason": ADMITTED_ORPHAN_EXPIRED,
        "now": now,
        "unsigned_before": now - timedelta(seconds=unsigned_s),
        "locked_before": now - timedelta(seconds=unsigned_s + cfg.confirm_timeout_s),
    }
    try:
        async with role_session(ctx.session_factory, db_role=WORKER_ROLE) as session:
            keys = [str(k) for k in (await session.execute(_EXPIRE, params)).scalars()]
    except Exception as exc:
        logger.warning("meme_live_orphan_expiry_failed", error_type=type(exc).__name__)
        return []
    for key in keys:
        ctx.state.record_refusal(ADMITTED_ORPHAN_EXPIRED)
        logger.warning("meme_live_orphan_buy_expired", order=key, reason=ADMITTED_ORPHAN_EXPIRED)
    return keys
