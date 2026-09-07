"""Tenant-scoped repository base — the code half of the double isolation.

CLAUDE.md: "Tenant isolation is double: tenant-scoped repositories in code AND
Row Level Security in Postgres." The two halves fail differently and that is the
point — RLS is what stops a query nobody reviewed, and the explicit
``organization_id`` predicate here is what stops a transaction that forgot to
set ``app.current_org`` from *silently* reading nothing and being interpreted as
"the wallet has no positions".

:meth:`TenantRepository.require_tenant_context` makes that second failure loud:
before the first tenant read of a unit of work, it asks Postgres which
organization this transaction declared, and refuses when the answer is missing
or is a different one. Without it, a ledger built outside a ``tenant_session``
would compute an equity of zero from zero visible rows — a number the risk
engine would then size against.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import text

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

_CURRENT_ORG = text("SELECT current_setting('app.current_org', true)")


class TenantContextMissing(RuntimeError):
    """The transaction has no ``app.current_org``, or it names another tenant."""


class TenantRepository:
    """Data access bound to one organization, inside one caller-owned transaction.

    Never commits and never rolls back: the surrounding ``tenant_session`` owns
    the unit of work, which is what lets the opening write six tables in one
    commit (DATABASE.md §18.2).
    """

    __slots__ = ("_organization_id", "_session")

    def __init__(self, session: AsyncSession, organization_id: uuid.UUID) -> None:
        self._session = session
        self._organization_id = organization_id

    @property
    def session(self) -> AsyncSession:
        return self._session

    @property
    def organization_id(self) -> uuid.UUID:
        return self._organization_id

    async def require_tenant_context(self) -> None:
        """Refuse a transaction whose RLS setting is absent or is another tenant."""
        declared = await self._session.scalar(_CURRENT_ORG)
        if not declared:
            raise TenantContextMissing(
                "app.current_org is not set in this transaction; every RLS policy would "
                "return zero rows and the ledger would read that as an empty wallet. Open "
                "the transaction with hunter_core.db.session.tenant_session()"
            )
        if uuid.UUID(declared) != self._organization_id:
            raise TenantContextMissing(
                f"this transaction declared organization {declared} but the repository is "
                f"scoped to {self._organization_id}"
            )
