"""The copy lane's durable T0 and coverage holes (H-037, design §5/§4.1), in ``meme_ingest_gaps`` where
every hole of the meme worker already lives: ``stream = 'copy_leader:<wallet>'`` or ``'copy_leader:*'``."""

from __future__ import annotations

import json
from datetime import timedelta
from typing import TYPE_CHECKING

from sqlalchemy import text

from hunter_core.domain.types import uuid7

if TYPE_CHECKING:
    from datetime import datetime

    from sqlalchemy.ext.asyncio import AsyncSession

    from hunter_exchanges.pumpfun.leader_events import LeaderGap
    from hunter_meme_worker.copy_spec import CopySpec

__all__ = ["ensure_t0", "record_gap"]

_T0 = text(
    "SELECT gap_end FROM meme_ingest_gaps WHERE stream = 'copy_leader:*' "
    "  AND reason = 'lane_not_started' AND detail ->> 'rule_set_id' = :rule_set_id "
    "ORDER BY gap_end LIMIT 1"
)
_RULE_SET_BORN = text("SELECT created_at FROM meme_rule_sets WHERE id = CAST(:rule_set_id AS uuid)")
_INSERT_GAP = text(
    "INSERT INTO meme_ingest_gaps (id, stream, gap_start, gap_end, reason, detail) "
    "VALUES (CAST(:id AS uuid), :stream, :gap_start, :gap_end, :reason, CAST(:detail AS jsonb))"
)


async def ensure_t0(session: AsyncSession, spec: CopySpec, now: datetime) -> datetime:
    """T0 of the cohort, durable (design §5): the **end** of the initial ``copy_leader:*`` gap
    (``lane_not_started``), written the first time the lane runs for this rule set and read back on
    every restart — T0 never moves."""
    existing = (await session.execute(_T0, {"rule_set_id": spec.id})).scalar_one_or_none()
    if existing is not None:
        return existing
    born = (await session.execute(_RULE_SET_BORN, {"rule_set_id": spec.id})).scalar_one_or_none()
    start = born if born is not None and born < now else now - timedelta(milliseconds=1)
    await session.execute(
        _INSERT_GAP,
        {
            "id": str(uuid7()),
            "stream": "copy_leader:*",
            "gap_start": start,
            "gap_end": now,
            "reason": "lane_not_started",
            "detail": json.dumps({"rule_set_id": spec.id, "source": "copy_lane"}),
        },
    )
    return now


async def record_gap(session: AsyncSession, spec: CopySpec, gap: LeaderGap) -> None:
    """A closed coverage hole of the source, as ``meme_ingest_gaps`` keeps every hole."""
    assert gap.end is not None
    end = gap.end if gap.end > gap.start else gap.start + timedelta(microseconds=1)
    await session.execute(
        _INSERT_GAP,
        {
            "id": str(uuid7()),
            "stream": "copy_leader:" + (gap.wallet or "*"),
            "gap_start": gap.start,
            "gap_end": end,
            "reason": gap.reason,
            "detail": json.dumps({"rule_set_id": spec.id, "source": "copy_lane"}),
        },
    )
