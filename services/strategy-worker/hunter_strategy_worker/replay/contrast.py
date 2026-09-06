"""Pairing the arms and running the seven declared contrasts.

A pair exists only when **both** arms of a contrast produced an evaluable
``R_net`` for the same signal. Everything else is coverage, counted by reason
and never replaced by a zero: an arm that could not be settled (funding
unestablishable) or could not be finished (a gap, an immature horizon) is not a
result of zero difference, and a signal the base never entered is not a
comparison at all.

The block of a pair is the UTC day of its entry (KB-0051: the dependence is
transversal, so the resampling unit is time). ``r_ex_funding`` is run through
the same machinery as a sensitivity, on its own — wider — coverage.
"""

from __future__ import annotations

import uuid
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from decimal import Decimal
from typing import TYPE_CHECKING

from hunter_core.domain.enums import ShadowTrackingState
from hunter_indicators.replay.metrics import LabMetrics, lab_metrics
from hunter_indicators.replay.policies import CONTRASTS, FAMILY_SIZE, MIN_EFFECT_R, Contrast
from hunter_indicators.replay.stats import ContrastResult, Pair, blocks_of, contrast, holm

if TYPE_CHECKING:
    from hunter_strategy_worker.replay.engine import ArmOutcome

__all__ = ["ArmCoverage", "ContrastRow", "coverage", "run_contrasts"]

Outcomes = Mapping[uuid.UUID, Mapping[str, "ArmOutcome"]]


@dataclass(frozen=True, slots=True)
class ArmCoverage:
    """How much of the population one arm could actually say something about."""

    policy_key: str
    total: int
    resolved: int
    no_entry_inherited: int
    no_entry_replayed: int
    unresolved: Mapping[str, int]
    matured: int
    """Entries whose whole horizon had closed by ``as_of`` — the population the
    contrasts are allowed to pair."""
    unevaluable_funding: int
    triggers: Mapping[str, int]
    """What set the pending invalidation, when one was set: the strategy's own
    level (``invalidation``), ``two_closes`` (INV-C) or ``channel``
    (EXIT-CHAN). The canonical ``result`` says ``invalidated`` for all three,
    so the mechanism would otherwise be invisible (Astra, R1 design review)."""
    metrics: LabMetrics


def coverage(policy_key: str, outcomes: Sequence[ArmOutcome]) -> ArmCoverage:
    """Counts and named metrics for one arm over the whole population."""
    unresolved: Counter[str] = Counter()
    triggers: Counter[str] = Counter()
    resolved: list[tuple[str, Decimal | None]] = []
    inherited = replayed_no_entry = unevaluable = 0
    matured = sum(1 for outcome in outcomes if outcome.matured)
    for outcome in outcomes:
        if outcome.trigger is not None:
            triggers[outcome.trigger] += 1
        if outcome.tracking_state is ShadowTrackingState.TERMINAL and outcome.result is not None:
            resolved.append((outcome.result.value, outcome.r_net))
            unevaluable += 1 if outcome.r_net is None else 0
            continue
        if outcome.tracking_state is ShadowTrackingState.NO_ENTRY:
            if outcome.inherited:
                inherited += 1
            else:
                replayed_no_entry += 1
            continue
        unresolved[(outcome.reason or "unknown").split(":", 1)[0]] += 1
    return ArmCoverage(
        policy_key=policy_key,
        total=len(outcomes),
        resolved=len(resolved),
        no_entry_inherited=inherited,
        no_entry_replayed=replayed_no_entry,
        unresolved=dict(sorted(unresolved.items())),
        matured=matured,
        unevaluable_funding=unevaluable,
        triggers=dict(sorted(triggers.items())),
        metrics=lab_metrics(resolved),
    )


def _value(outcome: ArmOutcome | None, *, metric: str) -> Decimal | None:
    if outcome is None or outcome.tracking_state is not ShadowTrackingState.TERMINAL:
        return None
    return outcome.r_net if metric == "r_net" else outcome.r_ex_funding


def _pairs(outcomes: Outcomes, spec: Contrast, *, metric: str) -> tuple[list[Pair], Counter[str]]:
    """Paired differences and why every other signal was dropped."""
    pairs: list[Pair] = []
    dropped: Counter[str] = Counter()
    for _signal_id, arms in sorted(outcomes.items(), key=lambda item: str(item[0])):
        treatment, control = arms.get(spec.treatment), arms.get(spec.control)
        if control is not None and control.tracking_state is ShadowTrackingState.NO_ENTRY:
            dropped["no_entry"] += 1
            continue
        if control is not None and not control.matured:
            # The common horizon cut comes *before* the pairing: an entry whose
            # horizon had not closed at ``as_of`` is out for every arm. Pairing
            # on "both happen to be resolved" would keep the fast exits and drop
            # the slow ones, selecting trades by how quickly they end (Astra, R1
            # fixes review).
            dropped["immature_horizon"] += 1
            continue
        left, right = _value(treatment, metric=metric), _value(control, metric=metric)
        if left is None and right is None:
            dropped["both_missing"] += 1
            continue
        if left is None:
            dropped[f"treatment_missing:{_reason(treatment)}"] += 1
            continue
        if right is None:
            dropped[f"control_missing:{_reason(control)}"] += 1
            continue
        entry_ts = control.entry_ts if control is not None else None
        if entry_ts is None:
            dropped["no_entry_ts"] += 1
            continue
        pairs.append(Pair(block=blocks_of(entry_ts), delta=left - right))
    return pairs, dropped


def _reason(outcome: ArmOutcome | None) -> str:
    if outcome is None:
        return "not_run"
    if outcome.tracking_state is ShadowTrackingState.TERMINAL:
        return "funding_unestablished"
    return (outcome.reason or "unknown").split(":", 1)[0]


@dataclass(frozen=True, slots=True)
class ContrastRow:
    """One contrast with its interval, its exploratory p and its coverage."""

    spec: Contrast
    net: ContrastResult
    ex_funding: ContrastResult
    dropped: Mapping[str, int]
    p_adjusted: float | None
    holm_rejects: bool
    abs_effect_at_least_min: bool
    """|Δ| >= the declared minimum effect — a **magnitude**, so a deterioration
    of the same size trips it too; the sign is in ``net.estimate`` and the
    report prints it (Astra, R1 diff review, must-fix 5)."""


def run_contrasts(
    outcomes: Outcomes,
    *,
    specs: Sequence[Contrast] = CONTRASTS,
    seed: int,
    resamples: int,
    alpha: float = 0.05,
) -> list[ContrastRow]:
    """Every declared contrast, Holm-adjusted over the family of seven."""
    computed: list[tuple[Contrast, ContrastResult, ContrastResult, Counter[str]]] = []
    for spec in specs:
        net_pairs, dropped = _pairs(outcomes, spec, metric="r_net")
        ex_pairs, _ = _pairs(outcomes, spec, metric="r_ex_funding")
        computed.append(
            (
                spec,
                contrast(spec.key, net_pairs, seed=seed, resamples=resamples, alpha=alpha),
                contrast(spec.key, ex_pairs, seed=seed, resamples=resamples, alpha=alpha),
                dropped,
            )
        )
    raw = {
        spec.key: result.p_value
        for spec, result, _ex, _dropped in computed
        if result.p_value is not None
    }
    adjusted = holm(raw, family_size=FAMILY_SIZE)
    rows: list[ContrastRow] = []
    for spec, net, ex_funding, dropped in computed:
        p_adjusted = adjusted.get(spec.key)
        estimate = net.estimate
        rows.append(
            ContrastRow(
                spec=spec,
                net=net,
                ex_funding=ex_funding,
                dropped=dict(sorted(dropped.items())),
                p_adjusted=p_adjusted,
                holm_rejects=p_adjusted is not None and p_adjusted <= alpha,
                abs_effect_at_least_min=estimate is not None and abs(estimate) >= MIN_EFFECT_R,
            )
        )
    return rows
