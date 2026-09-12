#!/usr/bin/env python3
"""Reclassify past ``rug_no_snapshot`` closes as ``indeterminate`` — audited,
dry-run by default, never a hand edit (T4.16, ``0030_meme_gate_v2``).

    uv run python infra/scripts/meme_reclassify_indeterminate.py                 # dry-run, every candidate
    uv run python infra/scripts/meme_reclassify_indeterminate.py --day 2026-09-12  # one Brasília day
    uv run python infra/scripts/meme_reclassify_indeterminate.py --bet-id <uuid> --bet-id <uuid>
    uv run python infra/scripts/meme_reclassify_indeterminate.py --day 2026-09-12 --apply \
        --reason "artefato do simulador antes de 12:14 BRT: sem fotografia por 3 min; mcap 30 min depois = entrada"

What it does, and what it refuses:

- a **candidate** is a closed paper bet whose ``exit.reason`` is
  ``rug_no_snapshot`` and whose ``outcome_quality`` is still ``measured``
  (the loop closes new ones as ``indeterminate`` itself since T4.16; this
  script is for the rows written before);
- ``--apply`` requires ``--reason`` (at least ten characters — a reason
  somebody can read in a month): the text is written on every row
  (``outcome_quality_reason``) with ``outcome_quality_at = now()``, and one
  ``system_events`` row names the bets and the reason;
- a ``--bet-id`` that is not a candidate refuses the whole run by name
  (``not_a_candidate``), nothing written; no candidate at all is a plain exit 0;
- the numbers on the row (``pnl_sol``, ``r_multiple``) are **not** touched:
  the sums stop counting the row (scoreboard, desk, the loop's wallet), the
  row keeps what the simulator computed.

Connects with ``DATABASE_URL_MIGRATIONS`` (direct, never the pooler), like
every ops script here. Exit codes: 0 done or nothing to do, 64 usage, 65 refused.
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

COMPONENT = "meme_reclassify_indeterminate"
MIN_REASON_LENGTH = 10
EX_USAGE, EX_REFUSED = 64, 65

__all__ = ["Candidate", "Refused", "candidates", "main", "run"]


class Connection(Protocol):
    async def execute(self, statement: Any, parameters: Any = None, /) -> Any: ...


@dataclass(frozen=True, slots=True)
class Candidate:
    id: uuid.UUID
    mint: str
    rule_set: str
    entry_at: datetime
    exit_at: datetime
    pnl_sol: Decimal
    pending_reason: str | None


class Refused(Exception):
    def __init__(self, reason: str, detail: str) -> None:
        super().__init__(f"{reason}: {detail}")
        self.reason = reason


_CANDIDATES = text(
    "SELECT b.id, b.mint, r.name || '/' || r.version AS rule_set, b.entry_at, b.exit_at, "
    "       b.pnl_sol, b.exit ->> 'pending_reason' AS pending_reason "
    "FROM meme_paper_bets b JOIN meme_rule_sets r ON r.id = b.rule_set_id "
    "WHERE b.status = 'closed' AND b.exit ->> 'reason' = 'rug_no_snapshot' "
    "  AND b.outcome_quality = 'measured' "
    "  AND (CAST(:day AS date) IS NULL "
    "       OR (b.entry_at AT TIME ZONE 'America/Sao_Paulo')::date = CAST(:day AS date)) "
    "  AND (CAST(:ids AS uuid[]) IS NULL OR b.id = ANY(CAST(:ids AS uuid[]))) "
    "ORDER BY b.entry_at"
)
_APPLY = text(
    "UPDATE meme_paper_bets SET outcome_quality = 'indeterminate', "
    "  outcome_quality_reason = :reason, outcome_quality_at = now() "
    "WHERE id = ANY(CAST(:ids AS uuid[])) AND status = 'closed' "
    "  AND exit ->> 'reason' = 'rug_no_snapshot' AND outcome_quality = 'measured' "
    "RETURNING id"
)


async def candidates(
    conn: Connection, *, day: date | None, ids: Sequence[uuid.UUID] | None
) -> list[Candidate]:
    rows = (
        await conn.execute(_CANDIDATES, {"day": day, "ids": list(ids) if ids else None})
    ).mappings()
    return [
        Candidate(
            id=r["id"],
            mint=str(r["mint"]),
            rule_set=str(r["rule_set"]),
            entry_at=r["entry_at"],
            exit_at=r["exit_at"],
            pnl_sol=Decimal(r["pnl_sol"]),
            pending_reason=r["pending_reason"],
        )
        for r in rows
    ]


def _describe(found: list[Candidate]) -> str:
    lines = [f"{len(found)} candidate(s): closed rug_no_snapshot still measured"]
    for c in found:
        lines.append(
            f"  {c.id}  {c.rule_set:<16} {c.mint[:12]}…  entry {c.entry_at.isoformat()}  "
            f"exit {c.exit_at.isoformat()}  pnl {c.pnl_sol} SOL  pending {c.pending_reason or '-'}"
        )
    return "\n".join(lines)


async def run(
    conn: Connection,
    *,
    day: date | None,
    ids: Sequence[uuid.UUID] | None,
    apply: bool,
    reason: str | None,
) -> tuple[int, str]:
    """``(exit code, report)``. Writes only with ``apply`` and a valid reason."""
    if apply and (reason is None or len(reason.strip()) < MIN_REASON_LENGTH):
        raise Refused("reason_required", f"--apply needs --reason of >= {MIN_REASON_LENGTH} chars")
    found = await candidates(conn, day=day, ids=ids)
    if ids:
        missing = sorted(set(ids) - {c.id for c in found})
        if missing:
            raise Refused("not_a_candidate", ", ".join(str(m) for m in missing))
    report = _describe(found)
    if not found:
        return 0, report + "\nnothing to do"
    if not apply:
        return 0, report + '\ndry-run: nothing written (add --apply --reason "…")'
    assert reason is not None
    updated = (
        (await conn.execute(_APPLY, {"ids": [c.id for c in found], "reason": reason.strip()}))
        .scalars()
        .all()
    )
    message = (
        f"reclassified {len(updated)} bet(s) as indeterminate; reason: {reason.strip()}; "
        f"ids: {', '.join(str(i) for i in updated)}"
    )
    await record_event(
        conn, component=COMPONENT, level="info", event="reclassified", message=message
    )
    return 0, report + f"\napplied: {len(updated)} row(s) now indeterminate; system_events written"


def _parse(argv: Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])  # type: ignore[union-attr]
    parser.add_argument(
        "--day", type=date.fromisoformat, default=None, help="Brasília day of entry"
    )
    parser.add_argument("--bet-id", dest="ids", type=uuid.UUID, action="append", default=None)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--reason", default=None)
    return parser.parse_args(argv)


async def _main(argv: Sequence[str]) -> int:
    args = _parse(argv)
    engine = create_async_engine(migration_url(), connect_args={"statement_cache_size": 0})
    try:
        async with engine.connect() as conn, conn.begin():
            try:
                code, report = await run(
                    conn, day=args.day, ids=args.ids, apply=args.apply, reason=args.reason
                )
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
