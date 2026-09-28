"""EXP-M26's opportunity record (R1, ``0066``, design §1.6/§2.2/§7): the first
1-minute evaluation per (rule set, mint) in which the set's **pure** gate lets
the mint through, written once, with the inputs read at that tick.

``lab._gate_step`` hands every set with ``exp_ref = 'EXP-M26'`` to
:func:`mature_gate_step` instead of the batch ``evaluate_gate``; every other set
is untouched, and with zero such sets nothing here runs. For each row of the
closed minute the step:

1. runs ``evaluate_gate`` on that row alone — the same proposals and the same
   refusal counts as the batch call (its loop body never reads a sibling row,
   the T4.43 argument) — so the proposal layer's refusals of **this** row are
   known by name, all of them;
2. decides the pure gate apart: ``evaluate_entry`` over the row's own features
   and the set's gate — age, progress, participation, line, Mayhem — without the
   cross-cutting exclusions (pedigree, identity, event) or the quote's photo;
   a mint the set already holds is not evaluated (``already_open``), exactly as
   the proposal layer does;
3. inserts the proposals, each in its own savepoint (``lab_repo_opportunities``);
4. for the mints passing the pure gate that this set has no row for yet, reads
   the photos of ``(T − 16 min, T]`` once (the coverage guard) and writes the
   row ``ON CONFLICT (rule_set_id, mint) DO NOTHING``.

**Never blocks the tick.** Every write is a savepoint; a failure is counted
(``MatureOpportunityState``, heartbeat ``lab_mature_*``) and logged, and the
minute goes on. **Deterministic order:** minutes oldest first
(``lab.closed_minutes``), sets by name/version, so after a restart the backlog
re-evaluates the same first minute; a pass the process could not write is
remembered and its successor is ``earlier_pass_unrecorded``, never a substitute.
``lane_since`` — the first minute this process evaluated for EXP-M26 — lets the
reader find the passes a restart gap may have hidden (§68).
"""

from __future__ import annotations

import os
from collections import Counter
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field, fields
from datetime import datetime, timedelta
from decimal import Decimal
from typing import TYPE_CHECKING, Any

from hunter_core.domain.types import uuid7
from hunter_indicators.meme.pedigree import PEDIGREE_V1
from hunter_indicators.meme.rules import evaluate_entry
from hunter_indicators.meme.rules_criteria import participation_pct
from hunter_meme_worker.lab_opportunities_coverage import (
    COVERAGE_VERSION,
    coverage_of,
    unread_coverage,
)
from hunter_meme_worker.lab_repo_opportunities import (
    bounded_line_points,
    insert_opportunity,
    insert_proposal_linked,
    linked_proposal,
    recorded_mints,
)
from hunter_meme_worker.proposals import entry_features_of, evaluate_gate, gate_reasons
from hunter_meme_worker.proposals_identity import event_features_of, identity_features_of

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from hunter_indicators.meme.pedigree import PedigreeFeatures
    from hunter_indicators.meme.pedigree_e2b import E2bFeatures
    from hunter_meme_worker.lab_models import RuleSetSpec
    from hunter_meme_worker.proposals import GateRow, ProposalDraft

__all__ = [
    "MATURE_CHART_RULE_SET_IDS",
    "MATURE_EXP_REF",
    "MatureOpportunityState",
    "MatureStepResult",
    "code_ref",
    "is_mature",
    "mature_gate_step",
]

MATURE_EXP_REF = "EXP-M26"
MATURE_CHART_RULE_SET_IDS: tuple[str, ...] = (
    "01994d00-6c1a-7000-8000-00000000001f",  # grafico_ctrl_v1/1 (C)
    "01994d00-6c1a-7000-8000-000000000020",  # grafico_v1/1 (L)
    "01994d00-6c1a-7000-8000-000000000021",  # grafico_v1/2 (H)
)
"""``0068``'s seed. The desk's pedigree read subtracts their paper bets
(``lab_repo_fast._PEDIGREE``), like the probe's and the pullback arms'."""


def is_mature(spec: RuleSetSpec) -> bool:
    return spec.exp_ref == MATURE_EXP_REF


def code_ref() -> str:
    """The commit this process runs (``HUNTER_RELEASE``, set from ``GIT_SHA`` by
    the image); ``unknown`` said out loud when the build did not stamp it."""
    return os.environ.get("HUNTER_RELEASE") or "unknown"


@dataclass
class MatureOpportunityState:
    """Since boot: what ``lab_heartbeat`` reports as ``lab_mature_*``."""

    written_total: int = 0
    unfaithful_total: int = 0
    """Rows written with ``fidelity`` other than ``faithful``."""
    failed_total: int = 0
    """Pairs whose full row **and** minimal marker were both refused."""
    proposal_failed_total: int = 0
    lane_since: datetime | None = None
    failed_pairs: set[tuple[str, str]] = field(default_factory=set[tuple[str, str]])


@dataclass(frozen=True, slots=True)
class MatureStepResult:
    refusals: Counter[str]
    evaluated: int
    proposals: int


def _json(value: Any) -> Any:
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    if value is None or isinstance(value, bool | int | str):
        return value
    as_json = getattr(value, "as_json", None)
    return as_json() if callable(as_json) else repr(value)


def _inputs(row: GateRow) -> dict[str, Any]:
    """The whole row as the lane read it — decimals as strings, never floats."""
    return {f.name: _json(getattr(row, f.name)) for f in fields(row)}


def _pedigree(lineage: PedigreeFeatures | None) -> dict[str, Any] | None:
    if lineage is None:
        return None
    return {f.name: getattr(lineage, f.name) for f in fields(lineage)}


def _values(
    spec: RuleSetSpec,
    row: GateRow,
    *,
    refusals: Iterable[str],
    link: tuple[str | None, str | None],
    ours: bool,
    lineage: PedigreeFeatures | None,
    coverage: tuple[str, dict[str, Any]],
    now: datetime,
    features_version: str,
    lane_since: datetime,
    fidelity: str,
) -> dict[str, Any]:
    features = entry_features_of(row, spec)
    names = sorted(set(refusals))
    proposal_id, reason = link
    if proposal_id is None and names:
        reason = "refused"
    status, detail = coverage
    return {
        "id": str(uuid7()),
        "rule_set_id": spec.id,
        "mint": row.mint,
        "evaluated_at": now,
        "features_end_time": row.end_time,
        "features_version": features_version,
        "features_computed_at": row.computed_at,
        "code_ref": code_ref(),
        "age_s": features.age_s,
        "curve_progress_pct": row.curve_progress_pct,
        "mcap_sol": row.mcap_sol,
        "curve_volume_1m_sol": row.curve_volume_1m_sol,
        "participation_pct": participation_pct(spec.size_sol, row.curve_volume_1m_sol),
        "creator_net_seller": row.creator_sold,
        "higher_lows": row.higher_lows,
        "breakout_15m": row.breakout_15m,
        "distance_to_support_pct": row.distance_to_support_pct,
        "line_reason": row.line_reason,
        "line_points": row.line_points,
        "mcap_slope_15m": row.mcap_slope_15m,
        "mayhem_enabled": row.mayhem_enabled,
        "mayhem_state": row.mayhem_state,
        "completed_at": row.completed_at,
        "migrated_at": row.migrated_at,
        "inputs": _inputs(row),
        "gate": gate_reasons(
            features,
            spec,
            pedigree=lineage,
            pedigree_gate=PEDIGREE_V1 if lineage is not None else None,
            identity=identity_features_of(row),
            event=event_features_of(row),
        ),
        "pedigree": _pedigree(lineage),
        "coverage_version": COVERAGE_VERSION,
        "coverage_status": status,
        "coverage": detail,
        "proposal_refusals": names,
        "proposal_id": proposal_id,
        "fresh_proposal_id": proposal_id if ours else None,
        "no_proposal_reason": None if proposal_id is not None else reason,
        "fidelity": fidelity,
        "lane_since": lane_since,
    }


def _fidelity(
    spec: RuleSetSpec, row: GateRow, state: MatureOpportunityState, lane_since: datetime
) -> str:
    """What the process can prove before the ``INSERT`` adds its own proof (an earlier
    proposal). ``eligible_before_lane``: the mint could pass this gate in a minute
    before the first one this process evaluated — a restart gap may hide its first
    pass, so it is never read as the first (Astra, R1 review, must-fix 1)."""
    if (spec.id, row.mint) in state.failed_pairs:
        return "earlier_pass_unrecorded"
    first_eligible = (
        None if row.created_at is None else row.created_at + timedelta(seconds=spec.gate.min_age_s)
    )
    if first_eligible is None or first_eligible <= lane_since - timedelta(minutes=1):
        return "eligible_before_lane"
    return "faithful"


async def mature_gate_step(
    session: AsyncSession,
    state: MatureOpportunityState,
    spec: RuleSetSpec,
    rows: list[GateRow],
    *,
    now: datetime,
    ttl_s: int,
    already_open: frozenset[str],
    pedigree: Mapping[str, PedigreeFeatures] | None,
    e2b: Mapping[tuple[str, datetime], E2bFeatures] | None,
    features_version: str,
    minute: datetime,
) -> MatureStepResult:
    """One closed minute of one EXP-M26 set: proposals, then first opportunities."""
    lane_since = state.lane_since = minute if state.lane_since is None else state.lane_since
    refusals: Counter[str] = Counter()
    evaluated = proposals = 0
    passed: list[tuple[GateRow, tuple[str, ...], tuple[str | None, str | None], bool]] = []
    for row in rows:
        outcome = evaluate_gate(
            spec, [row], now=now, ttl_s=ttl_s, already_open=already_open, pedigree=pedigree, e2b=e2b
        )
        refusals.update(outcome.refusals)
        evaluated += outcome.evaluated
        link: tuple[str | None, str | None] = (None, None)
        draft: ProposalDraft | None = outcome.drafts[0] if outcome.drafts else None
        if draft is not None:
            link = await insert_proposal_linked(session, draft)
            proposals += link[0] == draft.id
            state.proposal_failed_total += link[1] == "insert_failed"
        # An open mint is not skipped here (Astra, R1 review): an open position means an
        # earlier pass; if its row was lost, this pass records it as a non-faithful row.
        if evaluate_entry(entry_features_of(row, spec), spec.gate).allowed:
            ours = draft is not None and link[0] == draft.id
            passed.append((row, tuple(outcome.refusals), link, ours))
    if not passed:
        return MatureStepResult(refusals, evaluated, proposals)
    known = await recorded_mints(session, spec.id, [row.mint for row, _, _, _ in passed])
    if known is None:  # the read failed: nothing written, every pass remembered as lost
        state.failed_total += len(passed)
        state.failed_pairs.update((spec.id, row.mint) for row, _, _, _ in passed)
        return MatureStepResult(refusals, evaluated, proposals)
    fresh = [item for item in passed if item[0].mint not in known]
    points = await bounded_line_points(
        session, mints=[row.mint for row, _, _, _ in fresh], end_time=minute
    )
    for row, names, link, ours in fresh:
        if link[0] is None:  # a proposal of this very minute, committed by an earlier run
            found = await linked_proposal(session, spec.id, row)
            link, names = ((found, None), ()) if found else (link, names)
        pair = (spec.id, row.mint)
        coverage = (
            unread_coverage("line_points_read_failed")
            if points is None
            else coverage_of(points.get(row.mint, []), end_time=minute, created_at=row.created_at)
        )
        lineage = None
        if spec.pedigree_exclusions and pedigree is not None:
            lineage = pedigree.get(row.mint)
        values = _values(
            spec,
            row,
            refusals=names,
            link=link,
            ours=ours,
            lineage=lineage,
            coverage=coverage,
            now=now,
            features_version=features_version,
            lane_since=lane_since,
            fidelity=_fidelity(spec, row, state, lane_since),
        )
        written = await insert_opportunity(session, values)
        if written == "failed":
            state.failed_total += 1
            state.failed_pairs.add(pair)
            continue
        state.failed_pairs.discard(pair)
        if written.startswith("inserted:"):
            state.written_total += 1
            state.unfaithful_total += written != "inserted:faithful"
    return MatureStepResult(refusals, evaluated, proposals)
