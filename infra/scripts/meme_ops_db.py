"""Shared plumbing of the meme Lab's audited operator scripts (T4.16):
the owner's connection and the ``system_events`` row every run leaves.

``infra/scripts/activate_strategy_version.py`` has the same two pieces in
``hunter_strategy_worker.activation_db``; a meme script must not import the
strategy worker for them, so they are spelled here once, byte for byte the
same rule: ``DATABASE_URL_MIGRATIONS`` (direct, never the pooler) on asyncpg,
and an audit row with the component's own name.
"""

from __future__ import annotations

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
    conn: Connection, *, component: str, level: str, event: str, message: str
) -> None:
    """Every applied run leaves a ``system_events`` row — the audit the brief asks for."""
    await conn.execute(
        text(
            "INSERT INTO system_events (id, created_at, level, component, event, message) "
            "VALUES (gen_random_uuid(), now(), CAST(:level AS event_severity), :component, "
            ":event, :message)"
        ),
        {"level": level, "component": component, "event": event, "message": message[:1000]},
    )
