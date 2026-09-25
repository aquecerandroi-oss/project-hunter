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
- a proposal older than ``MEME_LIVE_AUTO_APPROVE_MAX_AGE_S`` (default
  :data:`AUTO_APPROVE_MAX_AGE_S`, 10 s since T4.94; 60 s before) is left to the
  human (the ``operator`` set expires in 180 s for a hand; the robot decides on
  its first passes or not at all);
- ``mint_busy_superseded`` (T4.94, R78): a proposal whose mint has an open live
  position or a buy in flight is **rejected** by the robot on that pass — before
  any other early return — and never opened later on a tape the market already
  moved past; the gate proposes the coin again if it still qualifies
  (``auto_plan.py``);
- ``MEME_LIVE_AUTO_APPROVE_MAX_PER_HOUR`` (default 5), counted from the rows —
  only proposals the admission did **not** reject (T4.28e): a refusal costs no
  slot, so in stage 1 the cap equals the scope's ``max_trades`` and never binds
  before it;
- a blocking kill switch, a diverged program or an exhausted scope skip the
  pass instead of opening a proposal the admission would refuse;
- ``MEME_LIVE_AUTO_APPROVE_REFUSAL_COOLDOWN_S`` (default 120 s, ``0`` disables,
  T4.28f): a mint the admission refused for a reason that cannot change in the
  next couple of minutes is not re-opened while the cooldown runs — skip
  ``recently_refused``, the reasons and the query in ``refusal_cooldown.py``;
- ``risk_snapshot_pending`` (T4.28g): the mint has no measured ``bundled_share``
  inside ``RISK_SNAPSHOT_MAX_AGE_S`` yet, so the proposal is left ``proposed``
  rather than opened and refused ``bundled_share_unmeasurable`` a minute before
  the answer lands — ``risk_snapshot.py``;
- any admission refusal of an auto-opened proposal writes the ``refused`` order
  **and** marks the proposal ``rejected`` with the reason (``entries._refuse``
  → :func:`reject_auto_proposal`), so the desk shows why.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from time import monotonic
from typing import TYPE_CHECKING

from sqlalchemy import text

from hunter_core.db.session import role_session
from hunter_core.execution.meme.approval import AUTO_STAGE1_DECIDED_BY, decide_proposal
from hunter_core.logging import get_logger
from hunter_meme_executor.auto_busy import overtaken_proposals
from hunter_meme_executor.auto_counters import auto_approved_last_hour, auto_refused_last_hour
from hunter_meme_executor.auto_plan import (
    AUTO_APPROVE_MAX_AGE_S,
    AUTO_NOTE,
    MINT_BUSY_SUPERSEDED,
    AutoPlan,
    OperatorProposal,
    auto_decision,
    plan_auto_approvals,
    superseded_decision,
)
from hunter_meme_executor.journal_db import WORKER_ROLE
from hunter_meme_executor.refusal_cooldown import refusal_cooling_mints
from hunter_meme_executor.repo import open_positions, pending_attempts
from hunter_meme_executor.risk_read import ensure_snapshots
from hunter_meme_executor.risk_snapshot import mints_with_snapshot
from hunter_meme_executor.scope import read_scope_use

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from hunter_meme_executor.context import ExecutorContext
    from hunter_meme_executor.repo import Candidate

__all__ = [
    "AUTO_APPROVE_MAX_AGE_S",
    "AUTO_NOTE",
    "MINT_BUSY_SUPERSEDED",
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
    "supersede_busy",
    "superseded_decision",
]

logger = get_logger(__name__)

_OPERATOR_PROPOSED = text(
    "SELECT p.id, p.mint, p.suggested, p.proposed_at, p.expires_at, rs.params, "
    "  p.reasons->0->>'series' AS series "
    "FROM meme_proposals p JOIN meme_rule_sets rs ON rs.id = p.rule_set_id "
    "WHERE rs.kind = 'operator' AND rs.status = 'active' "
    "  AND p.status = 'proposed' AND p.mode = 'paper' "
    "  AND p.expires_at > :now AND p.proposed_at >= :since "
    "ORDER BY p.proposed_at, p.id"
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
            series=r["series"],
        )
        for r in rows
    ]


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


async def supersede_busy(
    ctx: ExecutorContext, proposals: tuple[OperatorProposal, ...], *, now: datetime
) -> dict[str, int]:
    """T4.94: reject each proposal whose mint was busy, by name, with the one
    guarded statement every decision uses (``WHERE status = 'proposed'``) — so it
    is durable across passes and restarts, and the row no longer holds the
    gate's "already open" slot for the mint. Returns the skip counts:
    ``mint_busy_superseded`` per row moved, ``decided_concurrently`` when a click
    or the loop's ``expired`` stamp got there first."""
    counts: dict[str, int] = {}
    moved: list[OperatorProposal] = []
    if not proposals:
        return counts
    async with role_session(ctx.session_factory, db_role=WORKER_ROLE) as session:
        for proposal in proposals:
            if await decide_proposal(session, superseded_decision(proposal, now=now)):
                moved.append(proposal)
            else:
                counts["decided_concurrently"] = counts.get("decided_concurrently", 0) + 1
    # Counted and logged only once the transaction has committed.
    if moved:
        counts[MINT_BUSY_SUPERSEDED] = len(moved)
    for proposal in moved:
        logger.warning(
            "meme_live_auto_superseded",
            proposal_id=proposal.id,
            mint=proposal.mint,
            age_s=round((now - proposal.proposed_at).total_seconds(), 1),
        )
    return counts


async def auto_approve_once(ctx: ExecutorContext, *, now: datetime) -> list[str]:
    """One pass: open at most one ``operator`` proposal as live. Returns the ids
    opened; ``entries_once`` picks them up as live candidates in the same tick.

    ``now`` is the tick's instant, taken before any read; the final plan and the
    decision use ``now`` plus this pass's own elapsed time (T4.94), so a read
    that runs long counts against ``auto_approve_max_age_s`` and ``decided_at``
    is when the robot actually decided."""
    cfg, state = ctx.config, ctx.state
    small = ctx.mode.gates.small_test if ctx.mode.gates is not None else None
    if not cfg.auto_approve or not cfg.live or ctx.signer is None or small is None:
        return []
    started = monotonic()
    async with role_session(ctx.session_factory, db_role=WORKER_ROLE) as session:
        candidates = await operator_proposals(session, now=now)
        if not candidates:
            return []
        scope = await read_scope_use(session, small, requested_sol=small.max_sol_per_trade)
        approved_1h = await auto_approved_last_hour(session, now=now)
        busy = {p.mint for p in await open_positions(session)}
        busy |= {a.mint for a in await pending_attempts(session)}
        overtaken = await overtaken_proposals(session, candidates)  # guardian finding 1
        cooling = await refusal_cooling_mints(
            session, now=now, cooldown_s=cfg.auto_approve_refusal_cooldown_s
        )
        # T4.28g: of this tick's mints, the ones whose rug read already landed.
        measured = await mints_with_snapshot(session, {c.mint for c in candidates}, now=now)

    def skip(reason: str, count: int = 1) -> None:
        state.auto_skipped[reason] = state.auto_skipped.get(reason, 0) + count

    def plan_for(pool: list[OperatorProposal], snapshot_mints: frozenset[str] | None) -> AutoPlan:
        return plan_auto_approvals(
            pool,
            now=now,
            approved_last_hour=approved_1h,
            max_per_hour=cfg.auto_approve_max_per_hour,
            max_age_s=cfg.auto_approve_max_age_s,
            busy_mints=frozenset(busy),
            superseded_ids=overtaken,
            cooling_mints=cooling,
            snapshot_mints=snapshot_mints,
        )

    # T4.94: a proposal seen with its mint busy is rejected on this very pass,
    # before the returns below — a pass the kill switch blocks still sees it, and
    # no later pass may open it once the other position has exited.
    first = plan_for(candidates, None)
    for reason, count in (await supersede_busy(ctx, first.superseded, now=now)).items():
        skip(reason, count)
    gone = {p.id for p in first.superseded}
    candidates = [c for c in candidates if c.id not in gone]
    if not candidates:
        return []

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

    # T4.45: ask the planner who it *would* open with the read in hand, read for
    # exactly those mints, then plan for real. The wait of T4.28g stays as the
    # fallback - a mint whose read failed is still left ``proposed`` rather than
    # opened and refused ``bundled_share_unmeasurable``. (``first.picks`` never
    # held a superseded row, so it is the same list over what is left.)
    measured = await ensure_snapshots(ctx, [p.mint for p in first.picks], measured, now=now)
    now += timedelta(seconds=monotonic() - started)
    plan = plan_for(candidates, measured)
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
    # Guardian finding 1: a twin of what was just opened never waits for a later
    # tick, in which the pick may already have bought and exited.
    twins = tuple(
        s for s in plan.siblings if s.mint in {p.mint for p in plan.picks if p.id in opened}
    )
    for reason, count in (await supersede_busy(ctx, twins, now=now)).items():
        skip(reason, count)
    return opened
