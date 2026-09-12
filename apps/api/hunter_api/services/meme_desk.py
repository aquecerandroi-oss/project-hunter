"""The operator desk's decisions (T4.7): approve, reject, file a manual buy —
contract ``.claude/state/contrato-T4.6-T4.7-mesa-meme.md`` §Rotas, with its
exact status codes and named refusals. The two *orders* (sell now, cancel)
live in ``services/meme_desk_commands.py`` and are re-exported here so the
router and the tests see one module; the refusals, the audit row and the
replay helpers are ``services/meme_desk_common.py``.

Mirrors ``services/orders.py``'s shape: every POST is idempotent on
``Idempotency-Key`` (``services/meme_desk_idempotency.py``), refused by name
(``DeskRefusedError``, 422; the two conflict errors, 409), and audited in the
caller's own transaction through the sink ``hunter_api.deps.org_session``
already bound (``audit_logs``, actor = the real operator).

**Every write here is a decision or an intent, never a fill.** The loop
(T4.6) fills an approved proposal on the *next* snapshot and sells on the
*next* snapshot after a ``sell_now`` — this module never touches
``meme_paper_bets`` and never prices an execution (contract §Semântica 2–3).
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Any

from hunter_api.repositories.meme_desk_rows import ProposalRow
from hunter_api.schemas.meme_desk import (
    ApproveProposalIn,
    DeskParamsIn,
    ManualProposalIn,
    ProposalOut,
    RejectProposalIn,
)
from hunter_api.services.meme_desk_commands import cancel_proposal, sell_now
from hunter_api.services.meme_desk_common import (
    BetNotFoundError,
    BetStateConflictError,
    DeskRefusedError,
    ProposalNotFoundError,
    ProposalStateConflictError,
    actor_id,
    enforce_live_mode,
    enforce_max_sol_per_bet,
    proposal_out,
    record_desk_audit,
    replayed_proposal,
)
from hunter_api.services.meme_desk_idempotency import (
    IdempotencyStore,
    ReplayRecord,
    find_replay,
    fingerprint,
    remember,
)
from hunter_api.services.meme_desk_out import build_manual_quote, decision_json
from hunter_core.domain.types import uuid7

if TYPE_CHECKING:
    from hunter_api.auth.rbac import OrgContext
    from hunter_api.repositories.meme_desk import MemeDeskRepository

__all__ = [
    "PROPOSAL_TTL_S",
    "BetNotFoundError",
    "BetStateConflictError",
    "DeskRefusedError",
    "ProposalNotFoundError",
    "ProposalStateConflictError",
    "approve_proposal",
    "cancel_proposal",
    "file_manual_proposal",
    "reject_proposal",
    "sell_now",
]

PROPOSAL_TTL_S = 120
"""Contract §Tabelas: ``expires_at = proposed_at + 120 s`` by default."""


async def _decide(
    repo: MemeDeskRepository,
    store: IdempotencyStore,
    *,
    context: OrgContext,
    proposal_id: uuid.UUID,
    idempotency_key: str,
    now: datetime,
    action: str,
    new_status: str,
    decision: dict[str, Any] | None,
    body: DeskParamsIn | RejectProposalIn,
    live_enabled: bool = False,
) -> ProposalOut:
    fp = fingerprint(action, str(proposal_id), body.model_dump(mode="json"))
    replayed = await replayed_proposal(
        repo, await find_replay(store, context.org_id, idempotency_key, fp)
    )
    if replayed is not None:
        return replayed
    proposal = await repo.get_proposal(proposal_id)
    if proposal is None:
        raise ProposalNotFoundError
    if proposal.status != "proposed":
        raise ProposalStateConflictError(
            proposal_id, reason="not_proposed", current=proposal.status
        )
    if new_status == "approved" and now >= proposal.expires_at:
        # The loop stamps ``expired`` on its own tick; between the deadline
        # and that tick the row still reads ``proposed``, and approving it
        # would fill a window the contract closed at ``expires_at``.
        raise ProposalStateConflictError(proposal_id, reason="expired", current=proposal.status)
    mode = "paper"
    if isinstance(body, DeskParamsIn):
        enforce_max_sol_per_bet(await repo.get_rule_set(proposal.rule_set_id), body.size_sol)
        mode = enforce_live_mode(body, live_enabled=live_enabled)
    moved = await repo.decide_proposal(
        proposal_id,
        status=new_status,
        decision=decision,
        decided_by=actor_id(context),
        decided_at=now,
        mode=mode,
    )
    if not moved:
        current = await repo.get_proposal(proposal_id)
        raise ProposalStateConflictError(
            proposal_id,
            reason="decided_concurrently",
            current=current.status if current is not None else "missing",
        )
    await record_desk_audit(
        context,
        action=action,
        entity_type="meme_proposal",
        entity_id=proposal_id,
        after={"status": new_status, "mint": proposal.mint, "decision": decision},
        idempotency_key=idempotency_key,
    )
    await remember(
        store,
        context.org_id,
        idempotency_key,
        ReplayRecord(fingerprint=fp, entity_type="meme_proposal", entity_id=str(proposal_id)),
    )
    return await proposal_out(repo, proposal_id)


async def approve_proposal(
    repo: MemeDeskRepository,
    store: IdempotencyStore,
    *,
    context: OrgContext,
    proposal_id: uuid.UUID,
    idempotency_key: str,
    body: ApproveProposalIn,
    now: datetime,
    live_enabled: bool = False,
) -> ProposalOut:
    """``proposed`` → ``approved`` with ``decision = body`` (contract §Rotas).

    T4.14: ``body.mode = "live"`` files the same proposal for the real executor
    (``meme_proposals.mode``) — refused ``meme_live_disabled`` (422) unless the
    API's ``ENABLE_MEME_LIVE_TRADING`` is on (``live_enabled``). The API never
    signs; the executor admits the proposal again with its own flag and gates."""
    return await _decide(
        repo,
        store,
        context=context,
        proposal_id=proposal_id,
        idempotency_key=idempotency_key,
        now=now,
        action="meme_desk.proposal.approved",
        new_status="approved",
        decision=decision_json(body),
        body=body,
        live_enabled=live_enabled,
    )


async def reject_proposal(
    repo: MemeDeskRepository,
    store: IdempotencyStore,
    *,
    context: OrgContext,
    proposal_id: uuid.UUID,
    idempotency_key: str,
    body: RejectProposalIn,
    now: datetime,
) -> ProposalOut:
    """``proposed`` → ``rejected``; ``decision`` carries only the note."""
    return await _decide(
        repo,
        store,
        context=context,
        proposal_id=proposal_id,
        idempotency_key=idempotency_key,
        now=now,
        action="meme_desk.proposal.rejected",
        new_status="rejected",
        decision={"note": body.note} if body.note is not None else None,
        body=body,
    )


async def file_manual_proposal(
    repo: MemeDeskRepository,
    store: IdempotencyStore,
    *,
    context: OrgContext,
    idempotency_key: str,
    body: ManualProposalIn,
    now: datetime,
    live_enabled: bool = False,
) -> ProposalOut:
    """A proposal born ``approved`` under the active ``operator`` set
    (``operator/2`` since ``0029``; contract §Rotas): 422 ``mint_unknown`` /
    ``curve_completed`` / ``operator_rule_set_missing`` /
    ``exceeds_max_sol_per_bet`` / ``meme_live_disabled`` (T4.14, ``mode = "live"``
    without the API flag). Filled by the loop on the next snapshot."""
    fp = fingerprint("meme_desk.proposal.manual", body.mint, body.model_dump(mode="json"))
    replayed = await replayed_proposal(
        repo, await find_replay(store, context.org_id, idempotency_key, fp)
    )
    if replayed is not None:
        return replayed
    token = await repo.get_token(body.mint)
    if token is None:
        raise DeskRefusedError(
            f"mint {body.mint} is not tracked by the radar (reason: mint_unknown)"
        )
    if token.completed_at is not None or token.migrated_at is not None:
        raise DeskRefusedError(
            f"mint {body.mint} has left the bonding curve (reason: curve_completed)"
        )
    rule_set = await repo.get_operator_rule_set()
    if rule_set is None:
        raise DeskRefusedError(
            "the active operator rule set does not exist yet (reason: operator_rule_set_missing)"
        )
    enforce_max_sol_per_bet(rule_set, body.size_sol)
    mode = enforce_live_mode(body, live_enabled=live_enabled)
    quote = await repo.latest_curve_quote(body.mint)
    features_end = await repo.latest_features_end_time(body.mint)
    decision = decision_json(body)
    proposal = ProposalRow(
        id=uuid7(),
        mint=body.mint,
        rule_set_id=rule_set.id,
        origin="operator",
        status="approved",
        proposed_at=now,
        expires_at=now + timedelta(seconds=PROPOSAL_TTL_S),
        features_end_time=features_end or (quote.observed_at if quote is not None else now),
        quote=build_manual_quote(quote, body.size_sol),
        reasons=["operator_manual"],
        suggested=decision,
        decision=decision,
        decided_by=actor_id(context),
        decided_at=now,
        bet_id=None,
        refusal=None,
        mode=mode,
    )
    await repo.insert_proposal(proposal)
    await record_desk_audit(
        context,
        action="meme_desk.proposal.manual",
        entity_type="meme_proposal",
        entity_id=proposal.id,
        after={"status": "approved", "mint": body.mint, "decision": decision},
        idempotency_key=idempotency_key,
    )
    await remember(
        store,
        context.org_id,
        idempotency_key,
        ReplayRecord(fingerprint=fp, entity_type="meme_proposal", entity_id=str(proposal.id)),
    )
    return await proposal_out(repo, proposal.id)
