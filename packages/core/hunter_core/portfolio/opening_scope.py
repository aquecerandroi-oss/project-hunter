"""``verify_scope`` — the opening's own post-write, pre-commit tenancy check.

Split out of ``opening.py`` (file-size budget, not a change of ownership):
this is what :func:`hunter_core.portfolio.opening.open_paper_wallet` calls,
by default, right before it returns.

``hunter_worker`` (the only role that ever opens a wallet — there is no HTTP
route for it) runs ``BYPASSRLS`` (0007_paper_roles, DATABASE.md §19.6):
Postgres itself enforces nothing about which tenant a row this role inserts
belongs to. Every write the opening makes already sets ``organization_id``
explicitly (the repositories never derive it from RLS), so in the absence of
a bug this always passes — it is a defense-in-depth re-check, not the primary
mechanism (security review of ``open_paper_wallet.py``, S3b), and it is cheap
enough to run once per opening, ever, per organization.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import text

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


class ScopeViolation(Exception):
    """A row this opening just wrote does not belong to the organization it
    was scoped to — or a row the opening must have written is missing.

    Only reachable with ``verify_scope=True`` (the default). Raised *before*
    the caller may commit, so ``tenant_session``/``role_session`` roll back
    the whole transaction on the way out: the wallet, its lock row, its
    anchor and the first point of the curve are undone together, never left
    half-scoped.
    """


_SCOPE_TABLES: tuple[tuple[str, str], ...] = (
    ("portfolios", "id"),
    ("portfolio_risk_state", "portfolio_id"),
    ("portfolio_currency_anchor", "portfolio_id"),
    ("portfolio_equity_snapshots", "portfolio_id"),
)
"""Table and the column that names ``portfolio_id`` in it — every tenant table
the opening writes to except ``audit_logs`` (checked separately, by
``entity_id``) and ``fx_observations`` (global, checked by existence).
``noqa: S608`` at each use below: both fields are drawn from this literal
tuple, never from caller input."""


async def verify_scope(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID,
    portfolio_id: uuid.UUID,
    fx_observation_id: uuid.UUID,
) -> None:
    """Re-read, by ``organization_id``, every row the opening just wrote.

    ``fx_observations`` has no ``organization_id`` at all — it is global and
    immutable (DATABASE.md §18.2) — so its check is existence, not tenancy:
    the observation this wallet's anchor and first equity point both name
    must still be there.
    """
    for table, key_column in _SCOPE_TABLES:
        row = (
            await session.execute(
                text(
                    f"SELECT count(*) AS total, "  # noqa: S608
                    "count(*) FILTER (WHERE organization_id = :org) AS in_scope "
                    f"FROM {table} WHERE {key_column} = :portfolio_id"
                ),
                {"org": organization_id, "portfolio_id": portfolio_id},
            )
        ).one()
        if row.total == 0:
            raise ScopeViolation(
                f"{table}: expected a row for portfolio {portfolio_id}, found none"
            )
        if row.in_scope != row.total:
            raise ScopeViolation(
                f"{table}: {row.total - row.in_scope} of {row.total} row(s) for portfolio "
                f"{portfolio_id} do not belong to organization {organization_id}"
            )

    audited = (
        await session.execute(
            text(
                "SELECT count(*) AS total, "
                "count(*) FILTER (WHERE organization_id = :org) AS in_scope "
                "FROM audit_logs WHERE entity_id = :portfolio_id AND action = 'portfolio.opened'"
            ),
            {"org": organization_id, "portfolio_id": portfolio_id},
        )
    ).one()
    if audited.total == 0:
        raise ScopeViolation(f"audit_logs: no 'portfolio.opened' row for {portfolio_id}")
    if audited.in_scope != audited.total:
        raise ScopeViolation(
            f"audit_logs: {audited.total - audited.in_scope} of {audited.total} "
            f"'portfolio.opened' row(s) for {portfolio_id} do not belong to organization "
            f"{organization_id}"
        )

    observed = await session.scalar(
        text("SELECT 1 FROM fx_observations WHERE id = :id"), {"id": fx_observation_id}
    )
    if observed is None:
        raise ScopeViolation(
            f"fx_observations: {fx_observation_id}, named by this opening's anchor and its "
            "first equity point, does not exist"
        )
