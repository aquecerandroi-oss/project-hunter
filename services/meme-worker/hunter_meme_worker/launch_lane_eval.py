"""Fold one notification into a watched mint's state, and the two writes the
launch lane ever makes: the proposal (``on_create``) and the paper fill/close
(T4.67a) — split out of ``launch_lane.py`` for the 350-line budget, the same
cut ``event_gate.py``/``event_gate_eval.py`` took.
"""

from __future__ import annotations

from datetime import timedelta
from typing import TYPE_CHECKING

from hunter_core.db.session import role_session
from hunter_core.domain.types import utcnow
from hunter_core.logging import get_logger
from hunter_exchanges.base import ExchangeUnavailable, MalformedMessage
from hunter_exchanges.pumpfun.decode import decode_bonding_curve_account
from hunter_exchanges.pumpfun.pdas import bonding_curve_address
from hunter_exchanges.pumpfun.rpc_ws_models import AccountNotification, LogsNotification
from hunter_exchanges.pumpfun.trade_event import normalized_curve_trade, trade_events_from_logs
from hunter_indicators.meme.launch_lane import reconstruct_initial_real_token_reserves
from hunter_meme_worker.event_state import MintEventState
from hunter_meme_worker.features_tape import TapeTrade
from hunter_meme_worker.lab_repo import insert_proposals
from hunter_meme_worker.launch_lane_bets import close_launch_bet, open_launch_bet
from hunter_meme_worker.launch_lane_config import (
    BORN_FULL_PROGRESS_PCT,
    BORN_FULL_WINDOW_S,
    LAUNCH_LANE_OFF,
)
from hunter_meme_worker.launch_lane_entry import evaluate_create
from hunter_meme_worker.launch_lane_pricing import born_full, entry_point, exit_trigger
from hunter_meme_worker.launch_lane_runtime import LaunchWatch

if TYPE_CHECKING:
    from datetime import datetime

    from hunter_exchanges.pumpfun.models import NormalizedCurveTrade, NormalizedMemeTokenCreated
    from hunter_exchanges.pumpfun.rpc_ws_models import Notification
    from hunter_meme_worker.launch_lane_repo import LaunchRuleSpec
    from hunter_meme_worker.launch_lane_runtime import LaunchLaneRuntime
    from hunter_meme_worker.proposals import ProposalDraft

logger = get_logger(__name__)

WORKER_ROLE = "hunter_worker"

MAX_ENTRY_WAIT_S = 15
"""Give up on a watch (unsubscribe, drop) if no point ever qualifies for the
+1 s entry within this long — a dead feed, never a permanent subscription."""

__all__ = ["apply_notification", "on_create", "progress_mint"]


def _tape_trade(trade: NormalizedCurveTrade) -> TapeTrade:
    block_time = trade.block_time or trade.received_at
    return TapeTrade(
        block_time=block_time,
        received_at=trade.received_at,
        trader=trade.trader,
        side=trade.side,
        sol_lamports=int(trade.lamports),
    )


def _fold_logs(watch: LaunchWatch, notif: LogsNotification) -> TapeTrade | None:
    if notif.err is not None:
        return None
    latest: TapeTrade | None = None
    for event in trade_events_from_logs(notif.logs):
        trade = normalized_curve_trade(
            event, slot=notif.slot, signature=notif.signature, received_at=notif.received_at
        )
        watch.state.apply_trade(trade)
        latest = _tape_trade(trade)
    return latest


def _fold_account(watch: LaunchWatch, notif: AccountNotification) -> None:
    try:
        account = decode_bonding_curve_account(notif.data_base64, owner=notif.owner)
    except MalformedMessage:
        return
    watch.state.apply_account(account, slot=notif.slot, received_at=notif.received_at)


async def _unsubscribe(rt: LaunchLaneRuntime, mint: str) -> None:
    watch = rt.watches.pop(mint, None)
    if watch is None:
        return
    rt.subs_by_logical.pop(watch.logs_id, None)
    rt.subs_by_logical.pop(watch.account_id, None)
    try:
        await rt.ws.unsubscribe(watch.logs_id)
        await rt.ws.unsubscribe(watch.account_id)
    except Exception:  # a WS hiccup on unsubscribe must not stop the lane
        logger.warning("meme_launch_lane_unsubscribe_failed", mint=mint)


async def _enter(rt: LaunchLaneRuntime, mint: str, watch: LaunchWatch, now: datetime) -> None:
    point = entry_point(
        watch.state, created_at=watch.created_at, entry_delay_s=rt.config.entry_delay_s, as_of=now
    )
    if point is None:
        if now - watch.created_at > timedelta(seconds=MAX_ENTRY_WAIT_S):
            await _unsubscribe(rt, mint)
        return
    async with role_session(rt.session_factory, db_role=WORKER_ROLE) as session:
        bet_id, entry = await open_launch_bet(
            session,
            proposal_id=watch.proposal_id,
            rule_set_id=watch.rule_set_id,
            mint=mint,
            spec=watch.spec,
            entry_point=point,
        )
    watch.entered = True
    watch.bet_id = bet_id
    watch.entry = entry
    rt.stats.record_paper_open()


async def _check_exit(
    rt: LaunchLaneRuntime,
    mint: str,
    watch: LaunchWatch,
    now: datetime,
    latest_trade: TapeTrade | None,
) -> None:
    assert watch.entry is not None and watch.bet_id is not None
    decision = exit_trigger(
        watch.state,
        entered_at=watch.entry.entry_at,
        time_stop_s=watch.spec.time_stop_s,
        exit_on_first_third_party_sell=watch.spec.exit_on_first_third_party_sell,
        max_drawdown_from_peak_pct=watch.spec.max_drawdown_from_peak_pct,
        creation_buyers=watch.creation_buyers,
        latest_trade=latest_trade,
        as_of=now,
    )
    if decision is None:
        return
    async with role_session(rt.session_factory, db_role=WORKER_ROLE) as session:
        await close_launch_bet(
            session,
            bet_id=watch.bet_id,
            mint=mint,
            rule_set_id=watch.rule_set_id,
            entry=watch.entry,
            exit_point=decision.point,
            reason=decision.reason,
        )
    watch.closed = True
    rt.stats.record_paper_closed()
    await _unsubscribe(rt, mint)
    if rt.wake is not None:
        await rt.wake()


async def progress_mint(
    rt: LaunchLaneRuntime, mint: str, now: datetime, latest_trade: TapeTrade | None
) -> None:
    watch = rt.watches.get(mint)
    if watch is None or watch.closed:
        return
    if not watch.entered:
        if born_full(
            watch.state,
            created_at=watch.created_at,
            initial_real_token_reserves=watch.initial_real_token_reserves,
            window_s=BORN_FULL_WINDOW_S,
            threshold_pct=BORN_FULL_PROGRESS_PCT,
            as_of=now,
        ):
            rt.stats.record_born_full()
            await _unsubscribe(rt, mint)
            return
        await _enter(rt, mint, watch, now)
        return
    await _check_exit(rt, mint, watch, now, latest_trade)


async def apply_notification(rt: LaunchLaneRuntime, notif: Notification, now: datetime) -> None:
    mint = rt.subs_by_logical.get(notif.subscription_id)
    if mint is None or mint not in rt.watches:
        return
    latest_trade: TapeTrade | None = None
    if isinstance(notif, LogsNotification):
        latest_trade = _fold_logs(rt.watches[mint], notif)
    elif isinstance(notif, AccountNotification):
        _fold_account(rt.watches[mint], notif)
    else:
        return  # a bare SlotNotification carries nothing this lane prices with
    await progress_mint(rt, mint, now, latest_trade)


async def _open_watch(
    rt: LaunchLaneRuntime,
    event: NormalizedMemeTokenCreated,
    spec: LaunchRuleSpec,
    draft: ProposalDraft,
    now: datetime,
) -> None:
    pda = bonding_curve_address(event.mint)
    try:
        logs_id = await rt.ws.subscribe_logs(mentions=[pda], commitment=rt.config.commitment)
        account_id = await rt.ws.subscribe_account(pda, commitment=rt.config.commitment)
    except ExchangeUnavailable:
        return
    watch = LaunchWatch(
        mint=event.mint,
        spec=spec,
        proposal_id=draft.id,
        rule_set_id=spec.id,
        created_at=event.created_at,
        creation_buyers=frozenset({event.creator}),
        initial_real_token_reserves=reconstruct_initial_real_token_reserves(
            event.initial_virtual_token_reserves, event.creator_initial_tokens
        ),
        logs_id=logs_id,
        account_id=account_id,
        state=MintEventState(
            mint=event.mint,
            subscribed_at=now,
            first_seen_at=event.created_at,
            creator=event.creator,
        ),
    )
    rt.watches[event.mint] = watch
    rt.subs_by_logical[logs_id] = event.mint
    rt.subs_by_logical[account_id] = event.mint


async def _on_create(
    rt: LaunchLaneRuntime, event: NormalizedMemeTokenCreated, now: datetime
) -> None:
    rt.stats.record_create(now)
    outcome = evaluate_create(event, list(rt.specs), recent_symbols=rt.recent_symbols, now=now)
    rt.recent_symbols.observe(event.symbol, event.observed_at)
    for spec, result in outcome:
        if isinstance(result, tuple):
            continue  # a named refusal — no proposal, nothing more to do
        async with role_session(rt.session_factory, db_role=WORKER_ROLE) as session:
            inserted = await insert_proposals(session, [result])
        if not inserted:
            continue  # ON CONFLICT: this mint's launch proposal already exists
        rt.stats.record_proposal(
            latency_ms=int((utcnow() - event.received_at).total_seconds() * 1000)
        )
        if rt.wake is not None:
            await rt.wake()
        if rt.config.mode == LAUNCH_LANE_OFF or len(rt.watches) >= rt.config.max_watches:
            continue
        await _open_watch(rt, event, spec, result, now)


async def on_create(
    rt: LaunchLaneRuntime, event: NormalizedMemeTokenCreated, now: datetime
) -> None:
    """Called by ``discovery.py`` the instant a ``created`` frame is durable —
    never raises: a bad row here must not take the discovery loop down with it."""
    try:
        await _on_create(rt, event, now)
    except Exception as exc:  # a bad create must not stop discovery
        logger.warning(
            "meme_launch_lane_on_create_failed",
            mint=event.mint,
            error_type=type(exc).__name__,
            error=str(exc),
        )
