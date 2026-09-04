"""The Clerk webhook: signature verification, idempotency, and the mirror.

Clerk delivers through Svix, so every request is signed (``svix-signature``
over ``svix-id.svix-timestamp.body``) and every delivery is identified
(``svix-id``). Both matter:

- **Signature.** The endpoint is public by necessity. Without verification,
  anyone who learns the URL can create a user row with any email — and email
  is what an invitation is matched against, so a forged ``user.created`` is a
  path into somebody else's organization. The raw body is verified *before*
  it is parsed, because the signature covers bytes, not a re-serialization.
- **Idempotency.** Svix retries with the same ``svix-id`` until it gets a 2xx.
  Delivery is at-least-once, so the handler must be exactly-once in effect;
  ``processed_events`` (DATABASE.md §12) is the durable guard, chosen over a
  Redis SET because losing Redis must not turn into replaying webhooks.

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

import json
import uuid
from typing import TYPE_CHECKING, Any, cast

from fastapi import status
from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert
from svix.webhooks import Webhook, WebhookVerificationError

from hunter_api.auth.clerk_api import profile_from_clerk_user
from hunter_api.errors import HunterError
from hunter_api.services.audit import record as record_audit
from hunter_core.db.models.identity import OrganizationMember, User
from hunter_core.db.models.system import ProcessedEvent
from hunter_core.db.session import bootstrap_session, role_session, tenant_session
from hunter_core.domain.enums import MemberStatus
from hunter_core.domain.types import utcnow, uuid7
from hunter_core.logging import get_logger

if TYPE_CHECKING:
    from collections.abc import Mapping

    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

logger = get_logger(__name__)

CONSUMER = "clerk-webhook"
SVIX_HEADERS = ("svix-id", "svix-timestamp", "svix-signature")
HANDLED_TYPES = frozenset({"user.created", "user.updated", "user.deleted"})
MAX_BODY_BYTES = 256 * 1024


class WebhookSignatureError(HunterError):
    def __init__(self) -> None:
        super().__init__(
            type_slug="invalid-webhook-signature",
            title="Unauthorized",
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="The webhook signature could not be verified.",
        )


class WebhookNotConfiguredError(HunterError):
    def __init__(self) -> None:
        super().__init__(
            type_slug="webhook-not-configured",
            title="Service Unavailable",
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Webhook delivery is not configured on this deployment.",
        )


def verify_signature(secret: str, body: bytes, headers: Mapping[str, str]) -> dict[str, Any]:
    """Verify and parse. Raises before any parsing when verification fails.

    An unconfigured secret is a 503, never a bypass: "no secret, so accept
    everything" is the shape of the classic webhook forgery bug.
    """
    if not secret:
        raise WebhookNotConfiguredError
    if len(body) > MAX_BODY_BYTES:
        raise WebhookSignatureError
    svix_headers = {name: headers.get(name, "") for name in SVIX_HEADERS}
    if not all(svix_headers.values()):
        raise WebhookSignatureError
    try:
        Webhook(secret).verify(body, svix_headers)
    except WebhookVerificationError:
        logger.warning("webhook_signature_rejected", delivery_id=svix_headers["svix-id"])
        raise WebhookSignatureError from None
    try:
        payload: object = json.loads(body)
    except ValueError:
        raise WebhookSignatureError from None
    return cast("dict[str, Any]", payload) if isinstance(payload, dict) else {}


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
    if not await _claim_delivery(session_factory, delivery_id):
        return {"status": "duplicate", "type": event_type}
    if event_type not in HANDLED_TYPES:
        return {"status": "ignored", "type": event_type}
    profile_data = cast("dict[str, Any]", data)
    if event_type == "user.deleted":
        return await _revoke_user(session_factory, profile_data, audit)
    return await _upsert_user(session_factory, event_type, profile_data, audit)


async def _claim_delivery(
    session_factory: async_sessionmaker[AsyncSession], delivery_id: str
) -> bool:
    """Insert the delivery id; ``False`` when it was already there.

    Claimed in its own transaction and *before* the effect, so two concurrent
    retries of the same delivery cannot both proceed — the second one's insert
    finds the row and it returns early.
    """
    async with role_session(session_factory, db_role="hunter_worker") as session:
        claimed = (
            await session.execute(
                insert(ProcessedEvent)
                .values(consumer=CONSUMER, event_id=delivery_id)
                .on_conflict_do_nothing(index_elements=["consumer", "event_id"])
                .returning(ProcessedEvent.event_id)
            )
        ).first()
    return claimed is not None


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
    if profile is None or not profile.email:
        return {"status": "ignored", "reason": "no_email"}
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
    itself. The whole handler is idempotent (the ``svix-id`` is claimed first),
    so a retry after a partial failure completes the rest.
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
