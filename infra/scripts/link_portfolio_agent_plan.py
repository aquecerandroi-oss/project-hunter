"""The read half of ``link_portfolio_agent.py`` — every check, no write.

Split out of the script itself only to keep it under the 350-line budget
(``infra/scripts/check_file_size.py``): this module answers "what would the
link do, and is it even allowed", and ``link_portfolio_agent.py`` is left with
the write, the CLI and the transaction. See that module's docstring for the
why of the act itself.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any

from sqlalchemy import Row, text
from sqlalchemy.ext.asyncio import AsyncConnection

ALLOWED_DIRECTIONS = ("long",)
"""The only directions this script ever writes — see the module docstring of
``link_portfolio_agent.py`` ("Long-only by construction")."""


class Refused(Exception):
    """A refusal with a reason an operator can act on. Nothing was written."""


@dataclass(frozen=True)
class Plan:
    """What the write would do — printed before it happens, and after."""

    organization_id: uuid.UUID
    workspace_id: uuid.UUID
    portfolio_id: uuid.UUID
    portfolio_name: str
    strategy_version_id: uuid.UUID
    strategy_key: str
    version: str
    agent_name: str
    existing_agent_id: uuid.UUID | None
    existing_status: str | None

    @property
    def already_enabled(self) -> bool:
        return self.existing_status == "enabled"

    @property
    def reactivating(self) -> bool:
        return self.existing_agent_id is not None and not self.already_enabled


async def _organization(conn: AsyncConnection, slug: str) -> Row[Any]:
    row = (
        await conn.execute(
            text("SELECT id, slug FROM organizations WHERE slug = :slug"), {"slug": slug}
        )
    ).one_or_none()
    if row is None:
        raise Refused(f"no organization with slug {slug!r}")
    return row


async def _workspace(conn: AsyncConnection, organization_id: uuid.UUID) -> Row[Any]:
    rows = (
        await conn.execute(
            text(
                "SELECT id, name FROM workspaces WHERE organization_id = :org ORDER BY created_at"
            ),
            {"org": organization_id},
        )
    ).all()
    if not rows:
        raise Refused(f"organization {organization_id} has no workspace")
    if len(rows) > 1:
        raise Refused(
            f"organization {organization_id} has {len(rows)} workspaces; this script only "
            "handles the single-workspace case (pass --workspace to pick one explicitly — "
            "not implemented, add it if this ever fires)"
        )
    return rows[0]


async def _portfolio(conn: AsyncConnection, organization_id: uuid.UUID) -> Row[Any]:
    rows = (
        await conn.execute(
            text(
                "SELECT id, name FROM portfolios WHERE organization_id = :org "
                "AND type = 'paper' AND NOT is_arena ORDER BY created_at"
            ),
            {"org": organization_id},
        )
    ).all()
    if not rows:
        raise Refused(f"organization {organization_id} has no principal paper wallet")
    if len(rows) > 1:
        raise Refused(
            f"organization {organization_id} has {len(rows)} principal paper wallets; this "
            "script refuses to guess which one (pass --portfolio — not implemented, add it "
            "if this ever fires)"
        )
    return rows[0]


async def _strategy_version(conn: AsyncConnection, *, key: str, version: str) -> Row[Any]:
    row = (
        await conn.execute(
            text(
                "SELECT v.id, v.status::text AS status, v.purpose FROM strategy_versions v "
                "JOIN strategies s ON s.id = v.strategy_id "
                "WHERE s.key = :key AND v.version = :version"
            ),
            {"key": key, "version": version},
        )
    ).one_or_none()
    if row is None:
        raise Refused(f"no strategy_versions row for {key} {version}")
    if row.purpose != "paper":
        raise Refused(
            f"{key} {version} has purpose={row.purpose!r}, not 'paper' — link only a version "
            "activated with --paper-line (docs/ACTIVATION.md §6-7)"
        )
    if row.status != "active":
        raise Refused(f"{key} {version} has status={row.status!r}, not 'active'")
    return row


async def _existing_agent(
    conn: AsyncConnection,
    *,
    organization_id: uuid.UUID,
    portfolio_id: uuid.UUID,
    version_id: uuid.UUID,
) -> Row[Any] | None:
    return (
        await conn.execute(
            text(
                "SELECT id, status::text AS status FROM agents WHERE organization_id = :org "
                "AND portfolio_id = :pf AND strategy_version_id = :version "
                "AND deleted_at IS NULL ORDER BY created_at LIMIT 1"
            ),
            {"org": organization_id, "pf": portfolio_id, "version": version_id},
        )
    ).one_or_none()


async def plan_link(
    conn: AsyncConnection, *, org_slug: str, strategy_key: str, version: str, name: str | None
) -> Plan:
    """Every check, no write. Raises :class:`Refused` with the reason."""
    org = await _organization(conn, org_slug)
    workspace = await _workspace(conn, org.id)
    portfolio = await _portfolio(conn, org.id)
    strategy_version = await _strategy_version(conn, key=strategy_key, version=version)
    existing = await _existing_agent(
        conn, organization_id=org.id, portfolio_id=portfolio.id, version_id=strategy_version.id
    )
    return Plan(
        organization_id=org.id,
        workspace_id=workspace.id,
        portfolio_id=portfolio.id,
        portfolio_name=portfolio.name,
        strategy_version_id=strategy_version.id,
        strategy_key=strategy_key,
        version=version,
        agent_name=name or f"{strategy_key} {version} (paper)",
        existing_agent_id=existing.id if existing is not None else None,
        existing_status=existing.status if existing is not None else None,
    )


def describe(plan: Plan, *, written: bool) -> list[str]:
    verb = "linking" if written else "would link"
    return [
        f"agent for {plan.strategy_key} {plan.version} -> wallet {plan.portfolio_id} "
        f"({plan.portfolio_name})",
        f"  existing: id={plan.existing_agent_id} status={plan.existing_status}",
        f"  allowed_directions = {list(ALLOWED_DIRECTIONS)}",
        f"  {verb} — reactivating an existing row: {plan.reactivating}",
    ]
