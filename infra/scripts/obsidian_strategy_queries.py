"""Read-only queries behind ``export_strategies_to_obsidian.py``.

Every table read here is global (``strategies``, ``strategy_versions``,
``agent_signals``, ``system_events``) — SHADOW-LAB.md and DATABASE.md §1.1 say
shadow research carries no ``organization_id``, so there is no RLS to defeat and
no ``app.current_org`` to set. The exporter connects with the plain ``DATABASE_URL``
(``hunter_app``, SELECT only); nothing here ever writes.

Split from the renderer and the CLI so the renderer's unit tests never need a
database (350-line budget, and the right seam: this is *what the catalogue
says*, the renderer is *how a page says it*).
"""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import text

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncConnection

__all__ = [
    "ActivationEvent",
    "CohortCount",
    "VersionRow",
    "fetch_cohort_counts",
    "fetch_origin_events",
    "fetch_version_rows",
]


@dataclass(frozen=True, slots=True)
class VersionRow:
    """One ``strategy_versions`` row, joined with its family's ``key``."""

    id: uuid.UUID
    strategy_key: str
    version: str
    status: str
    purpose: str
    code_ref: str | None
    changelog: str | None
    parameters_schema: dict[str, Any]
    default_parameters: dict[str, Any]
    activated_at: datetime | None
    deprecated_at: datetime | None


@dataclass(frozen=True, slots=True)
class ActivationEvent:
    """One ``system_events`` row written by ``activate_strategy_version.py``
    for this ``(strategy_key, version)`` pair."""

    created_at: datetime
    level: str
    event: str
    message: str


@dataclass(frozen=True, slots=True)
class CohortCount:
    """How many ``agent_signals`` this version has emitted under one cohort."""

    cohort: str
    count: int


async def fetch_version_rows(conn: AsyncConnection) -> list[VersionRow]:
    """Every ``strategy_versions`` row, oldest strategy first, version second —
    a stable order the renderer never has to re-sort (determinism, brief item 2)."""
    rows = (
        await conn.execute(
            text(
                "SELECT s.key AS strategy_key, v.id, v.version, v.status, v.purpose, "
                "v.code_ref, v.changelog, v.parameters_schema, v.default_parameters, "
                "v.activated_at, v.deprecated_at "
                "FROM strategy_versions v JOIN strategies s ON s.id = v.strategy_id "
                "ORDER BY s.key, v.version"
            )
        )
    ).all()
    return [
        VersionRow(
            id=row.id,
            strategy_key=row.strategy_key,
            version=row.version,
            status=str(row.status),
            purpose=row.purpose,
            code_ref=row.code_ref,
            changelog=row.changelog,
            parameters_schema=dict(row.parameters_schema or {}),
            default_parameters=dict(row.default_parameters or {}),
            activated_at=row.activated_at,
            deprecated_at=row.deprecated_at,
        )
        for row in rows
    ]


def _word_boundary_pattern(key: str, version: str) -> str:
    """A POSIX word-boundary regex matching ``"<key> <version>"`` as whole
    tokens — so ``momentum v1`` never matches a future ``momentum v10``."""
    return rf"\m{re.escape(key)} {re.escape(version)}\M"


async def fetch_origin_events(
    conn: AsyncConnection, strategy_key: str, version: str
) -> list[ActivationEvent]:
    """Every ``activate_strategy_version.py`` audit row naming this version,
    oldest first — the "who/when" of the Origem section (the script writes no
    operator identity today; ``message`` and ``created_at`` are what exists)."""
    rows = (
        await conn.execute(
            text(
                "SELECT created_at, level, event, message FROM system_events "
                "WHERE component = 'activate_strategy_version' AND message ~ :pattern "
                "ORDER BY created_at"
            ),
            {"pattern": _word_boundary_pattern(strategy_key, version)},
        )
    ).all()
    return [
        ActivationEvent(
            created_at=row.created_at, level=str(row.level), event=row.event, message=row.message
        )
        for row in rows
    ]


async def fetch_cohort_counts(conn: AsyncConnection, version_id: uuid.UUID) -> list[CohortCount]:
    """Distinct ``supporting_features->>'cohort'`` values for this version, with
    counts — the "Coortes e sinais" table, sorted for determinism."""
    rows = (
        await conn.execute(
            text(
                "SELECT coalesce(supporting_features->>'cohort', '(sem coorte)') AS cohort, "
                "count(*) AS n FROM agent_signals WHERE strategy_version_id = :vid "
                "GROUP BY 1 ORDER BY 1"
            ),
            {"vid": version_id},
        )
    ).all()
    return [CohortCount(cohort=row.cohort, count=row.n) for row in rows]
