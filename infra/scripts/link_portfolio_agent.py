#!/usr/bin/env python3
"""Link a `purpose = paper` strategy version to a wallet — the `agents` act.

    uv run python infra/scripts/link_portfolio_agent.py \\
        --org-slug ever --strategy momentum --version v3 --dry-run
    uv run python infra/scripts/link_portfolio_agent.py \\
        --org-slug ever --strategy momentum --version v3 --yes \\
        --actor operator@example.com

``docs/ACTIVATION.md`` §8a measured the root cause of "154 sinais paper, 0
propostas" on 2026-09-08: the bridge (``bridge_screen._agent_for``) only
admits a signal whose ``strategy_version_id`` is run by an **enabled**
``agents`` row inside the target wallet, and nothing in the product writes
that row — activating a version (``activate_strategy_version.py
--paper-line``) does not create it. §8a ran the INSERT as raw SQL, by hand,
inside a manually-typed transaction. This script is that same act, made
repeatable and pre-checked, on the same audited pattern as
``link_portfolio_risk_profile.py``: every check runs and prints without
``--yes``; nothing is written without it; the INSERT and its ``audit_logs``
row commit or roll back together. The checks themselves live in
:mod:`link_portfolio_agent_plan` (kept apart so this file stays under the
350-line budget); this module is the write, the transaction and the CLI.

**It changes no risk limit and takes no trading decision.** It only tells the
bridge which wallet a strategy version's `purpose = paper` signals may reach —
the allocation itself (whether to link at all, and which version) stays
Everton's call, made in the terminal by typing ``--yes``. Nothing here
flips ``ENABLE_PAPER_AUTONOMY``; that switch is a deploy-time env var and is
untouched by this script on purpose (docs/ACTIVATION.md passo 8).

**Long-only by construction.** ``paper_v1`` is SPOT without borrow
(``max_leverage = 1``), and ``bridge_screen._geometry_reason`` already refuses
any non-``long`` signal by name (``direction_unsupported``). Leaving the
column at its schema default (``{long,short}``) would let the wallet queue
signals the engine refuses later — noise in the funnel, not an extra gate — so
this script always writes ``allowed_directions = ARRAY['long']``.

Connects with ``DATABASE_URL_MIGRATIONS`` (the owner DSN of the ``ops``
service), like ``infra/scripts/seed.py`` and
``infra/scripts/activate_strategy_version.py``.
"""

from __future__ import annotations

import argparse
import asyncio
import getpass
import json
import re
import socket
import uuid
from typing import Any

from link_portfolio_agent_plan import ALLOWED_DIRECTIONS, Plan, Refused, describe, plan_link
from seed import migration_url
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection, create_async_engine

from hunter_core.domain.types import uuid7

ACTION_CREATED = "agent.created"
ACTION_REACTIVATED = "agent.reactivated"
ENTITY = "agent"


async def write_link(conn: AsyncConnection, plan: Plan, *, actor: str | None) -> uuid.UUID:
    """The ``INSERT``/``UPDATE`` and its ``audit_logs`` row, same transaction.

    ``set_config`` rather than a literal ``SET LOCAL`` for the same reason as
    ``link_portfolio_risk_profile.write_link``: ``agents`` and ``audit_logs``
    are both ``FORCE ROW LEVEL SECURITY``.
    """
    await conn.execute(
        text("SELECT set_config('app.current_org', :org, true)"),
        {"org": str(plan.organization_id)},
    )
    metadata: dict[str, Any] = {
        "script": "infra/scripts/link_portfolio_agent.py",
        "strategy": plan.strategy_key,
        "version": plan.version,
        "actor_input": actor,
        "hostname": socket.gethostname(),
        "os_user": getpass.getuser(),
        "task": "T4.72",
    }
    if plan.reactivating:
        agent_id = plan.existing_agent_id
        assert agent_id is not None
        updated = (
            await conn.execute(
                text(
                    "UPDATE agents SET status = 'enabled', updated_at = now() "
                    "WHERE id = :id AND organization_id = :org "
                    "AND status IS NOT DISTINCT FROM :before RETURNING id"
                ),
                {"id": agent_id, "org": plan.organization_id, "before": plan.existing_status},
            )
        ).one_or_none()
        if updated is None:
            raise Refused(
                f"agent {agent_id} no longer has status {plan.existing_status!r}: someone "
                "changed it between the read and the write. Nothing was written; re-run."
            )
        action = ACTION_REACTIVATED
        after: dict[str, Any] = {"status": "enabled"}
        before: dict[str, Any] = {"status": plan.existing_status}
    else:
        agent_id = uuid7()
        await conn.execute(
            text(
                "INSERT INTO agents (id, organization_id, workspace_id, portfolio_id, name, "
                "strategy_version_id, uses_custom_params, status, allowed_directions, "
                "market_filter) VALUES (:id, :org, :workspace, :portfolio, :name, :version, "
                "false, 'enabled', :directions, '{}'::jsonb)"
            ),
            {
                "id": agent_id,
                "org": plan.organization_id,
                "workspace": plan.workspace_id,
                "portfolio": plan.portfolio_id,
                "name": plan.agent_name,
                "version": plan.strategy_version_id,
                "directions": list(ALLOWED_DIRECTIONS),
            },
        )
        action = ACTION_CREATED
        after = {
            "name": plan.agent_name,
            "strategy_version_id": str(plan.strategy_version_id),
            "portfolio_id": str(plan.portfolio_id),
            "status": "enabled",
            "allowed_directions": list(ALLOWED_DIRECTIONS),
        }
        before = {}
    await conn.execute(
        text(
            "INSERT INTO audit_logs (id, created_at, organization_id, actor_type, actor_id, "
            "action, entity_type, entity_id, before, after, metadata) VALUES (:id, now(), "
            ":org, 'system', NULL, :action, :entity, :entity_id, CAST(:before AS jsonb), "
            "CAST(:after AS jsonb), CAST(:metadata AS jsonb))"
        ),
        {
            "id": uuid7(),
            "org": plan.organization_id,
            "action": action,
            "entity": ENTITY,
            "entity_id": agent_id,
            "before": json.dumps(before),
            "after": json.dumps(after),
            "metadata": json.dumps(metadata),
        },
    )
    return agent_id


async def run(args: argparse.Namespace) -> int:
    engine = create_async_engine(migration_url(), connect_args={"statement_cache_size": 0})
    try:
        async with engine.connect() as conn:
            transaction = await conn.begin()
            try:
                plan = await plan_link(
                    conn,
                    org_slug=args.org_slug,
                    strategy_key=args.strategy,
                    version=args.version,
                    name=args.name,
                )
                if plan.already_enabled:
                    await transaction.rollback()
                    print(
                        f"agent {plan.existing_agent_id} already status=enabled for "
                        f"{plan.strategy_key} {plan.version} in wallet {plan.portfolio_id}; "
                        "nothing to do"
                    )
                    return 0
                for line in describe(plan, written=args.yes):
                    print(line)
                if not args.yes:
                    await transaction.rollback()
                    print("no --yes: nothing written. Re-run with --yes to link.")
                    return 0
                agent_id = await write_link(conn, plan, actor=args.actor)
                await transaction.commit()
                print(f"linked — agent {agent_id}, reactivated: {plan.reactivating}")
            except Refused:
                await transaction.rollback()
                raise
            print("audit_logs: one row written in the same transaction")
            return 0
    except Refused as refusal:
        print(f"REFUSED: {refusal}")
        return 1
    finally:
        await engine.dispose()


_ACTOR_INPUT = re.compile(r"^[ -~]{1,120}$")


def _actor_input(raw: str) -> str:
    """Bounded, printable free text — never an identity (``actor_type`` stays
    ``system``); same convention as ``link_portfolio_risk_profile.py``."""
    if not _ACTOR_INPUT.fullmatch(raw):
        raise argparse.ArgumentTypeError(
            "--actor must be printable ASCII, 1-120 characters (it is recorded unverified)"
        )
    return raw


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--org-slug", required=True, help="organizations.slug")
    parser.add_argument("--strategy", required=True, help="strategies.key, e.g. momentum")
    parser.add_argument("--version", required=True, help="strategy_versions.version, e.g. v3")
    parser.add_argument(
        "--name", default=None, help="agents.name (default: '<key> <version> (paper)')"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="run every check and write nothing — what happens without --yes anyway",
    )
    parser.add_argument("--yes", action="store_true", help="write the link and its audit row")
    parser.add_argument(
        "--actor",
        default=None,
        type=_actor_input,
        help=(
            "who asked for this; recorded UNVERIFIED in audit_logs.metadata.actor_input "
            "next to hostname/os_user (never actor_id) — printable ASCII, at most 120 chars"
        ),
    )
    args = parser.parse_args()
    if args.dry_run and args.yes:
        parser.error("--dry-run and --yes contradict each other; pass one")
    return asyncio.run(run(args))


if __name__ == "__main__":
    raise SystemExit(main())
