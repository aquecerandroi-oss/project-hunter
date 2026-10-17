"""The copy lane's durable T0, coverage holes and liveness marker (H-037, design §5/§4.1 and R2 fix B2), in
``meme_ingest_gaps`` where every hole of the meme worker already lives. The table is **append-only**
(``hunter_worker`` has ``INSERT`` and never ``UPDATE``) and ``gap_end`` is ``NOT NULL``, so:

* a hole is written **twice**: when it opens (``gap_end = gap_start + 1 µs``, ``detail.open = true``) and when
  it closes (the real end, ``detail.open = false``). Both rows share ``detail.gap_id`` — a deterministic
  uuid5 of (rule set, wallet, reason, start) — and a reader takes the latest row per ``gap_id``. A hole
  with only its opening row is closed at the next liveness marker (the worker died with it open);
* the lane is **alive** while the marker advances: one row per interval, ``stream =
  'copy_alive:<rule_set_id>'``, ``gap_start`` = previous marker, ``gap_end`` = now. After a restart the gap
  from the last marker to the instant the source is up again is the ``worker_downtime`` hole.

``stream = 'copy_leader:<wallet>'`` or ``'copy_leader:*'`` for holes; T0 is the end of the one
``lane_not_started`` hole of the rule set (design §5), written when the source is first up.
"""

from __future__ import annotations

import json
from datetime import timedelta
from typing import TYPE_CHECKING
from uuid import NAMESPACE_URL, uuid5

from sqlalchemy import text

from hunter_core.domain.types import uuid7
from hunter_exchanges.pumpfun.leader_events import LeaderGap

if TYPE_CHECKING:
    from datetime import datetime

    from sqlalchemy.ext.asyncio import AsyncSession

    from hunter_meme_worker.copy_spec import CopySpec

__all__ = [
    "ensure_t0",
    "gap_id",
    "last_alive",
    "owed_gaps",
    "record_gap",
    "record_recomposed",
    "unclosed_gaps",
    "write_alive",
]

ALIVE_REASON = "lane_alive"
RECOMPOSED_REASON = "recomposed"
NOT_A_HOLE = ("lane_alive", "lane_not_started", "recomposed")
ONE_US = timedelta(microseconds=1)

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
_LAST_ALIVE = text(
    "SELECT max(gap_end) FROM meme_ingest_gaps WHERE stream = :stream AND reason = 'lane_alive'"
)
_CLOSED_HOLES = text(
    "SELECT stream, gap_start, gap_end, reason, detail ->> 'gap_id' AS gid FROM meme_ingest_gaps "
    "WHERE stream LIKE 'copy_leader:%' AND detail ->> 'rule_set_id' = :rule_set_id "
    "  AND detail ->> 'open' = 'false' AND reason <> ALL(:not_holes)"
)
_RECOMPOSED = text(
    "SELECT detail ->> 'gap_id' AS gid, detail ->> 'wallet' AS wallet FROM meme_ingest_gaps "
    "WHERE stream LIKE 'copy_leader:%' AND detail ->> 'rule_set_id' = :rule_set_id "
    "  AND reason = 'recomposed'"
)
_UNCLOSED = text(
    "SELECT o.stream, o.gap_start, o.reason FROM meme_ingest_gaps o "
    "WHERE o.stream LIKE 'copy_leader:%' AND o.detail ->> 'rule_set_id' = :rule_set_id "
    "  AND o.detail ->> 'open' = 'true' "
    "  AND NOT EXISTS (SELECT 1 FROM meme_ingest_gaps c WHERE c.stream = o.stream "
    "    AND c.detail ->> 'gap_id' = o.detail ->> 'gap_id' AND c.detail ->> 'open' = 'false')"
)


def gap_id(spec_id: str, wallet: str | None, reason: str, start: datetime) -> str:
    return str(
        uuid5(NAMESPACE_URL, f"copy-gap|{spec_id}|{wallet or '*'}|{reason}|{start.isoformat()}")
    )


async def ensure_t0(session: AsyncSession, spec: CopySpec, now: datetime) -> tuple[datetime, bool]:
    """T0 of the cohort, durable (design §5): the **end** of the initial ``copy_leader:*`` gap
    (``lane_not_started``), written the first time the source is up for this rule set and read back on
    every restart — T0 never moves. ``(t0, created)``."""
    existing = (await session.execute(_T0, {"rule_set_id": spec.id})).scalar_one_or_none()
    if existing is not None:
        return existing, False
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
    return now, True


async def record_gap(session: AsyncSession, spec: CopySpec, gap: LeaderGap) -> None:
    """One row for a hole: its opening (``gap.end is None``) or its close."""
    is_open = gap.end is None
    end = gap.start + ONE_US if gap.end is None else max(gap.end, gap.start + ONE_US)
    await session.execute(
        _INSERT_GAP,
        {
            "id": str(uuid7()),
            "stream": "copy_leader:" + (gap.wallet or "*"),
            "gap_start": gap.start,
            "gap_end": end,
            "reason": gap.reason,
            "detail": json.dumps(
                {
                    "rule_set_id": spec.id,
                    "source": "copy_lane",
                    "open": is_open,
                    "gap_id": gap_id(spec.id, gap.wallet, gap.reason, gap.start),
                }
            ),
        },
    )


async def write_alive(
    session: AsyncSession, spec: CopySpec, start: datetime, end: datetime
) -> None:
    """The lane was alive over ``[start, end)``: the durable liveness marker."""
    await session.execute(
        _INSERT_GAP,
        {
            "id": str(uuid7()),
            "stream": f"copy_alive:{spec.id}",
            "gap_start": start,
            "gap_end": max(end, start + ONE_US),
            "reason": ALIVE_REASON,
            "detail": json.dumps({"rule_set_id": spec.id, "source": "copy_lane"}),
        },
    )


async def last_alive(session: AsyncSession, spec: CopySpec) -> datetime | None:
    return (
        await session.execute(_LAST_ALIVE, {"stream": f"copy_alive:{spec.id}"})
    ).scalar_one_or_none()


async def unclosed_gaps(session: AsyncSession, spec: CopySpec) -> list[LeaderGap]:
    """Holes whose opening was recorded and whose close never was (the worker died with them open)."""
    rows = (await session.execute(_UNCLOSED, {"rule_set_id": spec.id})).mappings().all()
    return [
        LeaderGap(
            None
            if str(r["stream"]).endswith(":*")
            else str(r["stream"]).removeprefix("copy_leader:"),
            r["gap_start"],
            None,
            str(r["reason"]),
        )
        for r in rows
    ]


async def record_recomposed(
    session: AsyncSession,
    spec: CopySpec,
    *,
    wallet: str,
    hole_id: str,
    start: datetime,
    end: datetime,
) -> None:
    """The durable mark that ``wallet``'s slice of the hole ``hole_id`` was read from the chain's history
    (and its pairs persisted): a restart owes only the slices without it."""
    await session.execute(
        _INSERT_GAP,
        {
            "id": str(uuid7()),
            "stream": f"copy_leader:{wallet}",
            "gap_start": start,
            "gap_end": max(end, start + ONE_US),
            "reason": RECOMPOSED_REASON,
            "detail": json.dumps(
                {
                    "rule_set_id": spec.id,
                    "source": "copy_lane",
                    "gap_id": hole_id,
                    "wallet": wallet,
                }
            ),
        },
    )


async def owed_gaps(
    session: AsyncSession, spec: CopySpec
) -> list[tuple[LeaderGap, frozenset[str]]]:
    """Closed holes (any kind but source health) with the leaders whose slice is already recomposed: what
    a restart still owes the chain's history."""
    from hunter_meme_worker.copy_gaps import classify  # local: copy_gaps imports this module

    done: dict[str, set[str]] = {}
    for r in (await session.execute(_RECOMPOSED, {"rule_set_id": spec.id})).mappings():
        done.setdefault(str(r["gid"]), set()).add(str(r["wallet"]))
    rows = (
        await session.execute(
            _CLOSED_HOLES, {"rule_set_id": spec.id, "not_holes": list(NOT_A_HOLE)}
        )
    ).mappings()
    out: list[tuple[LeaderGap, frozenset[str]]] = []
    for r in rows:
        if classify(str(r["reason"])) == "health":
            continue
        stream = str(r["stream"])
        wallet = None if stream.endswith(":*") else stream.removeprefix("copy_leader:")
        gap = LeaderGap(wallet, r["gap_start"], r["gap_end"], str(r["reason"]))
        out.append((gap, frozenset(done.get(str(r["gid"]), set()))))
    return out
