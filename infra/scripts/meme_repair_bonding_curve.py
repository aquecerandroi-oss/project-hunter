#!/usr/bin/env python3
"""Repair ``meme_tokens.bonding_curve`` rows a Mayhem ``create`` frame
contaminated with the program's shared sol-vault — audited, dry-run by
default, never a hand edit (T4.39/R36).

    uv run python infra/scripts/meme_repair_bonding_curve.py                # dry-run, every candidate
    uv run python infra/scripts/meme_repair_bonding_curve.py --limit 500    # dry-run, first 500 (by mint)
    uv run python infra/scripts/meme_repair_bonding_curve.py --apply \
        --reason "T4.39: mayhem create frame carried the shared sol-vault, not the coin's curve"

**Why.** R36 (``.claude/state/notes-R36-pda-mayhem.md``, ``docs/PUMPFUN.md``
§9) found 13 615 of 112 108 seven-day ``meme_tokens`` rows storing the Mayhem
program's shared ``["sol-vault"]`` PDA in ``bonding_curve`` instead of the
coin's own bonding-curve PDA — every one of them ``mayhem_enabled``. ``0047``
stops new rows from doing this (``hunter_exchanges.pumpfun.normalize
.parse_new_token`` derives the PDA and never trusts a frame's
``bondingCurveKey`` blindly); this script is the one-time, reviewable rewrite
of the rows ``0047`` could not touch, because a migration is not the place
for a scan of the whole table.

What it does, and what it refuses:

- a **candidate** is a row with ``bonding_curve IS NOT NULL`` and
  ``bonding_curve_raw IS NULL`` (never reconciled by this script or by the
  post-``0047`` ingest path) whose stored value disagrees with the PDA
  derived from its own mint (``hunter_exchanges.pumpfun.pdas
  .bonding_curve_address`` — the same function the executor and the radar's
  ``reconcile_once`` already use, never a hard-coded sol-vault address);
- ``--apply`` requires ``--reason`` (at least ten characters): every
  candidate row's ``bonding_curve`` becomes the derived PDA and
  ``bonding_curve_raw`` becomes the value it replaces, in one statement per
  batch with the write-once trigger
  (``meme_tokens_identity_is_written_once``) disabled for exactly that
  statement and re-enabled before commit — the same discipline ``0024``'s
  ``backfill_graduation_signals`` uses for the same trigger; one
  ``system_events`` row carries the count by ``mayhem_enabled`` and the
  human reason;
- run again after ``--apply``: every repaired row now has
  ``bonding_curve_raw IS NOT NULL`` and is no longer a candidate — the
  script is idempotent, nothing left to redo;
- ``--limit`` bounds how many candidates a single dry-run/apply touches
  (deterministic order: ``mint``), for a first look at a subset before a
  full run; omitted, every candidate is repaired in one transaction.

Connects with ``DATABASE_URL_MIGRATIONS`` (direct, never the pooler), like
every ops script here. Exit codes: 0 done or nothing to do, 64 usage,
65 refused.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, Protocol

from meme_ops_db import migration_url, record_event
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from hunter_exchanges.pumpfun.pdas import bonding_curve_address

COMPONENT = "meme_repair_bonding_curve"
TRIGGER = "meme_tokens_identity_is_written_once"
MIN_REASON_LENGTH = 10
EX_USAGE, EX_REFUSED = 64, 65

__all__ = ["Candidate", "Refused", "candidates", "main", "run"]


class Connection(Protocol):
    async def execute(self, statement: Any, parameters: Any = None, /) -> Any: ...


@dataclass(frozen=True, slots=True)
class Candidate:
    mint: str
    stored: str
    derived: str
    mayhem_enabled: bool | None


class Refused(Exception):
    def __init__(self, reason: str, detail: str) -> None:
        super().__init__(f"{reason}: {detail}")
        self.reason = reason


_CANDIDATE_ROWS = text(
    "SELECT mint, bonding_curve, mayhem_enabled FROM meme_tokens "
    "WHERE bonding_curve IS NOT NULL AND bonding_curve_raw IS NULL "
    "ORDER BY mint LIMIT :limit"
)
_APPLY = text(
    "UPDATE meme_tokens t SET bonding_curve = data.derived, "
    "  bonding_curve_raw = t.bonding_curve "
    "FROM (SELECT unnest(CAST(:mints AS text[])) AS mint, "
    "             unnest(CAST(:deriveds AS text[])) AS derived) AS data "
    "WHERE t.mint = data.mint AND t.bonding_curve_raw IS NULL "
    "RETURNING t.mint"
)


async def candidates(conn: Connection, *, limit: int | None) -> list[Candidate]:
    """Every row whose stored value disagrees with the PDA derived from its own
    mint — a plain read, no write, safe to call from a dry-run."""
    rows = (await conn.execute(_CANDIDATE_ROWS, {"limit": limit})).mappings()
    found: list[Candidate] = []
    for row in rows:
        mint = str(row["mint"])
        stored = str(row["bonding_curve"])
        derived = bonding_curve_address(mint)
        if derived != stored:
            found.append(
                Candidate(
                    mint=mint, stored=stored, derived=derived, mayhem_enabled=row["mayhem_enabled"]
                )
            )
    return found


def _describe(found: list[Candidate]) -> str:
    lines = [f"{len(found)} candidate(s): stored bonding_curve disagrees with the derived PDA"]
    for c in found:
        lines.append(
            f"  {c.mint}  mayhem_enabled={c.mayhem_enabled}  "
            f"stored {c.stored} -> derived {c.derived}"
        )
    return "\n".join(lines)


def _counts_by_mayhem(found: list[Candidate]) -> str:
    true_n = sum(1 for c in found if c.mayhem_enabled is True)
    false_n = sum(1 for c in found if c.mayhem_enabled is False)
    unknown_n = len(found) - true_n - false_n
    return f"mayhem_enabled=true: {true_n}, false: {false_n}, unknown: {unknown_n}"


async def run(
    conn: Connection,
    *,
    limit: int | None,
    apply: bool,
    reason: str | None,
) -> tuple[int, str]:
    """``(exit code, report)``. Writes only with ``apply`` and a valid reason."""
    if apply and (reason is None or len(reason.strip()) < MIN_REASON_LENGTH):
        raise Refused("reason_required", f"--apply needs --reason of >= {MIN_REASON_LENGTH} chars")
    found = await candidates(conn, limit=limit)
    report = _describe(found) + f"\n{_counts_by_mayhem(found)}"
    if not found:
        return 0, report + "\nnothing to do"
    if not apply:
        return 0, report + '\ndry-run: nothing written (add --apply --reason "…")'
    assert reason is not None
    await conn.execute(text(f"ALTER TABLE meme_tokens DISABLE TRIGGER {TRIGGER}"))
    updated = (
        (
            await conn.execute(
                _APPLY,
                {"mints": [c.mint for c in found], "deriveds": [c.derived for c in found]},
            )
        )
        .scalars()
        .all()
    )
    await conn.execute(text(f"ALTER TABLE meme_tokens ENABLE TRIGGER {TRIGGER}"))
    message = (
        f"repaired {len(updated)} bonding_curve row(s) to the derived PDA "
        f"({_counts_by_mayhem(found)}); reason: {reason.strip()}"
    )
    await record_event(conn, component=COMPONENT, level="info", event="repaired", message=message)
    return (
        0,
        report
        + f"\napplied: {len(updated)} row(s) now hold the derived PDA; system_events written",
    )


def _parse(argv: Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])  # type: ignore[union-attr]
    parser.add_argument("--limit", type=int, default=None)
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
                    conn, limit=args.limit, apply=args.apply, reason=args.reason
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
