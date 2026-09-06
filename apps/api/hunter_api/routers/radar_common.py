"""One connection per request, never two — the shared entry point of the four
T2.6 analysis routers (radar, opportunities, anomalies, regime).

**The invariant.** A request served by these routers holds **at most one**
pooled database connection at any instant. It is not a style preference: the
engine is built with ``db_pool_size=5`` + ``db_max_overflow=5``
(``hunter_core/settings.py``), so ten concurrent requests that each hold two
connections deadlock the whole process — every request owns one and waits 30s
(``QueuePool``'s default ``pool_timeout``) for a second that only another
waiter can release. Nothing recovers until the timeouts fire, and what the
caller finally gets is a ``sqlalchemy.exc.TimeoutError``.

That is exactly what MF-1 (security-reviewer, 2026-09-06) found: the routers
took ``PrincipalSession`` as a ``Depends`` — which opens the transaction while
*resolving the dependency*, i.e. before the handler body runs and holds it
until the response is assembled — and then called
``services/radar_org_derivation.py::load_org_derivation`` in the body, which
opens a second, tenant-scoped transaction. Two connections, for the whole
request, for every authenticated caller who passed ``org_id``.

**The fix** is the ordering below, and it is why these routers do not use
``deps.PrincipalSession``: derive the organization first — in a
``tenant_session`` that is opened *and closed*, returning its connection to
the pool — and only then open the caller's ``user_session``. A ``Depends``
cannot express "close before the next one opens" (FastAPI tears generator
dependencies down after the handler, not between dependencies), so the
sequence is an explicit ``async with`` in one place instead of being spelled
out, and re-derived, at each call site.

Opening the session here also closes the gap the previous revision recorded in
``.claude/state/notes-T2.6.md``: the transaction's first round trip (``SET
LOCAL ROLE``) now happens *inside* :func:`postgres_failures_as_503`, so a
Postgres outage at that instant is the honest 503 it always was, instead of
the generic 500 a failing dependency produces.
"""

from __future__ import annotations

import contextlib
import uuid
from dataclasses import dataclass
from typing import TYPE_CHECKING

from hunter_api.deps import get_session_factory
from hunter_api.repositories.radar_common import postgres_failures_as_503
from hunter_api.services.radar_org_derivation import load_org_derivation, resolve_optional_org
from hunter_core.db.session import user_session

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator

    from fastapi import Request
    from sqlalchemy.ext.asyncio import AsyncSession

    from hunter_api.auth.principal import Principal
    from hunter_api.services.radar_org_derivation import OrgDerivation

__all__ = ["AnalysisScope", "analysis_scope"]


@dataclass(frozen=True, slots=True)
class AnalysisScope:
    """What a T2.6 handler works with: the request's single open session and
    the per-organization derivation that was resolved *before* it.
    """

    session: AsyncSession
    org_derivation: OrgDerivation | None
    """``None`` when the request carried no ``org_id`` — absence of an
    organization context, never a claim that nothing is in position."""


@contextlib.asynccontextmanager
async def analysis_scope(
    request: Request, principal: Principal, org_id: uuid.UUID | None = None
) -> AsyncGenerator[AnalysisScope]:
    """Derive the organization, then open the caller's session — in that order,
    with only one connection checked out at a time.

    Raises ``OrganizationNotFoundError`` (404) when ``org_id`` names an
    organization the caller has no active membership of, before any connection
    is taken, and translates connection-level/pool failures anywhere inside
    into a 503 (``repositories/radar_common.py``).
    """
    session_factory = get_session_factory(request)
    async with postgres_failures_as_503():
        membership = resolve_optional_org(principal, org_id)
        derivation: OrgDerivation | None = None
        if membership is not None:
            # Opened and closed here: its connection is back in the pool before
            # the line below asks for one. This is the invariant.
            derivation = await load_org_derivation(
                session_factory, membership.org_id, principal.user_id
            )
        async with user_session(session_factory, principal.user_id) as session:
            yield AnalysisScope(session=session, org_derivation=derivation)
