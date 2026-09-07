"""Confirmation and actor resolution for ``open_paper_wallet.py``.

Split out for the file-size budget (CLAUDE.md: "no file over 350 lines, split
by responsibility, not by line count"), not a change of ownership: opening
the wallet itself stays in ``open_paper_wallet.py`` and
``hunter_core.portfolio.opening``; this module only decides two things —
*does the operator really mean it* (:func:`is_confirmed`) and *who says so*
(:func:`resolve_actor`) — both read-only, both needed before a single byte is
written (security review of ``2688ef1``, S3).
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import text

from hunter_core.audit import ActorType

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


def is_confirmed(*, org_slug: str, yes: str | None) -> bool:
    """Whether ``--yes`` repeats ``--org``'s slug **literally**.

    Opening the principal paper wallet is permanent and irreversible (D7):
    the safe default is "no" — a missing or mismatched ``--yes`` means the
    caller only previews what would happen.
    """
    return yes is not None and yes == org_slug


async def resolve_actor(
    session: AsyncSession, org_id: uuid.UUID, actor: str
) -> tuple[ActorType, str]:
    """``(actor_type, actor_id)`` for ``audit_logs``, from the operator's ``--actor``.

    An email that matches an existing ``users`` row that is a member of
    ``org_id`` is the real person confirming the opening: ``actor_type='user'``,
    ``actor_id`` is their uuid, exactly what ``AuditEvent``/``SqlAuditSink``
    already know how to store. Anything else — a name with no matching member,
    or free text that is not even an email — is recorded honestly as an
    operator handle rather than invented as a person the database has no row
    for: ``actor_type='system'``, ``actor_id='operator:<the text typed>'``.
    Never guesses a user from an email alone: membership in *this*
    organization is what the audit trail is meant to prove.
    """
    if "@" in actor:
        row = (
            await session.execute(
                text(
                    "SELECT u.id FROM users u "
                    "JOIN organization_members m ON m.user_id = u.id "
                    "WHERE u.email = :email AND m.organization_id = :org"
                ),
                {"email": actor, "org": org_id},
            )
        ).first()
        if row is not None:
            return "user", str(row[0])
    return "system", f"operator:{actor}"
