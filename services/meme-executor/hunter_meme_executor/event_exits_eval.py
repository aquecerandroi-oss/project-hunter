"""Fold one notification into its position and judge it (T4.63): the mark
from the notification's own reserves (``exit_common.mark_sol`` — the same
``quote_sell`` the tick uses), the running peak, ``decide_exit`` with the
position's own ``ExitParams``, and — when it fires — one sell task through
``exits.sell_on_event`` (the tick's own lock and sell path). A creator sell
seen in a ``TradeEvent`` stamps ``creator_sold_seen_at`` **with its measured
fraction** (sold ÷ ``creator_initial_tokens``, the columns of ``0038``/``0048``)
on the row before the same evaluation, so ``creator_dump`` fires on the event
itself; with no recorded allocation the sighting is memory-only (the schema
refuses a sighting without a fraction, and this path never invents one).
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta
from decimal import Decimal
from typing import TYPE_CHECKING

from hunter_core.db.session import role_session
from hunter_core.domain.enums import KillSwitchState
from hunter_core.domain.types import utcnow
from hunter_core.logging import get_logger, redact_url
from hunter_exchanges.pumpfun.curve import TOKEN_SUBUNITS_PER_TOKEN
from hunter_exchanges.pumpfun.decode import NATIVE_SOL_QUOTE_MINT, decode_bonding_curve_account
from hunter_exchanges.pumpfun.quote import CurveReserves
from hunter_exchanges.pumpfun.rpc_ws_models import AccountNotification, LogsNotification
from hunter_exchanges.pumpfun.trade_event import trade_events_from_logs
from hunter_meme_executor.build import reserves_of_account
from hunter_meme_executor.event_exits_runtime import EventExitsRuntime, Watched
from hunter_meme_executor.exit_common import LAMPORTS, exit_params, mark_sol
from hunter_meme_executor.exits import sell_on_event
from hunter_meme_executor.journal_db import WORKER_ROLE
from hunter_meme_executor.repo import latest_sell_submitted_at, stamp_creator_sold, update_mark
from hunter_risk_meme import PositionForExit, decide_exit

if TYPE_CHECKING:
    from hunter_exchanges.pumpfun.rpc_ws_models import Notification
    from hunter_exchanges.pumpfun.trade_event import TradeEvent

__all__ = [
    "MARK_SOURCE",
    "TRIGGER_MIN_INTERVAL_S",
    "creator_sold_fraction",
    "handle_notification",
    "note_third_party_sells",
]

logger = get_logger(__name__)

MARK_SOURCE = "solana_rpc"
"""The row's ``mark_source`` (``ck_meme_live_positions_mark_source_is_a_known_label``
admits ``solana_rpc`` | ``curve_snapshot`` | ``tape``): an ``accountNotification``
is the same account bytes ``ChainReader.curve`` reads from the same RPC node,
over its subscription endpoint — the provenance is the RPC, the transport is the
WS. Adding a ``solana_ws`` label needs a migration (not this task); the
heartbeat's ``event_exits_marks_written`` says how many marks came this way."""
TRIGGER_MIN_INTERVAL_S = 1.0
"""Two triggers of the same position closer than this are one: the sell in
flight (or its backoff) is the tick's and the lock's business, not a reason
to re-read the curve ten times a second."""


_FRACTION_QUANTUM = Decimal("0.000001")
"""``creator_sold_fraction`` is ``numeric(9, 6)``; the smallest non-zero value."""


def creator_sold_fraction(token_amount: int, initial_tokens: Decimal | None) -> Decimal | None:
    """The creator's sell (``TradeEvent.token_amount``, sub-units) over his
    allocation at the create instant (tokens, ``0048``), in ``(0, 1]`` — the
    number ``0038``'s watch writes as *sold ÷ previous balance*, measured here
    against the only base this path knows. ``None`` when there is no base
    (``NULL`` or ``0``: "sold ÷ nothing" is not a fraction) or no sale. A sell
    larger than the allocation (he bought more meanwhile) reads as ``1``; a
    sell too small for six decimals reads as the smallest non-zero value —
    never ``0``, which the CHECK refuses and would un-say the sale."""
    if token_amount <= 0 or initial_tokens is None or initial_tokens <= 0:
        return None
    sold = Decimal(token_amount) / TOKEN_SUBUNITS_PER_TOKEN
    fraction = min(Decimal(1), sold / initial_tokens).quantize(_FRACTION_QUANTUM)
    return max(_FRACTION_QUANTUM, fraction)


def _reserves_of_event(
    virtual_sol: int, virtual_token: int, real_sol: int, real_token: int
) -> CurveReserves:
    return CurveReserves(virtual_sol, virtual_token, real_sol, real_token, False)


async def _write_mark(
    rt: EventExitsRuntime, w: Watched, mark: Decimal | None, *, force: bool, now: datetime
) -> None:
    """The row's mark from the WS — at most once a second per position, except
    when ``force``: a new peak (a restart must not forget what the trailing stop
    measures from) or the frame that fired (the close and the desk must read the
    number the decision was made on). ``None`` (curve complete / unreadable) is
    the tick's business: it names the reason; this path never blanks a number."""
    if mark is None:
        return
    last = w.last_mark_write_at
    if (
        not force
        and last is not None
        and now - last < timedelta(seconds=rt.config.mark_write_min_interval_s)
    ):
        return
    async with role_session(rt.ctx.session_factory, db_role=WORKER_ROLE) as session:
        await update_mark(
            session,
            w.position.id,
            mark_sol=mark,
            source=MARK_SOURCE,
            reason=None,
            migrated=w.position.migrated,
            now=now,
        )
    w.last_mark_write_at = now
    rt.stats.marks_written_total += 1


def _decide(
    rt: EventExitsRuntime, w: Watched, mark: Decimal | None, *, complete: bool, now: datetime
) -> str | None:
    p, ctx = w.position, rt.ctx
    return decide_exit(
        PositionForExit(
            position_id=p.id,
            mint=p.mint,
            entry_at=p.entry_at,
            sol_spent=Decimal(p.sol_spent_lamports) / LAMPORTS,
            token_amount=max(1, p.tokens),
            peak_mark_sol=w.high_water,
            migrated=p.migrated,
            curve_complete=complete,
        ),
        mark,
        now,
        exit_params(p.params, ctx.config.limits),
        sell_now=p.sell_requested_at is not None,
        creator_dump=w.creator_sold or p.creator_dump_seen(w.tape_creator_sold),
        emergency_auto_close=(
            ctx.kill.effective is KillSwitchState.EMERGENCY and ctx.config.auto_close_on_emergency
        ),
        third_party_sell=w.third_party_rule and w.third_party_sell_seen,
    )


def note_third_party_sells(
    w: Watched, events: list[TradeEvent], *, slot: int, ours: str | None
) -> str | None:
    """T4.67b (launch only): learn creation-slot buyers from the frame (a buy at
    ``slot <= creation_slot``) and flag the first sell by anyone who is not the
    creator, not this wallet (``ours``) and not one of them. Pure over the
    frame; the seller when the flag was raised by this frame, else ``None``."""
    if not w.launch or not w.third_party_rule:
        return None
    raised: str | None = None
    for event in events:
        if event.is_buy:
            if w.creation_slot is not None and slot <= w.creation_slot:
                w.known_buyers.add(event.user)
            continue
        if event.user == w.creator or event.user == ours or event.user in w.known_buyers:
            continue
        if not w.third_party_sell_seen:
            w.third_party_sell_seen = True
            raised = event.user
    return raised


async def _evaluate(
    rt: EventExitsRuntime,
    w: Watched,
    reserves: CurveReserves | None,
    *,
    complete: bool,
    now: datetime,
    received_at: datetime,
) -> str | None:
    mark = None if reserves is None else mark_sol(rt.ctx, reserves, w.position.tokens)
    new_peak = mark is not None and mark > w.high_water
    if new_peak and mark is not None:
        w.high_water = mark
    reason = _decide(rt, w, mark, complete=complete, now=now)
    await _write_mark(rt, w, mark, force=new_peak or reason is not None, now=now)
    if reason is None:
        return None
    if w.selling is not None and not w.selling.done():
        return reason
    if w.last_trigger_at is not None and now - w.last_trigger_at < timedelta(
        seconds=TRIGGER_MIN_INTERVAL_S
    ):
        return reason
    w.last_trigger_at = now
    rt.stats.record_trigger()
    logger.warning(
        "meme_event_exit_triggered",
        position_id=w.position.id,
        mint=w.position.mint,
        reason=reason,
        mark_sol=None if mark is None else str(mark),
        high_water_sol=str(w.high_water),
    )
    task = asyncio.create_task(
        _sell_task(rt, w, reason, received_at), name=f"meme-event-sell-{w.position.id}"
    )
    w.selling = task
    rt.sell_tasks.add(task)
    task.add_done_callback(rt.sell_tasks.discard)
    return reason


async def _sell_task(rt: EventExitsRuntime, w: Watched, reason: str, received_at: datetime) -> None:
    try:
        await sell_on_event(rt.ctx, w.position.id, reason, now=utcnow())
        async with role_session(rt.ctx.session_factory, db_role=WORKER_ROLE) as session:
            submitted = await latest_sell_submitted_at(session, w.position.proposal_id)
        if submitted is not None and submitted >= received_at:
            rt.stats.record_submit_latency((submitted - received_at).total_seconds())
    except asyncio.CancelledError:
        raise
    except Exception as exc:
        rt.stats.sell_errors_total += 1
        logger.warning(
            "meme_event_exit_sell_failed",
            position_id=w.position.id,
            error_type=type(exc).__name__,
            error=redact_url(str(exc)),
        )


async def _on_account(
    rt: EventExitsRuntime, notif: AccountNotification, now: datetime
) -> str | None:
    position_id = rt.by_logical.get(notif.subscription_id)
    w = None if position_id is None else rt.watched.get(position_id)
    if w is None:
        return None
    account = decode_bonding_curve_account(notif.data_base64, owner=notif.owner)
    rt.stats.record_update(now)
    try:
        reserves = reserves_of_account(account)
    except ValueError:  # a quote other than SOL: no mark from here, the tick names it
        reserves = None
    await _evaluate(
        rt, w, reserves, complete=account.complete, now=now, received_at=notif.received_at
    )
    return position_id


async def _on_logs(rt: EventExitsRuntime, notif: LogsNotification, now: datetime) -> str | None:
    position_id = rt.by_logical.get(notif.subscription_id)
    w = None if position_id is None else rt.watched.get(position_id)
    if w is None or notif.err is not None:  # a failed instruction is not a trade
        return None
    # Only this curve's own events: a bot's bundle can mention several curves in
    # one transaction, and another mint's ``TradeEvent`` is neither this
    # position's reserves nor its creator's sell.
    events = [e for e in trade_events_from_logs(notif.logs) if e.mint == w.position.mint]
    if not events:
        return None
    rt.stats.record_update(now)
    ours = None if rt.ctx.signer is None else rt.ctx.signer.pubkey
    seller = note_third_party_sells(w, events, slot=notif.slot, ours=ours)
    if seller is not None:
        rt.stats.record_third_party_sell()
        logger.warning(
            "meme_event_exit_third_party_sell",
            position_id=w.position.id,
            mint=w.position.mint,
            signature=notif.signature,
            slot=notif.slot,
            seller=seller,
        )
    for event in events:
        if event.is_buy or w.creator is None or event.user != w.creator or w.creator_sold:
            continue
        w.creator_sold = True
        rt.stats.record_creator_sell()
        rt.ctx.state.creator_sold_on_chain.remember(w.position.mint, now)
        fraction = creator_sold_fraction(event.token_amount, w.creator_initial_tokens)
        stamped = False
        if fraction is not None:
            async with role_session(rt.ctx.session_factory, db_role=WORKER_ROLE) as session:
                stamped = await stamp_creator_sold(
                    session, w.position.id, at=now, fraction=fraction, now=now
                )
        logger.warning(
            "meme_event_exit_creator_sold",
            position_id=w.position.id,
            mint=w.position.mint,
            signature=notif.signature,
            slot=notif.slot,
            token_amount=event.token_amount,
            fraction=None if fraction is None else str(fraction),
            stamped=stamped,
            memory_only=fraction is None,
        )
    last = events[-1]
    reserves = (
        _reserves_of_event(
            last.virtual_sol_reserves,
            last.virtual_token_reserves,
            last.real_sol_reserves,
            last.real_token_reserves,
        )
        if last.quote_mint == NATIVE_SOL_QUOTE_MINT
        else None
    )
    await _evaluate(rt, w, reserves, complete=False, now=now, received_at=notif.received_at)
    return position_id


async def handle_notification(
    rt: EventExitsRuntime, notif: Notification, *, now: datetime
) -> str | None:
    """Fold one frame into its position and judge it; the position id when the
    frame named a watched one. Raises on a malformed frame — the loop counts it."""
    if isinstance(notif, AccountNotification):
        return await _on_account(rt, notif, now)
    if isinstance(notif, LogsNotification):
        return await _on_logs(rt, notif, now)
    return None
