"""``active -> resolved / expired``, as a pure transition on data alone.

No clock: the transition is driven by the ``observation_ts`` of the evaluation it
is given, so a watchdog (which feeds :func:`no_data` at the current minute), the
scanner and a replay all walk the same path and reach the same state. That is
what makes ``state_in`` / ``state_out`` in the envelope reproducible.

The rules, and why each one is there:

- **an anomaly is never resolved by absence, nor by a clock alone.** Five
  minutes below the holding line have to be five *readings* below it
  (``resolve_min_readings``): two samples seven minutes apart are elapsed time,
  not observed calm. The count proves five readings, **not five contiguous
  minutes** — readings at minutes 0, 1, 2, 3 and 60 satisfy it (Astra, revisão
  do fix-pass, item d). Contiguity is the watchdog's job: it feeds ``no_data``
  for the silent minutes and that zeroes the run. This function cannot infer a
  gap it was never told about, and inventing one would be a clock read;
- **an anomaly is never resolved by absence.** Missing data leaves it ``active``
  with ``evaluation_state = unknown``; a degraded reading leaves it ``active +
  stale``. Both are ineligible: they do not update the severity and, above all,
  they *break* the below-threshold streak. Four minutes below the line, ten
  minutes blind and one more minute below is not five consecutive proven minutes,
  and joining the two halves would resolve an anomaly nobody watched (Astra, T2.3
  design review, item 7);
- **expiry is absolute.** Four hours after ``detected_at`` the row expires
  whatever the data says — otherwise an ``active + unknown`` anomaly whose market
  went quiet would stay open forever;
- **hysteresis between firing and holding.** Opening needs
  ``fire_min_severity``, staying open only ``hold_min_severity``, so a reading
  oscillating around the line does not flap one row open and shut;
- **replays and duplicates do nothing.** An evaluation whose ``observation_ts``
  is not newer than the state's is ignored, which is what makes a redelivery
  safe;
- **one active row per ``(market, type)``**, mirroring
  ``uq_anomalies_active_per_market_type``. A batch with two evaluations for one
  pair is a caller bug and raises.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from dataclasses import dataclass, replace
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any

from hunter_core.domain.enums import AnomalyEvaluationState, AnomalyStatus, AnomalyType
from hunter_core.domain.types import ensure_utc
from hunter_indicators.anomalies.detectors import DetectorDefinition
from hunter_indicators.anomalies.evaluation import AnomalyEvaluation
from hunter_indicators.anomalies.severity import AnomalyDirection

REASON_NO_DATA = "no_data"
"""What a watchdog reports when nothing arrived for a market at all."""


class AnomalyAction(StrEnum):
    """What the caller has to persist, if anything."""

    NONE = "none"
    OPEN = "open"
    UPDATE = "update"
    HOLD = "hold"
    """The row stays open and something about it changed (quality, clock) — but
    not the severity: a stale or absent reading may not move a number."""
    RESOLVE = "resolve"
    EXPIRE = "expire"


@dataclass(frozen=True, slots=True)
class AnomalyState:
    """The durable state of one ``(market, type)`` pair."""

    market_id: uuid.UUID
    type: AnomalyType
    status: AnomalyStatus
    evaluation_state: AnomalyEvaluationState
    detected_at: datetime
    observation_ts: datetime
    severity: Decimal
    confidence: Decimal | None = None
    baseline: Decimal | None = None
    current_value: Decimal | None = None
    deviation: Decimal | None = None
    direction: AnomalyDirection = AnomalyDirection.FLAT
    unit: str | None = None
    detector_version: str | None = None
    normalization_version: str | None = None
    baseline_ids: tuple[uuid.UUID, ...] = ()
    below_hold_since: datetime | None = None
    """Start of the current run of **proven** readings under the holding line."""
    below_hold_readings: int = 0
    """How many distinct readings that run actually contains.

    ``below_hold_since`` alone measures elapsed time, and two readings seven
    minutes apart would satisfy it: an anomaly declared over on the strength of
    two samples. Resolution needs both — the five minutes *and* the five
    readings that prove them — and any ``no_data``/``stale`` step zeroes the
    count, because a market we could not see is not a market that was calm
    (cross review, nice-to-have d)."""
    resolved_at: datetime | None = None
    reason: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "detected_at", ensure_utc(self.detected_at))
        object.__setattr__(self, "observation_ts", ensure_utc(self.observation_ts))

    @property
    def is_open(self) -> bool:
        return self.status is AnomalyStatus.ACTIVE

    def as_wire(self) -> dict[str, Any]:
        return {
            "type": self.type.value,
            "status": self.status.value,
            "evaluation_state": self.evaluation_state.value,
            "detected_at": self.detected_at,
            "observation_ts": self.observation_ts,
            "severity": self.severity,
            "confidence": self.confidence,
            "baseline": self.baseline,
            "current_value": self.current_value,
            "deviation": self.deviation,
            "direction": self.direction.value,
            "unit": self.unit,
            "detector_version": self.detector_version,
            "normalization_version": self.normalization_version,
            "baseline_ids": [str(item) for item in self.baseline_ids],
            "below_hold_since": self.below_hold_since,
            "below_hold_readings": self.below_hold_readings,
            "resolved_at": self.resolved_at,
            "reason": self.reason,
        }


@dataclass(frozen=True, slots=True)
class AnomalyTransition:
    """What to do, and the state that results (``None`` when nothing changed)."""

    action: AnomalyAction
    state: AnomalyState | None = None
    previous: AnomalyState | None = None


def no_data(
    market_id: uuid.UUID,
    definition: DetectorDefinition,
    *,
    observation_ts: datetime,
    reason: str = REASON_NO_DATA,
) -> AnomalyEvaluation:
    """The evaluation a watchdog feeds when nothing was observed at all."""
    return AnomalyEvaluation(
        market_id=market_id,
        type=definition.type,
        observation_ts=observation_ts,
        evaluation_state=AnomalyEvaluationState.UNKNOWN,
        detector_version=definition.identity,
        normalization_version="",
        feature=definition.feature,
        feature_version=definition.feature_version,
        unit=definition.unit,
        reason=reason,
    )


def _opened(evaluation: AnomalyEvaluation, severity: Decimal) -> AnomalyState:
    return AnomalyState(
        market_id=evaluation.market_id,
        type=evaluation.type,
        status=AnomalyStatus.ACTIVE,
        evaluation_state=AnomalyEvaluationState.OK,
        detected_at=evaluation.observation_ts,
        observation_ts=evaluation.observation_ts,
        severity=severity,
        confidence=evaluation.confidence,
        baseline=evaluation.baseline,
        current_value=evaluation.current_value,
        deviation=evaluation.deviation,
        direction=evaluation.direction,
        unit=evaluation.unit,
        detector_version=evaluation.detector_version,
        normalization_version=evaluation.normalization_version,
        baseline_ids=evaluation.baseline_ids,
    )


def _with_evidence(
    state: AnomalyState, evaluation: AnomalyEvaluation, severity: Decimal
) -> AnomalyState:
    """The episode carrying the **whole** evidence of one eligible evaluation.

    Every believed reading replaces the full set — severity, value, deviation,
    baseline, ``baseline_ids``, confidence and both version strings — because a
    partial update stores a deviation computed against one revision next to the
    median of another, and the stored explanation stops reproducing (Astra, T2.3
    diff review, must-fix 2). What belongs to the *episode* and not to the
    reading (``detected_at``, ``status``, ``below_hold_since``) is untouched here
    and decided by the caller.
    """
    return replace(
        state,
        evaluation_state=AnomalyEvaluationState.OK,
        observation_ts=evaluation.observation_ts,
        severity=severity,
        confidence=evaluation.confidence,
        baseline=evaluation.baseline,
        current_value=evaluation.current_value,
        deviation=evaluation.deviation,
        direction=evaluation.direction,
        unit=evaluation.unit,
        detector_version=evaluation.detector_version,
        normalization_version=evaluation.normalization_version,
        baseline_ids=evaluation.baseline_ids,
        reason=None,
    )


def advance(
    state: AnomalyState | None,
    evaluation: AnomalyEvaluation,
    definition: DetectorDefinition,
) -> AnomalyTransition:
    """One step of the machine. Pure: everything it knows is in its arguments."""
    if evaluation.type is not definition.type:
        raise ValueError(f"{evaluation.type} evaluated against a {definition.type} detector")
    severity = evaluation.severity
    if state is not None and evaluation.observation_ts <= state.observation_ts:
        # A redelivery or an out-of-order event: it must not advance a timer, move
        # a severity, or **open** anything. The guard covers closed episodes too:
        # replaying the 10:00 evaluation after the 10:00 episode expired at 14:00
        # would otherwise open a second one dated 10:00 (Astra, diff review,
        # must-fix 1).
        return AnomalyTransition(action=AnomalyAction.NONE, previous=state)

    open_state = state if state is not None and state.is_open else None
    if open_state is None:
        if evaluation.fires(definition) and severity is not None:
            opened = _opened(evaluation, severity)
            return AnomalyTransition(action=AnomalyAction.OPEN, state=opened, previous=state)
        return AnomalyTransition(action=AnomalyAction.NONE, previous=state)

    if evaluation.observation_ts - open_state.detected_at >= definition.expire_after:
        expired = replace(
            open_state,
            status=AnomalyStatus.EXPIRED,
            observation_ts=evaluation.observation_ts,
            resolved_at=evaluation.observation_ts,
            evaluation_state=evaluation.evaluation_state,
            below_hold_since=None,
            below_hold_readings=0,
        )
        return AnomalyTransition(action=AnomalyAction.EXPIRE, state=expired, previous=open_state)

    if not evaluation.eligible:
        held = replace(
            open_state,
            evaluation_state=evaluation.evaluation_state,
            observation_ts=evaluation.observation_ts,
            below_hold_since=None,
            below_hold_readings=0,
            reason=evaluation.reason,
        )
        return AnomalyTransition(action=AnomalyAction.HOLD, state=held, previous=open_state)

    if severity is None:  # ``eligible`` already guarantees this; narrowing for the type
        return AnomalyTransition(action=AnomalyAction.NONE, previous=open_state)
    believed = _with_evidence(open_state, evaluation, severity)
    if evaluation.holds(definition):
        return AnomalyTransition(
            action=AnomalyAction.UPDATE,
            state=replace(believed, below_hold_since=None, below_hold_readings=0),
            previous=open_state,
        )

    since = open_state.below_hold_since or evaluation.observation_ts
    readings = open_state.below_hold_readings + 1
    long_enough = evaluation.observation_ts - since >= definition.resolve_after
    proven = readings >= definition.resolve_min_readings
    if long_enough and proven:
        resolved = replace(
            believed,
            status=AnomalyStatus.RESOLVED,
            resolved_at=evaluation.observation_ts,
            below_hold_since=since,
            below_hold_readings=readings,
        )
        return AnomalyTransition(action=AnomalyAction.RESOLVE, state=resolved, previous=open_state)
    held = replace(believed, below_hold_since=since, below_hold_readings=readings)
    return AnomalyTransition(action=AnomalyAction.HOLD, state=held, previous=open_state)


def advance_all(
    states: Sequence[AnomalyState],
    evaluations: Sequence[AnomalyEvaluation],
    definitions: Sequence[DetectorDefinition],
) -> tuple[AnomalyTransition, ...]:
    """One transition per evaluation, deduplicated by ``(market, type)``."""
    by_pair: dict[tuple[uuid.UUID, AnomalyType], AnomalyState] = {}
    for state in states:
        by_pair[(state.market_id, state.type)] = state
    by_type = {definition.type: definition for definition in definitions}
    seen: set[tuple[uuid.UUID, AnomalyType]] = set()
    out: list[AnomalyTransition] = []
    for evaluation in evaluations:
        pair = (evaluation.market_id, evaluation.type)
        if pair in seen:
            raise ValueError(f"one evaluation per (market, type); {pair} appears twice")
        seen.add(pair)
        definition = by_type.get(evaluation.type)
        if definition is None:
            continue
        out.append(advance(by_pair.get(pair), evaluation, definition))
    return tuple(out)


__all__ = [
    "REASON_NO_DATA",
    "AnomalyAction",
    "AnomalyState",
    "AnomalyTransition",
    "advance",
    "advance_all",
    "no_data",
]
