#!/usr/bin/env python3
"""Retire a meme Lab rule set, or set one parameter on the live sets — audited,
dry-run by default (T4.16; ``--set-param`` since T4.27; ``--history``/
``--backfill`` since T4.35, ``meme_rule_set_params.py``).

    uv run python infra/scripts/meme_rule_set.py --list
    uv run python infra/scripts/meme_rule_set.py --deprecate meme_paper_v0/1 \
        --reason "EXP-M1: descartar (9/9 negativas + artefato rug_no_snapshot)"          # dry-run
    uv run python infra/scripts/meme_rule_set.py --deprecate hype_probe_v0/1 --apply \
        --reason "EXP-M3: descartar (8/8 sondas em giro)" --note obsidian/05-EXPERIMENTS/EXP-M5.md
    uv run python infra/scripts/meme_rule_set.py --set-param exclude_mayhem=true --all-active \
        --apply --reason "T4.27: picos de mcap sao SOL virtual" --note "obsidian/11-KNOWLEDGE/Fila de Hipoteses.md"
    uv run python infra/scripts/meme_rule_set.py --history operator/5
    uv run python infra/scripts/meme_rule_set.py --backfill --apply
    uv run python infra/scripts/meme_rule_set.py --validate operator/5

``--deprecate name/version`` sets ``status = 'retired'``, ``retired_at = now()``
on an **active** row and leaves a ``system_events`` row with the reason — the
operator's act with a reason on record, which is why the migration ``0030``
retires nothing itself. The loop reads the active sets fresh every tick, so
the set stops proposing on the next tick; its **open bets keep being marked
and closed** (a bet is evidence), and its pending proposals are refused
``rule_set_inactive`` at the fill.

``--set-param KEY=VALUE`` (T4.27) writes one key into ``params`` of every
**active** set named by ``--all-active`` or ``--rule-set name/version`` (repeatable):
``params || {KEY: VALUE}``, the value parsed as JSON (``true``, ``900``, ``"0.05"``
— a bare word that is not JSON is taken as a string), one ``system_events``
row naming the sets, the key, the old values and the reason. A set that
already carries the value is listed and left alone; nothing to change is a
plain exit 0.

**``--set-param --apply`` also writes ``meme_rule_set_param_history`` (T4.35),
in the same transaction as the ``UPDATE``** — R27 (16/09/2026) found
``operator/5`` edited four times in 100 minutes with no row keeping the old
value. ``--history NAME/VERSION`` prints that table's timeline for one set;
``--backfill`` (dry-run by default, ``--apply`` to write) recovers what it can
of the changes made **before** this revision from the free-text
``system_events`` message that was, until now, the only copy — see
``meme_rule_set_params.py`` for both.

Refusals, by name and with nothing written: ``rule_set_missing``,
``already_retired``, ``last_operator_set`` (the desk files manual buys under
the active ``operator`` set; retiring the last one would leave it none),
``reason_required``, ``param_invalid`` (no ``=``, empty key), ``no_target``
(``--set-param`` without ``--all-active``/``--rule-set``), ``rule_set_retired``
(a parameter on a retired set is a rewrite of evidence).

**``--set-param`` never writes a document the Lab cannot load (T4.64,
``meme_rule_set_validate.py``).** Two incidents on 18/09/2026 (KB-0140):
``max_sol_per_bet=0.28`` stored a JSON number where the worker's
``RuleSetSpec.from_params`` demands a string, and ``trailing_arm_x="1.0"``
reached ``ExitRules.__post_init__``'s floor — both crash-looped the worker
before anyone noticed. In dry-run **and** ``--apply``, every set the merge
would change is loaded through that exact path (the entry gate and the exit
rules included); a value that would not load is refused as ``WouldNotLoad``
with the worker's own error, exit 2, nothing written — a bare number over a
key the live document already carries as a string is caught earlier still,
with the fix spelled out (``decimals are strings: use 'key="0.28"'``).
``--validate NAME/VERSION`` runs the same check, read-only, on a set already
in the table.

Connects with ``DATABASE_URL_MIGRATIONS`` (direct, never the pooler).
Exit codes: 0 done, 2 would not load, 64 usage, 65 refused.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import obsidian_note_gate
from meme_ops_db import migration_url, record_event
from meme_rule_set_params import backfill_history, history_for, parse_param
from meme_rule_set_params import set_param as _apply_set_param
from meme_rule_set_types import COMPONENT, Connection, Refused, WouldNotLoad, load
from meme_rule_set_validate import validate_live
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

MIN_REASON_LENGTH = 10
EX_USAGE, EX_REFUSED, EX_WOULD_NOT_LOAD = 64, 65, 2

__all__ = [
    "Connection",
    "Refused",
    "RuleSetRow",
    "WouldNotLoad",
    "list_rule_sets",
    "load",
    "main",
    "parse_param",
    "run",
]


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
    params: dict[str, Any] = field(default_factory=dict[str, Any])

    @property
    def label(self) -> str:
        return f"{self.name}/{self.version}"


_ROWS = text(
    "SELECT r.id::text AS id, r.name, r.version, r.kind, r.exp_ref, r.status, r.params, "
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
            params=dict(r.get("params") or {}),
        )
        for r in rows
    ]


def _describe(rows: Sequence[RuleSetRow]) -> str:
    lines = [f"{'name/version':<20} {'kind':<14} {'exp':<7} {'status':<8} open pending"]
    for r in rows:
        lines.append(
            f"{r.label:<20} {r.kind:<14} {r.exp_ref or '-':<7} {r.status:<8} "
            f"{r.open_bets:>4} {r.pending_proposals:>7}"
        )
    return "\n".join(lines)


def _require_reason(reason: str | None, flag: str) -> str:
    if reason is None or len(reason.strip()) < MIN_REASON_LENGTH:
        raise Refused("reason_required", f"{flag} needs --reason of >= {MIN_REASON_LENGTH} chars")
    return reason.strip()


def _note_refused(exc: obsidian_note_gate.NoteRefused) -> Refused:
    """``NoteRefused`` and this module's ``Refused`` share one ``(reason, detail)`` shape."""
    return Refused(exc.reason, str(exc).split(": ", 1)[1])


async def _deprecate(
    conn: Connection,
    rows: Sequence[RuleSetRow],
    deprecate: str,
    *,
    apply: bool,
    reason: str,
    note: str | None = None,
    repo_root: Path | None = None,
) -> tuple[int, str]:
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
        f"rule_set_inactive at the fill\nreason: {reason}"
    )
    if not apply:
        hint = obsidian_note_gate.describe_required_note([[deprecate]])
        return 0, plan + f"\ndry-run: nothing written (add --apply); {hint}"
    try:
        proof = obsidian_note_gate.gate(
            note, [[deprecate]], repo_root=repo_root or obsidian_note_gate.default_repo_root()
        )
    except obsidian_note_gate.NoteRefused as note_refused:
        raise _note_refused(note_refused) from note_refused
    retired = (await conn.execute(_RETIRE, {"id": row.id})).scalars().all()
    if not retired:
        raise Refused("already_retired", f"{deprecate} moved under us")
    await record_event(
        conn,
        component=COMPONENT,
        level="info",
        event="deprecated",
        message=f"{deprecate} retired; reason: {reason}",
        data=obsidian_note_gate.provenance_data(proof),
    )
    return 0, plan + "\napplied: retired; system_events written"


async def run(
    conn: Connection,
    *,
    deprecate: str | None,
    apply: bool,
    reason: str | None,
    set_param: str | None = None,
    all_active: bool = False,
    rule_sets: Sequence[str] = (),
    history: str | None = None,
    backfill: bool = False,
    validate: str | None = None,
    note: str | None = None,
    repo_root: Path | None = None,
) -> tuple[int, str]:
    """``(exit code, report)``. Writes only with ``--apply`` and a reason.

    ``--deprecate``/``--set-param`` also need ``--note`` at ``--apply`` time —
    a Markdown file under ``obsidian/`` mentioning the target set(s) (T4.93,
    "Obsidian primeiro"): :mod:`obsidian_note_gate`.
    """
    rows = await list_rule_sets(conn)
    if validate is not None:
        row = load(rows, validate)
        validate_live(row)  # raises WouldNotLoad; nothing to catch on success
        return 0, f"OK: {row.label} loads (gate, exit rules, RuleSetSpec.from_params)"
    if history is not None:
        return await history_for(conn, load(rows, history))
    if backfill:
        return await backfill_history(conn, rows, apply=apply)
    if deprecate is None and set_param is None:
        return 0, _describe(rows)
    if deprecate is not None:
        return await _deprecate(
            conn,
            rows,
            deprecate,
            apply=apply,
            reason=_require_reason(reason, "--deprecate"),
            note=note,
            repo_root=repo_root,
        )
    assert set_param is not None
    return await _apply_set_param(
        conn,
        rows,
        set_param,
        all_active=all_active,
        labels=rule_sets,
        apply=apply,
        reason=_require_reason(reason, "--set-param"),
        note=note,
        repo_root=repo_root,
    )


def _parse(argv: Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])  # type: ignore[union-attr]
    parser.add_argument("--list", action="store_true")
    parser.add_argument("--deprecate", metavar="NAME/VERSION", default=None)
    parser.add_argument("--set-param", dest="set_param", metavar="KEY=VALUE", default=None)
    parser.add_argument("--all-active", dest="all_active", action="store_true")
    parser.add_argument(
        "--rule-set", dest="rule_sets", metavar="NAME/VERSION", action="append", default=[]
    )
    parser.add_argument("--history", metavar="NAME/VERSION", default=None)
    parser.add_argument("--backfill", action="store_true")
    parser.add_argument("--validate", metavar="NAME/VERSION", default=None)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--reason", default=None)
    parser.add_argument(
        "--note",
        default=None,
        metavar="PATH",
        help="--deprecate/--set-param --apply only: a .md under obsidian/ mentioning the "
        "target set(s) (T4.93, Obsidian primeiro)",
    )
    args = parser.parse_args(argv)
    acts = [
        args.deprecate is not None,
        args.set_param is not None,
        args.history is not None,
        args.backfill,
        args.validate is not None,
    ]
    if not args.list and not any(acts):
        parser.error(
            "one of --list, --deprecate NAME/VERSION, --set-param KEY=VALUE, "
            "--history NAME/VERSION, --backfill or --validate NAME/VERSION is required"
        )
    if sum(acts) > 1:
        parser.error(
            "--deprecate/--set-param/--history/--backfill/--validate are acts; run one at a time"
        )
    return args


async def _main(argv: Sequence[str]) -> int:
    args = _parse(argv)
    engine = create_async_engine(migration_url(), connect_args={"statement_cache_size": 0})
    try:
        async with engine.connect() as conn, conn.begin():
            try:
                code, report = await run(
                    conn,
                    deprecate=args.deprecate,
                    apply=args.apply,
                    reason=args.reason,
                    set_param=args.set_param,
                    all_active=args.all_active,
                    rule_sets=args.rule_sets,
                    history=args.history,
                    backfill=args.backfill,
                    validate=args.validate,
                    note=args.note,
                )
            except Refused as refused:
                print(f"refused: {refused}", file=sys.stderr)
                return EX_REFUSED
            except WouldNotLoad as bad:
                print(f"would not load: {bad}", file=sys.stderr)
                return EX_WOULD_NOT_LOAD
        print(report)
        return code
    finally:
        await engine.dispose()


def main(argv: Sequence[str] | None = None) -> int:
    return asyncio.run(_main(sys.argv[1:] if argv is None else argv))


if __name__ == "__main__":
    sys.exit(main())
