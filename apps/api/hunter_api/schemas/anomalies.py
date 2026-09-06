"""``GET /api/v1/anomalies`` — DATABASE.md §17.4, PIPELINE.md §3.

24h window by default. ``evaluation_state`` is always exposed and never
collapsed into ``status``: an anomaly whose feed disappeared stays
``active`` + ``unknown`` forever, and this API must never let ``unknown``
read as ``resolved`` (``hunter_core.domain.enums.AnomalyEvaluationState``).
"""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Annotated, Any

from pydantic import BaseModel, PlainSerializer

from hunter_core.domain.enums import AnomalyEvaluationState, AnomalyStatus, AnomalyType

DecimalStr = Annotated[
    Decimal, PlainSerializer(lambda v: str(v), return_type=str, when_used="json")
]


class AnomalyOut(BaseModel):
    id: uuid.UUID
    market_id: uuid.UUID
    exchange: str
    symbol: str
    type: AnomalyType
    severity: DecimalStr
    confidence: DecimalStr
    status: AnomalyStatus
    evaluation_state: AnomalyEvaluationState
    baseline: DecimalStr | None = None
    current_value: DecimalStr | None = None
    deviation: DecimalStr | None = None
    unit: str | None = None
    detector_version: str | None = None
    detected_at: datetime
    resolved_at: datetime | None = None
    feature_snapshot: dict[str, Any]


class AnomalyPage(BaseModel):
    items: list[AnomalyOut]
    next_cursor: str | None = None
    as_of: datetime
    window_start: datetime
