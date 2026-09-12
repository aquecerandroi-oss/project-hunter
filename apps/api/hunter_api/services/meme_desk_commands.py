"""The operator's two orders on the desk (T4.7): ``sell_now`` on an open bet
and ``cancel`` on a proposal not yet filled — contract §Rotas, both an
``INSERT`` into ``meme_operator_commands`` that the loop (T4.6) applies on
the *next* snapshot (contract §Semântica 3). Nothing here sells, prices or
touches ``meme_paper_bets``.

Split out of ``services/meme_desk.py`` (the decisions) for the 350-line
budget; the shared refusals, audit and replay helpers are in
``services/meme_desk_common.py``.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any

from hunter_api.repositories.meme_desk_rows import CommandRow
from hunter_api.schemas.meme_desk import CommandOut
from hunter_api.services.meme_desk_common import (
    BetNotFoundError,
    BetStateConflictError,
    ProposalNotFoundError,
    ProposalStateConflictError,
    actor_id,
    record_desk_audit,
    replayed_command,
)
from hunter_api.services.meme_desk_idempotency import (
    IdempotencyStore,
    ReplayRecord,
    find_replay,
    fingerprint,
    remember,
)
from hunter_api.services.meme_desk_out import build_command_out
from hunter_core.domain.types import uuid7

if TYPE_CHECKING:
    from hunter_api.auth.rbac import OrgContext
    from hunter_api.repositories.meme_desk import MemeDeskRepository

__all__ = ["cancel_proposal", "sell_now"]


async def _file_command(
    repo: MemeDeskRepository,
    store: IdempotencyStore,
    *,
    context: OrgContext,
    idempotency_key: str,
    fp: str,
    row: CommandRow,
    action: str,
    after: dict[str, Any],
) -> CommandOut:
    await repo.insert_command(row)
    await record_desk_audit(
        context,
        action=action,
        entity_type="meme_operator_command",
        entity_id=row.id,
        after=after,
        idempotency_key=idempotency_key,
    )
    await remember(
        store,
        context.org_id,
        idempotency_key,
        ReplayRecord(fingerprint=fp, entity_type="meme_operator_command", entity_id=str(row.id)),
    )
    return build_command_out(row)


async def sell_now(
    repo: MemeDeskRepository,
    store: IdempotencyStore,
    *,
    context: OrgContext,
    bet_id: uuid.UUID,
    idempotency_key: str,
    now: datetime,
) -> CommandOut:
    """``meme_operator_commands(sell_now)``; 409 unless the bet is ``open``
    (and 409 ``sell_now_already_pending`` for a second one queued behind an
    unapplied first — the loop sells once, on the next snapshot)."""
    fp = fingerprint("meme_desk.bet.sell_now", str(bet_id), {})
    replayed = await replayed_command(
        repo, await find_replay(store, context.org_id, idempotency_key, fp)
    )
    if replayed is not None:
        return replayed
    bet = await repo.get_bet(bet_id)
    if bet is None:
        raise BetNotFoundError
    if bet.status != "open":
        raise BetStateConflictError(bet_id, reason="bet_not_open", current=bet.status)
    pending = await repo.pending_command(bet_id=bet_id, command="sell_now")
    if pending is not None:
        raise BetStateConflictError(bet_id, reason="sell_now_already_pending", current=bet.status)
    row = CommandRow(
        id=uuid7(),
        bet_id=bet_id,
        proposal_id=None,
        command="sell_now",
        issued_by=actor_id(context),
        issued_at=now,
        applied_at=None,
        result=None,
    )
    return await _file_command(
        repo,
        store,
        context=context,
        idempotency_key=idempotency_key,
        fp=fp,
        row=row,
        action="meme_desk.bet.sell_now",
        after={"bet_id": str(bet_id), "mint": bet.mint, "mark_sol": bet.mark_sol},
    )


async def cancel_proposal(
    repo: MemeDeskRepository,
    store: IdempotencyStore,
    *,
    context: OrgContext,
    proposal_id: uuid.UUID,
    idempotency_key: str,
    now: datetime,
) -> CommandOut:
    """``meme_operator_commands(cancel)``; 409 ``already_filled`` once a bet
    exists, 409 ``not_cancellable`` for a proposal already closed another way."""
    fp = fingerprint("meme_desk.proposal.cancel", str(proposal_id), {})
    replayed = await replayed_command(
        repo, await find_replay(store, context.org_id, idempotency_key, fp)
    )
    if replayed is not None:
        return replayed
    proposal = await repo.get_proposal(proposal_id)
    if proposal is None:
        raise ProposalNotFoundError
    if proposal.status == "filled" or proposal.bet_id is not None:
        raise ProposalStateConflictError(
            proposal_id, reason="already_filled", current=proposal.status
        )
    if proposal.status not in ("proposed", "approved"):
        raise ProposalStateConflictError(
            proposal_id, reason="not_cancellable", current=proposal.status
        )
    row = CommandRow(
        id=uuid7(),
        bet_id=None,
        proposal_id=proposal_id,
        command="cancel",
        issued_by=actor_id(context),
        issued_at=now,
        applied_at=None,
        result=None,
    )
    return await _file_command(
        repo,
        store,
        context=context,
        idempotency_key=idempotency_key,
        fp=fp,
        row=row,
        action="meme_desk.proposal.cancel",
        after={"proposal_id": str(proposal_id), "mint": proposal.mint, "status": proposal.status},
    )
