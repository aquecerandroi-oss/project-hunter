"""Stage 1 "liga sozinho" (T4.28): the executor opens the desk's ``operator``
proposal as a live one without the click — and nothing else changes.

The owner's decision (``obsidian/06-DECISIONS/2026-09-12-teste-pequeno-meme-real.md``,
"Estágio 1 — sozinho (16/09)"): inside the written small-test scope the robot
buys and sells without "Aprovar (REAL)". The design keeps the money decision
where it already was: this module only does what the click does — the shared
``hunter_core.execution.meme.approval`` rules and its one guarded statement,
``decided_by = 'executor:auto_stage1'``, ``decision = suggested`` — and the
admission that follows (the 25 checks, the sizing, the scope counters, the
kill switch re-read before signing) is **unchanged**. The paper loop keeps
filling the same proposal in shadow.

Brakes that exist only in this mode, all named in the heartbeat:

- at most **one** buy per tick, never two for the same mint in a tick;
- a proposal older than :data:`AUTO_APPROVE_MAX_AGE_S` (60 s) is left to the
  human (the ``operator`` set expires in 180 s for a hand; the robot decides on
  its first pass or not at all);
- ``MEME_LIVE_AUTO_APPROVE_MAX_PER_HOUR`` (default 5), counted from the rows —
  only proposals the admission did **not** reject (T4.28e): a refusal costs no
  slot, so in stage 1 the cap equals the scope's ``max_trades`` and never binds
  before it;
- a blocking kill switch, a diverged program or an exhausted scope skip the
  pass instead of opening a proposal the admission would refuse;
- any admission refusal of an auto-opened proposal writes the ``refused`` order
  **and** marks the proposal ``rejected`` with the reason (``entries._refuse``
  → :func:`reject_auto_proposal`), so the desk shows why.
"""

from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Any

from sqlalchemy import text

from hunter_core.db.session import role_session
from hunter_core.execution.meme.approval import (
    AUTO_STAGE1_DECIDED_BY,
    ProposalDecision,
    decide_proposal,
    max_sol_per_bet_of,
    proposal_state_refusal,
    size_cap_refusal,
)
from hunter_core.logging import get_logger
from hunter_meme_executor.journal_db import WORKER_ROLE
from hunter_meme_executor.repo import open_positions, pending_attempts
from hunter_meme_executor.scope import read_scope_use, requested_sol_of

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from hunter_meme_executor.context import ExecutorContext
    from hunter_meme_executor.repo import Candidate

__all__ = [
    "AUTO_APPROVE_MAX_AGE_S",
    "AUTO_NOTE",
    "AutoPlan",
    "OperatorProposal",
    "auto_approve_once",
    "auto_approved_last_hour",
    "auto_decision",
    "auto_refused_last_hour",
    "operator_proposals",
    "plan_auto_approvals",
    "reject_auto_proposal",
    "reject_if_auto",
]

logger = get_logger(__name__)

AUTO_APPROVE_MAX_AGE_S = 60.0
"""Older than this the robot does not decide: the proposal stays ``proposed`` for
the human until the set's own ``ttl_s`` expires it."""
AUTO_NOTE = "auto_stage1: aberta pelo executor sem clique"

_OPERATOR_PROPOSED = text(
    "SELECT p.id, p.mint, p.suggested, p.proposed_at, p.expires_at, rs.params "
    "FROM meme_proposals p JOIN meme_rule_sets rs ON rs.id = p.rule_set_id "
    "WHERE rs.kind = 'operator' AND rs.status = 'active' "
    "  AND p.status = 'proposed' AND p.mode = 'paper' "
    "  AND p.expires_at > :now AND p.proposed_at >= :since "
    "ORDER BY p.proposed_at, p.id"
)
_APPROVED_LAST_HOUR = text(
    "SELECT count(*) FROM meme_proposals "
    "WHERE decided_by = :by AND decided_at >= :since AND status <> 'rejected'"
)
"""What the hourly cap counts: proposals the robot opened **and the admission
let through**. An auto-opened proposal the admission refused is ``rejected`` in
the same transaction as its ``refused`` order (:func:`reject_if_auto`) and does
not spend the budget — T4.28e, 16/09/2026: four refusals of one mint in 80 s
had eaten 4 of the 5 slots of the hour before a single lamport moved, and the
owner said he does not want the robot rate-limited by its own refusals. The
money brakes are the scope (``max_trades``, ``max_total_sol``) and the
admission; the hourly cap only bounds *fills*."""
_REFUSED_LAST_HOUR = text(
    "SELECT o.reason, count(*) AS n FROM meme_live_orders o "
    "JOIN meme_proposals p ON p.id = o.proposal_id "
    "WHERE p.decided_by = :by AND o.side = 'buy' AND o.status = 'refused' "
    "  AND o.received_at >= :since GROUP BY o.reason"
)
_REJECT = text(
    "UPDATE meme_proposals SET status = 'rejected', "
    "  decision = coalesce(decision, '{}'::jsonb) || CAST(:note AS jsonb) "
    "WHERE id = :id AND status = 'approved' AND mode = 'live' AND decided_by = :by "
    "RETURNING id"
)
"""Only a row this executor opened and that nobody else moved since: the paper
loop that already filled it in shadow (``filled``/``unfilled``) wins — the
``refused`` order is the evidence then."""


@dataclass(frozen=True, slots=True)
class OperatorProposal:
    id: str
    mint: str
    suggested: dict[str, Any]
    proposed_at: datetime
    expires_at: datetime
    rule_set_params: dict[str, Any]


@dataclass(frozen=True, slots=True)
class AutoPlan:
    picks: tuple[OperatorProposal, ...] = ()
    skipped: dict[str, int] = field(default_factory=lambda: dict[str, int]())


def plan_auto_approvals(
    candidates: list[OperatorProposal],
    *,
    now: datetime,
    approved_last_hour: int,
    max_per_hour: int,
    max_per_tick: int = 1,
    max_age_s: float = AUTO_APPROVE_MAX_AGE_S,
    busy_mints: frozenset[str] = frozenset(),
) -> AutoPlan:
    """Pure: which ``proposed`` rows become live this tick, and why the rest do not.

    Skip names: ``expired`` · ``too_old`` · ``mint_busy`` (an open live position or
    a buy in flight on that mint — the admission would refuse ``duplicate_position``)
    · ``suggested_incomplete`` · ``exceeds_max_sol_per_bet`` (the click's rule) ·
    ``hourly_cap`` · ``tick_cap`` · ``mint_repeated``. Candidates are visited in the
    order given (oldest first)."""
    picks: list[OperatorProposal] = []
    skipped: Counter[str] = Counter()
    mints: set[str] = set()
    budget = max(0, max_per_hour - approved_last_hour)
    for candidate in candidates:
        if proposal_state_refusal("proposed", candidate.expires_at, now, approving=True):
            skipped["expired"] += 1
            continue
        if (now - candidate.proposed_at).total_seconds() > max_age_s:
            skipped["too_old"] += 1
            continue
        if candidate.mint in busy_mints:
            skipped["mint_busy"] += 1
            continue
        size = requested_sol_of(candidate.suggested)
        if size <= 0:
            skipped["suggested_incomplete"] += 1
            continue
        if size_cap_refusal(max_sol_per_bet_of(candidate.rule_set_params), size):
            skipped["exceeds_max_sol_per_bet"] += 1
            continue
        if len(picks) >= budget:
            skipped["hourly_cap"] += 1
            continue
        if len(picks) >= max_per_tick:
            skipped["tick_cap"] += 1
            continue
        if candidate.mint in mints:
            skipped["mint_repeated"] += 1
            continue
        mints.add(candidate.mint)
        picks.append(candidate)
    return AutoPlan(picks=tuple(picks), skipped=dict(skipped))


def auto_decision(proposal: OperatorProposal, *, now: datetime) -> ProposalDecision:
    """What the click writes, by the robot: ``decision = suggested`` (the set's own
    numbers, incl. ``manual_plan``) plus the note, ``mode = 'live'``."""
    return ProposalDecision(
        proposal_id=proposal.id,
        status="approved",
        decision={**proposal.suggested, "note": AUTO_NOTE},
        decided_by=AUTO_STAGE1_DECIDED_BY,
        decided_at=now,
        mode="live",
    )


async def operator_proposals(
    session: AsyncSession, *, now: datetime, lookback_s: float = 600
) -> list[OperatorProposal]:
    rows = (
        await session.execute(
            _OPERATOR_PROPOSED, {"now": now, "since": now - timedelta(seconds=lookback_s)}
        )
    ).mappings()
    return [
        OperatorProposal(
            id=str(r["id"]),
            mint=str(r["mint"]),
            suggested=dict(r["suggested"] or {}),
            proposed_at=r["proposed_at"],
            expires_at=r["expires_at"],
            rule_set_params=dict(r["params"] or {}),
        )
        for r in rows
    ]


async def auto_approved_last_hour(session: AsyncSession, *, now: datetime) -> int:
    since = now - timedelta(hours=1)
    return int(
        (
            await session.execute(
                _APPROVED_LAST_HOUR, {"by": AUTO_STAGE1_DECIDED_BY, "since": since}
            )
        ).scalar()
        or 0
    )


async def auto_refused_last_hour(session: AsyncSession, *, now: datetime) -> dict[str, int]:
    since = now - timedelta(hours=1)
    rows = await session.execute(_REFUSED_LAST_HOUR, {"by": AUTO_STAGE1_DECIDED_BY, "since": since})
    return {str(r[0]): int(r[1]) for r in rows}


async def reject_auto_proposal(
    session: AsyncSession, proposal_id: str, *, reason: str, now: datetime
) -> bool:
    """The admission refused what the robot opened: the proposal is ``rejected``
    with the reason in ``decision.note`` (``decided_by`` stays the robot's)."""
    note = json.dumps({"note": f"auto_stage1 recusada: {reason}", "auto_refusal": reason})
    rejected = await session.execute(
        _REJECT, {"id": proposal_id, "by": AUTO_STAGE1_DECIDED_BY, "note": note}
    )
    return rejected.scalar() is not None


async def reject_if_auto(
    ctx: ExecutorContext,
    session: AsyncSession,
    candidate: Candidate,
    reason: str,
    *,
    now: datetime,
) -> None:
    """(d): what the robot opened and the admission refused is ``rejected`` with
    the reason — in the same transaction as the refused order. A click's
    proposal is never touched here."""
    if candidate.decided_by != AUTO_STAGE1_DECIDED_BY:
        return
    if await reject_auto_proposal(session, candidate.id, reason=reason, now=now):
        ctx.state.auto_rejected += 1


async def auto_approve_once(ctx: ExecutorContext, *, now: datetime) -> list[str]:
    """One pass: open at most one ``operator`` proposal as live. Returns the ids
    opened; ``entries_once`` picks them up as live candidates in the same tick."""
    cfg, state = ctx.config, ctx.state
    small = ctx.mode.gates.small_test if ctx.mode.gates is not None else None
    if not cfg.auto_approve or not cfg.live or ctx.signer is None or small is None:
        return []
    async with role_session(ctx.session_factory, db_role=WORKER_ROLE) as session:
        candidates = await operator_proposals(session, now=now)
        if not candidates:
            return []
        scope = await read_scope_use(session, small, requested_sol=small.max_sol_per_trade)
        approved_1h = await auto_approved_last_hour(session, now=now)
        busy = {p.mint for p in await open_positions(session)}
        busy |= {a.mint for a in await pending_attempts(session)}

    def skip(reason: str, count: int = 1) -> None:
        state.auto_skipped[reason] = state.auto_skipped.get(reason, 0) + count

    # A pass that would only open proposals the admission is certain to refuse
    # opens none: the row stays ``proposed`` for the human instead of being
    # rejected by the robot (an auto-rejected proposal is gone for the click too).
    if ctx.kill.blocks_entries:
        skip("kill_switch", len(candidates))
        return []
    if state.program_divergence is not None:
        skip("program_upgraded", len(candidates))
        return []
    if scope.exhausted is not None:
        skip(f"scope_exhausted:{scope.exhausted}", len(candidates))
        return []
    plan = plan_auto_approvals(
        candidates,
        now=now,
        approved_last_hour=approved_1h,
        max_per_hour=cfg.auto_approve_max_per_hour,
        busy_mints=frozenset(busy),
    )
    for reason, count in plan.skipped.items():
        skip(reason, count)
    opened: list[str] = []
    for pick in plan.picks:
        decided = auto_decision(pick, now=now)
        async with role_session(ctx.session_factory, db_role=WORKER_ROLE) as session:
            moved = await decide_proposal(session, decided)
        if not moved:
            skip("decided_concurrently")
            continue
        opened.append(pick.id)
        state.auto_approved += 1
        logger.warning(
            "meme_live_auto_approved",
            proposal_id=pick.id,
            mint=pick.mint,
            size_sol=str(pick.suggested.get("size_sol")),
            age_s=round((now - pick.proposed_at).total_seconds(), 1),
            approved_last_hour=approved_1h + len(opened),
        )
    return opened
