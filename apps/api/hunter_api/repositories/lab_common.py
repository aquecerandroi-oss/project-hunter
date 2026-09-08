"""Shared read-only plumbing for the Shadow Lab repositories.

``agent_signals`` has no ``decision_at``/``cohort`` columns — S0 froze the
schema before this API existed, and both live only inside the immutable
envelope (``supporting_features``, written once — SHADOW-LAB.md §2). Extracting
them via ``->>'...'`` is what lets ``/summary`` and ``/signals`` filter, sort
and paginate by them; there is still no index on the expression, and
``signal_outcomes.tracking_state`` has none either (T3.37, ``EXPLAIN`` against
a ~6,000-row seed in ``tests/integration/test_lab_signals_explain.py``: fine
today because a ``strategy_version_id`` filter reaches the existing
``ix_agent_signals_version_emitted`` index first, but the version-less "every
strategy" listing already falls back to a ``Seq Scan`` + in-memory sort — a
brief for ``database-architect`` is in ``.claude/state/notes-T3.37.md`` §T3.37a).
"""

from __future__ import annotations

import base64
import binascii
import uuid
from datetime import datetime
from typing import Literal

from fastapi import status
from sqlalchemy import DateTime
from sqlalchemy import cast as sa_cast

from hunter_api.errors import HunterError
from hunter_core.db.models.agents import AgentSignal
from hunter_core.domain.enums import ShadowTrackingState
from hunter_core.domain.types import ensure_utc

DECISION_AT = sa_cast(
    AgentSignal.supporting_features["decision_at"].astext, DateTime(timezone=True)
)
COHORT = AgentSignal.supporting_features["cohort"].astext

MAX_CURSOR_LENGTH = 96

LabSignalState = Literal["closed", "open", "pending", "all"]
"""T3.37: the four segment tabs of ``GET /lab/shadow/signals``."""

PENDING_TRACKING_STATES: tuple[ShadowTrackingState, ...] = (
    ShadowTrackingState.PENDING_ENTRY,
    ShadowTrackingState.NO_ENTRY,
    ShadowTrackingState.CENSORED,
)


def tracking_states_for_lab_state(
    state: LabSignalState,
) -> tuple[ShadowTrackingState, ...] | None:
    """Mirrors ``apps/web/components/lab/lab-signal-segments.ts``'s
    ``matchesSegment`` exactly (T3.37 brief): ``closed`` = ``terminal``
    (resolved with R known), ``open`` = ``active`` (entered, tracking),
    ``pending`` folds ``pending_entry``/``no_entry``/``censored`` together
    (no entry yet, never entered, or unrecoverable — none of them a win, a
    loss, or a still-tracked position). ``all`` -> ``None`` (no filter).
    """
    if state == "closed":
        return (ShadowTrackingState.TERMINAL,)
    if state == "open":
        return (ShadowTrackingState.ACTIVE,)
    if state == "pending":
        return PENDING_TRACKING_STATES
    return None


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
