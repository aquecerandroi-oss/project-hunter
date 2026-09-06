"""``GET /api/v1/opportunities`` and ``/{id}`` — DATABASE.md §17.3.

``decomposition``/``explanation``/``feature_snapshot``/``envelope`` are passed
through as the raw JSONB the scanner wrote (``dict[str, Any]``), never
re-shaped into a narrower Pydantic model here: their internal structure is
owned by ``hunter_indicators.opportunity`` (T2.4) and ``scanner-worker``
(T2.5), both still in flight, and guessing a stricter schema than the
producer's would either reject a real payload or silently hide fields a
reviewer expects to see. ``.claude/state/notes-T2.6.md`` records the one
assumption this module *does* bake in: the per-feature path used by the
``volatility`` filter and the ``volume`` sort key.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Annotated, Any

from pydantic import BaseModel, PlainSerializer

from hunter_core.domain.enums import (
    AnomalyEvaluationState,
    AnomalyStatus,
    AnomalyType,
    MarketRegime,
    MarketType,
    OpportunityStage,
    OpportunityStatus,
    TradeDirection,
)

DecimalStr = Annotated[
    Decimal, PlainSerializer(lambda v: str(v), return_type=str, when_used="json")
]

MAX_HISTORY_LIMIT = 500
"""Ceiling of ``?history_limit=`` on ``GET /opportunities/{id}``."""

MAX_ENVELOPE_HISTORY_LIMIT = 50
"""Ceiling of ``?history_limit=`` **when ``?include_envelope=true``** (MF-3).

An envelope is the full per-sample recomputation proof — every feature value,
its quality, its inputs, the baselines and the classifier version. Five hundred
of them in one response is a multi-megabyte payload built from one cheap GET,
and it is read from a single connection held for the whole serialization. The
router answers 422 above this rather than silently truncating: a caller who
asked for 500 points and got 50 would chart a trajectory it believes is
complete."""


class OpportunityAnomalyOut(BaseModel):
    """One anomaly linked to the opportunity's market — active ones by
    default (``services/opportunities.py``), so an anomaly that resolved
    weeks ago does not clutter "why are we looking at this?".
    """

    id: uuid.UUID
    type: AnomalyType
    severity: DecimalStr
    confidence: DecimalStr
    status: AnomalyStatus
    evaluation_state: AnomalyEvaluationState
    detected_at: datetime


class OpportunityHistoryPointOut(BaseModel):
    ts: datetime
    score: DecimalStr
    confidence: DecimalStr | None = None
    status: OpportunityStatus
    stage: OpportunityStage
    decomposition: dict[str, Any]
    envelope: dict[str, Any] | None = None
    """``null`` unless the caller asked for it (``?include_envelope=true``) —
    the envelope is the full per-sample recomputation proof and is not cheap
    to ship for every point of a trajectory the UI usually just charts."""


class OpportunitySummaryOut(BaseModel):
    """One row of ``GET /api/v1/opportunities`` — the same shape as a radar row.

    Carries **no** ``decomposition`` (MF-2): the per-row JSONB breakdown is a
    detail-view field, and selecting it for every row of every page made the
    list statement read and decode the largest column in the table for data no
    list view renders. ``GET /opportunities/{id}`` is the one request that
    returns it.
    """

    id: uuid.UUID
    market_id: uuid.UUID
    exchange: str
    symbol: str
    market_type: MarketType
    direction: TradeDirection
    score: DecimalStr
    confidence: DecimalStr
    status: OpportunityStatus
    stage: OpportunityStage
    regime: MarketRegime | None = None
    weights_version: str | None = None
    first_seen_at: datetime
    last_updated_at: datetime
    in_position: bool | None = None
    risk_blocked: bool | None = None


class OpportunityDetailOut(OpportunitySummaryOut):
    """``GET /api/v1/opportunities/{id}`` — the full explainability contract:
    decomposition, deterministic pt-BR ``explanation``, the feature envelope
    the score was computed from, the anomalies backing it and its trajectory.
    """

    peak_score: DecimalStr | None = None
    decomposition: dict[str, Any]
    explanation: dict[str, Any]
    feature_snapshot: dict[str, Any]
    baseline_ids: list[uuid.UUID]
    regime_id: uuid.UUID | None = None
    below_40_since: datetime | None = None
    expired_at: datetime | None = None
    anomalies: list[OpportunityAnomalyOut]
    history: list[OpportunityHistoryPointOut]
    risk_blocked_reason: str | None = None
