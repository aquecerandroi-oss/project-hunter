"""Shared pieces of the operator desk's use cases (T4.7): the named refusals
(404/409/422), the ``audit_logs`` row every POST writes, the ceiling check
and the replay/read-back helpers.

Split out for the 350-line budget the way ``admission_audit.py`` backs
``admission.py``: ``services/meme_desk.py`` *decides* (approve/reject/manual),
``services/meme_desk_commands.py`` *orders* (sell now/cancel), and both build
on this module — which itself never writes a table.
"""

from __future__ import annotations

import uuid
from decimal import Decimal
from typing import TYPE_CHECKING, Any

from fastapi import status

from hunter_api.errors import HunterError
from hunter_api.schemas.meme_desk import CommandOut, ProposalOut
from hunter_api.services.meme_desk_idempotency import ReplayRecord, key_hash
from hunter_api.services.meme_desk_out import (
    build_command_out,
    build_desk_row_out,
    decimal_or_none,
)
from hunter_core.audit import AuditEvent, get_audit_sink

if TYPE_CHECKING:
    from hunter_api.auth.rbac import OrgContext
    from hunter_api.repositories.meme_desk import MemeDeskRepository
    from hunter_api.repositories.meme_desk_rows import RuleSetRow

__all__ = [
    "BetNotFoundError",
    "BetStateConflictError",
    "DeskRefusedError",
    "ProposalNotFoundError",
    "ProposalStateConflictError",
    "actor_id",
    "enforce_max_sol_per_bet",
    "proposal_out",
    "record_desk_audit",
    "replayed_command",
    "replayed_proposal",
]


class ProposalNotFoundError(HunterError):
    def __init__(self) -> None:
        super().__init__(
            type_slug="meme-proposal-not-found",
            title="Not Found",
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Meme proposal not found.",
        )


class BetNotFoundError(HunterError):
    def __init__(self) -> None:
        super().__init__(
            type_slug="meme-bet-not-found",
            title="Not Found",
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Meme paper bet not found.",
        )


class ProposalStateConflictError(HunterError):
    """409 — the proposal is not in the state this action needs."""

    def __init__(self, proposal_id: uuid.UUID, *, reason: str, current: str) -> None:
        super().__init__(
            type_slug="meme-proposal-state-conflict",
            title="Conflict",
            status_code=status.HTTP_409_CONFLICT,
            detail=f"proposal {proposal_id} is '{current}' (reason: {reason})",
        )


class BetStateConflictError(HunterError):
    """409 — the bet is not ``open`` (or already has this command pending)."""

    def __init__(self, bet_id: uuid.UUID, *, reason: str, current: str) -> None:
        super().__init__(
            type_slug="meme-bet-state-conflict",
            title="Conflict",
            status_code=status.HTTP_409_CONFLICT,
            detail=f"bet {bet_id} is '{current}' (reason: {reason})",
        )


class DeskRefusedError(HunterError):
    """422 — refused by name (``exceeds_max_sol_per_bet``, ``mint_unknown``,
    ``curve_completed``, ``operator_rule_set_missing``)."""

    def __init__(self, detail: str) -> None:
        super().__init__(
            type_slug="meme-desk-refused",
            title="Unprocessable Entity",
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=detail,
        )


def actor_id(context: OrgContext) -> str:
    """Contract §Tabelas: ``decided_by``/``issued_by`` is the Clerk user id."""
    return context.principal.external_auth_id


async def record_desk_audit(
    context: OrgContext,
    *,
    action: str,
    entity_type: str,
    entity_id: uuid.UUID,
    after: dict[str, Any],
    idempotency_key: str,
) -> None:
    """``audit_logs`` row for this POST, in the caller's own transaction; the
    key is stored as a hash, never verbatim (``admission_audit.py``'s rule).
    ``None`` sink only for a session built by hand outside the HTTP path."""
    sink = get_audit_sink()
    if sink is None:
        return
    await sink.record(
        AuditEvent(
            actor_type="user",
            actor_id=str(context.principal.user_id),
            organization_id=context.org_id,
            action=action,
            entity_type=entity_type,
            entity_id=str(entity_id),
            after={**after, "idempotency_key_hash": key_hash(idempotency_key)},
            metadata={"source": "meme_desk", "mode": "paper"},
        )
    )


def enforce_max_sol_per_bet(rule_set: RuleSetRow | None, size_sol: Decimal) -> None:
    """Contract §Rotas: 422 ``exceeds_max_sol_per_bet`` when the decided size
    is above the set's own ceiling. A set with no ceiling in ``params`` is not
    a ceiling of zero — nothing is refused for it here; the loop applies the
    rest of the set's ceilings on fill."""
    cap = decimal_or_none(rule_set.params.get("max_sol_per_bet")) if rule_set else None
    if cap is not None and size_sol > cap:
        raise DeskRefusedError(
            f"size_sol {size_sol} exceeds the rule set's max_sol_per_bet {cap} "
            "(reason: exceeds_max_sol_per_bet)"
        )


async def replayed_proposal(
    repo: MemeDeskRepository, record: ReplayRecord | None
) -> ProposalOut | None:
    """The proposal a remembered key produced, re-read from Postgres — or
    ``None`` (no record, or the write it remembers never committed)."""
    if record is None or record.entity_type != "meme_proposal":
        return None
    row = await repo.desk_row(uuid.UUID(record.entity_id))
    return ProposalOut(row=build_desk_row_out(row)) if row is not None else None


async def replayed_command(
    repo: MemeDeskRepository, record: ReplayRecord | None
) -> CommandOut | None:
    if record is None or record.entity_type != "meme_operator_command":
        return None
    row = await repo.get_command(uuid.UUID(record.entity_id))
    return build_command_out(row) if row is not None else None


async def proposal_out(repo: MemeDeskRepository, proposal_id: uuid.UUID) -> ProposalOut:
    row = await repo.desk_row(proposal_id)
    if row is None:  # pragma: no cover - just written/read in the same transaction
        raise RuntimeError(f"proposal {proposal_id} vanished right after being written")
    return ProposalOut(row=build_desk_row_out(row))
