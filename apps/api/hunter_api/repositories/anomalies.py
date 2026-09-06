"""``GET /api/v1/anomalies`` — DATABASE.md §17.4, PIPELINE.md §3.

Global, no-RLS table (``hunter_core/db/models/analysis.py``). 24h window by
default; ``evaluation_state`` is always selected and returned verbatim —
never filtered out or collapsed, so ``active`` + ``unknown`` (a feed that
went away) is as visible here as any other anomaly.
"""

from __future__ import annotations

import base64
import binascii
import uuid
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Any

from fastapi import status
from sqlalchemy import select

from hunter_api.errors import HunterError
from hunter_core.db.models.analysis import Anomaly
from hunter_core.db.models.markets import Exchange, Market
from hunter_core.domain.enums import AnomalyEvaluationState, AnomalyStatus, AnomalyType

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

MAX_CURSOR_LENGTH = 96


class InvalidAnomalyCursorError(HunterError):
    def __init__(self) -> None:
        super().__init__(
            type_slug="invalid-cursor",
            title="Validation Error",
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="The pagination cursor is not valid.",
        )


def encode_anomaly_cursor(detected_at: datetime, row_id: uuid.UUID) -> str:
    raw = f"{detected_at.isoformat()}|{row_id}"
    return base64.urlsafe_b64encode(raw.encode()).decode()


def decode_anomaly_cursor(cursor: str | None) -> tuple[datetime, uuid.UUID] | None:
    if cursor is None:
        return None
    if not cursor or len(cursor) > MAX_CURSOR_LENGTH:
        raise InvalidAnomalyCursorError
    try:
        raw = base64.urlsafe_b64decode(cursor.encode()).decode()
        ts_raw, _, id_raw = raw.partition("|")
        detected_at = datetime.fromisoformat(ts_raw)
        row_id = uuid.UUID(id_raw)
    except (ValueError, binascii.Error, UnicodeDecodeError):
        raise InvalidAnomalyCursorError from None
    if detected_at.tzinfo is None:
        # ``detected_at`` is ``timestamptz``; a naive cursor would be compared
        # against it as "whatever the session's timezone is", silently shifting
        # the page boundary. This encoder never emits one, so a naive value
        # only ever comes from a hand-built cursor: 422, not a quiet 0/+N hours.
        raise InvalidAnomalyCursorError
    return detected_at, row_id


@dataclass(frozen=True, slots=True)
class AnomalyRow:
    id: uuid.UUID
    market_id: uuid.UUID
    exchange: str
    symbol: str
    type: AnomalyType
    severity: Decimal
    confidence: Decimal
    status: AnomalyStatus
    evaluation_state: AnomalyEvaluationState
    baseline: Decimal | None
    current_value: Decimal | None
    deviation: Decimal | None
    unit: str | None
    detector_version: str | None
    detected_at: datetime
    resolved_at: datetime | None
    feature_snapshot: dict[str, Any]


class AnomalyRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list_page(
        self,
        *,
        since: datetime,
        anomaly_type: AnomalyType | None,
        anomaly_status: AnomalyStatus | None,
        market_id: uuid.UUID | None,
        min_severity: Decimal | None,
        limit: int,
        cursor: str | None,
    ) -> tuple[list[AnomalyRow], str | None]:
        stmt = (
            select(
                Anomaly.id,
                Anomaly.market_id,
                Exchange.code.label("exchange"),
                Market.symbol,
                Anomaly.type,
                Anomaly.severity,
                Anomaly.confidence,
                Anomaly.status,
                Anomaly.evaluation_state,
                Anomaly.baseline,
                Anomaly.current_value,
                Anomaly.deviation,
                Anomaly.unit,
                Anomaly.detector_version,
                Anomaly.detected_at,
                Anomaly.resolved_at,
                Anomaly.feature_snapshot,
            )
            .join(Market, Market.id == Anomaly.market_id)
            .join(Exchange, Exchange.id == Market.exchange_id)
            .where(Anomaly.detected_at >= since)
        )
        if anomaly_type is not None:
            stmt = stmt.where(Anomaly.type == anomaly_type)
        if anomaly_status is not None:
            stmt = stmt.where(Anomaly.status == anomaly_status)
        if market_id is not None:
            stmt = stmt.where(Anomaly.market_id == market_id)
        if min_severity is not None:
            stmt = stmt.where(Anomaly.severity >= min_severity)

        decoded = decode_anomaly_cursor(cursor)
        if decoded is not None:
            cursor_ts, cursor_id = decoded
            stmt = stmt.where(
                (Anomaly.detected_at < cursor_ts)
                | ((Anomaly.detected_at == cursor_ts) & (Anomaly.id < cursor_id))
            )
        stmt = stmt.order_by(Anomaly.detected_at.desc(), Anomaly.id.desc()).limit(limit + 1)
        rows = (await self.session.execute(stmt)).all()
        has_more = len(rows) > limit
        page = rows[:limit]
        items = [
            AnomalyRow(
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
            for row in page
        ]
        next_cursor = encode_anomaly_cursor(page[-1].detected_at, page[-1].id) if has_more else None
        return items, next_cursor
