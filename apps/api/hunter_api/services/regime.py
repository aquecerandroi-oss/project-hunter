"""Assembling ``GET /api/v1/regime`` and ``/regime/history`` responses.

``is_stale`` cannot be decided from ``end_time`` alone for ``regime_v0``
(Astra, T2.6 diff review, must-fix 3): a scanner that crashes right after
opening a regime row (``end_time IS NULL``) leaves that row looking "current"
forever, since nothing ever closes it. A ``regime_v0`` row is honestly
``is_stale`` when it is closed **or** when nothing confirms the classifier
that would close/replace it is still running — the same ``hb:scanner:*``
heartbeat ``/system/workers`` already reads (``services/system_status.py``),
passed in here rather than re-derived, so this module stays free of its own
Redis-scanning logic.

``regime_hourly_v1`` (T3.43) rows are **always** closed by construction
(``end_time = ts + 1h``, ``services/scanner-worker/hunter_scanner_worker
/regime_writer.py``) — the ``regime_v0`` rule above would therefore mark
every hourly row ``is_stale`` forever, which is honest about "the hour has
passed" but reads as a defect on a tile showing the newest hour a live
producer keeps writing (T3.43b, ``.claude/state/notes-T3.43.md`` concern 1).
An hourly row is ``is_stale`` only when the hour itself is old (more than
``HOURLY_STALE_AFTER`` past its own ``end_time``) **or** the producer's own
heartbeat (``regime_last_ts``, read raw off ``hb:scanner:*`` by
``routers/regime.py`` — not carried by ``WorkerHeartbeatOut``) has not
confirmed a write that recently.
"""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal, InvalidOperation
from typing import TYPE_CHECKING, Any, cast

from hunter_api.schemas.regime import (
    RegimeComponentOut,
    RegimeCurrentOut,
    RegimeHistoryPage,
    RegimeOut,
)
from hunter_core.domain.types import utcnow

if TYPE_CHECKING:
    from datetime import datetime

    from hunter_api.repositories.regime import RegimeRow

__all__ = [
    "HOURLY_ENGINE_VERSION_PREFIX",
    "HOURLY_STALE_AFTER",
    "build_current",
    "build_history_page",
    "is_regime_hourly_fresh",
]

HOURLY_ENGINE_VERSION_PREFIX = "regime_hourly_v1"
"""``classifier_version`` of every row `hunter_indicators.regime.hourly_model
.REGIME_HOURLY_VERSION` writes, including its ``+<digest>`` threshold-override
variants (``HourlyThresholds.identity``) — a prefix match, never an exact one."""

HOURLY_STALE_AFTER = timedelta(hours=2)
"""(T3.43b) How old an hourly row's own ``end_time`` — or the producer's
``regime_last_ts`` heartbeat — may be before the row stops reading as the
current hour. Two hours, not one: the job runs on the hour and the tile must
not flap ``stale`` during the ordinary minutes a cycle takes to catch up."""


def _is_hourly_engine(row: RegimeRow) -> bool:
    return row.classifier_version is not None and row.classifier_version.startswith(
        HOURLY_ENGINE_VERSION_PREFIX
    )


def is_regime_hourly_fresh(newest_regime_last_ts: datetime | None) -> bool:
    """Whether the producer's own heartbeat confirms a write within
    :data:`HOURLY_STALE_AFTER`. ``None`` (no ``hb:scanner:*`` heartbeat ever
    carried ``regime_last_ts``, or Redis could not be read) reads not-fresh —
    the same fail-safe direction as ``routers/regime.py::_scanner_alive``: a
    row is only ever *confirmed* fresh, never assumed to be by the absence of
    evidence.
    """
    if newest_regime_last_ts is None:
        return False
    return (utcnow() - newest_regime_last_ts) <= HOURLY_STALE_AFTER


def _hourly_is_stale(row: RegimeRow, *, regime_hourly_fresh: bool) -> bool:
    if row.end_time is not None and utcnow() - row.end_time > HOURLY_STALE_AFTER:
        return True
    return not regime_hourly_fresh


def _decimal(value: Any) -> Decimal | None:
    """A ``supporting_features`` leaf back to ``Decimal`` — every number in
    there was written as a canonical decimal *string*
    (``hunter_core.strategies.canonical.canonical_json``), never a JSON
    number, so plain ``Decimal(str(value))`` is exact. Malformed input (a
    hand-seeded fixture, a future engine version with a different shape)
    reads ``None`` rather than raising a 500 out of a read endpoint.
    """
    if value is None:
        return None
    if isinstance(value, Decimal):
        return value
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return None


def _components(raw: Any) -> list[RegimeComponentOut]:
    """``supporting_features.components`` (``ScoreComponent.as_wire()``,
    ``name``/``raw``/``normalized``/``weight``/``contribution``/``reason``)
    trimmed to the four fields the tile needs. An entry missing ``name`` or
    ``weight`` — the two fields a real row never omits — is dropped rather
    than fabricated; the rest of a well-formed row is still shown.
    """
    if not isinstance(raw, list):
        return []
    out: list[RegimeComponentOut] = []
    for entry in cast("list[object]", raw):
        if not isinstance(entry, dict):
            continue
        item = cast("dict[str, Any]", entry)
        name = item.get("name")
        weight = _decimal(item.get("weight"))
        if not isinstance(name, str) or weight is None:
            continue
        out.append(
            RegimeComponentOut(
                name=name,
                normalized=_decimal(item.get("normalized")),
                weight=weight,
                contribution=_decimal(item.get("contribution")),
            )
        )
    return out


def _to_out(row: RegimeRow, *, scanner_alive: bool, regime_hourly_fresh: bool) -> RegimeOut:
    hourly = _is_hourly_engine(row)
    is_stale = (
        _hourly_is_stale(row, regime_hourly_fresh=regime_hourly_fresh)
        if hourly
        else row.end_time is not None or not scanner_alive
    )
    return RegimeOut(
        id=row.id,
        scope=row.scope,
        regime=row.regime,
        confidence=row.confidence,
        start_time=row.start_time,
        end_time=row.end_time,
        classifier_version=row.classifier_version,
        supporting_features=row.supporting_features,
        is_stale=is_stale,
        as_of=row.start_time if hourly else None,
        score=_decimal(row.supporting_features.get("score_0_100")) if hourly else None,
        components=_components(row.supporting_features.get("components")) if hourly else [],
        identity=row.classifier_version if hourly else None,
    )


def build_current(
    rows: list[RegimeRow], *, scanner_alive: bool, regime_hourly_fresh: bool
) -> RegimeCurrentOut:
    return RegimeCurrentOut(
        items=[
            _to_out(row, scanner_alive=scanner_alive, regime_hourly_fresh=regime_hourly_fresh)
            for row in rows
        ],
        as_of=utcnow(),
    )


def build_history_page(
    rows: list[RegimeRow],
    next_cursor: str | None,
    *,
    scanner_alive: bool,
    regime_hourly_fresh: bool,
) -> RegimeHistoryPage:
    return RegimeHistoryPage(
        items=[
            _to_out(row, scanner_alive=scanner_alive, regime_hourly_fresh=regime_hourly_fresh)
            for row in rows
        ],
        next_cursor=next_cursor,
    )
