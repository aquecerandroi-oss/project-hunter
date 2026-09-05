"""FastAPI dependency providers.

Everything here reads from ``app.state``, populated once at startup by
``create_app``'s lifespan (``app.py``).

Two of them open a database transaction, and which one a route asks for is a
security decision, not a convenience:

- :func:`org_session` is the tenant transaction (``SET LOCAL ROLE hunter_app``
  + ``app.current_org`` + ``app.current_user``), for everything under
  ``/api/v1/orgs/{org_id}``. It **also** binds a
  :class:`~hunter_core.audit.SqlAuditSink` to that same session, so an
  ``@audited`` service writes its audit row inside the transaction carrying the
  mutation: either both commit or neither does. An audit trail that can
  disagree with the data it describes is worse than none, because it is
  trusted.
- :func:`principal_session` sets ``app.current_user`` and no organization, for
  the routes that are about a person rather than a tenant (``/me`` and the
  per-organization reads it fans out to). It carries no audit sink: nothing
  reached through it is a tenant mutation. Using it for a tenant route would
  leave ``app.current_org`` unset, and the RLS policies keyed on it would find
  nothing rather than the wrong thing — a 404-shaped bug, never a leak, but a
  bug.

Both are exported as ``Annotated`` aliases (:data:`OrgSession`,
:data:`PrincipalSession`) whose ``scope="function"`` matters — see the note
below them.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncGenerator
from typing import TYPE_CHECKING, Annotated, Any

from fastapi import Depends, Request

from hunter_api.auth.rbac import CurrentOrg, CurrentPrincipal, OrgContext
from hunter_core.audit import SqlAuditSink, use_audit_sink
from hunter_core.db.session import tenant_session, user_session

if TYPE_CHECKING:
    import redis.asyncio as redis_asyncio
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    from hunter_api.settings import ApiSettings

__all__ = [
    "AuditMeta",
    "CurrentOrg",
    "CurrentPrincipal",
    "OrgSession",
    "PrincipalSession",
    "audit_kwargs",
    "get_redis",
    "get_request_id",
    "get_session_factory",
    "get_settings",
    "org_session",
    "principal_session",
]


def get_settings(request: Request) -> ApiSettings:
    """The ``ApiSettings`` this process was started with."""
    settings: ApiSettings = request.app.state.settings
    return settings


def get_session_factory(request: Request) -> async_sessionmaker[AsyncSession]:
    factory: async_sessionmaker[AsyncSession] = request.app.state.session_factory
    return factory


async def principal_session(
    request: Request, principal: CurrentPrincipal
) -> AsyncGenerator[AsyncSession, None]:
    """A transaction scoped to the caller alone (``app.current_user``).

    For the routes that are about a person rather than an organization —
    ``/me`` and the per-organization reads it fans out to.
    """
    async with user_session(get_session_factory(request), principal.user_id) as session:
        yield session


async def org_session(request: Request, context: CurrentOrg) -> AsyncGenerator[AsyncSession, None]:
    """The request's tenant transaction, with the audit sink bound to it.

    Depends on :func:`~hunter_api.auth.rbac.get_org_context`, so a caller who
    is not a member never reaches the database at all — the 404 is raised
    while resolving dependencies.
    """
    async with tenant_session(
        get_session_factory(request), context.org_id, context.principal.user_id
    ) as session:
        with use_audit_sink(SqlAuditSink(session)):
            yield session


OrgSession = Annotated["AsyncSession", Depends(org_session, scope="function")]
PrincipalSession = Annotated["AsyncSession", Depends(principal_session, scope="function")]
"""``scope="function"``: the transaction closes — and therefore **commits** —
while the handler's response is still being assembled, not after it has been
sent.

FastAPI's default (``scope="request"``) tears dependencies down after
``await response(...)``. A commit that fails there fails *after* the client
has already read ``201 Created``, and the only trace is a stack trace in the
logs: the caller believes a workspace exists that was rolled back. With
``"function"`` the same failure propagates before a byte is written, so it
becomes the 500 problem+json it always was."""


def get_redis(request: Request) -> redis_asyncio.Redis:
    """The process-wide Redis client."""
    client: redis_asyncio.Redis = request.app.state.redis
    return client


def get_request_id(request: Request) -> str:
    """The request id bound by ``RequestIdMiddleware`` (inbound header or minted)."""
    request_id: str = request.state.request_id
    return request_id


class AuditMeta:
    """Where an audited call came from — the ``ip``/``user_agent``/``request_id``
    columns of ``audit_logs``, taken from the request rather than guessed.
    """

    def __init__(self, request: Request) -> None:
        client = request.client
        self.ip = client.host if client is not None else None
        self.user_agent = request.headers.get("user-agent")
        self.request_id = getattr(request.state, "request_id", None)


def audit_kwargs(
    request: Request,
    context: OrgContext | None,
    *,
    entity_id: uuid.UUID | str | None = None,
    actor_id: uuid.UUID | None = None,
    organization_id: uuid.UUID | None = None,
    **extra: Any,
) -> dict[str, Any]:
    """The keyword arguments ``@audited`` reads off a service call.

    ``hunter_core.audit`` deliberately knows nothing about requests or
    principals (T03 kept the package free of HTTP), so the binding between the
    two lives here, in one function, instead of being spelled out at each of
    the dozen call sites.
    """
    meta = AuditMeta(request)
    actor = actor_id or (context.principal.user_id if context else None)
    return {
        "actor_type": "user" if actor else "system",
        "actor_id": str(actor) if actor else "system",
        "organization_id": organization_id or (context.org_id if context else None),
        "entity_id": entity_id,
        "ip": meta.ip,
        "user_agent": meta.user_agent,
        "audit_metadata": {"request_id": meta.request_id, **extra},
    }
