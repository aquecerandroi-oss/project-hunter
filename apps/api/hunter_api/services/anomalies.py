"""Assembling ``GET /api/v1/anomalies`` responses."""

from __future__ import annotations

from typing import TYPE_CHECKING

from hunter_api.schemas.anomalies import AnomalyOut, AnomalyPage
from hunter_core.domain.types import utcnow

if TYPE_CHECKING:
    from datetime import datetime

    from hunter_api.repositories.anomalies import AnomalyRow

__all__ = ["build_anomaly_page"]


def _to_out(row: AnomalyRow) -> AnomalyOut:
    return AnomalyOut(
        id=row.id,
        market_id=row.market_id,
        exchange=row.exchange,
        symbol=row.symbol,
        type=row.type,
        severity=row.severity,
        confidence=row.confidence,
        status=row.status,
        evaluation_state=row.evaluation_state,
        baseline=row.baseline,
        current_value=row.current_value,
        deviation=row.deviation,
        unit=row.unit,
        detector_version=row.detector_version,
        detected_at=row.detected_at,
        resolved_at=row.resolved_at,
        feature_snapshot=row.feature_snapshot,
    )


def build_anomaly_page(
    rows: list[AnomalyRow], next_cursor: str | None, *, window_start: datetime
) -> AnomalyPage:
    return AnomalyPage(
        items=[_to_out(row) for row in rows],
        next_cursor=next_cursor,
        as_of=utcnow(),
        window_start=window_start,
    )
