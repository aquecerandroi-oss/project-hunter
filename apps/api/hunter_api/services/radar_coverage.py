"""Assembling ``GET /api/v1/radar/coverage`` — the honest state of how much
Radar exists yet (T3.46, ``.claude/state/notes-T3.46.md``): merges the
Postgres counts (``repositories/radar_coverage.py``) with the scanner's own
raw ``hb:scanner:*`` heartbeat fields, the same pattern ``routers/regime.py``
already uses for fields ``WorkerHeartbeatOut`` does not carry.
"""

from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING, cast

import redis.exceptions as redis_exceptions

from hunter_api.repositories.radar_coverage import (
    ANOMALY_LOOKBACK,
    BaselineGateProgress,
    RadarCoverageRepository,
)
from hunter_api.schemas.radar_coverage import RadarCoverageOut, RadarDetectorOut
from hunter_api.services.system_status import parse_heartbeat_datetime
from hunter_core.domain.enums import AnomalyType
from hunter_core.domain.types import utcnow
from hunter_core.logging import get_logger

if TYPE_CHECKING:
    from datetime import datetime

    import redis.asyncio as redis_asyncio
    from sqlalchemy.ext.asyncio import AsyncSession

logger = get_logger(__name__)

__all__ = ["build_radar_coverage"]

_SCANNER_HEARTBEAT_SCAN_PATTERN = "hb:scanner:*"
_SCANNER_HEARTBEAT_SCAN_COUNT = 500


def _parse_int(value: str | None) -> int:
    if not value:
        return 0
    try:
        return int(value)
    except ValueError:
        return 0


def _parse_disarmed(raw: str | None) -> dict[AnomalyType, str]:
    """``detectors_disarmed``'s wire shape (``health.py::write_heartbeat``):
    ``"TYPE:reason=count,TYPE:reason=count"``. An unknown type name is
    dropped, not raised — a detector added to the enum before this reader
    ships must not 500 the page; a malformed entry is dropped the same way.
    """
    out: dict[AnomalyType, str] = {}
    if not raw:
        return out
    for entry in raw.split(","):
        entry = entry.strip()
        if not entry:
            continue
        left, _, _count = entry.rpartition("=")
        kind, sep, reason = left.partition(":")
        if not sep or not reason:
            continue
        try:
            anomaly_type = AnomalyType(kind)
        except ValueError:
            continue
        out[anomaly_type] = reason
    return out


def gate_pct(progress: BaselineGateProgress | None) -> Decimal | None:
    """``progress.passing / progress.total`` as a 0-100 percentage, ``None``
    when there is nothing to divide by (no active gate, or the archive is
    still empty) — see ``RadarCoverageRepository.baseline_gate_progress``."""
    if progress is None or progress.total == 0:
        return None
    return (Decimal(progress.passing) / Decimal(progress.total) * Decimal(100)).quantize(
        Decimal("0.01")
    )


def build_detectors(
    rows_by_type: dict[AnomalyType, int], disarmed: dict[AnomalyType, str]
) -> list[RadarDetectorOut]:
    """Every ``AnomalyType`` member, always all twelve — a type with zero rows
    and no declared reason must still show up as "silencioso sem motivo"
    (T3.46), never be dropped for having nothing to report."""
    return [
        RadarDetectorOut(
            type=anomaly_type,
            rows_31d=rows_by_type.get(anomaly_type, 0),
            disarmed_reason=disarmed.get(anomaly_type),
        )
        for anomaly_type in AnomalyType
    ]


async def _freshest_scanner_heartbeat(redis: redis_asyncio.Redis) -> dict[str, str] | None:
    """The single freshest ``hb:scanner:*`` hash, by its own ``ts`` field —
    every field this module reads (``baselines_usable``, ``baselines_state``,
    ``detectors_disarmed``, ...) comes from the *same* instance, never mixed
    across scanner processes. A Redis failure reads as "no heartbeat" — this
    is a diagnostic strip, not the request's core data, so it fails soft
    rather than turning an otherwise-successful Postgres read into a 503.
    """
    freshest: dict[str, str] | None = None
    freshest_ts: datetime | None = None
    try:
        async for raw_key in redis.scan_iter(  # type: ignore[reportUnknownMemberType]
            match=_SCANNER_HEARTBEAT_SCAN_PATTERN, count=_SCANNER_HEARTBEAT_SCAN_COUNT
        ):
            key = cast(bytes, raw_key)
            raw = cast("dict[bytes, bytes]", await redis.hgetall(key))
            fields = {
                key.decode(errors="replace"): value.decode(errors="replace")
                for key, value in raw.items()
            }
            ts = parse_heartbeat_datetime(fields.get("ts"))
            if ts is not None and (freshest_ts is None or ts > freshest_ts):
                freshest = fields
                freshest_ts = ts
    except redis_exceptions.RedisError:
        logger.warning("radar_coverage_heartbeat_redis_error")
        return None
    return freshest


async def build_radar_coverage(
    session: AsyncSession, redis: redis_asyncio.Redis
) -> RadarCoverageOut:
    repo = RadarCoverageRepository(session)
    now = utcnow()
    since = now - ANOMALY_LOOKBACK

    markets_monitored = await repo.markets_monitored()
    markets_with_anomaly = await repo.markets_with_anomaly()
    max_score_ever = await repo.max_score_ever()
    first_anomaly_at = await repo.first_anomaly_at()
    rows_by_type = await repo.anomaly_rows_by_type(since=since)
    gate_progress = await repo.baseline_gate_progress()

    heartbeat = await _freshest_scanner_heartbeat(redis)
    baselines_usable = _parse_int(heartbeat.get("baselines_usable")) if heartbeat else 0
    baselines_under_construction = (
        _parse_int(heartbeat.get("baselines_under_construction")) if heartbeat else 0
    )
    bootstrap_pointer = heartbeat.get("baselines_state") if heartbeat else None
    disarmed = _parse_disarmed(heartbeat.get("detectors_disarmed")) if heartbeat else {}

    return RadarCoverageOut(
        markets_monitored=markets_monitored,
        markets_with_anomaly=markets_with_anomaly,
        baselines_usable=baselines_usable,
        baselines_under_construction=baselines_under_construction,
        bootstrap_pointer=bootstrap_pointer,
        baseline_gate_v2_pct=gate_pct(gate_progress),
        detectors=build_detectors(rows_by_type, disarmed),
        max_score_ever=max_score_ever,
        first_anomaly_at=first_anomaly_at,
        as_of=now,
    )
