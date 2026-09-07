"""What ``infra/scripts/activate_strategy_version.py`` reads and writes — shared by
its three modes (activate, ``--supersede``, ``--paper-line``).

Pulled out of the script when ``--paper-line`` (T3.15, D10) pushed it past the
350-line budget. Nothing here decides anything: these are the prerequisite
checks, the row reader and the ``system_events`` writer every mode uses. The
labels are spelled out rather than imported, the same choice
``ddl/strategy_purpose.py`` and :mod:`hunter_strategy_worker.catalogue` make for
their frozen strings.
"""

from __future__ import annotations

import re
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

__all__ = [
    "PURPOSE_LIVE",
    "PURPOSE_PAPER",
    "PURPOSE_RESEARCH_ONLY",
    "REQUIRED_TABLES",
    "VERSION_RE",
    "Refused",
    "load_row",
    "migration_applied",
    "next_free_version",
    "purpose_column_present",
    "record_event",
]

REQUIRED_TABLES = ("shadow_episodes", "shadow_outbox")
VERSION_RE = re.compile(r"^v(\d+)$")
PURPOSE_RESEARCH_ONLY = "research_only"
PURPOSE_PAPER = "paper"
PURPOSE_LIVE = "live"


class Refused(RuntimeError):
    """A prerequisite failed; nothing was activated."""


async def migration_applied(conn: AsyncConnection) -> bool:
    """``0002_shadow_lab`` applied — the tables and the column the Lab needs."""
    for table in REQUIRED_TABLES:
        if await conn.scalar(text("SELECT to_regclass(:name)"), {"name": table}) is None:
            return False
    column = await conn.scalar(
        text(
            "SELECT 1 FROM information_schema.columns WHERE table_name = 'signal_outcomes' "
            "AND column_name = 'tracking_state'"
        )
    )
    return column is not None


async def purpose_column_present(conn: AsyncConnection) -> bool:
    """``0010_strategy_purpose`` applied — the column every mode reads."""
    column = await conn.scalar(
        text(
            "SELECT 1 FROM information_schema.columns WHERE table_name = 'strategy_versions' "
            "AND column_name = 'purpose'"
        )
    )
    return column is not None


async def record_event(conn: AsyncConnection, level: str, event: str, message: str) -> None:
    """Every run leaves a ``system_events`` row, activation or refusal alike."""
    await conn.execute(
        text(
            "INSERT INTO system_events (id, created_at, level, component, event, message) "
            "VALUES (gen_random_uuid(), now(), CAST(:level AS event_severity), "
            "'activate_strategy_version', :event, :message)"
        ),
        {"level": level, "event": event, "message": message[:1000]},
    )


async def load_row(conn: AsyncConnection, key: str, version: str) -> Any:
    """The ``strategy_versions`` row for ``(strategies.key, version)``, or ``None``."""
    return (
        await conn.execute(
            text(
                "SELECT v.id, v.strategy_id, v.status, v.activated_at, v.code_ref, "
                "v.default_parameters, v.parameters_schema, v.params_format, v.purpose "
                "FROM strategy_versions v JOIN strategies s ON s.id = v.strategy_id "
                "WHERE s.key = :key AND v.version = :version"
            ),
            {"key": key, "version": version},
        )
    ).first()


async def next_free_version(conn: AsyncConnection, strategy_id: Any) -> str:
    """``max(v<n>) + 1`` over every version the strategy already has — a paper
    line must not collide with a supersede's successor (or the other way round)."""
    versions = (
        await conn.execute(
            text("SELECT version FROM strategy_versions WHERE strategy_id = :strategy_id"),
            {"strategy_id": strategy_id},
        )
    ).scalars()
    numbers = [int(m.group(1)) for v in versions if (m := VERSION_RE.fullmatch(v)) is not None]
    if not numbers:
        raise Refused("cannot derive the next version: no 'v<n>' version exists for this strategy")
    return f"v{max(numbers) + 1}"
