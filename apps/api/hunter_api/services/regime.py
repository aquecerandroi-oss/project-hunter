"""Assembling ``GET /api/v1/regime`` and ``/regime/history`` responses.

``is_stale`` cannot be decided from ``end_time`` alone (Astra, T2.6 diff
review, must-fix 3): a scanner that crashes right after opening a regime row
(``end_time IS NULL``) leaves that row looking "current" forever, since
nothing ever closes it. A row is honestly ``is_stale`` when it is closed
**or** when nothing confirms the classifier that would close/replace it is
still running — the same ``hb:scanner:*`` heartbeat ``/system/workers``
already reads (``services/system_status.py``), passed in here rather than
re-derived, so this module stays free of its own Redis-scanning logic.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from hunter_api.schemas.regime import RegimeCurrentOut, RegimeHistoryPage, RegimeOut
from hunter_core.domain.types import utcnow

if TYPE_CHECKING:
    from hunter_api.repositories.regime import RegimeRow

__all__ = ["build_current", "build_history_page"]


def _to_out(row: RegimeRow, *, scanner_alive: bool) -> RegimeOut:
    return RegimeOut(
        id=row.id,
        scope=row.scope,
        regime=row.regime,
        confidence=row.confidence,
        start_time=row.start_time,
        end_time=row.end_time,
        classifier_version=row.classifier_version,
        supporting_features=row.supporting_features,
        is_stale=row.end_time is not None or not scanner_alive,
    )


def build_current(rows: list[RegimeRow], *, scanner_alive: bool) -> RegimeCurrentOut:
    return RegimeCurrentOut(
        items=[_to_out(row, scanner_alive=scanner_alive) for row in rows], as_of=utcnow()
    )


def build_history_page(
    rows: list[RegimeRow], next_cursor: str | None, *, scanner_alive: bool
) -> RegimeHistoryPage:
    return RegimeHistoryPage(
        items=[_to_out(row, scanner_alive=scanner_alive) for row in rows],
        next_cursor=next_cursor,
    )
