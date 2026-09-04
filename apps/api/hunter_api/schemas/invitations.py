"""Invitation payloads.

M0 sends no email. The create response therefore returns the raw token **once**
(:class:`InvitationCreated`), and the frontend builds the invite link from it;
every later read returns the invitation without it, because only the SHA-256
hash is stored. That is an honest limitation, not a stub: nothing here pretends
a message was delivered.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, Field, StringConstraints

from hunter_api.schemas.common import StrictModel
from hunter_core.domain.enums import OrganizationRole

INVITATION_TTL_DAYS = 7

EMAIL_PATTERN = r"^[^@\s]+@[^@\s.]+(\.[^@\s.]+)+$"
"""Deliberately structural, not RFC-complete. The API does not own address
validation — Clerk does, at sign-in — so the only job here is to reject
obvious junk and anything that is not one address, without pulling in a
dependency to litigate the exotic corners of RFC 5322."""

Email = Annotated[
    str,
    StringConstraints(pattern=EMAIL_PATTERN, max_length=254, strip_whitespace=True, to_lower=True),
]
"""Lowercased on the way in, so the accept check ("does this invitation belong
to the person holding the token?") is a plain equality against the stored
address rather than a case-folding comparison someone forgets."""


class InvitationCreate(StrictModel):
    email: Email
    role: OrganizationRole = OrganizationRole.VIEWER


class InvitationOut(BaseModel):
    id: uuid.UUID
    organization_id: uuid.UUID
    email: str
    role: OrganizationRole
    expires_at: datetime
    accepted_at: datetime | None = None
    created_at: datetime


class InvitationCreated(InvitationOut):
    """The create response, and the only place the token ever appears.

    It is not recoverable afterwards — losing it means revoking the invitation
    and issuing a new one, which is exactly the property that makes a stolen
    database dump useless for joining an organization.
    """

    token: str = Field(
        description="Shown once. Store only the invite link built from it; the API keeps a hash."
    )
