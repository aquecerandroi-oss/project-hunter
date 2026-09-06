"""Turning an :class:`Evaluation` into rows and events. Pure; no session, no clock.

Two decisions are worth stating because everything else follows from them.

**The stored envelope is the engine's, unaltered.** An earlier revision of this
module renamed ``vector`` to ``features`` on the way to the column, because
``radar_common.py`` read ``feature_snapshot["features"]…`` at the commit this
task started from (``5bd17db``). That was already wrong when it was written and
is now provably so: ``98bcfea`` fixed the API to read the envelope the scorer
really writes (``FEATURE_ENVELOPE_PATH = ("vector", "values")``), with a contract
test built from ``opportunity_envelope()`` itself. Renaming here would break the
radar's volatility filter and volume sort in exactly the way that commit
existed to fix (Astra, T2.5 diff review). The envelope is stored as produced;
only the history mark rides along, under its own key.

**Every event id is deterministic and names the observation.** ``event_id_for``
over ``(row identity, observation_ts)``: keyed on the row alone, the outbox's
``ON CONFLICT (event_id) DO NOTHING`` would swallow the *second* update of the
same opportunity as a duplicate (Astra, T2.5 design review), and keyed on
nothing durable a redelivery would publish twice.
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any
from uuid import UUID

import orjson

from hunter_core.domain.enums import AnomalyStatus, OpportunityStatus
from hunter_core.events.streams import Streams
from hunter_indicators.opportunity import envelope_bytes

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

    from hunter_indicators.anomalies import AnomalyState
    from hunter_indicators.features import FeatureVector
    from hunter_indicators.regime import RegimeDecision
    from hunter_scanner_worker.evaluate import Evaluation

__all__ = [
    "anomaly_event_payload",
    "anomaly_row",
    "feature_snapshot_row",
    "history_row",
    "jsonable",
    "opportunity_event_payload",
    "opportunity_row",
    "regime_event_payload",
    "regime_row",
    "storage_envelope",
]


def jsonable(value: Mapping[str, Any]) -> dict[str, Any]:
    """The canonical JSON form of a dict that still holds ``Decimal``/``datetime``.

    Goes through the engines' own canonical serializer so the bytes a column
    holds are the bytes a recomputation compares against -- ordering included.
    """
    decoded: Any = orjson.loads(envelope_bytes(value))
    return dict(decoded)


def storage_envelope(evaluation: Evaluation) -> dict[str, Any]:
    """The envelope as a column holds it: exactly as produced, plus the mark.

    ``history_mark`` is additive and outside every path any reader names, so it
    cannot shadow a key the engine or the API depends on; it is here because the
    sampling rule has to compare against the **last persisted** sample and a
    restart would otherwise have nothing to compare with.
    """
    envelope = dict(evaluation.envelope)
    if evaluation.history_mark is not None:
        envelope["history_mark"] = evaluation.history_mark.as_wire()
    return jsonable(envelope)


def feature_snapshot_row(market_id: UUID, vector: FeatureVector, ts: datetime) -> dict[str, Any]:
    """One ``feature_snapshots`` row: the closed minute, the whole vector.

    ``ts`` is the **minute close**, not the cut the vector was computed at: the
    table is one row per market per closed minute, and two vectors of the same
    minute must land on the same row rather than racing for two.
    """
    return {
        "market_id": market_id,
        "ts": ts,
        "feature_set_version": vector.feature_set_version,
        "features": vector.as_json(),
    }


def anomaly_row(state: AnomalyState, *, anomaly_id: UUID) -> dict[str, Any]:
    """One ``anomalies`` row. The columns are the API's truth; ``metadata`` keeps
    what the table has no column for, written in the same statement so the two
    can never describe different states."""
    return {
        "id": anomaly_id,
        "market_id": state.market_id,
        "type": state.type,
        "severity": state.severity,
        "confidence": state.confidence if state.confidence is not None else 0,
        "detected_at": state.detected_at,
        "resolved_at": state.resolved_at,
        "status": state.status,
        "evaluation_state": state.evaluation_state,
        "baseline": state.baseline,
        "current_value": state.current_value,
        "deviation": state.deviation,
        "unit": state.unit,
        "detector_version": state.detector_version,
        # The ORM attribute is ``meta``; the column is ``metadata``. An insert
        # keyed on the column name collides with SQLAlchemy's own ``MetaData``
        # on the declarative class and fails at statement build time.
        "meta": jsonable({"state": state.as_wire()}),
    }


def anomaly_event_payload(state: AnomalyState, *, anomaly_id: UUID, action: str) -> dict[str, Any]:
    return jsonable(
        {
            "anomaly_id": str(anomaly_id),
            "market_id": str(state.market_id),
            "type": state.type.value,
            "action": action,
            "status": state.status.value,
            "evaluation_state": state.evaluation_state.value,
            "severity": state.severity,
            "confidence": state.confidence,
            "deviation": state.deviation,
            "observation_ts": state.observation_ts,
            "detector_version": state.detector_version,
        }
    )


def opportunity_row(
    evaluation: Evaluation,
    *,
    opportunity_id: UUID,
    regime_id: UUID | None,
    anomaly_ids: Sequence[UUID],
    now: datetime,
) -> dict[str, Any]:
    """The full column set of one ``opportunities`` row.

    ``status`` and ``expired_at`` are taken from the same state so the table's
    biconditional CHECK cannot be violated by a partial write, and the partial
    unique index (``WHERE expired_at IS NULL``) keys episode identity on the same
    pair.
    """
    state = evaluation.status.state_out if evaluation.status is not None else None
    score = evaluation.score
    if state is None or score is None:  # pragma: no cover - guarded by the caller
        raise ValueError("an opportunity row needs a scored evaluation with an episode state")
    return {
        "id": opportunity_id,
        "market_id": evaluation.market_id,
        "direction": state.direction,
        "score": state.score,
        "confidence": state.confidence if state.confidence is not None else 0,
        "peak_score": state.peak_score,
        "status": state.status,
        "decomposition": jsonable(score.decomposition()),
        "weights_version": score.weights_version,
        "regime_id": regime_id,
        "anomaly_ids": list(anomaly_ids),
        "stage": state.stage,
        "explanation": jsonable(evaluation.explanation),
        "below_40_since": state.below_floor_since,
        "feature_snapshot": storage_envelope(evaluation),
        "first_seen_at": state.first_seen_at,
        "last_updated_at": now,
        "expired_at": state.expired_at,
    }


def history_row(evaluation: Evaluation, *, opportunity_id: UUID) -> dict[str, Any]:
    """One preserved sample. Carries the whole envelope, by contract."""
    score = evaluation.score
    state = evaluation.status.state_out if evaluation.status is not None else None
    if score is None or state is None:  # pragma: no cover - guarded by the caller
        raise ValueError("a history row needs a scored evaluation")
    return {
        "opportunity_id": opportunity_id,
        "ts": evaluation.observation_ts,
        "score": state.score,
        "confidence": score.confidence,
        "status": state.status,
        "stage": state.stage,
        "decomposition": jsonable(score.decomposition()),
        "envelope": storage_envelope(evaluation),
    }


def opportunity_event_payload(
    evaluation: Evaluation, *, opportunity_id: UUID, action: str
) -> dict[str, Any]:
    score = evaluation.score
    state = evaluation.status.state_out if evaluation.status is not None else None
    return jsonable(
        {
            "opportunity_id": str(opportunity_id),
            "market_id": str(evaluation.market_id),
            "action": action,
            "status": (state.status if state is not None else OpportunityStatus.NORMAL).value,
            "stage": (state.stage.value if state is not None else None),
            "direction": (state.direction.value if state is not None else None),
            "score": None if state is None else state.score,
            "confidence": None if score is None else score.confidence,
            "eligible": bool(score is not None and score.eligible),
            "observation_ts": evaluation.observation_ts,
            "weights_version": None if score is None else score.weights_version,
        }
    )


def regime_row(
    decision: RegimeDecision, *, regime_id: UUID, scope: Any, start_time: datetime
) -> dict[str, Any]:
    """A new ``market_regimes`` row -- one row describes exactly one pair."""
    return {
        "id": regime_id,
        "scope": scope,
        "regime": decision.state_out.regime,
        "confidence": decision.confidence,
        "start_time": start_time,
        "end_time": None,
        "supporting_features": jsonable(
            {**decision.supporting_features(), "state_out": decision.state_out.as_wire()}
        ),
        "classifier_version": decision.classifier_version,
    }


def regime_event_payload(decision: RegimeDecision, *, regime_id: UUID) -> dict[str, Any]:
    """``regime.changed`` -- published by the **pair**, with ``label_changed``.

    A consumer that only cares about the projected label filters on
    ``label_changed``; a directional one needs the pair, and publishing by label
    would hide ``bull+high -> bear+high`` from it entirely.
    """
    trend, volatility = decision.state_out.pair
    return jsonable(
        {
            "regime_id": str(regime_id),
            "scope": "global",
            "regime": decision.state_out.regime.value,
            "trend": trend.value,
            "volatility": volatility.value,
            "label_changed": decision.label_changed,
            "confidence": decision.confidence,
            "observation_ts": decision.observation_ts,
            "classifier_version": decision.classifier_version,
        }
    )


def anomaly_stream() -> str:
    return Streams.ANOMALIES_DETECTED


def is_open(state: AnomalyState) -> bool:
    return state.status is AnomalyStatus.ACTIVE
