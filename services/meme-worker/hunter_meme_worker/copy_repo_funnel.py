"""The copy lane's funnel writes (H-037, design §4.1), as ``hunter_worker``: every first observation of a
(leader, mint) pair is one ``meme_proposals`` row — ``approved`` then ``filled``/``unfilled`` when
admitted, ``rejected`` (born decided, ``decision.reason``) when not. Split from ``copy_repo.py`` for the
350-line budget.

A copy proposal is **born decided** (never ``proposed``) and carries ``mode = 'paper'`` **written
explicitly** by this module's own insert — not inherited from a column default and not borrowed from the
Lab's insert — so the live-order approval path (``WHERE status = 'proposed'``) can never promote it and
no order can be born from it.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import TYPE_CHECKING, Any

from sqlalchemy import text

from hunter_core.domain.types import uuid7
from hunter_meme_worker.copy_events import ms_iso
from hunter_meme_worker.lab_repo_bets import mark_filled, mark_unfilled
from hunter_meme_worker.lab_rows import ApprovedProposal
from hunter_meme_worker.proposals import ProposalDraft

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from hunter_meme_worker.copy_events import LeaderRef
    from hunter_meme_worker.copy_spec import CopySpec
    from hunter_meme_worker.lab_models import BetEntry

__all__ = [
    "DECIDED_BY",
    "Funnel",
    "censor_entry",
    "insert_copy_proposal",
    "load_funnel",
    "open_copy_bet",
    "reject_entry",
]

PROPOSAL_TTL = timedelta(hours=1)
DECIDED_BY = "rules:copy"

_INSERT_COPY_PROPOSAL = text(
    "INSERT INTO meme_proposals (id, mint, rule_set_id, origin, status, mode, proposed_at, expires_at, "
    "  features_end_time, quote, reasons, suggested, decision, decided_by, decided_at) "
    "VALUES (:id, :mint, :rule_set_id, :origin, :status, 'paper', :proposed_at, :expires_at, "
    "  :features_end_time, CAST(:quote AS jsonb), CAST(:reasons AS jsonb), "
    "  CAST(:suggested AS jsonb), CAST(:decision AS jsonb), :decided_by, :decided_at) "
    "ON CONFLICT (rule_set_id, mint, features_end_time) WHERE origin = 'rules' DO NOTHING "
    "RETURNING id"
)

_FUNNEL = text(
    "SELECT quote ->> 'leader_wallet' AS wallet, quote ->> 'stratum' AS stratum, mint, status, "
    "       decided_at FROM meme_proposals "
    "WHERE rule_set_id = :rule_set_id AND quote ->> 'leader_wallet' IS NOT NULL"
)


def _draft(
    spec: CopySpec,
    mint: str,
    ref: LeaderRef,
    decided_at: datetime,
    *,
    status: str,
    decision: dict[str, Any],
) -> ProposalDraft:
    return ProposalDraft(
        id=str(uuid7()),
        mint=mint,
        rule_set_id=spec.id,
        origin="rules",
        status=status,
        proposed_at=decided_at,
        expires_at=decided_at + PROPOSAL_TTL,
        features_end_time=ref.fields_complete_at,
        quote={
            "leader_wallet": ref.wallet,
            "stratum": ref.stratum,
            "leader_signature": ref.signature,
        },
        reasons=[
            {
                "rule": "copy_leader_first_observation",
                "leader_wallet": ref.wallet,
                "stratum": ref.stratum,
                "signature": ref.signature,
                "slot": ref.slot,
                "observed_at": ms_iso(ref.observed_at),
                "decided_at": ms_iso(decided_at),
            }
        ],
        suggested={"size_sol": str(spec.size_sol)},
        decision=decision,
        decided_by=DECIDED_BY,
        decided_at=decided_at,
    )


async def _insert(session: AsyncSession, draft: ProposalDraft) -> ApprovedProposal | None:
    """``None`` when the unique funnel index already holds this (set, mint, instant). The row is born
    decided and **explicitly** ``mode = 'paper'``: the live-order path selects ``mode = 'live'`` and
    promotes only ``proposed`` rows, so a copy row is neither — by construction, not by default."""
    if not await insert_copy_proposal(session, draft):
        return None
    assert draft.decided_at is not None and draft.decision is not None
    return ApprovedProposal(
        id=draft.id,
        mint=draft.mint,
        rule_set_id=draft.rule_set_id,
        decision=draft.decision,
        decided_at=draft.decided_at,
        migrated=False,
    )


async def open_copy_bet(
    session: AsyncSession,
    spec: CopySpec,
    *,
    mint: str,
    ref: LeaderRef,
    decided_at: datetime,
    entry: BetEntry,
) -> str:
    """The approved proposal and the filled bet, one transaction (``mark_filled`` is the Lab's)."""
    draft = _draft(
        spec,
        mint,
        ref,
        decided_at,
        status="approved",
        decision={"size_sol": str(spec.size_sol), "decided_at": ms_iso(decided_at)},
    )
    proposal = await _insert(session, draft)
    if proposal is None:
        raise RuntimeError(f"copy proposal for {mint} already exists at this instant")
    return await mark_filled(session, proposal, entry)


async def censor_entry(
    session: AsyncSession,
    spec: CopySpec,
    *,
    mint: str,
    ref: LeaderRef,
    decided_at: datetime,
    reason: str,
) -> None:
    """An admitted attempt that never filled: the proposal exists and says why."""
    draft = _draft(
        spec,
        mint,
        ref,
        decided_at,
        status="approved",
        decision={"size_sol": str(spec.size_sol), "decided_at": ms_iso(decided_at)},
    )
    proposal = await _insert(session, draft)
    if proposal is None:
        raise RuntimeError(f"copy proposal for {mint} already exists at this instant")
    await mark_unfilled(session, proposal.id, reason)


async def reject_entry(
    session: AsyncSession,
    spec: CopySpec,
    *,
    mint: str,
    ref: LeaderRef,
    decided_at: datetime,
    reason: str,
) -> bool:
    """A first observation that was not admitted: one ``rejected`` row, born decided. ``False`` when
    the unique index already holds the instant (two leaders, one mint, one microsecond) — counted by
    the caller, never an error: the pair is still known from memory."""
    draft = _draft(
        spec,
        mint,
        ref,
        decided_at,
        status="rejected",
        decision={"reason": reason, "decided_at": ms_iso(decided_at)},
    )
    return await _insert(session, draft) is not None


async def insert_copy_proposal(session: AsyncSession, d: ProposalDraft) -> bool:
    result = await session.execute(
        _INSERT_COPY_PROPOSAL,
        {
            "id": d.id,
            "mint": d.mint,
            "rule_set_id": d.rule_set_id,
            "origin": d.origin,
            "status": d.status,
            "proposed_at": d.proposed_at,
            "expires_at": d.expires_at,
            "features_end_time": d.features_end_time,
            "quote": json.dumps(d.quote),
            "reasons": json.dumps(d.reasons),
            "suggested": json.dumps(d.suggested),
            "decision": None if d.decision is None else json.dumps(d.decision),
            "decided_by": d.decided_by,
            "decided_at": d.decided_at,
        },
    )
    return bool(result.scalars().all())


@dataclass(frozen=True, slots=True)
class Funnel:
    """What the durable funnel says the book must know before the source opens."""

    pairs: list[tuple[str, str]]
    """Every (leader, mint) pair ever observed by this rule set."""
    consumed: list[tuple[str, str]]
    """(stratum, mint) keys consumed by an admitted attempt."""
    attempts: list[tuple[str, date]]
    """One (leader, UTC day) per admitted attempt."""


async def load_funnel(session: AsyncSession, spec: CopySpec) -> Funnel:
    rows = (await session.execute(_FUNNEL, {"rule_set_id": spec.id})).mappings().all()
    pairs = [(str(r["wallet"]), str(r["mint"])) for r in rows]
    admitted = [r for r in rows if r["status"] != "rejected"]
    return Funnel(
        pairs=pairs,
        consumed=[(str(r["stratum"]), str(r["mint"])) for r in admitted],
        attempts=[(str(r["wallet"]), r["decided_at"].date()) for r in admitted],
    )
