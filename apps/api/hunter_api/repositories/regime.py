"""``GET /api/v1/regime`` and ``/regime/history`` — DATABASE.md §17,
PIPELINE.md §4. Global, no-RLS table; scoped by :class:`RegimeScope`
(``global``/``btc``), not by individual market — the classifier is
cross-market by construction (PIPELINE.md §4's "Escopo: global").
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
from hunter_core.db.models.analysis import MarketRegimeRow
from hunter_core.domain.enums import MarketRegime, RegimeScope

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

MAX_CURSOR_LENGTH = 96


class InvalidRegimeCursorError(HunterError):
    def __init__(self) -> None:
        super().__init__(
            type_slug="invalid-cursor",
            title="Validation Error",
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="The pagination cursor is not valid.",
        )


def encode_regime_cursor(start_time: datetime, row_id: uuid.UUID) -> str:
    raw = f"{start_time.isoformat()}|{row_id}"
    return base64.urlsafe_b64encode(raw.encode()).decode()


def decode_regime_cursor(cursor: str | None) -> tuple[datetime, uuid.UUID] | None:
    if cursor is None:
        return None
    if not cursor or len(cursor) > MAX_CURSOR_LENGTH:
        raise InvalidRegimeCursorError
    try:
        raw = base64.urlsafe_b64decode(cursor.encode()).decode()
        ts_raw, _, id_raw = raw.partition("|")
        start_time = datetime.fromisoformat(ts_raw)
        row_id = uuid.UUID(id_raw)
    except (ValueError, binascii.Error, UnicodeDecodeError):
        raise InvalidRegimeCursorError from None
    if start_time.tzinfo is None:
        # ``start_time`` is ``timestamptz`` — same reason as
        # ``repositories/anomalies.py::decode_anomaly_cursor``.
        raise InvalidRegimeCursorError
    return start_time, row_id


@dataclass(frozen=True, slots=True)
class RegimeRow:
    id: uuid.UUID
    scope: RegimeScope
    regime: MarketRegime
    confidence: Decimal | None
    start_time: datetime
    end_time: datetime | None
    classifier_version: str | None
    supporting_features: dict[str, Any]


def _row_from(row: Any) -> RegimeRow:
    return RegimeRow(
        id=row.id,
        scope=row.scope,
        regime=row.regime,
        confidence=row.confidence,
        start_time=row.start_time,
        end_time=row.end_time,
        classifier_version=row.classifier_version,
        supporting_features=row.supporting_features,
    )


class RegimeRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def current_per_scope(self) -> list[RegimeRow]:
        """The most recent row of every scope that has ever been classified —
        a scope with no row at all is simply absent (nothing to be "stale"
        about yet), never fabricated as ``UNKNOWN``.
        """
        out: list[RegimeRow] = []
        for scope in RegimeScope:
            stmt = (
                select(MarketRegimeRow)
                .where(MarketRegimeRow.scope == scope)
                .order_by(MarketRegimeRow.start_time.desc())
                .limit(1)
            )
            row = (await self.session.execute(stmt)).scalar_one_or_none()
            if row is not None:
                out.append(_row_from(row))
        return out

    async def history(
        self, *, scope: RegimeScope | None, limit: int, cursor: str | None
    ) -> tuple[list[RegimeRow], str | None]:
        stmt = select(MarketRegimeRow)
        if scope is not None:
            stmt = stmt.where(MarketRegimeRow.scope == scope)
        decoded = decode_regime_cursor(cursor)
        if decoded is not None:
            cursor_ts, cursor_id = decoded
            stmt = stmt.where(
                (MarketRegimeRow.start_time < cursor_ts)
                | ((MarketRegimeRow.start_time == cursor_ts) & (MarketRegimeRow.id < cursor_id))
            )
        stmt = stmt.order_by(MarketRegimeRow.start_time.desc(), MarketRegimeRow.id.desc()).limit(
            limit + 1
        )
        rows = (await self.session.execute(stmt)).scalars().all()
        has_more = len(rows) > limit
        page = rows[:limit]
        items = [_row_from(row) for row in page]
        next_cursor = encode_regime_cursor(page[-1].start_time, page[-1].id) if has_more else None
        return items, next_cursor
