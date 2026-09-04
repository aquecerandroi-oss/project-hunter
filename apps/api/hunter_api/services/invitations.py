"""Invitations: minting, revoking and accepting.

The token is 32 random bytes, URL-safe encoded. Only its SHA-256 hash is
stored, so a database dump does not let anyone join an organization — the same
reason password hashes exist. SHA-256 without a salt or a KDF is the right
choice *here* and would be wrong for a password: the input already has 256 bits
of entropy, so there is nothing to brute-force and nothing a rainbow table
could precompute.

M0 sends no email. The raw token is returned once, from the create endpoint,
and the frontend builds the link. Nothing pretends a message went out.
"""

from __future__ import annotations

import hashlib
import secrets
import uuid
from datetime import timedelta
from typing import TYPE_CHECKING, Any

from fastapi import status
from sqlalchemy import select, update

from hunter_api.errors import HunterError
from hunter_api.repositories.invitations import InvitationRepository
from hunter_api.repositories.organizations import MemberRepository
from hunter_api.schemas.invitations import INVITATION_TTL_DAYS
from hunter_api.services.audit import record as record_audit
from hunter_core.audit import audited
from hunter_core.db.models.identity import OrganizationInvitation
from hunter_core.db.session import role_session, tenant_session
from hunter_core.domain.enums import MemberStatus, OrganizationRole
from hunter_core.domain.types import utcnow

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    from hunter_api.auth.principal import Principal

TOKEN_BYTES = 32


class InvitationNotFoundError(HunterError):
    """One error for "no such token", "expired" and "already accepted".

    They are the same fact from the holder's point of view — this link does not
    work — and distinguishing them would turn the endpoint into an oracle for
    which tokens once existed.
    """

    def __init__(self) -> None:
        super().__init__(
            type_slug="invitation-not-found",
            title="Not Found",
            status_code=status.HTTP_404_NOT_FOUND,
            detail="This invitation link is not valid or has expired.",
        )


class InvitationEmailMismatchError(HunterError):
    def __init__(self) -> None:
        super().__init__(
            type_slug="invitation-email-mismatch",
            title="Forbidden",
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This invitation was issued to a different email address.",
        )


class RoleAboveInviterError(HunterError):
    def __init__(self) -> None:
        super().__init__(
            type_slug="role-above-inviter",
            title="Forbidden",
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You cannot invite someone at a role higher than your own.",
        )


def mint_token() -> tuple[str, str]:
    """A fresh invitation token and the hash to store. Only the pair is ever
    held together, and only for the duration of the create request.
    """
    token = secrets.token_urlsafe(TOKEN_BYTES)
    return token, hash_token(token)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


@audited("invitation.created", "organization_invitation")
async def create_invitation(
    *,
    session: AsyncSession,
    org_id: uuid.UUID,
    email: str,
    role: OrganizationRole,
    inviter_role: OrganizationRole,
    created_by: uuid.UUID,
    token_hash: str,
    invitation_id: uuid.UUID,
    **_audit: Any,
) -> dict[str, Any]:
    """``invitation_id`` is minted by the caller, next to the token, so the
    audit row can name the row this call creates: ``@audited`` reads
    ``entity_id`` off the keyword arguments, which are fixed before the call
    runs. An audit row with a NULL ``entity_id`` is unfindable by the only key
    anyone searches the trail with.
    """
    from hunter_api.auth.rbac import at_least

    if not at_least(inviter_role, role):
        raise RoleAboveInviterError
    invitation = await InvitationRepository(session, org_id).create(
        email=email,
        role=role,
        token_hash=token_hash,
        expires_at=utcnow() + timedelta(days=INVITATION_TTL_DAYS),
        created_by=created_by,
        invitation_id=invitation_id,
    )
    # never the token, and never its hash: this dict becomes the ``after``
    # column of a row admins can read back
    return {
        "id": str(invitation.id),
        "organization_id": str(org_id),
        "email": email,
        "role": role.value,
        "expires_at": invitation.expires_at.isoformat(),
        "accepted_at": None,
        "created_at": invitation.created_at.isoformat(),
    }


async def _invitation_before(**kwargs: Any) -> dict[str, Any] | None:
    """The row as it stood, captured before it is deleted.

    Revocation removes the row, so ``before`` is the only place the invitation
    survives at all: without it the trail records that *an* invitation was
    revoked and cannot say to whom, at what role, or by when it would have
    expired. Never the token hash — a deleted invitation's secret has no
    business outliving it in an append-only table.
    """
    session: AsyncSession = kwargs["session"]
    org_id: uuid.UUID = kwargs["org_id"]
    invitation_id: uuid.UUID = kwargs["invitation_id"]
    invitation = await InvitationRepository(session, org_id).get(invitation_id)
    if invitation is None:
        return None
    return {
        "id": str(invitation.id),
        "email": invitation.email,
        "role": invitation.role.value,
        "expires_at": invitation.expires_at.isoformat(),
        "accepted_at": invitation.accepted_at.isoformat() if invitation.accepted_at else None,
    }


@audited("invitation.revoked", "organization_invitation", before=_invitation_before)
async def revoke_invitation(
    *, session: AsyncSession, org_id: uuid.UUID, invitation_id: uuid.UUID, **_audit: Any
) -> dict[str, Any]:
    repository = InvitationRepository(session, org_id)
    invitation = await repository.get(invitation_id)
    if invitation is None:
        raise InvitationNotFoundError
    revoked = {"id": str(invitation.id), "email": invitation.email, "revoked": True}
    await repository.delete(invitation)
    return revoked


async def accept_invitation(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    token: str,
    principal: Principal,
    audit: dict[str, Any],
) -> dict[str, Any]:
    """Join the organization an invitation names.

    Two transactions on purpose. The lookup is by token hash across every
    organization — the holder of a link does not know which organization it
    belongs to, and neither do we until we resolve it — and
    ``organization_invitations`` is filtered by ``app.current_org``, which is
    exactly what we are trying to learn. So that one statement runs as
    ``hunter_worker``, keyed on a 256-bit hash that cannot be guessed or
    enumerated. Everything that *writes* runs as ``hunter_app`` in a normal
    tenant transaction, once the organization is known.
    """
    token_hash = hash_token(token)
    async with role_session(session_factory, db_role="hunter_worker") as lookup:
        found = (
            await lookup.execute(
                select(
                    OrganizationInvitation.id,
                    OrganizationInvitation.organization_id,
                    OrganizationInvitation.email,
                    OrganizationInvitation.role,
                    OrganizationInvitation.expires_at,
                    OrganizationInvitation.accepted_at,
                ).where(OrganizationInvitation.token_hash == token_hash)
            )
        ).first()
    if found is None or found.accepted_at is not None or found.expires_at <= utcnow():
        raise InvitationNotFoundError
    if not principal.email or principal.email.lower() != found.email.lower():
        raise InvitationEmailMismatchError

    org_id: uuid.UUID = found.organization_id
    async with tenant_session(session_factory, org_id, principal.user_id) as session:
        await _claim(session, found.id)
        members = MemberRepository(session, org_id)
        if await members.get(principal.user_id) is None:
            await members.add(
                user_id=principal.user_id,
                role=found.role,
                status=MemberStatus.ACTIVE,
                invited_by=None,
                joined_at=utcnow(),
            )
        accepted = {
            "organization_id": str(org_id),
            "user_id": str(principal.user_id),
            "role": found.role.value,
        }
        await record_audit(
            session,
            "invitation.accepted",
            "organization_member",
            {**audit, "organization_id": org_id, "entity_id": found.id},
            after=accepted,
        )
    return accepted


async def _claim(session: AsyncSession, invitation_id: uuid.UUID) -> None:
    """Mark the invitation used, refusing a second claim.

    ``WHERE accepted_at IS NULL`` makes this the concurrency guard too: two
    simultaneous accepts of the same link both reach here, and only one updates
    a row.
    """
    claimed = (
        await session.execute(
            update(OrganizationInvitation)
            .where(
                OrganizationInvitation.id == invitation_id,
                OrganizationInvitation.accepted_at.is_(None),
            )
            .values(accepted_at=utcnow())
            .returning(OrganizationInvitation.id)
        )
    ).first()
    if claimed is None:
        raise InvitationNotFoundError
