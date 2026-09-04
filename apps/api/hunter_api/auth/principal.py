"""The authenticated caller: who they are locally, and which organizations
they belong to (SECURITY.md §1's ``Principal``).

Clerk owns identity; this database owns everything financial. A verified token
carries a Clerk user id, and turning it into a ``users.id`` is the join between
the two. When there is no local row yet — the very first API call of a new
account, or a webhook we never received — the user is provisioned here, from
Clerk's Backend API, rather than the request failing with something the user
cannot act on.

**Why the lookup runs as ``hunter_worker``.** The ``users`` policies key on
``app.current_user`` (the local id) and the ``organization_members`` policy on
``app.current_org``. Principal resolution is what *produces* both of those: it
starts from a Clerk id and must answer "which organizations?", which is by
definition a cross-organization question. There is no organization to scope it
to yet. So exactly two statements run under the ``BYPASSRLS`` role, both
filtered by the authenticated subject, in a transaction opened and closed by
:meth:`PrincipalResolver.resolve` and never handed to a caller. Everything
downstream — every router, every repository — runs as ``hunter_app`` with both
settings in place.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from fastapi import status
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import IntegrityError

from hunter_api.errors import HunterError
from hunter_core.audit import AuditEvent, SqlAuditSink
from hunter_core.db.models.identity import OrganizationMember, User
from hunter_core.db.session import bootstrap_session, role_session
from hunter_core.domain.enums import MemberStatus, OrganizationRole
from hunter_core.domain.types import uuid7
from hunter_core.logging import get_logger

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    from hunter_api.auth.clerk import TokenClaims
    from hunter_api.auth.clerk_api import ProfileSource, UserProfile

logger = get_logger(__name__)

MAX_MEMBERSHIPS = 200
"""A defensive bound on how many memberships one principal carries into a
request. Nobody in M0 is in 200 organizations; the cap exists so a pathological
row count cannot make every request quadratically expensive."""


class ProvisioningError(HunterError):
    """The token verified, but no local user could be established for it.

    503, not 401: the credential is good, our side is what could not complete
    (typically Clerk's Backend API being unreachable). Telling the user to sign
    in again would be a lie. Subclasses narrow *why*, because "try again" is
    only honest when trying again can work.
    """

    def __init__(
        self,
        detail: str = "Your account could not be prepared. Try again.",
        *,
        type_slug: str = "provisioning-failed",
    ) -> None:
        super().__init__(
            type_slug=type_slug,
            title="Service Unavailable",
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=detail,
        )


class UnverifiedEmailError(ProvisioningError):
    """Clerk has no *verified* primary address for this account.

    A distinct ``type`` because the fix is the user's, not ours: confirm the
    address in Clerk and come back. Provisioning fails closed rather than
    mirroring an unverified address, because ``users.email`` is what an
    invitation is matched against — see ``auth.clerk_api._primary_email``.
    """

    def __init__(self) -> None:
        super().__init__(
            "Confirm your email address with your identity provider, then try again.",
            type_slug="email-not-verified",
        )


class EmailAlreadyRegisteredError(HunterError):
    """``users.email`` is unique and this address belongs to another account.

    409, not 503: nothing is temporarily broken and a retry will never work.
    The caller signed in with a Clerk account whose verified address is already
    mirrored against a *different* ``external_auth_id`` — which happens when
    someone deletes and recreates their Clerk account, or when two providers
    (email and Google, say) end up as two accounts on one address. The client
    can act on that; it cannot act on "try again".
    """

    def __init__(self) -> None:
        super().__init__(
            type_slug="email-already-registered",
            title="Conflict",
            status_code=status.HTTP_409_CONFLICT,
            detail="This email address is already registered to another account.",
        )


@dataclass(frozen=True, slots=True)
class Membership:
    """One row of ``organization_members``, as the request sees it."""

    org_id: uuid.UUID
    role: OrganizationRole
    status: MemberStatus = MemberStatus.ACTIVE

    @property
    def is_active(self) -> bool:
        return self.status is MemberStatus.ACTIVE


@dataclass(frozen=True, slots=True)
class Principal:
    """The caller. Built once per request, never mutated, never serialized to
    the client wholesale (``/me`` picks fields deliberately).
    """

    user_id: uuid.UUID
    external_auth_id: str
    email: str | None = None
    memberships: tuple[Membership, ...] = field(default_factory=tuple)

    def membership(self, org_id: uuid.UUID) -> Membership | None:
        """The caller's **active** membership of ``org_id``, or ``None``.

        An ``invited`` or ``suspended`` row is not a membership for access
        purposes: it grants nothing, and treating it as one would let a
        suspended member keep reading a tenant's data.
        """
        for membership in self.memberships:
            if membership.org_id == org_id and membership.is_active:
                return membership
        return None

    def active_memberships(self) -> tuple[Membership, ...]:
        return tuple(membership for membership in self.memberships if membership.is_active)


class PrincipalResolver:
    """Verified claims in, :class:`Principal` out — with just-in-time provisioning."""

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        profile_source: ProfileSource,
    ) -> None:
        self._session_factory = session_factory
        self._profile_source = profile_source

    async def resolve(self, claims: TokenClaims) -> Principal:
        found = await self._load(claims.subject)
        if found is None:
            await self._provision(claims)
            found = await self._load(claims.subject)
            if found is None:
                # the insert reported no conflict on ``external_auth_id`` yet
                # the row is not there: the only way that happens is a
                # concurrent delete, and the caller can retry
                logger.warning("jit_provisioning_vanished", subject=claims.subject)
                raise ProvisioningError
        user_id, email, memberships = found
        return Principal(
            user_id=user_id,
            external_auth_id=claims.subject,
            email=email,
            memberships=memberships,
        )

    async def _load(
        self, external_auth_id: str
    ) -> tuple[uuid.UUID, str | None, tuple[Membership, ...]] | None:
        """The two elevated statements — see this module's docstring."""
        async with role_session(self._session_factory, db_role="hunter_worker") as session:
            row = (
                await session.execute(
                    select(User.id, User.email).where(User.external_auth_id == external_auth_id)
                )
            ).first()
            if row is None:
                return None
            user_id, email = row.id, row.email
            members = (
                await session.execute(
                    select(
                        OrganizationMember.organization_id,
                        OrganizationMember.role,
                        OrganizationMember.status,
                    )
                    .where(OrganizationMember.user_id == user_id)
                    .order_by(OrganizationMember.created_at)
                    .limit(MAX_MEMBERSHIPS)
                )
            ).all()
        memberships = tuple(
            Membership(org_id=member.organization_id, role=member.role, status=member.status)
            for member in members
        )
        return user_id, email, memberships

    async def _provision(self, claims: TokenClaims) -> None:
        """Create the local mirror of a Clerk user we have never seen.

        The id is generated here, before the insert, because ``users`` is under
        ``FORCE ROW LEVEL SECURITY``: the transaction has to declare which row
        it is allowed to write (``app.current_user``) before writing it
        (DATABASE.md §15.4).

        Two collisions are possible and they are not the same event.
        ``ON CONFLICT (external_auth_id) DO NOTHING`` absorbs the first — two
        concurrent first requests of one brand-new account — and the
        ``RETURNING`` is what says whether *this* call inserted, so
        ``user.provisioned`` is recorded once rather than once per racer. The
        second is a different Clerk account whose verified address is already
        mirrored: ``users.email`` is unique, so that raises, and it is a 409
        with its own audit row rather than a retry-forever 503.
        """
        profile = await self._profile_source.fetch(claims.subject)
        if profile is None:
            logger.warning("jit_profile_unavailable", subject=claims.subject)
            raise ProvisioningError
        if not profile.email:
            # the token's own ``email`` claim is deliberately not a fallback:
            # it carries no verification state
            logger.warning("jit_provisioning_without_verified_email", subject=claims.subject)
            raise UnverifiedEmailError
        user_id = uuid7()
        try:
            inserted = await self._insert_user(user_id, claims.subject, profile)
        except IntegrityError:
            await self._record_email_conflict(claims.subject)
            raise EmailAlreadyRegisteredError from None
        if inserted:
            logger.info("user_provisioned", user_id=str(user_id))

    async def _insert_user(self, user_id: uuid.UUID, subject: str, profile: UserProfile) -> bool:
        async with bootstrap_session(self._session_factory, user_id=user_id) as session:
            row = (
                await session.execute(
                    insert(User)
                    .values(
                        id=user_id,
                        external_auth_id=subject,
                        email=profile.email,
                        display_name=profile.display_name,
                        avatar_url=profile.avatar_url,
                    )
                    .on_conflict_do_nothing(index_elements=["external_auth_id"])
                    .returning(User.id)
                )
            ).first()
            if row is None:
                return False
            await SqlAuditSink(session).record(
                AuditEvent(
                    actor_type="system",
                    actor_id=str(user_id),
                    organization_id=None,
                    action="user.provisioned",
                    entity_type="user",
                    entity_id=str(user_id),
                    after={"external_auth_id": subject},
                )
            )
        return True

    async def _record_email_conflict(self, subject: str) -> None:
        """Leave a trace of the refusal, with no address in it.

        The audit row names the Clerk subject and nothing else: writing the
        colliding email here would put one account holder's address into a
        record about a different person's failed sign-in.
        """
        logger.warning("jit_email_conflict", subject=subject)
        async with role_session(self._session_factory, db_role="hunter_app") as session:
            await SqlAuditSink(session).record(
                AuditEvent(
                    actor_type="system",
                    actor_id="jit-provisioning",
                    organization_id=None,
                    action="user.provision_conflict",
                    entity_type="user",
                    entity_id=None,
                    after={"external_auth_id": subject, "reason": "email_already_registered"},
                )
            )
