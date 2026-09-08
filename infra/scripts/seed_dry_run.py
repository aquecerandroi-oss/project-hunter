"""The diff engine behind ``seed.py --dry-run``/``--only`` (T3.39).

Reuses every ``seed_*`` upsert unchanged: rather than a second copy of "what
would this write", each diffable table is snapshotted by its natural key
**inside the same open transaction**, before and after the real function runs.
What differs is read straight from Postgres, never guessed from the reference
constants — the guarantee a hand-written diff could not make, and the same one
``_written()`` (``seed.py``) already relies on for its counts.

Four tables are diffable, matched to ``--only``'s choices: ``strategies``
(``strategies.key``), ``risk_profiles`` (the three presets plus ``paper_v1``,
``organization_id IS NULL``), ``feature_definitions`` (``name`` — this build
ships one version per name, so it is a natural key in practice even though the
table's real uniqueness is ``(name, version)``) and ``opportunity_weights``
(``version``). Other tables the full run touches (``exchanges``,
``plan_entitlements``, ``feature_flags``) are reported by count only, the way
``seed()`` always has — the operator's stated need (T3.33e/f: ``session_orb``
missing, stale descriptions, the risk directive on ``risk_profiles``) is these
four.
"""

from __future__ import annotations

from typing import Any

from seed_reference import (
    OPPORTUNITY_WEIGHTS,
    PAPER_V1_LIMITS,
    REGIME_MULTIPLIERS,
    RISK_LIMITS,
    RISK_PRESETS,
    STRATEGIES,
    feature_definition_rows,
)
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

_IGNORED_COLUMNS = {"id", "created_at", "updated_at"}
"""Columns that change on every run (surrogate key, timestamps) and would
otherwise show up as a "change" on a row nothing meaningful moved on."""

Row = dict[str, Any]
Snapshot = dict[str, dict[Any, Row]]

TABLE_CHOICES: tuple[str, ...] = (
    "strategies",
    "risk_profiles",
    "feature_definitions",
    "opportunity_weights",
)


def risk_profile_targets() -> dict[str, dict[str, Any]]:
    """``preset -> limits`` this build would write — the 3 presets + ``paper_v1``.

    The same computation ``seed_risk_profiles``/``seed_paper_preset`` do, kept
    here rather than duplicated as a second literal: both read straight from
    :mod:`seed_reference`.
    """
    targets: dict[str, dict[str, Any]] = {}
    for index, (preset, _name) in enumerate(RISK_PRESETS):
        limits: dict[str, Any] = {key: values[index] for key, values in RISK_LIMITS.items()}
        limits["regime_size_multiplier"] = REGIME_MULTIPLIERS[index]
        targets[preset.value] = limits
    targets["paper_v1"] = dict(PAPER_V1_LIMITS)
    return targets


async def _snapshot_one(
    conn: AsyncConnection, table: str, key_column: str, keys: list[Any], *, extra_where: str = ""
) -> dict[Any, Row]:
    if not keys:
        return {}
    where = f"{key_column} = ANY(:keys)" + (f" AND {extra_where}" if extra_where else "")
    result = await conn.execute(
        text(f"SELECT * FROM {table} WHERE {where}"),  # noqa: S608 - table/column are literals above
        {"keys": keys},
    )
    return {row[key_column]: dict(row) for row in result.mappings()}


async def _snapshot_strategy_versions(conn: AsyncConnection) -> dict[Any, Row]:
    """``<strategy key> v1`` -> the ``strategy_versions`` row ``seed_strategies`` writes.

    ``strategies`` and ``strategy_versions`` move together (one upsert, two
    report keys, ``seed.py``'s own convention): a diff that showed the catalogue
    changing without showing the version row moving alongside it — the actual
    complaint behind ``--only strategies`` (T3.33e/f, ``session_orb``'s stale
    description) — would have missed the row that operator was there to check
    (T3.39b review, BAIXA-9).
    """
    keys = [key for key, *_ in STRATEGIES]
    result = await conn.execute(
        text(
            "SELECT s.key AS strategy_key, v.* FROM strategy_versions v "
            "JOIN strategies s ON s.id = v.strategy_id "
            "WHERE s.key = ANY(:keys) AND v.version = 'v1'"
        ),
        {"keys": keys},
    )
    rows: dict[Any, Row] = {}
    for mapped in result.mappings():
        row = dict(mapped)
        strategy_key = row.pop("strategy_key")
        rows[f"{strategy_key} v1"] = row
    return rows


async def snapshot(conn: AsyncConnection, only: str | None) -> Snapshot:
    """The diffable tables' rows, keyed by natural key, restricted to ``only`` if given."""
    wanted = TABLE_CHOICES if only is None else (only,)
    out: Snapshot = {}
    if "strategies" in wanted:
        out["strategies"] = await _snapshot_one(
            conn, "strategies", "key", [key for key, *_ in STRATEGIES]
        )
        out["strategy_versions"] = await _snapshot_strategy_versions(conn)
    if "risk_profiles" in wanted:
        out["risk_profiles"] = await _snapshot_one(
            conn,
            "risk_profiles",
            "preset",
            list(risk_profile_targets()),
            extra_where="organization_id IS NULL",
        )
    if "feature_definitions" in wanted:
        out["feature_definitions"] = await _snapshot_one(
            conn,
            "feature_definitions",
            "name",
            [row["name"] for row in feature_definition_rows()],
        )
    if "opportunity_weights" in wanted:
        out["opportunity_weights"] = await _snapshot_one(
            conn,
            "opportunity_weights",
            "version",
            [version for version, _w, _d in OPPORTUNITY_WEIGHTS],
        )
    return out


def diff_lines(before: Snapshot, after: Snapshot) -> list[str]:
    """``table.key: field: old -> new`` for every row that changed or is new."""
    lines: list[str] = []
    for table in sorted(after):
        table_before = before.get(table, {})
        for key, new in sorted(after[table].items(), key=str):
            old = table_before.get(key)
            if old is None:
                shown = {c: v for c, v in new.items() if c not in _IGNORED_COLUMNS}
                lines.append(f"{table}.{key}: NEW {shown}")
                continue
            changed = {
                column: (old.get(column), value)
                for column, value in new.items()
                if column not in _IGNORED_COLUMNS and old.get(column) != value
            }
            if changed:
                parts = ", ".join(f"{c}: {o!r} -> {n!r}" for c, (o, n) in sorted(changed.items()))
                lines.append(f"{table}.{key}: {parts}")
    return lines


async def risk_profiles_would_change(conn: AsyncConnection) -> list[str]:
    """Presets whose stored ``limits`` differ from what this build would ship."""
    stored = await _snapshot_one(
        conn,
        "risk_profiles",
        "preset",
        list(risk_profile_targets()),
        extra_where="organization_id IS NULL",
    )
    changed: list[str] = []
    for preset, target in risk_profile_targets().items():
        row = stored.get(preset)
        if row is not None and row.get("limits") != target:
            changed.append(preset)
    return changed
