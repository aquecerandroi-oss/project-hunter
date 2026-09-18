"""Fold one notification into a mint's state, and judge it (T4.52b-3): the
part of the event gate that touches the database — one row, the same
``evaluate_gate``/``insert_proposals``/``write_refusal_trail`` the 15-second
lane already uses (module docstring of ``event_gate.py``).
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import TYPE_CHECKING

from hunter_core.db.session import role_session
from hunter_core.logging import get_logger
from hunter_exchanges.base import MalformedMessage
from hunter_exchanges.pumpfun.curve import raw_lamports_to_sol, raw_subunits_to_tokens
from hunter_exchanges.pumpfun.decode import decode_bonding_curve_account
from hunter_exchanges.pumpfun.rpc_ws_models import AccountNotification, LogsNotification
from hunter_exchanges.pumpfun.trade_event import normalized_curve_trade, trade_events_from_logs
from hunter_meme_worker.event_gate_config import GATE_SHADOW
from hunter_meme_worker.event_gate_rows import EventReserves, build_event_row
from hunter_meme_worker.lab_fast import _trail_row  # pyright: ignore[reportPrivateUsage]
from hunter_meme_worker.lab_repo import insert_proposals
from hunter_meme_worker.lab_trail import write_refusal_trail
from hunter_meme_worker.proposals import evaluate_gate
from hunter_meme_worker.repo import record_gap
from hunter_meme_worker.repo_rows import GapRow

if TYPE_CHECKING:
    from hunter_exchanges.pumpfun.rpc_ws_models import Notification
    from hunter_indicators.meme.pedigree import PedigreeFeatures
    from hunter_indicators.meme.pedigree_e2b import E2bFeatures
    from hunter_meme_worker.context import RadarContext
    from hunter_meme_worker.event_gate_runtime import EventGateRuntime
    from hunter_meme_worker.features_tape import HoldersObservation
    from hunter_meme_worker.gate_refusal_trail import RefusalTrailRow

logger = get_logger(__name__)

WORKER_ROLE = "hunter_worker"
GAP_STREAM = "solana_ws"

__all__ = ["apply_notification", "evaluate_mint", "handle_reconnect"]


def _holders_readings(radar: RadarContext, mint: str) -> list[HoldersObservation]:
    """``fast_lane._readings``'s own convention, duplicated: both sources
    already in memory, no new query."""
    out: list[HoldersObservation] = []
    if radar.boards is not None:
        out.extend(radar.boards.readings(mint))
    if radar.risk is not None:
        out.extend(radar.risk.readings(mint))
    return out


def _event_to_proposal_s(rt: EventGateRuntime, mint: str, now: datetime) -> float | None:
    """``(current slot − event slot) × 0.4 + path_s`` (plan §3) — ``None``
    when either clock is unmeasured yet (never a fabricated zero)."""
    state = rt.book.get(mint)
    if state is None or state.slot is None or rt.slot is None or state.last_event_at is None:
        return None
    lag = max(0, rt.slot - state.slot) * 0.4
    path_s = max(0.0, (now - state.last_event_at).total_seconds())
    return lag + path_s


def _handle_logs(rt: EventGateRuntime, notif: LogsNotification) -> str | None:
    mint = rt.subs_by_logical.get(notif.subscription_id)
    if mint is None:
        return None
    state = rt.book.get(mint)
    if state is None or notif.err is not None:  # a failed instruction is not a fill
        return None
    for event in trade_events_from_logs(notif.logs):
        trade = normalized_curve_trade(
            event, slot=notif.slot, signature=notif.signature, received_at=notif.received_at
        )
        state.apply_trade(trade)
        rt.reserves[mint] = EventReserves(trade.virtual_sol_reserves, trade.virtual_token_reserves)
    return mint


def _handle_account(rt: EventGateRuntime, notif: AccountNotification) -> str | None:
    mint = rt.subs_by_logical.get(notif.subscription_id)
    if mint is None:
        return None
    state = rt.book.get(mint)
    if state is None:
        return None
    try:
        account = decode_bonding_curve_account(notif.data_base64, owner=notif.owner)
    except MalformedMessage:
        return None
    state.apply_account(account, slot=notif.slot, received_at=notif.received_at)
    rt.reserves[mint] = EventReserves(
        raw_lamports_to_sol(account.virtual_sol_reserves),
        raw_subunits_to_tokens(account.virtual_token_reserves),
    )
    return mint


def apply_notification(rt: EventGateRuntime, notif: Notification) -> str | None:
    """Fold one notification into its mint's state; ``None`` when it names no
    tracked mint, a failed instruction, or is a bare ``SlotNotification``
    (which only updates ``rt.slot``, the lag anchor)."""
    if isinstance(notif, LogsNotification):
        return _handle_logs(rt, notif)
    if isinstance(notif, AccountNotification):
        return _handle_account(rt, notif)
    rt.slot = notif.slot if rt.slot is None else max(rt.slot, notif.slot)
    return None


def _pedigree_of(rt: EventGateRuntime, mint: str) -> dict[str, PedigreeFeatures]:
    caches = rt.lab.caches
    assert caches is not None
    features = caches.pedigree.get(mint)
    return {} if features is None else {mint: features}


def _e2b_of(
    rt: EventGateRuntime, mint: str, end_time: datetime
) -> dict[tuple[str, datetime], E2bFeatures] | None:
    caches = rt.lab.caches
    assert caches is not None
    if not any(spec.pedigree_e2b for spec in caches.specs):
        return None
    features = caches.e2b.get(mint)
    return {} if features is None else {(mint, end_time): features}


async def evaluate_mint(rt: EventGateRuntime, mint: str, now: datetime) -> None:
    """Build the row, judge it against every cached 15-second set, and — in
    ``on`` — write through. ``shadow`` counts and logs, never inserts."""
    state = rt.book.get(mint)
    caches = rt.lab.caches
    if state is None or caches is None or not caches.specs:
        return
    base = caches.base_rows.get(mint)
    if base is None:
        rt.stats.record_no_base_row(now)
        return
    row = build_event_row(
        base,
        state,
        as_of=now,
        reserves=rt.reserves.get(mint),
        holders_readings=_holders_readings(rt.radar, mint),
    )
    rt.stats.record_evaluation(now)
    proposed = False
    trail: list[RefusalTrailRow] = []
    shadow = rt.config.mode == GATE_SHADOW
    async with role_session(rt.lab.session_factory, db_role=WORKER_ROLE) as session:
        for spec in caches.specs:
            already_open = caches.open_mints.get(spec.id, frozenset()) | (
                caches.recently_proposed_mints(spec.id, now=now)
            )
            outcome = evaluate_gate(
                spec,
                [row],
                now=now,
                ttl_s=rt.lab.config.lab_proposal_ttl_s,
                already_open=already_open,
                pedigree=_pedigree_of(rt, mint),
                e2b=_e2b_of(rt, mint, row.end_time),
            )
            if outcome.drafts:
                if shadow:
                    rt.stats.record_shadow_proposals(len(outcome.drafts))
                    logger.info(
                        "meme_event_gate_would_propose",
                        mint=mint,
                        rule_set=spec.label,
                        mcap_sol=str(row.mcap_sol),
                        progress_pct=str(row.curve_progress_pct),
                    )
                else:
                    inserted = await insert_proposals(session, outcome.drafts)
                    if inserted:
                        ttl = rt.lab.config.lab_proposal_ttl_s if spec.ttl_s is None else spec.ttl_s
                        latency = _event_to_proposal_s(rt, mint, now)
                        rt.stats.record_proposals(
                            inserted, latencies=[latency] if latency is not None else None
                        )
                        for draft in outcome.drafts:
                            caches.mark_proposed(draft.mint, spec.id, now=now, ttl_s=ttl)
                        proposed = True
            candidate = _trail_row(spec, row, outcome.refusals)
            if candidate is not None:
                trail.append(candidate)
        if trail:
            await write_refusal_trail(session, rt.lab.state.trail, trail)
    if proposed and rt.lab.wake is not None:
        await rt.lab.wake()


def _gap_start(rt: EventGateRuntime, *, before: datetime) -> datetime:
    """The oldest ``last_event_at`` still on the book — "from the last frame
    we saw to the first we see now" (``discovery._record_reconnect_gap``'s own
    wording). No subscribed mint yet, or every one of them a hair too new for
    a strict window: a second before ``before``, never a zero-width lie."""
    seen = [
        state.last_event_at
        for mint in rt.book.mints()
        if (state := rt.book.get(mint)) is not None and state.last_event_at is not None
    ]
    start = min(seen) if seen else before - timedelta(seconds=1)
    return start if start < before else before - timedelta(seconds=1)


async def handle_reconnect(rt: EventGateRuntime, now: datetime) -> None:
    """A WS reconnect invalidates every window (plan §4 "WS morre"): every
    subscribed mint's tape warms again, and the gap is durable."""
    rt.seen_reconnects = rt.ws.state.reconnects
    rt.stats.record_reconnect()
    rt.stats.ws_state = rt.ws.state.ws_state
    start = _gap_start(rt, before=now)
    for mint in rt.book.mints():
        state = rt.book.get(mint)
        if state is not None:
            state.mark_gap(now)
    async with role_session(rt.lab.session_factory, db_role=WORKER_ROLE) as session:
        await record_gap(
            session,
            GapRow(
                stream=GAP_STREAM,
                gap_start=start,
                gap_end=now,
                reason="reconnect",
                generation=rt.seen_reconnects,
            ),
        )
