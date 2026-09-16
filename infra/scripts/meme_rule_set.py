#!/usr/bin/env python3
"""Retire a meme Lab rule set, or set one parameter on the live sets — audited,
dry-run by default (T4.16; ``--set-param`` since T4.27).

    uv run python infra/scripts/meme_rule_set.py --list
    uv run python infra/scripts/meme_rule_set.py --deprecate meme_paper_v0/1 \
        --reason "EXP-M1: descartar (9/9 negativas + artefato rug_no_snapshot)"          # dry-run
    uv run python infra/scripts/meme_rule_set.py --deprecate hype_probe_v0/1 --apply \
        --reason "EXP-M3: descartar (8/8 sondas em giro, vendas ≈ compras); sucessora hype_probe_v0/2 (EXP-M5)"
    uv run python infra/scripts/meme_rule_set.py --set-param exclude_mayhem=true --all-active \
        --apply --reason "T4.27: os picos de mcap sao SOL virtual do agente Mayhem, nao demanda"

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
plain exit 0. The only key written this way so far is ``exclude_mayhem``,
whose code default is already ``true`` (``hunter_indicators.meme.rules``):
the row is made to say it, so the registration and the EXP-M* pages agree.

Refusals, by name and with nothing written: ``rule_set_missing``,
``already_retired``, ``last_operator_set`` (the desk files manual buys under
the active ``operator`` set; retiring the last one would leave it none),
``reason_required``, ``param_invalid`` (no ``=``, empty key), ``no_target``
(``--set-param`` without ``--all-active``/``--rule-set``), ``rule_set_retired``
(a parameter on a retired set is a rewrite of evidence).

Connects with ``DATABASE_URL_MIGRATIONS`` (direct, never the pooler).
Exit codes: 0 done, 64 usage, 65 refused.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any, Protocol

from meme_ops_db import migration_url, record_event
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

COMPONENT = "meme_rule_set"
MIN_REASON_LENGTH = 10
EX_USAGE, EX_REFUSED = 64, 65

__all__ = ["Refused", "RuleSetRow", "list_rule_sets", "load", "main", "parse_param", "run"]


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
    params: dict[str, Any] = field(default_factory=dict[str, Any])

    @property
    def label(self) -> str:
        return f"{self.name}/{self.version}"


class Refused(Exception):
    def __init__(self, reason: str, detail: str) -> None:
        super().__init__(f"{reason}: {detail}")
        self.reason = reason


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
_SET_PARAM = text(
    "UPDATE meme_rule_sets SET params = params || jsonb_build_object(CAST(:key AS text), CAST(:value AS jsonb)) "
    "WHERE id = ANY(CAST(:ids AS uuid[])) AND status = 'active' RETURNING id"
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
            f"{r.label:<20} {r.kind:<14} {r.exp_ref or '-':<7} {r.status:<8} "
            f"{r.open_bets:>4} {r.pending_proposals:>7}"
        )
    return "\n".join(lines)


def _require_reason(reason: str | None, flag: str) -> str:
    if reason is None or len(reason.strip()) < MIN_REASON_LENGTH:
        raise Refused("reason_required", f"{flag} needs --reason of >= {MIN_REASON_LENGTH} chars")
    return reason.strip()


async def _deprecate(
    conn: Connection, rows: Sequence[RuleSetRow], deprecate: str, *, apply: bool, reason: str
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
        return 0, plan + "\ndry-run: nothing written (add --apply)"
    retired = (await conn.execute(_RETIRE, {"id": row.id})).scalars().all()
    if not retired:
        raise Refused("already_retired", f"{deprecate} moved under us")
    await record_event(
        conn,
        component=COMPONENT,
        level="info",
        event="deprecated",
        message=f"{deprecate} retired; reason: {reason}",
    )
    return 0, plan + "\napplied: retired; system_events written"


def parse_param(spec: str) -> tuple[str, Any]:
    """``KEY=VALUE`` → ``(key, value)``, the value as JSON when it parses as such."""
    key, sep, raw = spec.partition("=")
    if not sep or not key.strip():
        raise Refused("param_invalid", f"--set-param wants KEY=VALUE, got {spec!r}")
    try:
        value: Any = json.loads(raw)
    except ValueError:
        value = raw
    return key.strip(), value


def _targets(
    rows: Sequence[RuleSetRow], *, all_active: bool, labels: Sequence[str]
) -> list[RuleSetRow]:
    if all_active:
        return [r for r in rows if r.status == "active"]
    if not labels:
        raise Refused("no_target", "--set-param needs --all-active or --rule-set NAME/VERSION")
    chosen = [load(rows, label) for label in labels]
    retired = [r.label for r in chosen if r.status != "active"]
    if retired:
        raise Refused("rule_set_retired", ", ".join(retired))
    return chosen


async def _set_param(
    conn: Connection,
    rows: Sequence[RuleSetRow],
    spec: str,
    *,
    all_active: bool,
    labels: Sequence[str],
    apply: bool,
    reason: str,
) -> tuple[int, str]:
    key, value = parse_param(spec)
    targets = _targets(rows, all_active=all_active, labels=labels)
    encoded = json.dumps(value)
    to_change = [r for r in targets if r.params.get(key) != value]
    lines = [f"set-param {key} = {encoded} on {len(targets)} active set(s):"]
    for r in targets:
        current = "<unset>" if key not in r.params else json.dumps(r.params[key])
        verb = "unchanged" if r.params.get(key) == value else "change"
        lines.append(
            f"  {r.label:<20} {r.kind:<14} {r.exp_ref or '-':<7} {current} -> {encoded} ({verb})"
        )
    lines.append(f"reason: {reason}")
    plan = "\n".join(lines)
    if not to_change:
        return 0, plan + "\nnothing to do: every target already carries the value"
    if not apply:
        return 0, plan + "\ndry-run: nothing written (add --apply)"
    updated = (
        (
            await conn.execute(
                _SET_PARAM, {"key": key, "value": encoded, "ids": [r.id for r in to_change]}
            )
        )
        .scalars()
        .all()
    )
    changed = ", ".join(
        f"{r.label} ({'<unset>' if key not in r.params else json.dumps(r.params[key])})"
        for r in to_change
    )
    await record_event(
        conn,
        component=COMPONENT,
        level="info",
        event="param_set",
        message=f"{key} = {encoded} on {len(updated)} set(s): {changed}; reason: {reason}",
    )
    return 0, plan + f"\napplied: {len(updated)} row(s) updated; system_events written"


async def run(
    conn: Connection,
    *,
    deprecate: str | None,
    apply: bool,
    reason: str | None,
    set_param: str | None = None,
    all_active: bool = False,
    rule_sets: Sequence[str] = (),
) -> tuple[int, str]:
    """``(exit code, report)``. Writes only with ``--apply`` and a reason."""
    rows = await list_rule_sets(conn)
    if deprecate is None and set_param is None:
        return 0, _describe(rows)
    if deprecate is not None:
        return await _deprecate(
            conn, rows, deprecate, apply=apply, reason=_require_reason(reason, "--deprecate")
        )
    assert set_param is not None
    return await _set_param(
        conn,
        rows,
        set_param,
        all_active=all_active,
        labels=rule_sets,
        apply=apply,
        reason=_require_reason(reason, "--set-param"),
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
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--reason", default=None)
    args = parser.parse_args(argv)
    if not args.list and args.deprecate is None and args.set_param is None:
        parser.error("one of --list, --deprecate NAME/VERSION or --set-param KEY=VALUE is required")
    if args.deprecate is not None and args.set_param is not None:
        parser.error("--deprecate and --set-param are two acts; run them one at a time")
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
