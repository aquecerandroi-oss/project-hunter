#!/usr/bin/env python3
"""Retire a meme Lab rule set — audited, dry-run by default (T4.16).

    uv run python infra/scripts/meme_rule_set.py --list
    uv run python infra/scripts/meme_rule_set.py --deprecate meme_paper_v0/1 \
        --reason "EXP-M1: descartar (9/9 negativas + artefato rug_no_snapshot)"          # dry-run
    uv run python infra/scripts/meme_rule_set.py --deprecate hype_probe_v0/1 --apply \
        --reason "EXP-M3: descartar (8/8 sondas em giro, vendas ≈ compras); sucessora hype_probe_v0/2 (EXP-M5)"

``--deprecate name/version`` sets ``status = 'retired'``, ``retired_at = now()``
on an **active** row and leaves a ``system_events`` row with the reason — the
operator's act with a reason on record, which is why the migration ``0030``
retires nothing itself. The loop reads the active sets fresh every tick, so
the set stops proposing on the next tick; its **open bets keep being marked
and closed** (a bet is evidence), and its pending proposals are refused
``rule_set_inactive`` at the fill.

Refusals, by name and with nothing written: ``rule_set_missing``,
``already_retired``, ``last_operator_set`` (the desk files manual buys under
the active ``operator`` set; retiring the last one would leave it none),
``reason_required``.

Connects with ``DATABASE_URL_MIGRATIONS`` (direct, never the pooler).
Exit codes: 0 done, 64 usage, 65 refused.
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

COMPONENT = "meme_rule_set"
MIN_REASON_LENGTH = 10
EX_USAGE, EX_REFUSED = 64, 65

__all__ = ["Refused", "RuleSetRow", "list_rule_sets", "load", "main", "run"]


class Connection(Protocol):
    async def execute(self, statement: Any, parameters: Any = None, /) -> Any: ...


@dataclass(frozen=True, slots=True)
class RuleSetRow:
    id: str
    name: str
    version: str
    kind: str
    exp_ref: str | None
    status: str
    open_bets: int
    pending_proposals: int


class Refused(Exception):
    def __init__(self, reason: str, detail: str) -> None:
        super().__init__(f"{reason}: {detail}")
        self.reason = reason


_ROWS = text(
    "SELECT r.id::text AS id, r.name, r.version, r.kind, r.exp_ref, r.status, "
    "       (SELECT count(*) FROM meme_paper_bets b WHERE b.rule_set_id = r.id "
    "          AND b.status = 'open') AS open_bets, "
    "       (SELECT count(*) FROM meme_proposals p WHERE p.rule_set_id = r.id "
    "          AND p.status IN ('proposed', 'approved')) AS pending_proposals "
    "FROM meme_rule_sets r ORDER BY r.status, r.name, r.version"
)
_RETIRE = text(
    "UPDATE meme_rule_sets SET status = 'retired', retired_at = now() "
    "WHERE id = CAST(:id AS uuid) AND status = 'active' RETURNING id"
)


async def list_rule_sets(conn: Connection) -> list[RuleSetRow]:
    rows = (await conn.execute(_ROWS)).mappings()
    return [
        RuleSetRow(
            id=str(r["id"]),
            name=str(r["name"]),
            version=str(r["version"]),
            kind=str(r["kind"]),
            exp_ref=r["exp_ref"],
            status=str(r["status"]),
            open_bets=int(r["open_bets"]),
            pending_proposals=int(r["pending_proposals"]),
        )
        for r in rows
    ]


def load(rows: Sequence[RuleSetRow], label: str) -> RuleSetRow:
    """The row ``name/version`` names, or ``rule_set_missing``."""
    name, _, version = label.partition("/")
    for row in rows:
        if row.name == name and row.version == version:
            return row
    raise Refused("rule_set_missing", label)


def _describe(rows: Sequence[RuleSetRow]) -> str:
    lines = [f"{'name/version':<20} {'kind':<14} {'exp':<7} {'status':<8} open pending"]
    for r in rows:
        lines.append(
            f"{r.name + '/' + r.version:<20} {r.kind:<14} {r.exp_ref or '-':<7} {r.status:<8} "
            f"{r.open_bets:>4} {r.pending_proposals:>7}"
        )
    return "\n".join(lines)


async def run(
    conn: Connection, *, deprecate: str | None, apply: bool, reason: str | None
) -> tuple[int, str]:
    """``(exit code, report)``. Writes only with ``--deprecate --apply`` and a reason."""
    rows = await list_rule_sets(conn)
    if deprecate is None:
        return 0, _describe(rows)
    if reason is None or len(reason.strip()) < MIN_REASON_LENGTH:
        raise Refused(
            "reason_required", f"--deprecate needs --reason of >= {MIN_REASON_LENGTH} chars"
        )
    row = load(rows, deprecate)
    if row.status != "active":
        raise Refused("already_retired", deprecate)
    if row.kind == "operator" and not any(
        r.kind == "operator" and r.status == "active" and r.id != row.id for r in rows
    ):
        raise Refused("last_operator_set", "the desk needs one active operator set")
    plan = (
        f"deprecate {deprecate} ({row.kind}, {row.exp_ref or '-'}): {row.open_bets} open bet(s) keep "
        f"being marked and closed; {row.pending_proposals} pending proposal(s) will be refused "
        f"rule_set_inactive at the fill\nreason: {reason.strip()}"
    )
    if not apply:
        return 0, plan + "\ndry-run: nothing written (add --apply)"
    retired = (await conn.execute(_RETIRE, {"id": row.id})).scalars().all()
    if not retired:
        raise Refused("already_retired", f"{deprecate} moved under us")
    await record_event(
        conn,
        component=COMPONENT,
        level="info",
        event="deprecated",
        message=f"{deprecate} retired; reason: {reason.strip()}",
    )
    return 0, plan + "\napplied: retired; system_events written"


def _parse(argv: Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])  # type: ignore[union-attr]
    parser.add_argument("--list", action="store_true")
    parser.add_argument("--deprecate", metavar="NAME/VERSION", default=None)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--reason", default=None)
    args = parser.parse_args(argv)
    if not args.list and args.deprecate is None:
        parser.error("one of --list or --deprecate NAME/VERSION is required")
    return args


async def _main(argv: Sequence[str]) -> int:
    args = _parse(argv)
    engine = create_async_engine(migration_url(), connect_args={"statement_cache_size": 0})
    try:
        async with engine.connect() as conn, conn.begin():
            try:
                code, report = await run(
                    conn, deprecate=args.deprecate, apply=args.apply, reason=args.reason
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
