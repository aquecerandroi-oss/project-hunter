"""Shared plumbing of the meme Lab's audited operator scripts (T4.16):
the owner's connection and the ``system_events`` row every run leaves.

``infra/scripts/activate_strategy_version.py`` has the same two pieces in
``hunter_strategy_worker.activation_db``; a meme script must not import the
strategy worker for them, so they are spelled here once, byte for byte the
same rule: ``DATABASE_URL_MIGRATIONS`` (direct, never the pooler) on asyncpg,
and an audit row with the component's own name.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any, Protocol

from sqlalchemy import text

from hunter_core.settings import Settings

__all__ = ["Connection", "migration_url", "record_event"]


class Connection(Protocol):
    """What the scripts need from a connection: ``execute`` (an ``AsyncConnection`` fits)."""

    async def execute(self, statement: Any, parameters: Any = None, /) -> Any: ...


def migration_url() -> str:
    """``DATABASE_URL_MIGRATIONS`` on the asyncpg driver (as ``seed.py`` does)."""
    secret = Settings().database_url_migrations
    if secret is None or not secret.get_secret_value():
        raise SystemExit("DATABASE_URL_MIGRATIONS is not configured")
    url = secret.get_secret_value()
    if url.startswith("postgresql+"):
        return url
    return url.replace("postgresql://", "postgresql+asyncpg://", 1)


async def record_event(
    conn: Connection,
    *,
    component: str,
    level: str,
    event: str,
    message: str,
    data: Mapping[str, Any] | None = None,
) -> str | None:
    """Every applied run leaves a ``system_events`` row — the audit the brief asks for.

    ``data`` (T4.35) is the structured half the free-text ``message`` never
    carried: a caller that wants its payload readable by a script later (not
    just by a human reading the message) passes it here and gets the row's
    ``id`` back — ``None`` against any of this repo's fake connections (none
    of them model ``RETURNING``'s ``.scalars()``, and each has its own shape),
    never a crash: an event this call cannot confirm the id of is still an
    event worth writing.
    """
    result = await conn.execute(
        text(
            "INSERT INTO system_events (id, created_at, level, component, event, message, data) "
            "VALUES (gen_random_uuid(), now(), CAST(:level AS event_severity), :component, "
            ":event, :message, CAST(:data AS jsonb)) RETURNING id"
        ),
        {
            "level": level,
            "component": component,
            "event": event,
            "message": message[:1000],
            "data": json.dumps(data or {}),
        },
    )
    try:
        rows = result.scalars().all()
    except AttributeError:
        return None
    return None if not rows else str(rows[0])
