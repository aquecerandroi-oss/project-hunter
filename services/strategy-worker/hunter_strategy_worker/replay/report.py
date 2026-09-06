"""The record of a run: one canonical dictionary, and its JSON.

Canonical shape (keys sorted, decimals as normalised strings, timestamps
ISO-8601 UTC), so two runs over the same database with the same ``--as-of``
produce the same bytes. :mod:`.render` turns this same dictionary into the
Markdown a human reads — one source, so a number in the text cannot drift from
the number in the record.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from decimal import Decimal
from typing import TYPE_CHECKING, Any

from hunter_core.strategies.canonical import canonical_json
from hunter_indicators.replay.metrics import LabMetrics
from hunter_indicators.replay.policies import CONTRASTS, FAMILY_SIZE, MIN_EFFECT_R, POLICIES

if TYPE_CHECKING:
    from datetime import datetime

    from hunter_strategy_worker.replay.contrast import ArmCoverage, ContrastRow
    from hunter_strategy_worker.replay.load import VersionRow
    from hunter_strategy_worker.replay.reproduce import VersionAudit

__all__ = ["MATURITY_DAYS", "MATURITY_OUTCOMES", "build_document", "render_json"]

MATURITY_OUTCOMES = 100
MATURITY_DAYS = 30
"""The editorial gate of SHADOW-LAB.md §9: below either of these the reading is
``inconclusive`` by contract, whatever the numbers say."""


def _d(value: Decimal | None) -> str | None:
    return None if value is None else format(value, "f")


def _rate(value: Decimal | None) -> str | None:
    """A rate with four decimals — enough to read 0.9714 as what it is."""
    return None if value is None else format(value.quantize(Decimal("0.0001")), "f")


def _stat(value: Decimal | None) -> str | None:
    """A reported statistic at six decimals.

    An exact ratio of Decimals carries 28 significant digits; printing them all
    would suggest a precision the sample does not have. The full value stays in
    the arithmetic — this is presentation only, and it is declared."""
    return None if value is None else format(value.quantize(Decimal("0.000001")), "f")


def _f(value: float | None, digits: int = 4) -> str | None:
    return None if value is None else f"{value:.{digits}f}"


def _metrics(metrics: LabMetrics) -> dict[str, Any]:
    return {
        "outcomes": metrics.total,
        "resolved_touches": metrics.resolved_touches,
        "targets": metrics.targets,
        "stops": metrics.stops,
        "target_rate_among_resolved": _stat(metrics.target_rate_among_resolved),
        "target_rate_reason": metrics.target_rate_reason,
        "evaluable": metrics.evaluable,
        "unevaluable": metrics.unevaluable,
        "net_win_rate": _stat(metrics.net_win_rate),
        "expectancy_r": _stat(metrics.expectancy_r),
        "sum_r": _stat(metrics.sum_r),
        "profit_factor": _stat(metrics.profit_factor),
        "profit_factor_denominator": _stat(metrics.profit_factor_denominator),
        "profit_factor_reason": metrics.profit_factor_reason,
    }


def _audit(audit: VersionAudit) -> dict[str, Any]:
    return {
        "version": audit.label,
        "total": audit.total,
        "comparable": audit.comparable,
        "reproduced": audit.reproduced,
        "diverged": audit.diverged,
        "not_comparable_late": audit.not_comparable,
        "unresolved": audit.unresolved,
        "diverged_settlement_only": audit.diverged_settlement_only,
        "reproduction_rate": _rate(audit.rate),
        "trajectory_rate": _rate(audit.trajectory_rate),
        "divergences": [
            {
                "signal_id": str(d.signal_id),
                "kind": d.kind,
                "field": d.field,
                "stored": d.stored,
                "replayed": d.replayed,
            }
            for d in audit.divergences
        ],
    }


def _contrast(row: ContrastRow) -> dict[str, Any]:
    return {
        "contrast": row.spec.key,
        "question": row.spec.question,
        "n_pairs": row.net.n_pairs,
        "blocks": row.net.blocks,
        "estimate_r": _stat(row.net.estimate),
        "ci_low": _f(row.net.ci_low),
        "ci_high": _f(row.net.ci_high),
        "ci_reason": row.net.ci_reason,
        "p_value": _f(row.net.p_value, 6),
        "p_method": row.net.p_method,
        "p_holm": _f(row.p_adjusted, 6),
        "holm_rejects": row.holm_rejects,
        "abs_effect_at_least_min": row.abs_effect_at_least_min,
        "ex_funding": {
            "n_pairs": row.ex_funding.n_pairs,
            "estimate_r": _stat(row.ex_funding.estimate),
            "ci_low": _f(row.ex_funding.ci_low),
            "ci_high": _f(row.ex_funding.ci_high),
        },
        "dropped": dict(row.dropped),
    }


def build_document(
    *,
    as_of: datetime,
    seed: int,
    resamples: int,
    versions: Sequence[VersionRow],
    population: Mapping[str, Mapping[str, int]],
    audits: Sequence[VersionAudit],
    coverages: Sequence[ArmCoverage],
    contrasts: Sequence[ContrastRow],
    policy_keys: Sequence[str],
    distinct_days: int,
    gate: Mapping[str, Any],
    input_digest: str,
    series_digest: str,
) -> dict[str, Any]:
    """Everything the run established, in one canonical dictionary."""
    base = next((cov for cov in coverages if cov.policy_key == "base"), None)
    matured = 0 if base is None else base.matured
    evaluable = 0 if base is None else base.metrics.evaluable
    return {
        "experiment": "EXP-0004",
        "purpose": "research_only",
        "as_of": as_of.isoformat(),
        "input_digest": input_digest,
        "series_digest": series_digest,
        "funding_read": "as_stored_at_read_time",
        "gate": dict(gate),
        "seed": seed,
        "resamples": resamples,
        "family_size": FAMILY_SIZE,
        "min_effect_r": _d(MIN_EFFECT_R),
        "policies": [
            {
                "key": key,
                "version": POLICIES[key].version,
                "description": POLICIES[key].description,
                "parameters": dict(POLICIES[key].parameters),
                "inputs": list(POLICIES[key].inputs),
            }
            for key in policy_keys
        ],
        "contrasts_declared": [c.key for c in CONTRASTS],
        "manifest": [
            {
                "strategy_version_id": str(v.id),
                "version": v.label,
                "params_hash": v.params_hash,
                "code_ref": v.code_ref,
                "activated_at": None if v.activated_at is None else v.activated_at.isoformat(),
            }
            for v in versions
        ],
        "population": {label: dict(counts) for label, counts in sorted(population.items())},
        "reproduction": [_audit(audit) for audit in audits],
        "coverage": [
            {
                "policy": cov.policy_key,
                "total": cov.total,
                "resolved": cov.resolved,
                "no_entry_inherited": cov.no_entry_inherited,
                "no_entry_replayed": cov.no_entry_replayed,
                "unresolved": dict(cov.unresolved),
                "matured": cov.matured,
                "unevaluable_funding": cov.unevaluable_funding,
                "triggers": dict(cov.triggers),
                "metrics": _metrics(cov.metrics),
            }
            for cov in coverages
        ],
        "contrasts": [_contrast(row) for row in contrasts],
        "maturity": {
            "matured_outcomes_base": matured,
            "evaluable_outcomes_base": evaluable,
            "distinct_days": distinct_days,
            "threshold_outcomes": MATURITY_OUTCOMES,
            "threshold_days": MATURITY_DAYS,
            "verdict": (
                "inconclusive"
                if matured < MATURITY_OUTCOMES or distinct_days < MATURITY_DAYS
                else "above_editorial_threshold"
            ),
        },
    }


def render_json(document: Mapping[str, Any]) -> bytes:
    """The canonical JSON of the run."""
    return canonical_json(document) + b"\n"
