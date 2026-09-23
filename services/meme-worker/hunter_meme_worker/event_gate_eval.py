"""Fold one notification into a mint's state, and judge it (T4.52b-3/4): the
part of the event gate that touches the database — one row, the same
``evaluate_gate``/``insert_proposals_reserved``/``write_refusal_trail`` the
15-second lane already uses (module docstring of ``event_gate.py``).

**F6/F7 (review-T4.52b.md §4): a session only when there is something to
write.** ``shadow`` never opens ``role_session`` at all — it judges every
spec in memory, counts, logs, and returns. ``on`` opens one only when at
least one spec produced a draft to insert; the per-mint refusal trail is
queued (``EventGateRuntime.pending_trail``) rather than written every
evaluation, flushed either piggybacked on that same insert's session (this
module) or by the periodic ``flush_pending_trail`` (``event_gate.py``'s own
15-second loop) — never more than once per mint per minute either way
(``event_gate_trail.py``, re-exported here).

**T4.89 — the decision tape.** When an evaluation has something to record (a
draft or a trail candidate), ``decision_tape.capture_decision_tape`` snapshots
the in-memory tape at ``now``, synchronously and before the first ``await``;
a proposal carries its derived block in ``reasons`` (evidence, not a
criterion) and the tape itself is offered to the background writer after the
transaction commits — the decision never waits on it and never fails for it.
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
from hunter_meme_worker.event_gate_rows import SERIES_EVENT, EventReserves, build_event_row
from hunter_meme_worker.event_gate_trail import (
    capture_tape,
    flush_pending_trail,
    queue_trail,
    record_tapes,
    with_evidence,
    write_pending_trail,
)
from hunter_meme_worker.lab_fast import _trail_row  # pyright: ignore[reportPrivateUsage]
from hunter_meme_worker.proposal_race import insert_proposals_reserved, reserve_all
from hunter_meme_worker.proposals import evaluate_gate
from hunter_meme_worker.repo import record_gap
from hunter_meme_worker.repo_rows import GapRow

if TYPE_CHECKING:
    from hunter_exchanges.pumpfun.rpc_ws_models import Notification
    from hunter_indicators.meme.pedigree import PedigreeFeatures
    from hunter_indicators.meme.pedigree_e2b import E2bFeatures
    from hunter_meme_worker.context import RadarContext
    from hunter_meme_worker.event_gate_caches import EventGateCaches
    from hunter_meme_worker.event_gate_runtime import EventGateRuntime
    from hunter_meme_worker.features_tape import HoldersObservation
    from hunter_meme_worker.gate_refusal_trail import RefusalTrailRow
    from hunter_meme_worker.lab_models import RuleSetSpec
    from hunter_meme_worker.proposals import GateOutcome, GateRow, ProposalDraft

logger = get_logger(__name__)

WORKER_ROLE = "hunter_worker"
GAP_STREAM = "solana_ws"

__all__ = ["apply_notification", "evaluate_mint", "flush_pending_trail", "handle_reconnect"]


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


def _record_shadow(
    rt: EventGateRuntime,
    caches: EventGateCaches,
    spec: RuleSetSpec,
    mint: str,
    row: GateRow,
    outcome: GateOutcome,
    already_proposed: frozenset[str],
    *,
    now: datetime,
) -> None:
    """``shadow`` writes nothing (F6/F7) — only counts, logs, and classifies
    against ``already_proposed`` (the 15-second lane's own recent proposals;
    ``shadow`` itself never populates this set — only ``lab_fast.py`` does).
    A mint the 15-second lane already covered is "agree" (both lanes would
    act on it); one it did not is "only" (the event lane's own edge) —
    metrics §5's ``shadow_agree_mints``/``shadow_only_event_mints``.
    ``shadow_proposals_total`` is deduplicated per ``(mint, rule_set)``
    (``caches.shadow_marked_until``) so one hot mint re-evaluated every
    debounce window is not counted every time."""
    if mint in already_proposed:
        rt.stats.record_shadow_agree(mint, now)
        return
    if not outcome.drafts:
        return
    rt.stats.record_shadow_only(mint, now)
    ttl = rt.lab.config.lab_proposal_ttl_s if spec.ttl_s is None else spec.ttl_s
    if not caches.shadow_recently_marked(spec.id, mint, now=now):
        rt.stats.record_shadow_proposals(len(outcome.drafts))
        # Re-review 9d3c72a1: the latency must be observable in shadow, or
        # there is nothing to demand (p50 < 1 s) before turning it on.
        latency = _event_to_proposal_s(rt, mint, now)
        if latency is not None:
            rt.stats.latency_s.append(latency)
    caches.mark_shadow(mint, spec.id, now=now, ttl_s=ttl)
    logger.info(
        "meme_event_gate_would_propose",
        mint=mint,
        rule_set=spec.label,
        mcap_sol=str(row.mcap_sol),
        progress_pct=str(row.curve_progress_pct),
    )


async def evaluate_mint(rt: EventGateRuntime, mint: str, now: datetime) -> None:
    """Build the row and judge it against every cached 15-second set.
    ``shadow`` never opens a session (F6); ``on`` opens one only when a spec
    produced a draft to insert, piggybacking that mint's queued trail onto
    the same transaction."""
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
    if row.early_retention_pct is None:
        # T4.70 (notes-T4.66.md §7, P0): the heartbeat's own acceptance
        # number — the share of judged mints EXP-M19 could not measure.
        rt.stats.record_early_retention_unknown(now)
    shadow = rt.config.mode == GATE_SHADOW
    to_insert: list[tuple[RuleSetSpec, list[ProposalDraft]]] = []
    trail_candidates: list[RefusalTrailRow] = []
    for spec in caches.specs:
        already_positions = caches.open_mints.get(spec.id, frozenset())
        already_proposed = caches.recently_proposed_mints(spec.id, now=now)
        outcome = evaluate_gate(
            spec,
            [row],
            now=now,
            ttl_s=rt.lab.config.lab_proposal_ttl_s,
            already_open=already_positions | already_proposed,
            pedigree=_pedigree_of(rt, mint),
            e2b=_e2b_of(rt, mint, row.end_time),
        )
        if shadow:
            _record_shadow(rt, caches, spec, mint, row, outcome, already_proposed, now=now)
            continue  # F6/F7: shadow never touches the trail or the database
        if outcome.drafts:
            to_insert.append((spec, outcome.drafts))
        candidate = _trail_row(spec, row, outcome.refusals)
        if candidate is not None:
            trail_candidates.append(candidate)
    if shadow:
        return
    # T4.89: the tape at ``now``, before the first ``await`` — only when this
    # evaluation has something to record.
    tape = (
        capture_tape(rt, state, as_of=now, series=SERIES_EVENT)
        if rt.config.decision_tape and (to_insert or trail_candidates)
        else None
    )
    if trail_candidates:
        queue_trail(rt, mint, trail_candidates, tape)
    if not to_insert:
        return  # F6: nothing to insert — never open a session for the trail alone
    to_insert = [(spec, with_evidence(drafts, tape)) for spec, drafts in to_insert]
    for spec, drafts in to_insert:  # re-review 9d3c72a1: reserve BEFORE the session await
        ttl = rt.lab.config.lab_proposal_ttl_s if spec.ttl_s is None else spec.ttl_s
        reserve_all(caches, spec.id, drafts, now=now, ttl_s=ttl)
    proposed = False
    proposal_ids: list[str] = []
    rt.proposing.add(mint)  # T4.89: the periodic trail flush leaves this mint alone
    try:
        async with role_session(rt.lab.session_factory, db_role=WORKER_ROLE) as session:
            for spec, drafts in to_insert:
                ttl = rt.lab.config.lab_proposal_ttl_s if spec.ttl_s is None else spec.ttl_s
                inserted = await insert_proposals_reserved(
                    session, caches, spec.id, drafts, now=now, ttl_s=ttl
                )
                if inserted:
                    latency = _event_to_proposal_s(rt, mint, now)
                    rt.stats.record_proposals(
                        inserted, latencies=[latency] if latency is not None else None
                    )
                    proposed = True
                    # One row judged: at most one draft per set, so "all inserted"
                    # names exactly the ids that landed (a partial batch names none).
                    if inserted == len(drafts):
                        proposal_ids.extend(d.id for d in drafts)
            trail_tape = await write_pending_trail(rt, session, mint, now)
    finally:
        rt.proposing.discard(mint)
    record_tapes(rt, mint, tape, proposal_ids, trail_tape)
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
    subscribed mint's tape warms again, and the gap is durable.

    S-T4.62 MEDIUM: this runs inline in ``_read_loop`` (``event_gate.py``) —
    a ``statement_timeout``/pool error out of the ``INSERT`` below must not
    kill the gate's own ``TaskGroup`` (the likely source of the 13
    restarts/h the security review measured). The in-memory gap marks above
    always land; only the durable record can fail, and it fails quietly."""
    rt.seen_reconnects = rt.ws.state.reconnects
    rt.stats.record_reconnect()
    rt.stats.ws_state = rt.ws.state.ws_state
    start = _gap_start(rt, before=now)
    for mint in rt.book.mints():
        state = rt.book.get(mint)
        if state is not None:
            state.mark_gap(now)
    try:
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
    except Exception as exc:  # never let a DB hiccup kill the read loop
        rt.stats.record_gap_write_failed()
        logger.warning(
            "meme_event_gate_gap_write_failed", error_type=type(exc).__name__, error=str(exc)
        )
