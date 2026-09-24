"""The event lane's entry at the pullback (T4.91, EXP-M24 / H-017) — the
part that touches the database: the recheck at the trigger, the proposal,
the outcome rows. The pure half (the params, the running max, the book) is
:mod:`hunter_meme_worker.entry_pullback` / :mod:`~.entry_pullback_book`.

**Where it runs.** ``event_gate_eval.evaluate_mint`` arms (``PullbackBook
.arm_gate``) instead of inserting; ``_handle_logs`` prices every
``TradeEvent`` into the book (O(1) for an unarmed mint); ``event_gate
._evaluate_loop`` calls :func:`fire_pullbacks` right after the frame is
folded — before the debounce: the trade is the trigger; the decision is
synchronous, only the insert runs in the bounded pool — and marks every
folded frame (the FIFO proof :func:`expire_pullbacks` needs); ``event_gate
._pullback_loop`` expires and flushes once a second. Nothing here waits:
the arming is a dict entry, not a task.

**Two instants, both declared.** ``trigger_at`` is the ``received_at`` of the
trade that touched the pullback; the decision is ``now`` — the instant the
lane processed it (``proposed_at``), a microsecond after the frame's own
evaluation instant so the two tapes never share ``(mint, as_of)``. The
recheck and the quote read the state at ``now``, which may already include
later fills of the same notification.

**The recheck (fail closed).** In order: the mint still on the book, no feed
gap since ``t0``, the set unchanged since ``t0`` (the whole frozen
``RuleSetSpec``), the creator's flow not overflowed and no creator sale since
``t0``, a base row; then the same ``evaluate_gate`` at ``now`` — any refusal
outside :data:`~.entry_pullback.WAIVED_AT_TRIGGER` kills — and a snapshot to
quote. A judgement is the trail row ``pullback_killed:<name>``; an
operational loss is ``pullback_censored:<name>`` (``entry_pullback.CENSORING``).

**The proposal.** ``draft_proposal`` over the ``t0`` row (``features_end_time
= t0``: the features judged), the quote at ``now``, the ``t0`` reasons (their
``decision_tape`` block is ``t0``'s) plus the ``entry_pullback`` block. The
trail row ``refusal = NULL`` is written only for a row that really landed;
the tape of ``now`` is offered once, linked to every id inserted.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from hunter_core.db.session import role_session
from hunter_core.logging import get_logger
from hunter_meme_worker import event_gate_eval as _eval
from hunter_meme_worker.entry_pullback import (
    CENSORED_PREFIX,
    FEED_LOST,
    NO_PULLBACK,
    fatal_refusals,
    outcome_of,
)
from hunter_meme_worker.event_gate_rows import SERIES_EVENT, build_event_row
from hunter_meme_worker.event_gate_trail import capture_tape
from hunter_meme_worker.event_state import MAX_TRADES
from hunter_meme_worker.gate_refusal_trail import RefusalTrailRow
from hunter_meme_worker.lab_trail import write_refusal_trail
from hunter_meme_worker.proposal_race import insert_proposals_reserved, reserve_all
from hunter_meme_worker.proposals import (
    REFUSAL_NO_SNAPSHOT_FOR_QUOTE,
    draft_proposal,
    evaluate_gate,
    quote_for,
)
from hunter_meme_worker.proposals_plan import manual_plan, ticker_of

if TYPE_CHECKING:
    from hunter_meme_worker.decision_tape import DecisionTape
    from hunter_meme_worker.entry_pullback import ArmedEntry
    from hunter_meme_worker.event_gate_runtime import EventGateRuntime
    from hunter_meme_worker.lab_models import RuleSetSpec
    from hunter_meme_worker.proposals import ProposalDraft
    from hunter_meme_worker.proposals_row import GateRow

logger = get_logger(__name__)

WORKER_ROLE = "hunter_worker"
TRAIL_BATCH = 200
"""Rows per flush — ``config_trail``'s default cap, so the cap never drops one."""
DEPTH_QUANTUM = Decimal("0.000001")
INSERT_FAILED = "pullback_insert_failed"
INSERT_SATURATED = "pullback_insert_saturated"
NOT_INSERTED = "pullback_not_inserted"

__all__ = ["expire_pullbacks", "fire_pullbacks", "flush_pullback_trail"]


def _ttl(rt: EventGateRuntime, spec: RuleSetSpec) -> int:
    return rt.lab.config.lab_proposal_ttl_s if spec.ttl_s is None else spec.ttl_s


def _trigger_draft(
    rt: EventGateRuntime, entry: ArmedEntry, spec: RuleSetSpec, row: GateRow, *, now: datetime
) -> ProposalDraft:
    assert row.snapshot is not None
    ttl = _ttl(rt, spec)
    suggested = spec.suggested()
    if spec.kind == "operator":
        ticker = ticker_of(row.symbol, row.mint)
        suggested["manual_plan"] = manual_plan(spec, ticker=ticker, proposed_at=now, ttl_s=ttl)
    return draft_proposal(
        entry.row,
        spec,
        quote=quote_for(row, row.snapshot, spec),
        reasons=[*entry.draft.reasons, entry.block(now)],
        suggested=suggested,
        now=now,
        ttl_s=ttl,
    )


def _recheck(rt: EventGateRuntime, entry: ArmedEntry, now: datetime) -> ProposalDraft | str:
    """The draft to insert, or the name of what killed the entry."""
    state, caches = rt.book.get(entry.mint), rt.lab.caches
    if state is None or caches is None:
        return "feed_lost"
    if state.gaps != entry.gaps:
        return "feed_gap"
    spec = next((s for s in caches.specs if s.id == entry.spec_id), None)
    if spec is None or spec != entry.spec:
        return "spec_changed"
    if len(state.creator_trades) >= MAX_TRADES:
        return "creator_flow_overflow"  # the deque dropped fills: the count is not monotonic
    if state.creator_flow(now).sells > entry.creator_sells:
        return "creator_sold_during_wait"
    base = caches.base_rows.get(entry.mint)
    if base is None:
        return "no_base_row"
    row = build_event_row(
        base,
        state,
        as_of=now,
        reserves=rt.reserves.get(entry.mint),
        holders_readings=_eval._holders_readings(rt.radar, entry.mint),  # pyright: ignore[reportPrivateUsage]
    )
    outcome = evaluate_gate(
        spec,
        [row],
        now=now,
        ttl_s=rt.lab.config.lab_proposal_ttl_s,
        already_open=caches.open_mints.get(spec.id, frozenset())
        | caches.recently_proposed_mints(spec.id, now=now),
        pedigree=_eval._pedigree_of(rt, entry.mint),  # pyright: ignore[reportPrivateUsage]
        e2b=_eval._e2b_of(rt, entry.mint, row.end_time),  # pyright: ignore[reportPrivateUsage]
    )
    fatal = fatal_refusals(outcome.refusals.elements())
    if fatal:
        return fatal[0]
    if row.snapshot is None:
        return REFUSAL_NO_SNAPSHOT_FOR_QUOTE
    return _trigger_draft(rt, entry, spec, row, now=now)


async def _insert(
    rt: EventGateRuntime, mint: str, ready: list[tuple[ArmedEntry, ProposalDraft]], now: datetime
) -> tuple[list[str], list[tuple[ArmedEntry, str]]]:
    """``(ids inserted, (entry, outcome) of every draft that did not land)``.

    Never touches ``rt.proposing`` (risk-engine-guardian): that guard is the
    open proposal transaction's of whoever took it — ``evaluate_mint`` of the
    same mint may hold it right now — and this path queues nothing on
    ``pending_trail`` for the periodic flush to race with."""
    caches = rt.lab.caches
    assert caches is not None
    ids: list[str] = []
    missed: list[tuple[ArmedEntry, str]] = []
    try:
        async with role_session(rt.lab.session_factory, db_role=WORKER_ROLE) as session:
            rows: list[RefusalTrailRow] = []
            for entry, draft in ready:
                assert entry.spec is not None
                inserted = await insert_proposals_reserved(
                    session, caches, entry.spec_id, [draft], now=now, ttl_s=_ttl(rt, entry.spec)
                )
                if inserted:
                    ids.append(draft.id)
                    rows.append(RefusalTrailRow(now, entry.spec_id, mint, None))
                else:
                    missed.append((entry, NOT_INSERTED))
            await write_refusal_trail(session, rt.lab.state.trail, rows)
    except Exception as exc:  # the proposal did not land: named, never a no_pullback
        logger.warning("meme_event_gate_pullback_insert_failed", mint=mint, error=str(exc))
        return [], [(entry, INSERT_FAILED) for entry, _draft in ready]
    return ids, missed


def _queue_outcomes(
    rt: EventGateRuntime,
    mint: str,
    outcomes: list[tuple[ArmedEntry, str]],
    tape: DecisionTape | None,
    now: datetime,
) -> None:
    for entry, outcome in outcomes:
        logger.info("meme_event_gate_pullback_outcome", mint=mint, outcome=outcome)
        rt.pullback.queue_trail(RefusalTrailRow(now, entry.spec_id, mint, outcome), tape)
        tape = None  # one offer per (mint, as_of)


async def _insert_and_record(
    rt: EventGateRuntime,
    mint: str,
    ready: list[tuple[ArmedEntry, ProposalDraft]],
    tape: DecisionTape | None,
    now: datetime,
) -> None:
    """The pool's half (``rt.pullback_inserts``): the insert, then the tape
    linked to every id that landed (or handed to the first miss), the
    counters and the Lab's wake — never on the evaluation loop."""
    ids, missed = await _insert(rt, mint, ready, now)
    rt.pullback.proposed += len(ids)
    rt.pullback.not_inserted += len(missed)
    if ids:
        rt.stats.record_proposals(len(ids))
        if tape is not None:
            rt.tapes.offer(tape, proposal_ids=ids)
            tape = None
    _queue_outcomes(rt, mint, missed, tape, now)
    if ids and rt.lab.wake is not None:
        await rt.lab.wake()


def fire_pullbacks(rt: EventGateRuntime, mint: str, now: datetime) -> None:
    """Every entry of ``mint`` whose pullback a trade just touched, decided at
    ``now`` **synchronously** (recheck, draft, reservation, tape — the
    decision instant never moves); only the insert goes to the bounded pool
    (``BoundedTasks``) so the shared evaluation loop never waits on the
    database. A full pool is the named miss ``pullback_insert_saturated``."""
    fired = rt.pullback.pop_fired(mint)
    if not fired:
        return
    ready: list[tuple[ArmedEntry, ProposalDraft]] = []
    outcomes: list[tuple[ArmedEntry, str]] = []
    for entry in fired:
        verdict = _recheck(rt, entry, now)
        if isinstance(verdict, str):
            outcome = outcome_of(verdict)
            if outcome.startswith(CENSORED_PREFIX):
                rt.pullback.censored += 1
            else:
                rt.pullback.killed_by_recheck += 1
            outcomes.append((entry, outcome))
        else:
            ready.append((entry, verdict))
    state = rt.book.get(mint)
    tape = (
        capture_tape(rt, state, as_of=now, series=SERIES_EVENT)
        if rt.config.decision_tape and state is not None
        else None
    )
    if ready and not rt.pullback_inserts.has_room():
        rt.pullback_inserts.saturated += 1
        rt.pullback.not_inserted += len(ready)
        outcomes.extend((entry, INSERT_SATURATED) for entry, _draft in ready)
        ready = []
    if ready:
        caches = rt.lab.caches
        assert caches is not None
        for entry, draft in ready:  # reserved now: no other lane proposes it meanwhile
            assert entry.spec is not None
            reserve_all(caches, entry.spec_id, [draft], now=now, ttl_s=_ttl(rt, entry.spec))
        rt.pullback_inserts.spawn(_insert_and_record(rt, mint, ready, tape, now))
        tape = None  # travels with the insert: linked to the ids that land
    _queue_outcomes(rt, mint, outcomes, tape, now)


def expire_pullbacks(rt: EventGateRuntime, now: datetime) -> None:
    """Every entry whose window is over (``PullbackBook.pop_due``): a
    ``no_pullback`` row (``value`` = the deepest pullback seen, %) — or
    ``pullback_censored:feed_lost`` when the mint left the book or its feed
    had a gap, since "no pullback" is then a claim the lane cannot make."""
    tapes: dict[str, DecisionTape | None] = {}
    for entry, due in rt.pullback.pop_due(now):
        state = rt.book.get(entry.mint)
        outcome = due if state is not None and state.gaps == entry.gaps else FEED_LOST
        if outcome == NO_PULLBACK:
            rt.pullback.expired_no_pullback += 1
        else:
            rt.pullback.censored += 1
        tape = None
        if entry.mint not in tapes:
            tape = (
                capture_tape(rt, state, as_of=now, series=SERIES_EVENT)
                if rt.config.decision_tape and state is not None
                else None
            )
            tapes[entry.mint] = tape
        depth = entry.deepest_pct.quantize(DEPTH_QUANTUM) if outcome == NO_PULLBACK else None
        row = RefusalTrailRow(
            now, entry.spec_id, entry.mint, outcome, value=depth, limit=entry.params.pct
        )
        rt.pullback.queue_trail(row, tape)


async def flush_pullback_trail(rt: EventGateRuntime) -> None:
    """Write the queued outcome rows (at most :data:`TRAIL_BATCH`), then offer
    their tapes — ``event_gate._pullback_loop``'s own write, never the
    evaluation's."""
    queued = rt.pullback.drain_trail(TRAIL_BATCH)
    if not queued:
        return
    try:
        async with role_session(rt.lab.session_factory, db_role=WORKER_ROLE) as session:
            await write_refusal_trail(session, rt.lab.state.trail, [row for row, _t in queued])
    except Exception:
        rt.pullback.requeue_trail(queued)  # retried next cycle; never lost to a timeout
        raise
    for _row, tape in queued:
        if tape is not None:
            rt.tapes.offer(tape, proposal_ids=())
