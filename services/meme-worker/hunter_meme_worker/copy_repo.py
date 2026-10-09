"""The copy lane's database writes and reads (H-037), as ``hunter_worker``. Every write reuses the
Lab's own repository functions — ``insert_proposals``/``mark_filled``/``mark_unfilled``/
``close_bet_row``/``update_mark`` — so a copy is the same row shape every paper lane writes; this
module adds only what is the copy lane's own: the funnel row that carries the leader, the late
confirmation facts, and the restart recovery.

**The funnel is durable** (design §4.1): every first observation of a (leader, mint) pair is one
``meme_proposals`` row — ``approved`` then ``filled``/``unfilled`` when admitted, ``rejected`` (born
decided, ``decision.reason``) when not. A proposal is **born decided** (never ``proposed``), so the
live-order approval path (``WHERE status = 'proposed'``) can never promote it. A copy that was censored
**after** entry is a closed bet with ``outcome_quality = 'indeterminate'`` and the named reason.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import TYPE_CHECKING, Any

from sqlalchemy import text

from hunter_core.domain.types import uuid7
from hunter_core.logging import get_logger
from hunter_meme_worker.copy_events import ms_iso
from hunter_meme_worker.lab_models import MARK_CURVE, BetState, EffectiveParams, decimal_of
from hunter_meme_worker.lab_repo import insert_proposals
from hunter_meme_worker.lab_repo_bets import (
    close_bet_row,
    mark_filled,
    mark_unfilled,
)
from hunter_meme_worker.lab_rows import ApprovedProposal
from hunter_meme_worker.proposals import ProposalDraft

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from hunter_meme_worker.copy_events import LeaderRef
    from hunter_meme_worker.copy_spec import CopySpec
    from hunter_meme_worker.lab_models import BetEntry, BetExit

__all__ = [
    "DECIDED_BY",
    "Funnel",
    "RecoveredCopy",
    "censor_entry",
    "close_copy_bet",
    "load_funnel",
    "load_open_copies",
    "open_copy_bet",
    "reject_entry",
    "set_copy_fact",
]

logger = get_logger(__name__)

PROPOSAL_TTL = timedelta(hours=1)
DECIDED_BY = "rules:copy"

_FUNNEL = text(
    "SELECT quote ->> 'leader_wallet' AS wallet, quote ->> 'stratum' AS stratum, mint, status, "
    "       decided_at FROM meme_proposals "
    "WHERE rule_set_id = :rule_set_id AND quote ->> 'leader_wallet' IS NOT NULL"
)
_LANDED = text(
    "SELECT 1 FROM meme_paper_bets WHERE id = CAST(:id AS uuid) AND status = 'closed' "
    "  AND exit -> 'copy' -> 'ts' ->> 'persisted_at' = :stamp"
)
_OPEN_COPIES = text(
    "SELECT b.id, b.proposal_id, b.rule_set_id, b.mint, b.entry_at, b.entry, b.initial_risk_sol, "
    "       b.params, b.high_water_x, b.mark_sol, b.mark_at, b.mark_source, t.mayhem_enabled "
    "FROM meme_paper_bets b LEFT JOIN meme_tokens t ON t.mint = b.mint "
    "WHERE b.rule_set_id = CAST(:rule_set_id AS uuid) AND b.status = 'open' ORDER BY b.entry_at"
)
"""Its own read, not ``lab_repo_bets.load_open_bets``: the Lab is about to stop reading copy rows
(task I), and recovery must keep working when it does."""
_SET_ENTRY_FACT = text(
    "UPDATE meme_paper_bets SET entry = jsonb_set(entry, CAST(CAST(:path AS text) AS text[]), "
    "  CAST(:value AS jsonb), true) WHERE id = :id"
)
_SET_EXIT_FACT = text(
    "UPDATE meme_paper_bets SET exit = jsonb_set(exit, CAST(CAST(:path AS text) AS text[]), "
    "  CAST(:value AS jsonb), true) WHERE id = :id AND exit IS NOT NULL"
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
    """``None`` when the unique funnel index already holds this (set, mint, instant)."""
    if not await insert_proposals(session, [draft]):
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


async def set_copy_fact(
    session: AsyncSession, bet_id: str, *, where: str, name: str, value: Any
) -> None:
    """Late facts about a copy (the confirmation delay, an invalid reason) on its ``entry.copy`` or
    ``exit.copy`` block — a value the lane learned after the row was written."""
    statement = _SET_ENTRY_FACT if where == "entry" else _SET_EXIT_FACT
    await session.execute(
        statement, {"id": bet_id, "path": "{copy," + name + "}", "value": json.dumps(value)}
    )


async def close_copy_bet(
    session: AsyncSession, bet_id: str, closed: BetExit, *, mark_source: str | None, stamp: str
) -> bool:
    """The Lab's ``close_bet_row`` — then proof that **our** close is the one on the row. Another
    writer (the Lab's tick, an operator ``sell_now``) may have closed it first; ``UPDATE ... WHERE
    status = 'open'`` then touches nothing and the caller must not count a sale that is not ours."""
    await close_bet_row(session, bet_id, closed, mark_source=mark_source)
    landed = await session.execute(_LANDED, {"id": bet_id, "stamp": stamp})
    return landed.first() is not None


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


@dataclass(frozen=True, slots=True)
class RecoveredCopy:
    state: BetState
    leader: str
    stratum: str
    peak_atoms: int
    priced_slot: int
    unconfirmed_signature: str | None
    """Set when the copy was opened on an unconfirmed signal that never got its confirmation."""
    leader_observed_at: datetime
    leader_token_delta: int
    leader_slot: int


async def load_open_copies(session: AsyncSession, spec: CopySpec) -> list[RecoveredCopy]:
    """The copies still open in the database, rebuilt for the book and the executor."""
    out: list[RecoveredCopy] = []
    for r in (await session.execute(_OPEN_COPIES, {"rule_set_id": spec.id})).mappings():
        entry = r["entry"]
        copy = entry["copy"]
        leader = copy["leader"]
        state = BetState(
            id=str(r["id"]),
            proposal_id=str(r["proposal_id"]),
            rule_set_id=str(r["rule_set_id"]),
            mint=str(r["mint"]),
            entry_at=r["entry_at"],
            tokens=decimal_of(entry["tokens"]),
            sol_spent=decimal_of(entry["sol_spent"]),
            initial_risk_sol=r["initial_risk_sol"],
            params=EffectiveParams.from_json(r["params"]),
            high_water_x=r["high_water_x"],
            mark_sol=r["mark_sol"],
            mark_at=r["mark_at"],
            exit_intent=None,
            fee_pct=decimal_of(entry["fee_pct"]),
            priority_fee_sol=decimal_of(entry["priority_fee_sol"]),
            curve_cost_sol=decimal_of(entry["curve_cost_sol"]),
            mark_source=str(r["mark_source"] or MARK_CURVE),
            is_mayhem=r["mayhem_enabled"],
        )
        out.append(
            RecoveredCopy(
                state=state,
                leader=str(leader["wallet"]),
                stratum=str(leader["stratum"]),
                peak_atoms=int(leader["position_after_atoms"]),
                priced_slot=int(copy.get("priced_slot") or 0),
                unconfirmed_signature=(
                    str(leader["signature"])
                    if leader.get("confirmed_at_decision") is False
                    and copy.get("confirmation_delay_ms") is None
                    and copy.get("invalid_reason") is None
                    else None
                ),
                leader_observed_at=datetime.fromisoformat(str(leader["observed_at"])),
                leader_token_delta=int(leader["token_delta_atoms"]),
                leader_slot=int(leader["slot"]),
            )
        )
    return out
