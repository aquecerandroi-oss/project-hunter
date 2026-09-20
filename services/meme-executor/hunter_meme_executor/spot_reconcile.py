"""T4.74-5 — the reconcile of the ``spot/1`` desk, riding the executor's 30 s
``reconcile`` task: every ``submitted_unconfirmed`` row is asked of the chain
by its signature, never re-sent. ``getSignatureStatuses`` for all of them in
one call; then per row:

* **confirmed** → ``getTransaction`` meta → the fill of *this signature*
  (``fill_from_transaction``) → ``mark_confirmed`` → a **buy** opens the
  position with the geometry the order's ``admission.spot1``/``intent``
  recorded (the T4.74-4 concern: tokens that landed late sat in the wallet
  with no position and the reservation still held); a **sell** closes it
  with the lamports that landed.
* **errored on chain** → ``failed:onchain_error``; a sell's pending marker is
  cleared so the exits loop may try again; a buy's reservation is released by
  the status itself (``pending_spot_markets`` counts only rows in flight).
* **not found** → ``getBlockHeight`` once per tick; past
  ``last_valid_block_height`` (or, without one, past ``SUBMITTED_MAX_AGE_S``)
  the row is ``failed:blockhash_expired_never_landed`` and the reservation
  goes with it; otherwise it waits for the next tick.

Then the two orphans a crash between ``mark_confirmed`` and the position
write leaves — a confirmed buy with no position, an open position whose
pending sell already confirmed — are repaired from the row's own ``fill``.
Runs whenever the process has a signer (the wallet the fill is read for): a
row with a signature is money on the chain whatever ``SPOT1_ENABLED`` reads
today. Nothing here signs or sends.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any

from hunter_core.db.session import role_session
from hunter_core.domain.types import utcnow
from hunter_core.logging import get_logger
from hunter_meme_executor.exit_common import exit_lock
from hunter_meme_executor.journal_db import WORKER_ROLE
from hunter_meme_executor.spot_entries import spot_config_of, spot_stats_of
from hunter_meme_executor.spot_exit_repo import (
    SpotOrderRow,
    abandoned_orders,
    clear_exit_pending,
    confirmed_buys_without_position,
    confirmed_sells_still_pending,
    fail_abandoned,
    open_position_by_id,
    pending_exits_on_terminal_orders,
    unconfirmed_spot_orders,
)
from hunter_meme_executor.spot_exit_rules import backoff_s
from hunter_meme_executor.spot_repo import mark_confirmed, mark_failed
from hunter_meme_executor.spot_send_rules import ATA_RENT_LAMPORTS, TxFill, fill_from_transaction
from hunter_meme_executor.spot_settle import open_from_order, settle_closed
from hunter_meme_executor.treasury_rules import SUBMITTED_MAX_AGE_S

if TYPE_CHECKING:
    from hunter_meme_executor.context import ExecutorContext
    from hunter_meme_executor.spot_config import SpotConfig
    from hunter_meme_executor.spot_stats import SpotStats

__all__ = ["ABANDONED_AFTER_S", "ABANDONED_REASON", "EXPIRED_REASON", "spot_reconcile_once"]

logger = get_logger(__name__)
EXPIRED_REASON = "blockhash_expired_never_landed"
ABANDONED_REASON = "abandoned_before_signing"
ABANDONED_AFTER_S = 300
"""An ``admitted``/``simulated`` row never signed after this long was a leg the
process died inside (a live leg is bounded by the quote, the swap build, the
simulation and ``CONFIRM_ATTEMPTS_CAP`` seconds — well under this)."""
LANDED = ("confirmed", "finalized")


async def spot_reconcile_once(ctx: ExecutorContext) -> None:
    if ctx.signer is None:
        return
    cfg, stats = spot_config_of(ctx), spot_stats_of(ctx)
    try:
        await _tick(ctx, cfg, stats, utcnow())
    except Exception as exc:
        ctx.state.rpc_errors += 1
        logger.exception("meme_spot_reconcile_failed", error_type=type(exc).__name__)


async def _tick(ctx: ExecutorContext, cfg: SpotConfig, stats: SpotStats, now: datetime) -> None:
    async with role_session(ctx.session_factory, db_role=WORKER_ROLE) as session:
        rows = await unconfirmed_spot_orders(session)
    if rows:
        await _settle_by_signature(ctx, cfg, stats, rows, now)
    async with role_session(ctx.session_factory, db_role=WORKER_ROLE) as session:
        orphans = await confirmed_buys_without_position(session)
        orphans += await confirmed_sells_still_pending(session)
    for row in orphans:
        if row.fill is None:
            continue  # the CHECK forbids it; never guess a fill
        logger.warning("meme_spot_orphan_repaired", order_id=row.id, side=row.side)
        await _apply_fill(ctx, cfg, stats, row, row.fill, now)
    async with role_session(ctx.session_factory, db_role=WORKER_ROLE) as session:
        stuck = await pending_exits_on_terminal_orders(session)
    for row in stuck:
        if row.position_id is None:
            continue
        async with exit_lock(ctx, row.position_id):
            async with role_session(ctx.session_factory, db_role=WORKER_ROLE) as session:
                outcome = f"{row.status}:{_reason_of(row)}"
                cleared = await clear_exit_pending(
                    session, row.position_id, order_id=row.id, outcome=outcome, now=now
                )
        if cleared:
            logger.warning("meme_spot_stuck_marker_cleared", order_id=row.id, outcome=outcome)
    async with role_session(ctx.session_factory, db_role=WORKER_ROLE) as session:
        abandoned = await abandoned_orders(
            session, before=now - timedelta(seconds=ABANDONED_AFTER_S)
        )
    for row in abandoned:
        async with role_session(ctx.session_factory, db_role=WORKER_ROLE) as session:
            failed = await fail_abandoned(session, row.id, reason=ABANDONED_REASON, now=now)
            if failed and row.side == "sell" and row.position_id is not None:
                await clear_exit_pending(
                    session, row.position_id, order_id=row.id, outcome=ABANDONED_REASON, now=now
                )
        if failed:
            logger.warning("meme_spot_abandoned_failed", order_id=row.id, side=row.side)


async def _settle_by_signature(
    ctx: ExecutorContext, cfg: SpotConfig, stats: SpotStats, rows: list[SpotOrderRow], now: datetime
) -> None:
    try:
        statuses = await asyncio.to_thread(
            ctx.chain.rpc.get_signature_statuses, [row.signature for row in rows]
        )
    except Exception as exc:
        ctx.state.rpc_errors += 1
        logger.warning("meme_spot_reconcile_unreadable", error_type=type(exc).__name__)
        return
    if len(statuses) != len(rows):
        # A short answer is not "not found" for the rows it left out (Astra).
        ctx.state.rpc_errors += 1
        logger.warning("meme_spot_reconcile_short_answer", asked=len(rows), got=len(statuses))
        return
    height: int | None = None
    for row, status in zip(rows, list(statuses), strict=True):
        if status is None:
            if height is None and row.last_valid_block_height is not None:
                try:
                    height = await asyncio.to_thread(ctx.chain.rpc.get_block_height)
                except Exception as exc:
                    ctx.state.rpc_errors += 1
                    logger.warning("meme_spot_height_unreadable", error_type=type(exc).__name__)
                    continue
            if not _expired(row, height, now):
                continue
            # The height was read **after** the status: the transaction may have
            # landed in its last valid block between the two reads. Absence is
            # proven only by a second look that still finds nothing (Astra).
            try:
                again = await asyncio.to_thread(
                    ctx.chain.rpc.get_signature_statuses, [row.signature]
                )
            except Exception as exc:
                ctx.state.rpc_errors += 1
                logger.warning("meme_spot_reconcile_unreadable", error_type=type(exc).__name__)
                continue
            if again and again[0] is not None:
                continue  # it did land: settled on the next tick from its real status
            await _settle_failed(ctx, stats, row, EXPIRED_REASON, now)
            stats.reconciled_expired += 1
            continue
        if status.get("err") is not None:
            await _settle_failed(ctx, stats, row, f"onchain_error:{str(status['err'])[:120]}", now)
            continue
        if status.get("confirmationStatus") not in LANDED:
            continue  # processed, not yet confirmed: next tick
        await _settle_landed(ctx, cfg, stats, row, now)


def _expired(row: SpotOrderRow, height: int | None, now: datetime) -> bool:
    if row.last_valid_block_height is not None:
        return height is not None and height > row.last_valid_block_height
    return (now - row.submitted_at).total_seconds() > SUBMITTED_MAX_AGE_S


async def _settle_failed(
    ctx: ExecutorContext, stats: SpotStats, row: SpotOrderRow, reason: str, now: datetime
) -> None:
    """``failed`` only if the row is not ``confirmed`` meanwhile (the leg's own
    confirm loop may have won); a sell's marker is cleared only when that
    transition won, under the position's lock — a confirmed sell must keep
    ``exit_order_id`` for the orphan repair (Astra, T4.74-5 review)."""
    if row.side != "sell" or row.position_id is None:
        async with role_session(ctx.session_factory, db_role=WORKER_ROLE) as session:
            failed = await mark_failed(session, row.id, reason=reason, now=now)
    else:
        async with exit_lock(ctx, row.position_id):
            async with role_session(ctx.session_factory, db_role=WORKER_ROLE) as session:
                failed = await mark_failed(session, row.id, reason=reason, now=now)
                if failed:
                    await clear_exit_pending(
                        session,
                        row.position_id,
                        order_id=row.id,
                        outcome=f"failed:{reason}",
                        now=now,
                    )
        if failed:
            attempt = int(row.intent.get("attempt") or 1)
            stats.exit_backoff_until[row.position_id] = now + timedelta(seconds=backoff_s(attempt))
    if not failed:
        logger.info("meme_spot_reconcile_row_moved", order_id=row.id, side=row.side)
        return
    logger.warning(
        "meme_spot_reconciled", order_id=row.id, side=row.side, state="failed", reason=reason
    )


async def _settle_landed(
    ctx: ExecutorContext, cfg: SpotConfig, stats: SpotStats, row: SpotOrderRow, now: datetime
) -> None:
    assert ctx.signer is not None
    try:
        tx = await asyncio.to_thread(ctx.chain.rpc.get_transaction, row.signature)
    except Exception as exc:
        ctx.state.rpc_errors += 1
        logger.warning("meme_spot_reconcile_fill_unreadable", error_type=type(exc).__name__)
        return
    landed = None
    if tx is not None:
        landed = fill_from_transaction(tx, wallet=ctx.signer.pubkey, mint=row.mint)
    if landed is None:
        logger.warning("meme_spot_reconcile_fill_not_visible", order_id=row.id)
        return  # confirmed by status, not served yet: next tick, never a fill of zero
    is_buy = row.side == "buy"
    sol, tok = landed.sol_delta_lamports, landed.token_delta_atoms
    if not ((tok > 0 and sol < 0) if is_buy else (sol > 0 and tok < 0)):
        logger.error("meme_spot_reconcile_fill_inconsistent", order_id=row.id, side=row.side)
        return  # left for a human: a landed transaction whose meta contradicts its side
    fill = _fill_payload(row, landed, is_buy)
    block_time = tx.get("blockTime") if tx is not None else None
    if isinstance(block_time, int) and not isinstance(block_time, bool):
        fill["landed_at"] = datetime.fromtimestamp(block_time, tz=UTC).isoformat()
    async with role_session(ctx.session_factory, db_role=WORKER_ROLE) as session:
        confirmed = await mark_confirmed(session, row.id, fill=fill, now=now)
    if not confirmed:
        return  # settled by another pass meanwhile
    stats.last_signature = row.signature
    logger.info("meme_spot_reconciled", order_id=row.id, side=row.side, state="confirmed")
    await _apply_fill(ctx, cfg, stats, row, fill, now)


async def _apply_fill(
    ctx: ExecutorContext,
    cfg: SpotConfig,
    stats: SpotStats,
    row: SpotOrderRow,
    fill: dict[str, Any],
    now: datetime,
) -> None:
    """A confirmed row's effect on the book: a buy opens, a sell closes."""
    if row.side == "buy":
        await open_from_order(ctx, cfg, stats, row, fill, now)
        return
    if row.position_id is None:
        return
    async with exit_lock(ctx, row.position_id):
        async with role_session(ctx.session_factory, db_role=WORKER_ROLE) as session:
            position = await open_position_by_id(session, row.position_id)
        if position is None:
            logger.warning("meme_spot_reconcile_position_gone", position_id=row.position_id)
            return
        pending = position.exit_intent or {}
        received = int(fill["sol_delta_lamports"])
        exit_payload = {
            "reason": row.intent.get("reason") or pending.get("reason") or "unknown",
            "attempt": row.intent.get("attempt"),
            "order_id": row.id,
            "signature": row.signature,
            "slippage_bps": row.intent.get("slippage_bps"),
            "filled_lamports": received,
            "sol_delta_lamports": received,
            "settled_by": "reconcile",
        }
        await settle_closed(
            ctx, cfg, stats, position, order_id=row.id, exit_payload=exit_payload, now=now
        )


def _reason_of(row: SpotOrderRow) -> str:
    return str(row.intent.get("reason") or "")


def _fill_payload(row: SpotOrderRow, landed: TxFill, is_buy: bool) -> dict[str, Any]:
    quoted = (row.quote or {}).get("outAmount")
    return {
        "signature": row.signature,
        "side": row.side,
        "source": "transaction_meta",
        "settled_by": "reconcile",
        "sol_delta_lamports": landed.sol_delta_lamports,
        "token_before_atoms": landed.token_before_atoms,
        "token_after_atoms": landed.token_after_atoms,
        "filled_atoms": landed.token_delta_atoms if is_buy else landed.sol_delta_lamports,
        "ata_rent_lamports": ATA_RENT_LAMPORTS if is_buy and landed.ata_created else 0,
        "network_fee_lamports": landed.network_fee_lamports,
        "quoted_out_atoms": None if quoted is None else int(str(quoted)),
    }
