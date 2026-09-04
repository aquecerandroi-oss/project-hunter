"""The Clerk webhook: what each event does to the local mirror.

Authentication and de-duplication of a delivery live one module over
(:mod:`hunter_api.services.webhook_delivery`): the signature is verified before
the body is parsed, and the ``svix-id`` is claimed — reversibly — before any
effect is applied. This module is what happens *after* both of those pass.

**Which role does what.** The handler acts for no organization and no
signed-in person, so it starts by *reading* across every tenant as
``hunter_worker`` (the ``BYPASSRLS`` role) to turn a Clerk id into a local
``users.id``. Every **write** then runs as ``hunter_app`` with the RLS setting
that names the row it is about — because ``hunter_worker`` has no DML on
``users`` or ``organization_members`` at all (DATABASE.md §15.6: its grants
cover market data, analysis and system tables). The elevated role is therefore
read-only here, which is the property to preserve if this file changes.
``processed_events`` is the exception: it is a system table ``hunter_worker``
owns and ``hunter_app`` may only read.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, Any, cast

from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert

from hunter_api.auth.clerk_api import profile_from_clerk_user
from hunter_api.services.audit import record as record_audit
from hunter_api.services.webhook_delivery import (
    CONSUMER,
    claim_delivery,
    release_delivery,
)
from hunter_core.db.models.identity import OrganizationMember, User
from hunter_core.db.session import bootstrap_session, role_session, tenant_session
from hunter_core.domain.enums import MemberStatus
from hunter_core.domain.types import utcnow, uuid7
from hunter_core.logging import get_logger

if TYPE_CHECKING:
    from collections.abc import Mapping

    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

logger = get_logger(__name__)

HANDLED_TYPES = frozenset({"user.created", "user.updated", "user.deleted"})


async def handle_event(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    delivery_id: str,
    payload: Mapping[str, Any],
    audit: dict[str, Any],
) -> dict[str, str]:
    """Apply one delivery, at most once. Returns what was done, for the response."""
    event_type = payload.get("type")
    data = payload.get("data")
    if not isinstance(event_type, str) or not isinstance(data, dict):
        return {"status": "ignored", "reason": "malformed"}
    if not await claim_delivery(session_factory, delivery_id):
        return {"status": "duplicate", "type": event_type}
    try:
        if event_type not in HANDLED_TYPES:
            return {"status": "ignored", "type": event_type}
        profile_data = cast("dict[str, Any]", data)
        if event_type == "user.deleted":
            return await _revoke_user(session_factory, profile_data, audit)
        return await _upsert_user(session_factory, event_type, profile_data, audit)
    except Exception:
        await release_delivery(session_factory, delivery_id)
        raise


async def _find_user(
    session_factory: async_sessionmaker[AsyncSession], external_auth_id: str
) -> uuid.UUID | None:
    """Resolve a Clerk id to a local ``users.id`` — the one elevated statement.

    ``hunter_worker`` because the lookup spans every tenant and the ``users``
    policies key on ``app.current_user``, which is what we are resolving. It is
    a ``SELECT`` and nothing else: the role has no DML on ``users`` at all
    (DATABASE.md §15.6), so this cannot become a write path by accident.
    """
    async with role_session(session_factory, db_role="hunter_worker") as session:
        return await session.scalar(
            select(User.id).where(User.external_auth_id == external_auth_id)
        )


async def _upsert_user(
    session_factory: async_sessionmaker[AsyncSession],
    event_type: str,
    data: Mapping[str, Any],
    audit: dict[str, Any],
) -> dict[str, str]:
    """Create or refresh the local mirror of a Clerk user.

    The write runs as ``hunter_app`` with ``app.current_user`` set to the row
    being written, which is what the ``user_reads_own_row`` policy checks
    (DATABASE.md §15.4) — the id is generated before the insert precisely so
    that setting is possible. ``hunter_worker`` cannot be used for the write:
    its grants cover market data and system tables, never ``users``.
    """
    profile = profile_from_clerk_user(data)
    if profile is None:
        return {"status": "ignored", "reason": "malformed"}
    if not profile.email:
        # Clerk names no verified primary address. Acknowledged (a non-2xx is
        # an infinite Svix retry loop) but never mirrored: ``users.email`` is
        # what invitations are matched against, so an unverified address here
        # is a way into somebody else's organization
        await _record_unverified(session_factory, profile.external_auth_id, audit)
        return {"status": "ignored", "reason": "no_verified_email"}
    user_id = await _find_user(session_factory, profile.external_auth_id) or uuid7()
    async with bootstrap_session(session_factory, user_id=user_id) as session:
        await session.execute(
            insert(User)
            .values(
                id=user_id,
                external_auth_id=profile.external_auth_id,
                email=profile.email,
                display_name=profile.display_name,
                avatar_url=profile.avatar_url,
            )
            # the conflict target is the id, not external_auth_id: RLS only
            # lets this transaction touch the row app.current_user names, and
            # that is the row we just resolved (or minted)
            .on_conflict_do_update(
                index_elements=["id"],
                set_={
                    "email": profile.email,
                    "display_name": profile.display_name,
                    "avatar_url": profile.avatar_url,
                },
            )
        )
        await record_audit(
            session,
            event_type,
            "user",
            {**audit, "entity_id": user_id},
            after={"external_auth_id": profile.external_auth_id},
        )
    return {"status": "applied", "type": event_type}


async def _record_unverified(
    session_factory: async_sessionmaker[AsyncSession],
    external_auth_id: str,
    audit: dict[str, Any],
) -> None:
    """A system-scope row saying we refused to mirror this account.

    No organization and no ``users`` row exist for it, so this runs as
    ``hunter_app`` with neither setting: the ``audit_system_scope`` policy
    (DATABASE.md §15.4) accepts an insert whose ``organization_id`` is NULL,
    and that is the only row being written.
    """
    logger.info("webhook_user_without_verified_email", external_auth_id=external_auth_id)
    async with role_session(session_factory, db_role="hunter_app") as session:
        await record_audit(
            session,
            "user.email_unverified",
            "user",
            audit,
            after={"external_auth_id": external_auth_id, "reason": "no_verified_email"},
        )


async def _revoke_user(
    session_factory: async_sessionmaker[AsyncSession],
    data: Mapping[str, Any],
    audit: dict[str, Any],
) -> dict[str, str]:
    """Clerk deleted the account: revoke every membership, keep the history.

    ``users`` has no ``deleted_at`` column in the M0 schema (DATABASE.md §1
    limits soft delete to five tables), and T06 does not change the schema. So
    the deletion is expressed where it actually has teeth: every membership
    goes to ``suspended``, which the RBAC layer treats as no membership at all,
    while the rows — and every audit row pointing at this user — survive. The
    ``users`` row itself stays as the mirror of an account that once existed.

    One transaction per organization, because ``organization_members`` is
    filtered by ``app.current_org`` and a transaction has exactly one. Each
    one carries its own audit row, so the organization's admins see the
    revocation in their own trail; a final system-scope row records the event
    itself. Every step is idempotent (the update is a state assignment, not a
    transition), and a failure part-way releases the delivery claim — so the
    Svix retry re-runs the organizations that already succeeded, harmlessly,
    and finishes the ones that never ran.
    """
    external_auth_id = data.get("id")
    if not isinstance(external_auth_id, str):
        return {"status": "ignored", "reason": "no_id"}
    user_id = await _find_user(session_factory, external_auth_id)
    if user_id is None:
        return {"status": "ignored", "reason": "unknown_user"}

    async with role_session(session_factory, db_role="hunter_worker") as session:
        org_ids = (
            (
                await session.execute(
                    select(OrganizationMember.organization_id).where(
                        OrganizationMember.user_id == user_id
                    )
                )
            )
            .scalars()
            .all()
        )

    for org_id in org_ids:
        async with tenant_session(session_factory, org_id, user_id) as session:
            await session.execute(
                update(OrganizationMember)
                .where(
                    OrganizationMember.organization_id == org_id,
                    OrganizationMember.user_id == user_id,
                )
                .values(status=MemberStatus.SUSPENDED)
            )
            await record_audit(
                session,
                "member.revoked",
                "organization_member",
                {**audit, "organization_id": org_id, "entity_id": user_id},
                after={"user_id": str(user_id), "status": MemberStatus.SUSPENDED.value},
            )

    async with bootstrap_session(session_factory, user_id=user_id) as session:
        await record_audit(
            session,
            "user.deleted",
            "user",
            {**audit, "entity_id": user_id},
            after={
                "external_auth_id": external_auth_id,
                "memberships_suspended": len(org_ids),
                "revoked_at": utcnow().isoformat(),
            },
        )
    return {"status": "applied", "type": "user.deleted"}


def system_audit(delivery_id: str, request_id: str | None) -> dict[str, Any]:
    """Audit metadata for a webhook: an actor with no user id, no organization."""
    return {
        "actor_type": "system",
        "actor_id": CONSUMER,
        "organization_id": None,
        "entity_id": None,
        "ip": None,
        "user_agent": None,
        "audit_metadata": {"request_id": request_id, "delivery_id": delivery_id},
    }
