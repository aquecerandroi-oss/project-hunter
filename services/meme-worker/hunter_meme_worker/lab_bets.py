"""The two stateful steps of a Lab tick: filling approved proposals and walking
every open bet through the snapshots it has not seen yet.

Both read and write through ``lab_repo_bets`` as ``hunter_worker``, one short
transaction per proposal or bet, and both take ``now`` as an argument — the
clock is the loop's, so a test can drive a whole life of a bet in one call.

**Fill** (contract §Semântica 2): the first snapshot with ``observed_at >
decided_at``, the rule set's ceilings, the derived wallet; ``filled`` with a
bet or ``unfilled`` with a name; ``wait`` inside the window.

**Bets** (§Semântica 3): every new snapshot marks the position (``mark_sol``,
``high_water_x``); the exit rules — and a pending ``sell_now`` — fire on a
snapshot and are recorded as ``exit_intent``; the sale is priced on the **next**
snapshot; no next snapshot inside the window is ``rug_no_snapshot``. A curve
nobody has observed for the whole horizon plus the window is closed the same
way with ``pending_reason = "time_stop"``: an open bet that can never be priced
is not a position, it is a hole in the ledger.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Any

from hunter_core.db.session import role_session
from hunter_core.logging import get_logger
from hunter_meme_worker.lab_bets_pool import (
    holds_through_migration,
    process_pool_bet,
    settle_command,
)
from hunter_meme_worker.lab_models import BetState, RuleSetSpec, Snapshot, money_str
from hunter_meme_worker.lab_repo import apply_command, load_approved_proposals, pending_commands
from hunter_meme_worker.lab_repo_bets import (
    close_bet_row,
    first_snapshot_after,
    load_open_bets,
    mark_filled,
    mark_unfilled,
    snapshots_after,
    update_mark,
    wallet_state,
)
from hunter_meme_worker.lab_repo_lines import snapshot_at, support_lines_for
from hunter_meme_worker.lines_exit import SupportLine, below_support, next_streak, support_at
from hunter_meme_worker.paper_engine import (
    close_bet,
    close_without_snapshot,
    decide_exit,
    evaluate_fill,
    mark_bet,
)

if TYPE_CHECKING:
    from collections.abc import Mapping

    from sqlalchemy.ext.asyncio import AsyncSession

    from hunter_meme_worker.lab import LabContext
    from hunter_meme_worker.lab_rows import CommandRow, OpenBet

logger = get_logger(__name__)

WORKER_ROLE = "hunter_worker"
REFUSAL_RULE_SET_INACTIVE = "rule_set_inactive"


@dataclass(frozen=True, slots=True)
class FillReport:
    filled: int = 0
    unfilled: int = 0
    waiting: int = 0


@dataclass(frozen=True, slots=True)
class BetsReport:
    open: int = 0
    closed: int = 0
    marked: int = 0


async def fill_approved(
    ctx: LabContext,
    specs: Mapping[str, RuleSetSpec],
    *,
    now: datetime,
    day_start: datetime,
    day_end: datetime,
) -> FillReport:
    """Every ``approved`` proposal: fill on the next snapshot or refuse by name."""
    async with role_session(ctx.session_factory, db_role=WORKER_ROLE) as session:
        approved = await load_approved_proposals(session)
    filled = unfilled = waiting = 0
    for proposal in approved:
        spec = specs.get(proposal.rule_set_id)
        async with role_session(ctx.session_factory, db_role=WORKER_ROLE) as session:
            if spec is None:
                await mark_unfilled(session, proposal.id, REFUSAL_RULE_SET_INACTIVE)
                unfilled += 1
                continue
            snapshot = await first_snapshot_after(
                session, mint=proposal.mint, after=proposal.decided_at
            )
            wallet = await wallet_state(session, spec, day_start=day_start, day_end=day_end)
            sol_usd = await ctx.sol_usd(now) if snapshot is not None else None
            verdict = evaluate_fill(
                spec,
                proposal.decision,
                wallet,
                snapshot,
                decided_at=proposal.decided_at,
                now=now,
                migrated=proposal.migrated,
                fill_window_s=ctx.config.lab_fill_window_s,
                sol_usd=sol_usd,
            )
            if verdict.kind == "filled" and verdict.entry is not None:
                bet_id = await mark_filled(session, proposal, verdict.entry)
                filled += 1
                logger.info(
                    "meme_lab_bet_opened",
                    bet_id=bet_id,
                    mint=proposal.mint,
                    rule_set=spec.name,
                    sol_spent=money_str(verdict.entry.sol_spent),
                )
            elif verdict.kind == "refused" and verdict.refusal is not None:
                await mark_unfilled(session, proposal.id, verdict.refusal)
                unfilled += 1
                logger.info(
                    "meme_lab_proposal_unfilled",
                    proposal_id=proposal.id,
                    mint=proposal.mint,
                    refusal=verdict.refusal,
                )
            else:
                waiting += 1
    return FillReport(filled=filled, unfilled=unfilled, waiting=waiting)


def _parse(value: Any) -> datetime:
    return datetime.fromisoformat(str(value))


def _sell_now_intent(command: CommandRow) -> dict[str, Any]:
    return {
        "reason": "sell_now",
        "decided_at": command.issued_at.isoformat(),
        "snapshot_observed_at": None,
        "trigger": "operator",
        "command_id": command.id,
        "issued_by": command.issued_by,
    }


async def process_open_bets(ctx: LabContext, *, now: datetime) -> BetsReport:
    """Mark, decide and sell every open bet over the snapshots it has not seen."""
    async with role_session(ctx.session_factory, db_role=WORKER_ROLE) as session:
        bets = await load_open_bets(session)
        commands = await pending_commands(session)
    sell_now = {c.bet_id: c for c in commands if c.command == "sell_now" and c.bet_id}
    open_bets = {b.state.id for b in bets}
    closed = marked = 0
    async with role_session(ctx.session_factory, db_role=WORKER_ROLE) as session:
        for bet_id, command in sell_now.items():
            if bet_id not in open_bets:
                await apply_command(
                    session,
                    command.id,
                    now=now,
                    result={"status": "refused", "refusal": "bet_not_open"},
                )
    for bet in bets:
        async with role_session(ctx.session_factory, db_role=WORKER_ROLE) as session:
            outcome = await _process_one(ctx, session, bet, sell_now.get(bet.state.id), now=now)
        closed += outcome == "closed"
        marked += outcome == "marked"
    return BetsReport(open=len(bets) - closed, closed=closed, marked=marked)


async def _process_one(
    ctx: LabContext,
    session: AsyncSession,
    bet: OpenBet,
    command: CommandRow | None,
    *,
    now: datetime,
) -> str:
    state = bet.state
    intent: dict[str, Any] | None = dict(state.exit_intent) if state.exit_intent else None
    if intent is None and command is not None:
        intent = _sell_now_intent(command)
    if holds_through_migration(bet):
        # T4.11: the curve stopped being the venue and the set did not sell on
        # that — from here the PumpSwap pool's tape marks and sells the position.
        return await process_pool_bet(ctx, session, bet, command, intent=intent, now=now)
    after = state.mark_at or state.entry_at
    snapshots = await snapshots_after(session, mint=state.mint, after=after)
    lines, streak = await _line_state(ctx, session, state, after=after, now=now)
    last: tuple[Snapshot, Any] | None = None
    for snapshot in snapshots:
        if state.params.exit_on_line_break:
            below = below_support(snapshot.mcap_sol, support_at(lines, snapshot.observed_at))
            streak = next_streak(streak, below)
        if intent is not None and snapshot.observed_at > _parse(intent["decided_at"]):
            sol_usd = await ctx.sol_usd(now)
            trigger_at = intent.get("snapshot_observed_at")
            exit_ = close_bet(
                state,
                snapshot,
                str(intent["reason"]),
                sol_usd,
                intent_snapshot_at=None if trigger_at is None else _parse(trigger_at),
            )
            exit_.exit["trigger"] = intent.get("trigger")
            await close_bet_row(session, state.id, exit_, exit_intent=intent)
            await settle_command(session, command, intent, exit_.exit["reason"], now=now)
            logger.info(
                "meme_lab_bet_closed",
                bet_id=state.id,
                mint=state.mint,
                reason=exit_.exit["reason"],
                pnl_sol=money_str(exit_.pnl_sol),
            )
            return "closed"
        mark = mark_bet(state, snapshot)
        state = replace(state, high_water_x=mark.high_water_x)
        last = (snapshot, mark)
        if intent is None:
            reason = decide_exit(
                state,
                snapshot,
                mark,
                migrated=bet.migrated_at is not None and snapshot.observed_at >= bet.migrated_at,
                creator_net_seller=bet.creator_net_seller,
                sell_now=False,
                below_support_streak=streak,
            )
            if reason is not None:
                intent = {
                    "reason": reason,
                    "decided_at": snapshot.observed_at.isoformat(),
                    "snapshot_observed_at": snapshot.observed_at.isoformat(),
                    "trigger": "rules",
                }
    if last is not None:
        snapshot, mark = last
        await update_mark(
            session,
            state.id,
            mark_sol=mark.mark_sol,
            mark_at=snapshot.observed_at,
            high_water_x=mark.high_water_x,
            exit_intent=intent,
        )
    elif intent != state.exit_intent and state.mark_sol is not None and state.mark_at is not None:
        await update_mark(
            session,
            state.id,
            mark_sol=state.mark_sol,
            mark_at=state.mark_at,
            high_water_x=state.high_water_x,
            exit_intent=intent,
        )
    window = timedelta(seconds=ctx.config.lab_fill_window_s)
    pending_reason: str | None = None
    if intent is not None and now - _parse(intent["decided_at"]) >= window:
        pending_reason = str(intent["reason"])
    elif intent is None and last is None:
        silent_for = now - after
        if silent_for >= timedelta(seconds=state.params.max_hold_s) + window:
            pending_reason = "time_stop"
    if pending_reason is None:
        return "marked" if last is not None else "unchanged"
    exit_ = close_without_snapshot(state, now=now, pending_reason=pending_reason)
    await close_bet_row(session, state.id, exit_, exit_intent=intent)
    await settle_command(session, command, intent, "rug_no_snapshot", now=now)
    logger.warning(
        "meme_lab_bet_closed_without_snapshot",
        bet_id=state.id,
        mint=state.mint,
        pending_reason=pending_reason,
    )
    return "closed"


async def _line_state(
    ctx: LabContext,
    session: AsyncSession,
    state: BetState,
    *,
    after: datetime,
    now: datetime,
) -> tuple[list[SupportLine], int | None]:
    """T4.10: the support lines a bet that watches the line may read (folded at
    or before ``now``; ``support_at`` further refuses any folded after the
    snapshot being judged) and the streak rebuilt from the snapshot the last
    mark was written on — one back, which is all a two-snapshot rule needs and
    never lets a restart fire it early."""
    if not state.params.exit_on_line_break:
        return [], None
    lines = await support_lines_for(
        session, mint=state.mint, features_version=ctx.config.features_version, until=now
    )
    seed = await snapshot_at(session, mint=state.mint, at=after)
    if seed is None:
        return lines, None
    return lines, next_streak(None, below_support(seed.mcap_sol, support_at(lines, after)))
