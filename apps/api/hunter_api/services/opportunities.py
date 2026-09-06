"""Assembling ``GET /api/v1/opportunities`` and ``/{id}`` responses."""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, Any, cast

from hunter_api.repositories.opportunities import OpportunityDetailRow, OpportunityListRow
from hunter_api.schemas.common import CursorPage
from hunter_api.schemas.opportunities import (
    OpportunityAnomalyOut,
    OpportunityDetailOut,
    OpportunityHistoryPointOut,
    OpportunitySummaryOut,
)

if TYPE_CHECKING:
    from collections.abc import Sequence

    from hunter_api.services.radar_org_derivation import OrgDerivation
    from hunter_core.db.models.analysis import Anomaly, OpportunityHistory

__all__ = ["build_detail", "build_list_page", "build_summary", "extract_baseline_ids"]


def extract_baseline_ids(feature_snapshot: dict[str, Any]) -> list[uuid.UUID]:
    """``feature_snapshot["baseline_ids"]`` — see ``repositories/radar_common
    .py``'s module docstring for the envelope-shape assumption this reads.
    Malformed or absent entries are dropped rather than raising: a corrupt
    envelope must degrade this one field, never 500 the whole response.
    """
    raw = feature_snapshot.get("baseline_ids")
    if not isinstance(raw, list):
        return []
    items = cast("list[Any]", raw)
    out: list[uuid.UUID] = []
    for entry in items:
        try:
            out.append(uuid.UUID(str(entry)))
        except (ValueError, AttributeError, TypeError):
            continue
    return out


def _in_position(market_id: uuid.UUID, org_derivation: OrgDerivation | None) -> bool | None:
    return None if org_derivation is None else market_id in org_derivation.in_position_market_ids


def build_summary(
    row: OpportunityListRow, org_derivation: OrgDerivation | None
) -> OpportunitySummaryOut:
    return OpportunitySummaryOut(
        id=row.id,
        market_id=row.market_id,
        exchange=row.exchange,
        symbol=row.symbol,
        market_type=row.market_type,
        direction=row.direction,
        score=row.score,
        confidence=row.confidence,
        status=row.status,
        stage=row.stage,
        regime=row.regime,
        weights_version=row.weights_version,
        first_seen_at=row.first_seen_at,
        last_updated_at=row.last_updated_at,
        in_position=_in_position(row.market_id, org_derivation),
        risk_blocked=None if org_derivation is None else org_derivation.risk_blocked,
    )


def build_list_page(
    rows: list[OpportunityListRow],
    next_cursor: str | None,
    org_derivation: OrgDerivation | None,
) -> CursorPage[OpportunitySummaryOut]:
    """Wrap one already-paginated page (MF-2: the window is a keyset ``LIMIT``
    in ``repositories/opportunities.py::list_page``, not a slice taken here
    after reading the whole table).
    """
    return CursorPage[OpportunitySummaryOut](
        items=[build_summary(row, org_derivation) for row in rows], next_cursor=next_cursor
    )


def _anomaly_out(anomaly: Anomaly) -> OpportunityAnomalyOut:
    return OpportunityAnomalyOut(
        id=anomaly.id,
        type=anomaly.type,
        severity=anomaly.severity,
        confidence=anomaly.confidence,
        status=anomaly.status,
        evaluation_state=anomaly.evaluation_state,
        detected_at=anomaly.detected_at,
    )


def _history_point(
    row: OpportunityHistory, *, include_envelope: bool
) -> OpportunityHistoryPointOut:
    return OpportunityHistoryPointOut(
        ts=row.ts,
        score=row.score,
        confidence=row.confidence,
        status=row.status,
        stage=row.stage,
        decomposition=row.decomposition,
        envelope=row.envelope if include_envelope else None,
    )


def build_detail(
    row: OpportunityDetailRow,
    anomalies: Sequence[Anomaly],
    history: Sequence[OpportunityHistory],
    org_derivation: OrgDerivation | None,
    *,
    include_envelope: bool,
) -> OpportunityDetailOut:
    return OpportunityDetailOut(
        id=row.id,
        market_id=row.market_id,
        exchange=row.exchange,
        symbol=row.symbol,
        market_type=row.market_type,
        direction=row.direction,
        score=row.score,
        confidence=row.confidence,
        peak_score=row.peak_score,
        status=row.status,
        stage=row.stage,
        regime=row.regime,
        weights_version=row.weights_version,
        decomposition=row.decomposition,
        explanation=row.explanation,
        feature_snapshot=row.feature_snapshot,
        baseline_ids=extract_baseline_ids(row.feature_snapshot),
        regime_id=row.regime_id,
        below_40_since=row.below_40_since,
        expired_at=row.expired_at,
        first_seen_at=row.first_seen_at,
        last_updated_at=row.last_updated_at,
        anomalies=[_anomaly_out(anomaly) for anomaly in anomalies],
        history=[_history_point(point, include_envelope=include_envelope) for point in history],
        in_position=_in_position(row.market_id, org_derivation),
        risk_blocked=None if org_derivation is None else org_derivation.risk_blocked,
        risk_blocked_reason=None if org_derivation is None else org_derivation.risk_blocked_reason,
    )
