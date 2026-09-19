"""Keep the WS subscriptions equal to ``open_positions`` (T4.63): one
``logsSubscribe`` + one ``accountSubscribe`` on the bonding-curve PDA per
open real position, capped at ``max_open_positions`` positions; closed
positions are unsubscribed; the exit locks of positions no longer open are
pruned here (never while held).
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from hunter_core.db.session import role_session
from hunter_core.logging import get_logger
from hunter_exchanges.pumpfun.pdas import bonding_curve_address
from hunter_meme_executor.event_exits_runtime import EventExitsRuntime, Watched
from hunter_meme_executor.journal_db import WORKER_ROLE
from hunter_meme_executor.repo import OpenPosition, open_positions, token_context

__all__ = ["sync_watch"]

logger = get_logger(__name__)


async def _watch(rt: EventExitsRuntime, position: OpenPosition) -> None:
    pda = bonding_curve_address(position.mint)
    async with role_session(rt.ctx.session_factory, db_role=WORKER_ROLE) as session:
        token = await token_context(session, position.mint)
    commitment = rt.config.commitment
    try:
        logs_id = await rt.ws.subscribe_logs(mentions=[pda], commitment=commitment)
    except Exception as exc:  # the next sync retries; the tick covers meanwhile
        logger.warning(
            "meme_event_exits_subscribe_failed", mint=position.mint, error_type=type(exc).__name__
        )
        return
    try:
        account_id = await rt.ws.subscribe_account(pda, commitment=commitment)
    except Exception as exc:
        logger.warning(
            "meme_event_exits_subscribe_failed", mint=position.mint, error_type=type(exc).__name__
        )
        try:
            await rt.ws.unsubscribe(logs_id)
        except Exception:
            logger.warning("meme_event_exits_unsubscribe_failed", mint=position.mint)
        return
    rt.watched[position.id] = Watched(
        position=position,
        creator=token.creator,
        tape_creator_sold=token.creator_sold,
        logs_id=logs_id,
        account_id=account_id,
        high_water=position.high_water_sol or Decimal(0),
        creator_initial_tokens=token.creator_initial_tokens,
        creator_sold=position.creator_sold_seen_at is not None,
    )
    rt.by_logical[logs_id] = position.id
    rt.by_logical[account_id] = position.id
    logger.info("meme_event_exits_watching", position_id=position.id, mint=position.mint, pda=pda)


async def _unwatch(rt: EventExitsRuntime, position_id: str) -> None:
    w = rt.watched.pop(position_id, None)
    if w is None:
        return
    rt.by_logical.pop(w.logs_id, None)
    rt.by_logical.pop(w.account_id, None)
    for logical_id in (w.logs_id, w.account_id):
        try:
            await rt.ws.unsubscribe(logical_id)
        except Exception:
            logger.warning("meme_event_exits_unsubscribe_failed", mint=w.position.mint)
    logger.info("meme_event_exits_unwatched", position_id=position_id, mint=w.position.mint)


def _refresh(w: Watched, position: OpenPosition) -> None:
    """The row as the tick (or the operator, or the radar's watch) left it:
    ``sell_requested_at``, ``creator_sold_seen_at``, ``migrated``, ``tokens``,
    and a ``high_water_sol`` the tick may have raised."""
    w.position = position
    w.high_water = max(w.high_water, position.high_water_sol or Decimal(0))
    if position.creator_sold_seen_at is not None:
        w.creator_sold = True


async def sync_watch(rt: EventExitsRuntime, *, now: datetime) -> None:
    """One pass: unsubscribe every closed position, subscribe every open one
    not yet watched (oldest entry first, capped at ``max_open_positions``),
    refresh the rest, prune the exit locks of positions no longer open."""
    async with role_session(rt.ctx.session_factory, db_role=WORKER_ROLE) as session:
        positions = await open_positions(session)
    open_ids = {p.id for p in positions}
    for position_id in [pid for pid in rt.watched if pid not in open_ids]:
        await _unwatch(rt, position_id)
    cap = rt.ctx.config.limits.max_open_positions
    for position in positions:
        w = rt.watched.get(position.id)
        if w is not None:
            _refresh(w, position)
            continue
        if len(rt.watched) >= cap:
            break
        await _watch(rt, position)
    rt.stats.subscriptions = 2 * len(rt.watched)
    rt.stats.ws_state = rt.ws.state.ws_state
    locks = rt.ctx.state.exit_locks
    for position_id in [
        pid for pid, lock in locks.items() if pid not in open_ids and not lock.locked()
    ]:
        locks.pop(position_id, None)
