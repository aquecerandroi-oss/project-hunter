"""The event lane's refusal trail and decision tapes (T4.52b F6/F7, T4.89) —
split from :mod:`hunter_meme_worker.event_gate_eval` for the 350-line budget;
that module re-exports :func:`flush_pending_trail`.

**The trail** (F6/F7): a mint's latest candidates are queued
(``EventGateRuntime.pending_trail``) and written at most once a minute per
mint — piggybacked on a proposal's session, or by the periodic flush.

**The tape** (T4.89) rides the same pairing: the capture taken at an
evaluation is queued **with** that evaluation's candidates
(``pending_tapes``) and replaced with them, so the tape offered for a trail
row is the one taken at that row's own ``as_of`` — never a re-capture at
flush time (another state), and never one tape per evaluation of a mint that
stays a near-miss (only the written trail row gets one). A proposal's tape is
offered once per evaluation, after the transaction committed, with the ids it
really inserted; when its trail row is written later, the tape is already
recorded. While a proposal's transaction is open for a mint
(``EventGateRuntime.proposing``), the periodic flush leaves that mint alone —
its trail row and tape are the proposal's own session's to write, or the
flush would offer the tape unlinked first and ``ON CONFLICT DO NOTHING`` would
keep it that way. Nothing here awaits the tape write: :meth:`DecisionTapeWriter.offer`
is O(1) and the flush is ``event_gate._tape_flush_loop``'s.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta
from typing import TYPE_CHECKING

from hunter_core.db.session import role_session
from hunter_core.logging import get_logger
from hunter_meme_worker.decision_tape import capture_decision_tape
from hunter_meme_worker.lab_trail import write_refusal_trail

if TYPE_CHECKING:
    from collections.abc import Sequence

    from sqlalchemy.ext.asyncio import AsyncSession

    from hunter_meme_worker.decision_tape import DecisionTape
    from hunter_meme_worker.event_gate_runtime import EventGateRuntime
    from hunter_meme_worker.event_state import MintEventState
    from hunter_meme_worker.gate_refusal_trail import RefusalTrailRow
    from hunter_meme_worker.proposals import ProposalDraft

logger = get_logger(__name__)

WORKER_ROLE = "hunter_worker"
TRAIL_COOLDOWN_S = 60
"""F7: at most one refusal-trail write per mint in this window."""

__all__ = [
    "TRAIL_COOLDOWN_S",
    "capture_tape",
    "flush_pending_trail",
    "queue_trail",
    "record_tapes",
    "with_evidence",
    "write_pending_trail",
]


def capture_tape(
    rt: EventGateRuntime, state: MintEventState, *, as_of: datetime, series: str
) -> DecisionTape | None:
    """The snapshot, or ``None`` (logged, counted) — a bug here never costs
    the decision it was meant to explain."""
    try:
        return capture_decision_tape(state, as_of=as_of, series=series)
    except Exception as exc:
        rt.tapes.record_capture_failed()
        logger.warning(
            "meme_decision_tape_capture_failed",
            mint=state.mint,
            error_type=type(exc).__name__,
            error=str(exc),
        )
        return None


def with_evidence(drafts: list[ProposalDraft], tape: DecisionTape | None) -> list[ProposalDraft]:
    """Append the tape's derived block to each draft's ``reasons`` (evidence,
    ``used_by_gate = false``) — inserted in the proposal's own transaction."""
    if tape is None:
        return drafts
    block = tape.reasons_block()
    return [replace(d, reasons=[*d.reasons, block]) for d in drafts]


def queue_trail(
    rt: EventGateRuntime,
    mint: str,
    candidates: list[RefusalTrailRow],
    tape: DecisionTape | None,
) -> None:
    """The candidates and the capture of the same evaluation, replaced together."""
    rt.pending_trail[mint] = candidates
    if tape is None:
        rt.pending_tapes.pop(mint, None)
    else:
        rt.pending_tapes[mint] = tape


def record_tapes(
    rt: EventGateRuntime,
    mint: str,
    tape: DecisionTape | None,
    proposal_ids: Sequence[str],
    trail_tape: DecisionTape | None,
) -> None:
    """After the proposal's transaction committed: one offer per instant. A
    capture no row explains (every insert lost its ``ON CONFLICT`` and no trail
    row of that instant is queued) is counted ``unlinked``, never dropped
    silently."""
    if trail_tape is not None and trail_tape is not tape:
        rt.tapes.offer(trail_tape, proposal_ids=())  # an older instant's trail row
    if tape is None:
        return
    if not (proposal_ids or trail_tape is tape):
        if rt.pending_tapes.get(mint) is not tape:
            rt.tapes.record_unlinked()
        return
    rt.tapes.offer(tape, proposal_ids=proposal_ids)
    if rt.pending_tapes.get(mint) is tape:
        del rt.pending_tapes[mint]  # its trail row, written later, finds it recorded


async def write_pending_trail(
    rt: EventGateRuntime, session: AsyncSession, mint: str, now: datetime
) -> DecisionTape | None:
    """Write ``mint``'s queued trail if its cooldown elapsed; the tape taken
    at those candidates' instant, for the caller to offer after commit."""
    last = rt.trail_last_written.get(mint)
    if last is not None and now - last < timedelta(seconds=TRAIL_COOLDOWN_S):
        return None
    candidates = rt.pending_trail.pop(mint, None)
    tape = rt.pending_tapes.pop(mint, None)
    if not candidates:
        return None
    await write_refusal_trail(session, rt.lab.state.trail, candidates)
    rt.trail_last_written[mint] = now
    return tape


async def flush_pending_trail(rt: EventGateRuntime, now: datetime) -> None:
    """The periodic path (``event_gate.py``'s own 15-second loop): every mint
    whose cooldown has elapsed and still has something queued, written once,
    in one shared session — the other half of F6/F7's "never per evaluation"."""
    due = [
        mint
        for mint, candidates in rt.pending_trail.items()
        if candidates
        and mint not in rt.proposing  # the proposal's own session writes it
        and (
            (last := rt.trail_last_written.get(mint)) is None
            or now - last >= timedelta(seconds=TRAIL_COOLDOWN_S)
        )
    ]
    if not due:
        return
    tapes: list[DecisionTape] = []
    async with role_session(rt.lab.session_factory, db_role=WORKER_ROLE) as session:
        for mint in due:
            tape = await write_pending_trail(rt, session, mint, now)
            if tape is not None:
                tapes.append(tape)
    for tape in tapes:
        rt.tapes.offer(tape, proposal_ids=())
