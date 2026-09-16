#!/usr/bin/env python3
"""Label a ``time_stop`` close as ``indeterminate``/``series_ended`` when the
series it was priced on had already ended — audited, dry-run by default,
never a hand edit (T4.33, KB-0113 §2).

    uv run python infra/scripts/meme_reclassify_series_ended.py                  # dry-run, every candidate
    uv run python infra/scripts/meme_reclassify_series_ended.py --day 2026-09-15   # one Brasília day
    uv run python infra/scripts/meme_reclassify_series_ended.py --bet-id <uuid> --bet-id <uuid>
    uv run python infra/scripts/meme_reclassify_series_ended.py --day 2026-09-15 --apply

What it does, and what it refuses:

- a **candidate** is a closed paper bet whose ``exit.reason`` is ``time_stop``
  and whose ``outcome_quality`` is still ``measured``, with **no**
  ``meme_features_1m`` row for the mint priced (``mcap_sol IS NOT NULL``)
  more than 90 s after ``exit_at`` and inside the next 35 min — KB-0113 §2's
  own definition of "closed on the series' last existing bar": 8 of the 11
  ``time_stop`` closes of 15/09 measured exactly this, priced on a photo up
  to 32 minutes stale, at a median −0,340 R;
- ``--apply`` writes ``outcome_quality = 'indeterminate'``,
  ``outcome_quality_reason = 'series_ended'`` (a fixed name, not a sentence —
  the mechanical twin of the loop's own ``no_snapshot_in_window``),
  ``outcome_quality_at = now()``, and one ``system_events`` row naming the
  bets; nothing else needs a human-written ``--reason`` because the criterion
  is the query above, not a judgement call;
- a ``--bet-id`` that is not a candidate refuses the whole run by name
  (``not_a_candidate``), nothing written; no candidate at all is a plain exit 0;
- the numbers on the row (``pnl_sol``, ``r_multiple``) are **not** touched:
  the loop's own mark already priced the exit on the last real observation it
  had; this only says the market past that point was never seen again.

Connects with ``DATABASE_URL_MIGRATIONS`` (direct, never the pooler), like
every ops script here. Exit codes: 0 done or nothing to do, 65 refused.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Protocol

from meme_ops_db import migration_url, record_event
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from hunter_core.domain.types import utcnow

COMPONENT = "meme_reclassify_series_ended"
SERIES_ENDED = "series_ended"
EX_REFUSED = 65

__all__ = ["Candidate", "Refused", "SERIES_ENDED", "candidates", "main", "run"]


class Connection(Protocol):
    async def execute(self, statement: Any, parameters: Any = None, /) -> Any: ...


class Refused(Exception):
    def __init__(self, reason: str, detail: str) -> None:
        super().__init__(f"{reason}: {detail}")
        self.reason = reason


@dataclass(frozen=True, slots=True)
class Candidate:
    id: uuid.UUID
    mint: str
    rule_set: str
    entry_at: datetime
    exit_at: datetime
    pnl_sol: Decimal


_CANDIDATES = text(
    "SELECT b.id, b.mint, r.name || '/' || r.version AS rule_set, b.entry_at, b.exit_at, "
    "       b.pnl_sol "
    "FROM meme_paper_bets b JOIN meme_rule_sets r ON r.id = b.rule_set_id "
    "WHERE b.status = 'closed' AND b.exit ->> 'reason' = 'time_stop' "
    "  AND b.outcome_quality = 'measured' "
    "  AND CAST(:as_of AS timestamptz) >= b.exit_at + interval '35 minutes' "
    "  AND NOT EXISTS ("
    "    SELECT 1 FROM meme_features_1m f WHERE f.mint = b.mint AND f.mcap_sol IS NOT NULL "
    "      AND f.end_time > b.exit_at + interval '90 seconds' "
    "      AND f.end_time <= b.exit_at + interval '35 minutes') "
    "  AND (CAST(:day AS date) IS NULL "
    "       OR (b.entry_at AT TIME ZONE 'America/Sao_Paulo')::date = CAST(:day AS date)) "
    "  AND (CAST(:ids AS uuid[]) IS NULL OR b.id = ANY(CAST(:ids AS uuid[]))) "
    "ORDER BY b.entry_at"
)
"""``:as_of >= exit_at + 35 min`` is not a filter of taste: a bet that exited in
the last 35 min of the day the cron closes has not yet had the time to earn a
later ``meme_features_1m`` row — without this guard the query would call a
series "ended" only because real time had not passed yet, the exact false
positive the label exists to avoid. Bound as a parameter (never SQL ``now()``)
so a caller — the nightly cron, or a test — names the instant it judges from."""
_APPLY = text(
    "UPDATE meme_paper_bets SET outcome_quality = 'indeterminate', "
    "  outcome_quality_reason = :reason, outcome_quality_at = now() "
    "WHERE id = ANY(CAST(:ids AS uuid[])) AND status = 'closed' "
    "  AND exit ->> 'reason' = 'time_stop' AND outcome_quality = 'measured' "
    "RETURNING id"
)


async def candidates(
    conn: Connection,
    *,
    day: date | None,
    ids: Sequence[uuid.UUID] | None,
    as_of: datetime | None = None,
) -> list[Candidate]:
    rows = (
        await conn.execute(
            _CANDIDATES,
            {"day": day, "ids": list(ids) if ids else None, "as_of": as_of or utcnow()},
        )
    ).mappings()
    return [
        Candidate(
            id=r["id"],
            mint=str(r["mint"]),
            rule_set=str(r["rule_set"]),
            entry_at=r["entry_at"],
            exit_at=r["exit_at"],
            pnl_sol=Decimal(r["pnl_sol"]),
        )
        for r in rows
    ]


def _describe(found: list[Candidate]) -> str:
    lines = [f"{len(found)} candidate(s): closed time_stop, series ended before the mark"]
    for c in found:
        lines.append(
            f"  {c.id}  {c.rule_set:<16} {c.mint[:12]}…  entry {c.entry_at.isoformat()}  "
            f"exit {c.exit_at.isoformat()}  pnl {c.pnl_sol} SOL"
        )
    return "\n".join(lines)


async def run(
    conn: Connection,
    *,
    day: date | None,
    ids: Sequence[uuid.UUID] | None,
    apply: bool,
    as_of: datetime | None = None,
) -> tuple[int, str]:
    """``(exit code, report)``. Writes only with ``apply``."""
    found = await candidates(conn, day=day, ids=ids, as_of=as_of)
    if ids:
        missing = sorted(set(ids) - {c.id for c in found})
        if missing:
            raise Refused("not_a_candidate", ", ".join(str(m) for m in missing))
    report = _describe(found)
    if not found:
        return 0, report + "\nnothing to do"
    if not apply:
        return 0, report + "\ndry-run: nothing written (add --apply)"
    updated = (
        (await conn.execute(_APPLY, {"ids": [c.id for c in found], "reason": SERIES_ENDED}))
        .scalars()
        .all()
    )
    message = (
        f"reclassified {len(updated)} bet(s) as indeterminate/{SERIES_ENDED}; "
        f"ids: {', '.join(str(i) for i in updated)}"
    )
    await record_event(
        conn, component=COMPONENT, level="info", event="reclassified", message=message
    )
    return 0, report + f"\napplied: {len(updated)} row(s) now indeterminate/{SERIES_ENDED}"


def _parse(argv: Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])  # type: ignore[union-attr]
    parser.add_argument(
        "--day", type=date.fromisoformat, default=None, help="Brasília day of entry"
    )
    parser.add_argument("--bet-id", dest="ids", type=uuid.UUID, action="append", default=None)
    parser.add_argument("--apply", action="store_true")
    return parser.parse_args(argv)


async def _main(argv: Sequence[str]) -> int:
    args = _parse(argv)
    engine = create_async_engine(migration_url(), connect_args={"statement_cache_size": 0})
    try:
        async with engine.connect() as conn, conn.begin():
            try:
                code, report = await run(conn, day=args.day, ids=args.ids, apply=args.apply)
            except Refused as refused:
                print(f"refused: {refused}", file=sys.stderr)
                return EX_REFUSED
        print(report)
        return code
    finally:
        await engine.dispose()


def main(argv: Sequence[str] | None = None) -> int:
    return asyncio.run(_main(sys.argv[1:] if argv is None else argv))


if __name__ == "__main__":
    sys.exit(main())
