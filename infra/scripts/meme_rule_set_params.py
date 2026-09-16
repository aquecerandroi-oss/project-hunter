"""``meme_rule_set.py --set-param`` (T4.27) and its param history (T4.35) —
split out for the 350-line budget: ``meme_rule_set.py`` keeps the row model,
``--deprecate`` and the CLI; this module owns everything about *changing* and
*remembering* one parameter.

**The history.** Every ``--set-param --apply`` writes one
``meme_rule_set_param_history`` row per changed set, in the same transaction
as the ``UPDATE`` (:func:`insert_history_row`, called from :func:`set_param`).
``--history NAME/VERSION`` (:func:`history_for`) prints that table's timeline.

**The backfill.** Before this revision the only record of a param change was
the free-text ``message`` of a ``system_events`` row (verified against
``meme_ops_db.record_event``: it never carried a structured ``data`` payload
until T4.35) — exactly the shape R27 (16/09/2026) found unrecoverable for
``operator/5``'s sniper cap. :func:`backfill_history` parses that frozen shape
(``_MESSAGE_RE``): ``KEY = VALUE on N set(s): LABEL (OLD), LABEL (OLD); reason:
REASON``. A message that does not match is counted ``unparsed`` and skipped —
never guessed; a ``(rule_set, key, system_event_id)`` already recovered is
left alone, so a second run changes nothing new.
"""

from __future__ import annotations

import json
import re
from datetime import datetime
from typing import TYPE_CHECKING, Any

from meme_ops_db import record_event
from meme_rule_set_types import COMPONENT, Refused, load
from sqlalchemy import text

from hunter_core.domain.types import utcnow

if TYPE_CHECKING:
    from collections.abc import Sequence

    from meme_rule_set import RuleSetRow
    from meme_rule_set_types import Connection

__all__ = [
    "backfill_history",
    "history_for",
    "insert_history_row",
    "parse_param",
    "set_param",
]

_SET_PARAM = text(
    "UPDATE meme_rule_sets SET params = params || jsonb_build_object(CAST(:key AS text), CAST(:value AS jsonb)) "
    "WHERE id = ANY(CAST(:ids AS uuid[])) AND status = 'active' RETURNING id"
)
_HISTORY_INSERT = text(
    "INSERT INTO meme_rule_set_param_history "
    "(id, rule_set_id, changed_at, changed_by, reason, key, old_value, new_value, system_event_id) "
    "VALUES (gen_random_uuid(), CAST(:rule_set_id AS uuid), :changed_at, :changed_by, :reason, "
    ":key, CAST(:old_value AS jsonb), CAST(:new_value AS jsonb), CAST(:system_event_id AS uuid))"
)
_HISTORY_FOR_RULE_SET = text(
    "SELECT changed_at, changed_by, reason, key, old_value, new_value, system_event_id "
    "FROM meme_rule_set_param_history WHERE rule_set_id = CAST(:id AS uuid) ORDER BY changed_at"
)
_HISTORY_EXISTS = text(
    "SELECT 1 FROM meme_rule_set_param_history "
    "WHERE system_event_id = CAST(:system_event_id AS uuid) "
    "AND rule_set_id = CAST(:rule_set_id AS uuid) AND key = :key LIMIT 1"
)
_PARAM_SET_EVENTS = text(
    "SELECT id::text AS id, created_at, message FROM system_events "
    "WHERE component = 'meme_rule_set' AND event = 'param_set' ORDER BY created_at"
)
_MESSAGE_RE = re.compile(
    r"^(?P<key>.+?) = (?P<encoded>.+?) on \d+ set\(s\): (?P<changed>.+); reason: (?P<reason>.+)$"
)
_CHANGED_ITEM_RE = re.compile(r"([^\s,()]+) \(([^()]*)\)")


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


async def insert_history_row(
    conn: Connection,
    *,
    rule_set_id: str,
    changed_at: datetime,
    changed_by: str,
    reason: str,
    key: str,
    old_value: str | None,
    new_value: str,
    system_event_id: str | None,
) -> None:
    """One ``meme_rule_set_param_history`` row. ``old_value``/``new_value`` are
    already JSON text (``json.dumps`` of the Python value, or ``None``)."""
    await conn.execute(
        _HISTORY_INSERT,
        {
            "rule_set_id": rule_set_id,
            "changed_at": changed_at,
            "changed_by": changed_by,
            "reason": reason,
            "key": key,
            "old_value": old_value,
            "new_value": new_value,
            "system_event_id": system_event_id,
        },
    )


async def set_param(
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
    system_event_id = await record_event(
        conn,
        component=COMPONENT,
        level="info",
        event="param_set",
        message=f"{key} = {encoded} on {len(updated)} set(s): {changed}; reason: {reason}",
        data={
            "key": key,
            "new_value": value,
            "changes": [
                {"rule_set": r.label, "rule_set_id": r.id, "old_value": r.params.get(key)}
                for r in to_change
            ],
        },
    )
    changed_at = utcnow()
    for r in to_change:
        await insert_history_row(
            conn,
            rule_set_id=r.id,
            changed_at=changed_at,
            changed_by=COMPONENT,
            reason=reason,
            key=key,
            old_value=None if key not in r.params else json.dumps(r.params[key]),
            new_value=encoded,
            system_event_id=system_event_id,
        )
    return 0, plan + f"\napplied: {len(updated)} row(s) updated; system_events written"


async def history_for(conn: Connection, row: RuleSetRow) -> tuple[int, str]:
    """``--history NAME/VERSION``: the timeline of one set, oldest first."""
    history = (await conn.execute(_HISTORY_FOR_RULE_SET, {"id": row.id})).mappings().all()
    if not history:
        return 0, f"{row.label}: no recorded change (before T4.35, or --backfill has not run)"
    lines = [f"{row.label} — {len(history)} change(s):"]
    for h in history:
        old = "<unset>" if h["old_value"] is None else json.dumps(h["old_value"])
        new = json.dumps(h["new_value"])
        lines.append(
            f"  {h['changed_at'].isoformat()}  {h['key']} = {old} -> {new}  "
            f"(by {h['changed_by']}; {h['reason']})"
        )
    return 0, "\n".join(lines)


async def backfill_history(
    conn: Connection, rows: Sequence[RuleSetRow], *, apply: bool
) -> tuple[int, str]:
    """``--backfill``: see the module docstring."""
    events = (await conn.execute(_PARAM_SET_EVENTS)).mappings().all()
    by_label = {r.label: r for r in rows}
    planned: list[dict[str, Any]] = []
    unparsed = 0
    for ev in events:
        match = _MESSAGE_RE.match(ev["message"] or "")
        if match is None:
            unparsed += 1
            continue
        key, reason = match["key"].strip(), match["reason"].strip()
        for item in _CHANGED_ITEM_RE.finditer(match["changed"]):
            label, old_raw = item.group(1), item.group(2)
            row = by_label.get(label)
            if row is None:  # a set later renamed/removed: nothing to attach the row to
                continue
            exists = (
                (
                    await conn.execute(
                        _HISTORY_EXISTS,
                        {"system_event_id": ev["id"], "rule_set_id": row.id, "key": key},
                    )
                )
                .scalars()
                .all()
            )
            if exists:
                continue
            planned.append(
                {
                    "rule_set_id": row.id,
                    "label": label,
                    "key": key,
                    "old_value": None if old_raw == "<unset>" else old_raw,
                    "new_value": match["encoded"].strip(),
                    "reason": reason,
                    "system_event_id": ev["id"],
                    "changed_at": ev["created_at"],
                }
            )
    lines = [
        f"backfill: {len(events)} param_set event(s), {unparsed} unparsed, "
        f"{len(planned)} row(s) to write"
    ]
    for p in planned:
        lines.append(f"  {p['label']:<20} {p['key']} {p['old_value']} -> {p['new_value']}")
    plan = "\n".join(lines)
    if not planned:
        return 0, plan + "\nnothing to do"
    if not apply:
        return 0, plan + "\ndry-run: nothing written (add --apply)"
    for p in planned:
        await insert_history_row(
            conn,
            rule_set_id=p["rule_set_id"],
            changed_at=p["changed_at"],
            changed_by=COMPONENT,
            reason=p["reason"],
            key=p["key"],
            old_value=p["old_value"],
            new_value=p["new_value"],
            system_event_id=p["system_event_id"],
        )
    return 0, plan + f"\napplied: {len(planned)} row(s) written"
