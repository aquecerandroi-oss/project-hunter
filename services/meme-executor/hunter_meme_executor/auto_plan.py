"""Stage 1's pure half (T4.28, split out in T4.94 for the 350-line budget):
which ``proposed`` operator rows the robot opens this tick, which it rejects,
and why the rest wait. No clock, no database, no network — ``auto_approve``
reads the inputs and writes the outcome.

T4.94 (R78, ``.claude/state/notes-R78.md``; ``obsidian/11-KNOWLEDGE/KB-0158``):
a proposal skipped ``mint_busy`` used to wait up to 60 s and was opened by the
first pass after the other operator's exit — on a tape older than the move that
caused that exit (007, BAGI, ANT on 20–25/09/2026; all three lost). Now:

- a proposal whose mint is busy — seen now, or by the rows since it was born
  (``auto_busy.overtaken_proposals``, the guardian's finding 1) — is
  **superseded**: handed back in :attr:`AutoPlan.superseded` for a durable
  rejection by name (:data:`MINT_BUSY_SUPERSEDED`), never a pick then or later;
  so is a same-mint sibling of this pass's pick (:attr:`AutoPlan.siblings`,
  rejected once the pick is opened); the gate proposes the coin again on fresh
  data if it still qualifies;
- the robot opens nothing older than ``max_age_s``
  (``MEME_LIVE_AUTO_APPROVE_MAX_AGE_S``, :data:`AUTO_APPROVE_MAX_AGE_S`), measured
  from ``proposed_at``.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from hunter_core.execution.meme.approval import (
    AUTO_STAGE1_DECIDED_BY,
    ProposalDecision,
    max_sol_per_bet_of,
    proposal_state_refusal,
    size_cap_refusal,
)
from hunter_meme_executor.scope import requested_sol_of

__all__ = [
    "AUTO_APPROVE_MAX_AGE_S",
    "AUTO_NOTE",
    "MINT_BUSY_SUPERSEDED",
    "AutoPlan",
    "OperatorProposal",
    "auto_decision",
    "plan_auto_approvals",
    "superseded_decision",
]

AUTO_APPROVE_MAX_AGE_S = 10.0
"""Default of ``MEME_LIVE_AUTO_APPROVE_MAX_AGE_S`` (T4.94; 60 s before). Older than
this the robot does not decide: the row stays ``proposed`` for the human until
the set's own ``ttl_s`` expires it. Measured on the real desk
(``.claude/state/r78/cache/pop.csv``, 148 positions to 25/09/2026): of the 130
event-lane approvals, the 125 that did not wait in the ``mint_busy`` queue came
within 2.67 s of their tape; the five that waited were 11.5–53.8 s old. Ten
ticks of the 1 s loop plus the 1.5 s risk read fit well inside it.

Measured from ``proposed_at``, not ``features_end_time``: on the 15-second lane
``features_end_time`` is the bucket's end and trails the Lab tick that proposes
by up to ~15 s by design (decided − features_end_time 1.8–28.7 s, 18 real
entries) — bounding that lag would be a strategy change, not this fix."""
AUTO_NOTE = "auto_stage1: aberta pelo executor sem clique"
MINT_BUSY_SUPERSEDED = "mint_busy_superseded"
"""The rejection of a proposal whose mint had an open position or a buy in flight
at a pass: its quote, flow and holders predate whatever that position is about
to do, so it is never opened later — ``decision.auto_refusal`` and the skip
name alike."""


@dataclass(frozen=True, slots=True)
class OperatorProposal:
    id: str
    mint: str
    suggested: dict[str, Any]
    proposed_at: datetime
    expires_at: datetime
    rule_set_params: dict[str, Any]
    series: str | None = None
    """``reasons[0].series`` — the lane, for the per-lane ``too_old`` count."""


@dataclass(frozen=True, slots=True)
class AutoPlan:
    picks: tuple[OperatorProposal, ...] = ()
    superseded: tuple[OperatorProposal, ...] = ()
    """To be rejected ``mint_busy_superseded`` now (T4.94) — never a pick."""
    siblings: tuple[OperatorProposal, ...] = ()
    """Same mint as a pick of this pass: rejected ``mint_busy_superseded`` once
    that pick is actually opened (the caller counts them then, not here)."""
    skipped: dict[str, int] = field(default_factory=lambda: dict[str, int]())


def plan_auto_approvals(
    candidates: list[OperatorProposal],
    *,
    now: datetime,
    approved_last_hour: int,
    max_per_hour: int,
    max_per_tick: int = 1,
    max_age_s: float = AUTO_APPROVE_MAX_AGE_S,
    busy_mints: frozenset[str] = frozenset(),
    superseded_ids: frozenset[str] = frozenset(),
    cooling_mints: frozenset[str] = frozenset(),
    snapshot_mints: frozenset[str] | None = None,
) -> AutoPlan:
    """Pure: which ``proposed`` rows become live this tick, and why the rest do not.

    Skip names: ``expired`` · ``too_old`` (older than ``max_age_s``; also counted
    as ``too_old:<series>`` when the lane is known) · ``mint_busy_superseded``
    (T4.94: an open live position or a buy in flight on that mint, or an id in
    ``superseded_ids`` — the rows show activity on the mint since the proposal
    was born; the row goes to :attr:`AutoPlan.superseded` for a rejection, it
    does not wait for the mint to free) · ``recently_refused`` (T4.28f: the
    admission refused this mint for a reason that needs more than a tick to
    change — ``refusal_cooldown``) · ``risk_snapshot_pending`` (T4.28g: the rug
    read check 11 needs has not landed for this mint yet — ``risk_snapshot``) ·
    ``suggested_incomplete`` · ``exceeds_max_sol_per_bet`` (the click's rule) ·
    ``hourly_cap`` · ``tick_cap``. A candidate on the mint of an earlier pick of
    this pass goes to :attr:`AutoPlan.siblings` (before the caps, so it is never
    left queued as ``tick_cap``). Candidates are visited in the order given
    (oldest first).

    ``snapshot_mints`` is the subset of candidate mints with a fresh, measured
    ``bundled_share``; ``None`` means the caller did not measure and the skip does
    not run — the pre-T4.28g behaviour (open, and let the admission refuse by name).
    ``auto_approve_once`` always measures. The skip needs no age condition of its
    own: ``too_old`` is evaluated first, so anything reaching it is younger than
    ``max_age_s`` and an older row is the human's either way."""
    picks: list[OperatorProposal] = []
    superseded: list[OperatorProposal] = []
    siblings: list[OperatorProposal] = []
    skipped: Counter[str] = Counter()
    mints: set[str] = set()
    budget = max(0, max_per_hour - approved_last_hour)
    for candidate in candidates:
        if proposal_state_refusal("proposed", candidate.expires_at, now, approving=True):
            skipped["expired"] += 1
            continue
        if (now - candidate.proposed_at).total_seconds() > max_age_s:
            skipped["too_old"] += 1
            if candidate.series:
                skipped[f"too_old:{candidate.series}"] += 1
            continue
        if candidate.mint in busy_mints or candidate.id in superseded_ids:
            skipped[MINT_BUSY_SUPERSEDED] += 1
            superseded.append(candidate)
            continue
        if candidate.mint in mints:
            siblings.append(candidate)
            continue
        if candidate.mint in cooling_mints:
            skipped["recently_refused"] += 1
            continue
        if snapshot_mints is not None and candidate.mint not in snapshot_mints:
            skipped["risk_snapshot_pending"] += 1
            continue
        size = requested_sol_of(candidate.suggested)
        if size <= 0:
            skipped["suggested_incomplete"] += 1
            continue
        if size_cap_refusal(max_sol_per_bet_of(candidate.rule_set_params), size):
            skipped["exceeds_max_sol_per_bet"] += 1
            continue
        if len(picks) >= budget:
            skipped["hourly_cap"] += 1
            continue
        if len(picks) >= max_per_tick:
            skipped["tick_cap"] += 1
            continue
        mints.add(candidate.mint)
        picks.append(candidate)
    return AutoPlan(
        picks=tuple(picks),
        superseded=tuple(superseded),
        siblings=tuple(siblings),
        skipped=dict(skipped),
    )


def auto_decision(proposal: OperatorProposal, *, now: datetime) -> ProposalDecision:
    """What the click writes, by the robot: ``decision = suggested`` (the set's own
    numbers, incl. ``manual_plan``) plus the note, ``mode = 'live'``."""
    return ProposalDecision(
        proposal_id=proposal.id,
        status="approved",
        decision={**proposal.suggested, "note": AUTO_NOTE},
        decided_by=AUTO_STAGE1_DECIDED_BY,
        decided_at=now,
        mode="live",
    )


def superseded_decision(proposal: OperatorProposal, *, now: datetime) -> ProposalDecision:
    """T4.94: the robot's rejection of a proposal whose mint was busy — the same
    guarded statement as any decision, ``mode`` left ``paper`` (it never became a
    live proposal), the reason where every robot refusal keeps it."""
    return ProposalDecision(
        proposal_id=proposal.id,
        status="rejected",
        decision={
            "note": f"auto_stage1 recusada: {MINT_BUSY_SUPERSEDED}",
            "auto_refusal": MINT_BUSY_SUPERSEDED,
        },
        decided_by=AUTO_STAGE1_DECIDED_BY,
        decided_at=now,
        mode="paper",
    )
