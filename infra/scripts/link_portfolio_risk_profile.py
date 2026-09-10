#!/usr/bin/env python3
"""Point a paper wallet at the persisted ``paper_v1`` risk profile — audited.

    uv run python infra/scripts/link_portfolio_risk_profile.py \\
        --portfolio 01a07a1e-f6ae-7366-a7fe-ab3d9c83d488 --preset paper_v1 --dry-run
    uv run python infra/scripts/link_portfolio_risk_profile.py \\
        --portfolio 01a07a1e-f6ae-7366-a7fe-ab3d9c83d488 --preset paper_v1 --yes \\
        --actor operator@example.com

``docs/RISK_ENGINE.md`` §2 calls the persisted row "the single source" of the
wallet's profile, and ``portfolios.risk_profile_id`` is how a wallet names it.
Nothing in the product sets that column: ``open_paper_wallet`` accepts a
``risk_profile_id`` and every production caller leaves it ``None``, and the
default profile an organization gets at sign-up
(``apps/api/hunter_api/services/organizations.py``) lands on
``workspaces.default_risk_profile_id``, which is a different column on a
different table. So the link is an operator act, like opening the wallet — and
this is its script.

**It changes no limit, and refuses to be the place where one changes.** The
only accepted ``--preset`` is ``paper_v1``: pointing the wallet at
``conservative``/``balanced``/``aggressive`` would move every ceiling the engine
enforces, and "documente e me apresente antes de alterar os limites" makes that
a question for Everton, not a flag on a script. Before writing anything it
re-validates the stored row into :data:`hunter_risk.limits.PAPER_V1` and refuses
if a single field differs — a wallet linked to a divergent row would be a limit
change made by nobody, which is what ``seed_paper._refuse_diverging_preset``
already refuses on the seed side.

**What the engine reads today is the code constant, not this column.**
``hunter_core.admission.admit`` takes ``limits: RiskLimits = PAPER_V1`` and
``execution-worker``'s ``admission_cycle`` never passes the argument, so the row
this script links is the **declared** source while the constant is the
**enforced** one; the two are proved equal by
``test_the_seeded_paper_profile_has_exactly_one_source`` and by the round-trip
test in ``infra/scripts/tests/test_link_portfolio_risk_profile.py``. Making
``admit`` read the wallet's profile is T3.69b, and it is not this script.

Connects with ``DATABASE_URL_MIGRATIONS`` (the owner DSN of the ``ops`` service,
never the pooler), like ``infra/scripts/seed.py`` and
``infra/scripts/activate_strategy_version.py``. One transaction: the read, the
``UPDATE`` and the ``audit_logs`` row commit or roll back together. Without
``--yes`` nothing is written — the preview is the default.
"""

from __future__ import annotations

import argparse
import asyncio
import getpass
import json
import socket
import uuid
from dataclasses import dataclass
from typing import Any

from seed import migration_url
from sqlalchemy import Row, text
from sqlalchemy.ext.asyncio import AsyncConnection, create_async_engine

from hunter_core.domain.types import uuid7
from hunter_risk.limits import PAPER_V1, RiskLimits

PRESET = "paper_v1"
"""The only preset this script links. See the module docstring."""

ACTION = "portfolio.risk_profile_linked"
ENTITY = "portfolio"


class Refused(Exception):
    """A refusal with a reason an operator can act on. Nothing was written."""


@dataclass(frozen=True)
class Plan:
    """What the write would do — printed before it happens, and after."""

    portfolio_id: uuid.UUID
    organization_id: uuid.UUID
    portfolio_name: str
    profile_id: uuid.UUID
    profile_name: str
    before: uuid.UUID | None
    replacing: bool

    @property
    def already_linked(self) -> bool:
        return self.before == self.profile_id


async def _portfolio(conn: AsyncConnection, portfolio_id: uuid.UUID) -> Row[Any]:
    row = (
        await conn.execute(
            text(
                "SELECT id, organization_id, name, type::text AS type, is_arena, "
                "risk_profile_id FROM portfolios WHERE id = :id"
            ),
            {"id": portfolio_id},
        )
    ).one_or_none()
    if row is None:
        raise Refused(
            f"no portfolio {portfolio_id} is visible to this connection. Check the id, and "
            "check that this is the owner DSN (DATABASE_URL_MIGRATIONS, the `ops` service): "
            "portfolios is FORCE ROW LEVEL SECURITY, so a role without app.current_org set "
            "sees no rows at all rather than an error"
        )
    if row.type != "paper" or row.is_arena:
        raise Refused(
            f"portfolio {portfolio_id} is type={row.type} is_arena={row.is_arena}; this script "
            "links the principal paper wallet only (live is Fase 4, ENABLE_LIVE_TRADING=false)"
        )
    return row


async def _profile(conn: AsyncConnection, preset: str) -> Row[Any]:
    row = (
        await conn.execute(
            text(
                "SELECT id, name, preset::text AS preset, limits FROM risk_profiles "
                "WHERE organization_id IS NULL AND preset = :preset"
            ),
            {"preset": preset},
        )
    ).one_or_none()
    if row is None:
        raise Refused(
            f"there is no system risk_profiles row with preset '{preset}'. Seed it first: "
            "`python infra/scripts/seed.py --only risk_profiles --dry-run` and then with "
            "--yes (docs/ACTIVATION.md §9). Nothing was written."
        )
    return row


def refuse_diverging_profile(limits: dict[str, Any]) -> RiskLimits:
    """The stored row must be ``PAPER_V1`` itself, field by field, or no link.

    ``RiskLimits.model_validate`` alone already refuses a JSON *number* where the
    profile carries a fraction (``RiskModel._refuse_float``: ``Decimal("0.0025")
    != Decimal(0.0025)``), so a row whose limits were re-typed by hand as floats
    never reaches the comparison below.
    """
    try:
        stored = RiskLimits.model_validate(limits)
    except Exception as invalid:
        raise Refused(
            f"the stored {PRESET} limits do not validate as RiskLimits ({invalid}). Linking a "
            "wallet to a row the engine cannot read would be a profile nobody can enforce."
        ) from invalid
    if stored != PAPER_V1:
        differing = sorted(
            field
            for field in PAPER_V1.model_dump(mode="json")
            if getattr(stored, field) != getattr(PAPER_V1, field)
        )
        raise Refused(
            f"the stored {PRESET} limits differ from hunter_risk.limits.PAPER_V1 on: "
            f"{', '.join(differing)}. Every limit in paper_v1 is Everton's and changing one is "
            "a question to him (docs/RISK_ENGINE.md §2), so this link is refused rather than "
            "quietly moving the wallet onto other numbers. Reconcile the row first."
        )
    return stored


async def plan_link(
    conn: AsyncConnection, *, portfolio_id: uuid.UUID, preset: str, replace: bool
) -> Plan:
    """Every check, no write. Raises :class:`Refused` with the reason."""
    if preset != PRESET:
        raise Refused(f"--preset {preset!r} is not linkable by this script; only {PRESET!r} is")
    wallet = await _portfolio(conn, portfolio_id)
    profile = await _profile(conn, preset)
    refuse_diverging_profile(dict(profile.limits))
    linked_elsewhere = wallet.risk_profile_id is not None and wallet.risk_profile_id != profile.id
    if linked_elsewhere and not replace:
        raise Refused(
            f"portfolio {portfolio_id} already points at risk_profile {wallet.risk_profile_id}, "
            f"not at {preset} ({profile.id}). Re-run with --replace if moving it is deliberate; "
            "a wallet's profile is not repointed by accident."
        )
    return Plan(
        portfolio_id=wallet.id,
        organization_id=wallet.organization_id,
        portfolio_name=wallet.name,
        profile_id=profile.id,
        profile_name=profile.name,
        before=wallet.risk_profile_id,
        replacing=linked_elsewhere,
    )


def describe(plan: Plan, *, written: bool) -> list[str]:
    """``before``/``after``, always both, whether or not anything was written."""
    verb = "linked" if written else "would link"
    return [
        f"portfolio {plan.portfolio_id} ({plan.portfolio_name})",
        f"  before: risk_profile_id = {plan.before}",
        f"  after:  risk_profile_id = {plan.profile_id} ({PRESET}, {plan.profile_name!r})",
        f"  {verb} — replacing an existing link: {plan.replacing}",
    ]


async def write_link(conn: AsyncConnection, plan: Plan, *, actor: str | None) -> None:
    """The ``UPDATE`` and its ``audit_logs`` row, in the caller's transaction.

    ``set_config('app.current_org', ..., true)`` rather than a literal ``SET
    LOCAL``: ``portfolios`` and ``audit_logs`` are both ``FORCE ROW LEVEL
    SECURITY``, so an owner that is not a superuser would write zero rows and
    report success without it (the ``risk_profiles`` bug of DATABASE.md §15.6,
    one table over). ``true`` is ``is_local`` — the setting dies with the
    transaction.
    """
    await conn.execute(
        text("SELECT set_config('app.current_org', :org, true)"),
        {"org": str(plan.organization_id)},
    )
    updated = (
        await conn.execute(
            text(
                "UPDATE portfolios SET risk_profile_id = :profile, updated_at = now() "
                "WHERE id = :portfolio AND risk_profile_id IS NOT DISTINCT FROM :before "
                "RETURNING risk_profile_id"
            ),
            {"profile": plan.profile_id, "portfolio": plan.portfolio_id, "before": plan.before},
        )
    ).one_or_none()
    if updated is None:
        raise Refused(
            f"portfolio {plan.portfolio_id} no longer carries risk_profile_id {plan.before}: "
            "someone changed it between the read and the write. Nothing was written; re-run "
            "the --dry-run and look again."
        )
    metadata: dict[str, Any] = {
        "script": "infra/scripts/link_portfolio_risk_profile.py",
        "preset": PRESET,
        "profile_name": plan.profile_name,
        "replaced": plan.replacing,
        "actor_input": actor,
        "hostname": socket.gethostname(),
        "os_user": getpass.getuser(),
    }
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
            "action": ACTION,
            "entity": ENTITY,
            "entity_id": plan.portfolio_id,
            "before": json.dumps({"risk_profile_id": str(plan.before) if plan.before else None}),
            "after": json.dumps({"risk_profile_id": str(plan.profile_id), "preset": PRESET}),
            "metadata": json.dumps(metadata),
        },
    )


async def run(args: argparse.Namespace) -> int:
    """Resolve, print, and — only with ``--yes`` — write. Returns the exit code."""
    engine = create_async_engine(migration_url(), connect_args={"statement_cache_size": 0})
    try:
        async with engine.connect() as conn:
            transaction = await conn.begin()
            try:
                plan = await plan_link(
                    conn, portfolio_id=args.portfolio, preset=args.preset, replace=args.replace
                )
                if plan.already_linked:
                    await transaction.rollback()
                    print(
                        f"portfolio {plan.portfolio_id} already points at {PRESET} "
                        f"({plan.profile_id}); nothing to do"
                    )
                    return 0
                for line in describe(plan, written=args.yes):
                    print(line)
                if not args.yes:
                    await transaction.rollback()
                    print("no --yes: nothing written. Re-run with --yes to link.")
                    return 0
                await write_link(conn, plan, actor=args.actor)
                await transaction.commit()
            except Refused:
                await transaction.rollback()
                raise
            print(f"audit_logs: one {ACTION} row written in the same transaction")
            return 0
    except Refused as refusal:
        print(f"REFUSED: {refusal}")
        return 1
    finally:
        await engine.dispose()


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--portfolio", required=True, type=uuid.UUID, help="portfolios.id")
    parser.add_argument(
        "--preset",
        required=True,
        choices=[PRESET],
        help="the system risk_profiles preset to link (only paper_v1; see the module docstring)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="run every check and write nothing — what happens without --yes anyway",
    )
    parser.add_argument("--yes", action="store_true", help="write the link and its audit row")
    parser.add_argument(
        "--replace",
        action="store_true",
        help="required when the wallet already points at another risk profile",
    )
    parser.add_argument(
        "--actor", default=None, help="who asked for this; recorded in audit_logs.metadata"
    )
    args = parser.parse_args()
    if args.dry_run and args.yes:
        parser.error("--dry-run and --yes contradict each other; pass one")
    return asyncio.run(run(args))


if __name__ == "__main__":
    raise SystemExit(main())
