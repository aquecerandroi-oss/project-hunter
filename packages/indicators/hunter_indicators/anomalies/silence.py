"""Why a detector produced nothing — the operator's vocabulary for muteness.

A detector that is armed and never emits is indistinguishable, from outside,
from a market that is simply calm. The T3.46 study measured exactly that on the
VPS: ``ORDERBOOK_IMBALANCE``, ``OPEN_INTEREST_SPIKE`` and
``TRADE_VELOCITY_SPIKE`` had **zero** rows in the whole series while three other
detectors declared their reason in the heartbeat's ``detectors_disarmed``. Two
of the three had a usable feature and no usable baseline; one had neither. None
of them said so anywhere.

This module turns the verdict :func:`~hunter_indicators.anomalies.evaluation.
evaluate_detector` *already produces* into that sentence. Nothing new is
computed here — that is the whole point. A parallel diagnosis would drift from
the decision it claims to explain, and the reason an operator reads has to be
the reason the detector actually acted on.

**Three axes, and only one of them is silence.**

- an ``ok`` evaluation is an **answer**, whatever its severity. Severity 0 means
  "the market is normal", which is the output, not the absence of one. It is
  never reported here;
- a ``stale`` evaluation is a reading the pipeline refuses to believe
  (``docs/PIPELINE.md`` §2, degraded data does not feed anomalies). It is
  reported as :data:`REASON_DATA_DEGRADED` — one word, because *which* input
  went stale belongs to the feature vector, not to the detector's roll-call;
- an ``unknown`` evaluation is the detector saying it could not look. Its reason
  is translated below, never passed through raw: ``insufficient_history`` is the
  baseline archive's word and ``baselines_under_construction`` is the operator's
  word for the same fact, and the heartbeat is read by people.

**An open episode is not a mute detector.** A detector holding an ``active``
anomaly is producing even when the current reading is blind — that is exactly
what ``AnomalyAction.HOLD`` is for. Naming it here would hide a live anomaly
behind a warm-up label.

Feature-side reasons keep their own prefix (``feature_after_cut``,
``feature_warmup``) because the two axes are genuinely different repairs: a
missing feature is fixed upstream in the collector, an immature baseline is
fixed only by waiting.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence

from hunter_core.domain.enums import AnomalyEvaluationState, AnomalyStatus
from hunter_indicators.anomalies.detectors import REASON_DISABLED, REASON_NO_FEATURE
from hunter_indicators.anomalies.evaluation import AnomalyEvaluation
from hunter_indicators.anomalies.lifecycle import REASON_NO_DATA, AnomalyState
from hunter_indicators.anomalies.severity import REASON_MAD_ZERO
from hunter_indicators.baselines.projection import REASON_NO_BASELINE, REASON_VERSION_MISMATCH
from hunter_indicators.baselines.revision import REASON_INSUFFICIENT_HISTORY
from hunter_indicators.features.vector import Reason

REASON_BASELINES_UNDER_CONSTRUCTION = "baselines_under_construction"
"""The archive holds a bucket for this reading and it does not pass the gate.

The measured cause of ``TRADE_VELOCITY_SPIKE`` and ``OPEN_INTEREST_SPIKE`` being
mute: both read a feature the *bootstrap* cannot reproduce (tape and derivative
history), so their only source is the live hourly refresh, and a live bucket for
hour ``H`` only becomes usable a full day after its third distinct day at hour
``H``. Nothing is broken; nothing can fire either, and that is a fact the
heartbeat owes the operator."""

REASON_BASELINE_ABSENT = "baseline_absent"
"""No revision at all for this ``(market, feature, hour)`` — not even a thin one.

Deliberately not the same word as the one above: "the archive has never written
this bucket" and "it wrote it and it is too young" have different fixes."""

REASON_BASELINE_VERSION_MISMATCH = "baseline_version_mismatch"
"""A revision exists for another feature version: visible and unusable."""

REASON_BASELINE_WITHOUT_DISPERSION = "baseline_without_dispersion"
"""MAD is zero and the reading is off the median: no scale to measure in."""

REASON_DATA_DEGRADED = "data_degraded"
"""The reading exists and the pipeline refuses to believe it."""

REASON_UNDECLARED = "undeclared"
"""Last resort: a verdict with no reason at all. It must never happen — an
``unknown`` evaluation always carries one — and if it does, the page says
"undeclared" rather than dropping the detector back into silence."""

_BASELINE_VOCABULARY: dict[str, str] = {
    REASON_INSUFFICIENT_HISTORY: REASON_BASELINES_UNDER_CONSTRUCTION,
    REASON_NO_BASELINE: REASON_BASELINE_ABSENT,
    REASON_VERSION_MISMATCH: REASON_BASELINE_VERSION_MISMATCH,
    REASON_MAD_ZERO: REASON_BASELINE_WITHOUT_DISPERSION,
    REASON_NO_FEATURE: REASON_NO_FEATURE,
    REASON_NO_DATA: REASON_NO_DATA,
}
"""Reasons that are about the *judgement*, mapped to the operator's word."""

_FEATURE_REASONS: frozenset[str] = frozenset(item.value for item in Reason)
"""Reasons that are about the *input*; they get the ``feature_`` prefix."""


def silence_reason(evaluation: AnomalyEvaluation) -> str | None:
    """Why this verdict produced no anomaly, or ``None`` when it is an answer.

    ``None`` covers the only honest silence there is: an ``ok`` reading whose
    severity did not reach the firing line. Everything else names itself.
    """
    if evaluation.evaluation_state is AnomalyEvaluationState.OK:
        return None
    if evaluation.evaluation_state is AnomalyEvaluationState.STALE:
        return REASON_DATA_DEGRADED
    reason = evaluation.reason
    if reason == REASON_DISABLED:
        # A registered-and-disarmed detector already carries the sentence its
        # own declaration wrote (``feature_not_implemented``,
        # ``single_exchange_until_m1b``, ``funding_unavailable``). Restating it
        # in this module's words would give one fact two names.
        return evaluation.detail or REASON_DISABLED
    if reason is None:
        return REASON_UNDECLARED
    mapped = _BASELINE_VOCABULARY.get(reason)
    if mapped is not None:
        return mapped
    if reason in _FEATURE_REASONS:
        return f"feature_{reason}"
    return reason


def silence_reasons(
    evaluations: Sequence[AnomalyEvaluation],
    *,
    states: Iterable[AnomalyState] = (),
) -> tuple[tuple[str, str], ...]:
    """``(anomaly_type, reason)`` for every detector that could not produce one.

    Ordered by type so the heartbeat string is stable between cycles: an
    operator diffing two heartbeats should see a *change*, not a reshuffle.
    """
    producing = {state.type for state in states if state.status is AnomalyStatus.ACTIVE}
    out: list[tuple[str, str]] = []
    for evaluation in evaluations:
        if evaluation.type in producing:
            continue
        reason = silence_reason(evaluation)
        if reason is not None:
            out.append((evaluation.type.value, reason))
    return tuple(sorted(out))


__all__ = [
    "REASON_BASELINES_UNDER_CONSTRUCTION",
    "REASON_BASELINE_ABSENT",
    "REASON_BASELINE_VERSION_MISMATCH",
    "REASON_BASELINE_WITHOUT_DISPERSION",
    "REASON_DATA_DEGRADED",
    "REASON_UNDECLARED",
    "silence_reason",
    "silence_reasons",
]
