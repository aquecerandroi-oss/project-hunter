"""Shared read-only plumbing for the Shadow Lab repositories.

``agent_signals`` has no ``decision_at``/``cohort`` columns — S0 froze the
schema before this API existed, and both live only inside the immutable
envelope (``supporting_features``, written once — SHADOW-LAB.md §2). Extracting
them via ``->>'...'`` is what lets ``/summary`` and ``/signals`` filter, sort
and paginate by them; there is no index on the expression yet (declared as a
pending item in ``contract-S3-lab.md`` for ``database-architect`` if volume
grows past the low hundreds of rows this experiment has today).
"""

from __future__ import annotations

import base64
import binascii
import uuid
from datetime import datetime

from fastapi import status
from sqlalchemy import DateTime
from sqlalchemy import cast as sa_cast

from hunter_api.errors import HunterError
from hunter_core.db.models.agents import AgentSignal
from hunter_core.domain.types import ensure_utc

DECISION_AT = sa_cast(
    AgentSignal.supporting_features["decision_at"].astext, DateTime(timezone=True)
)
COHORT = AgentSignal.supporting_features["cohort"].astext

MAX_CURSOR_LENGTH = 96


class InvalidLabCursorError(HunterError):
    def __init__(self) -> None:
        super().__init__(
            type_slug="invalid-cursor",
            title="Validation Error",
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="The pagination cursor is not valid.",
        )


def encode_lab_cursor(decision_at: datetime, row_id: uuid.UUID) -> str:
    raw = f"{ensure_utc(decision_at).isoformat()}|{row_id}"
    return base64.urlsafe_b64encode(raw.encode()).decode()


def decode_lab_cursor(cursor: str | None) -> tuple[datetime, uuid.UUID] | None:
    if cursor is None:
        return None
    if not cursor or len(cursor) > MAX_CURSOR_LENGTH:
        raise InvalidLabCursorError
    try:
        raw = base64.urlsafe_b64decode(cursor.encode()).decode()
        ts_raw, _, id_raw = raw.partition("|")
        return ensure_utc(datetime.fromisoformat(ts_raw)), uuid.UUID(id_raw)
    except (ValueError, binascii.Error, UnicodeDecodeError):
        raise InvalidLabCursorError from None
