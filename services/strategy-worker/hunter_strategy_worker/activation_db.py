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
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine

from hunter_core.settings import Settings

__all__ = [
    "PURPOSE_LIVE",
    "PURPOSE_PAPER",
    "PURPOSE_RESEARCH_ONLY",
    "REQUIRED_TABLES",
    "VERSION_RE",
    "Refused",
    "append_deprecation_note",
    "load_row",
    "migration_applied",
    "migration_url",
    "next_free_version",
    "open_paper_exposure",
    "purpose_column_present",
    "record_event",
    "record_failure",
]

REQUIRED_TABLES = ("shadow_episodes", "shadow_outbox")
VERSION_RE = re.compile(r"^v(\d+)$")
PURPOSE_RESEARCH_ONLY = "research_only"
PURPOSE_PAPER = "paper"
PURPOSE_LIVE = "live"


class Refused(RuntimeError):
    """A prerequisite failed; nothing was activated."""


def migration_url() -> str:
    """``DATABASE_URL_MIGRATIONS`` on the asyncpg driver (as ``seed.py`` does).

    One spelling for every ops script. It lived, byte for byte identical, in both
    ``activate_strategy_version.py`` and ``derive_variant.py``; two copies of the
    rule that decides *which connection writes a frozen version* is one copy too
    many, and the 350-line budget was what surfaced it (T3.26c).
    """
    secret = Settings().database_url_migrations
    if secret is None or not secret.get_secret_value():
        raise SystemExit("DATABASE_URL_MIGRATIONS is not configured")
    url = secret.get_secret_value()
    if url.startswith("postgresql+"):
        return url
    return url.replace("postgresql://", "postgresql+asyncpg://", 1)


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


async def record_failure(engine: AsyncEngine, level: str, event: str, message: str) -> None:
    """A fresh connection and transaction for the audit row (T3.15c).

    The one that failed may be aborted (a ``DBAPIError`` leaves Postgres
    refusing every further statement until the transaction ends), so the audit
    trail cannot share it — and by the time this runs, the caller's own ``async
    with conn.begin():`` has already rolled the failed attempt back on its own
    (an exception leaving that block always rolls it back), so nothing partial
    is ever committed alongside a refusal or an error (security review T3.15
    MEDIUM 5).
    """
    async with engine.connect() as conn, conn.begin():
        await record_event(conn, level, event, message)


async def load_row(conn: AsyncConnection, key: str, version: str) -> Any:
    """The ``strategy_versions`` row for ``(strategies.key, version)``, or ``None``."""
    return (
        await conn.execute(
            text(
                "SELECT v.id, v.strategy_id, v.status, v.activated_at, v.code_ref, "
                "v.default_parameters, v.parameters_schema, v.params_format, v.purpose, "
                "v.changelog "
                "FROM strategy_versions v JOIN strategies s ON s.id = v.strategy_id "
                "WHERE s.key = :key AND v.version = :version"
            ),
            {"key": key, "version": version},
        )
    ).first()


def append_deprecation_note(existing: str | None, note: str, *, now: datetime | None = None) -> str:
    """The ``changelog`` for a row moving to ``status = 'deprecated'`` — the
    existing value kept **verbatim**, with a dated line appended (T3.47c).

    A derived variant's analysable lineage (``derive_variant.py``'s
    ``derived_from=v<n> | overrides=...``, read back by
    ``infra/scripts/obsidian_strategy_pages.py``'s ``parse_parent_version``) lives
    in this same column, and it is the only place it lives — no other column
    freezes it. ``deprecate()`` and ``supersede()`` (retiring the row it
    replaces) used to overwrite ``changelog`` outright with the operator's
    verdict text, which silently erased that prefix on any row that had one
    (found by T3.47b, CONCERN 3). Both now build the new value through this
    function instead of assigning a bare string, so the frozen prefix a variant
    was born with survives every later status change.
    """
    timestamp = (now or datetime.now(UTC)).isoformat()
    return f"{existing or ''}\n[deprecated {timestamp}] {note}"


async def open_paper_exposure(conn: AsyncConnection, version_id: Any) -> list[str]:
    """Reasons a ``purpose = 'paper'`` version still has skin in the game.

    Shared by ``deprecate()`` and ``supersede()`` (T3.39b review, ALTA-1/ALTA-2:
    the two writers that may retire the paper line must refuse on the same
    evidence, or one of them becomes the back door the other closes).

    ``positions.agent_id`` is never written by the execution worker
    (``hunter_execution_worker.positions.open_position``'s ``INSERT`` has no
    such column — confirmed by reading it, not assumed); the link production
    actually carries is ``positions.metadata->>'proposal_id'`` — the same value
    ``orders.proposal_id`` holds for the order that opened it — to
    ``trade_proposals.agent_id`` to ``agents.strategy_version_id``, the same
    three-table chain ``ddl/paper.py``'s own consistency check joins
    (``orders o JOIN trade_proposals p ON p.id = o.proposal_id``). ``status <>
    'closed' AND NOT is_residual`` is the project's own definition of "a live
    position" (``hunter_execution_worker.positions.load_open_position``): dust
    no price makes sellable is not exposure a deprecation needs to protect.

    The second reason is a ``shadow_episodes`` slot still tracking an entry
    (``open_outcome_signal_id IS NOT NULL``) — a research row with a signal in
    flight, independent of any wallet.
    """
    reasons: list[str] = []
    open_positions = await conn.scalar(
        text(
            "SELECT count(DISTINCT p.id) FROM positions p "
            "JOIN orders o ON o.proposal_id = (p.metadata->>'proposal_id')::uuid "
            "JOIN trade_proposals tp ON tp.id = o.proposal_id "
            "JOIN agents a ON a.id = tp.agent_id "
            "WHERE a.strategy_version_id = :version_id "
            "AND p.status <> 'closed' AND NOT p.is_residual"
        ),
        {"version_id": version_id},
    )
    if open_positions:
        reasons.append(f"{open_positions} open position(s) via its agents")
    open_slots = await conn.scalar(
        text(
            "SELECT count(*) FROM shadow_episodes WHERE strategy_version_id = :version_id "
            "AND open_outcome_signal_id IS NOT NULL"
        ),
        {"version_id": version_id},
    )
    if open_slots:
        reasons.append(f"{open_slots} shadow slot(s) tracking an open outcome")
    return reasons


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
