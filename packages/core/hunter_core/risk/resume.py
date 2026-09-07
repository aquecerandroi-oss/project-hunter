"""Leaving a block is an act, and the act has to prove the trigger stopped biting.

RISK_ENGINE.md §5: there is no automatic return from ``TRADING_DISABLED``; the
resumption is manual, authorised, audited, and it "não redefine pico nem perdas".
v2.1 added the half this module exists to enforce with real numbers: a resume is
**refused** while the automatic assessment still blocks, instead of being written
as a transition the next evaluation would undo.

Which means a resume needs an equity, and this module will not accept a stale
one. When the caller has no freshly built ``PortfolioState``, the evidence is the
newest ``portfolio_equity_snapshots`` row for the wallet, and it is refused past
:data:`~hunter_core.risk.kill_switch.RESUME_EVIDENCE_MAX_AGE_S`. Failing closed
is the contract's default for a missing input (§7): "cannot prove the wallet
recovered" and "the wallet recovered" are different answers.

**This module writes to ``portfolio_risk_state`` never at all** — that is how
"não redefine pico nem perdas" is guaranteed rather than promised. It reads the
lock row (which serialises it against a concurrent evaluation) and writes only
the transition and the column the workers read.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import timedelta
from typing import TYPE_CHECKING

from hunter_core.domain.enums import KillSwitchState
from hunter_core.domain.types import ensure_utc
from hunter_core.risk.curve import latest_observation
from hunter_core.risk.scopes import EffectiveKillSwitch, effective_state, load_locked_state
from hunter_core.risk.transitions import (
    ACTOR_USER,
    build_evidence,
    latest_transition,
    record_transition,
)
from hunter_risk import PAPER_V1, PortfolioState, RiskLimits, sao_paulo_day_start_utc
from hunter_risk.kill_switch import (
    KillSwitchAssessment,
    KillSwitchInputs,
    ResumeAuthorization,
    assess,
    blocks_entries,
)
from hunter_risk.kill_switch import resume as authorize

if TYPE_CHECKING:
    from datetime import datetime

    from sqlalchemy.ext.asyncio import AsyncSession

    from hunter_core.risk.daily import PersistedRiskState

__all__ = ["RESUME_EVIDENCE_MAX_AGE_S", "ResumeOutcome", "ResumeRefused", "resume"]

RESUME_EVIDENCE_MAX_AGE_S = 120
"""How old the equity behind a resume may be, in seconds. The equity curve is
written every minute (PIPELINE.md §8.5), so two minutes is one missed sample."""


class ResumeRefused(PermissionError):
    """The resume was not written. ``reason`` is the sentence the operator reads."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


@dataclass(frozen=True, slots=True)
class ResumeOutcome:
    """A resume that happened: who, from what, to what, and on which numbers."""

    portfolio_id: uuid.UUID
    from_state: KillSwitchState
    to_state: KillSwitchState
    actor_id: uuid.UUID
    scopes: EffectiveKillSwitch
    assessment: KillSwitchAssessment


async def resume(
    session: AsyncSession,
    portfolio_id: uuid.UUID,
    *,
    actor_id: uuid.UUID,
    reason: str,
    now: datetime,
    limits: RiskLimits = PAPER_V1,
    state: PortfolioState | None = None,
    system: KillSwitchState | None = None,
    publish: bool = False,
) -> ResumeOutcome:
    """Clear the wallet's latch, if the automatic assessment allows it.

    ``actor_id`` is the person the API authenticated — this function does not
    authenticate anybody, and neither does the schema: ``actor_id`` has no FK to
    ``users`` on purpose (§18.7), so a filled UUID proves somebody was *named*,
    not that somebody signed in. Naming them is the API's job (SECURITY.md §2,
    "Kill switch de portfolio" = TRADER and above).

    Raises :class:`ResumeRefused` — never writes a no-op transition.
    """
    instant = ensure_utc(now)
    if not reason.strip():
        raise ResumeRefused("a resume states a reason; blank is not a reason")
    row = await load_locked_state(session, portfolio_id)
    scopes = await effective_state(session, portfolio_id, system=system)
    latch = scopes.portfolio
    if latch is KillSwitchState.ACTIVE:
        raise ResumeRefused(
            f"portfolio {portfolio_id} is already ACTIVE: there is nothing to resume"
        )

    blocked_at = await _latched_since(session, portfolio_id)
    offered = state if state is not None else await _from_curve(session, row, instant, blocked_at)
    evidence_state = _anchored(offered, row, portfolio_id, instant, blocked_at)
    assessment = assess(
        evidence_state,
        limits,
        KillSwitchInputs(system=scopes.system, organization=scopes.organization, portfolio=latch),
    )
    target = (
        KillSwitchState.WARNING
        if assessment.automatic is KillSwitchState.WARNING
        else KillSwitchState.ACTIVE
    )
    if blocks_entries(assessment.automatic):
        raise ResumeRefused(
            f"the automatic assessment is still {assessment.automatic.value} (daily loss "
            f"{assessment.daily_loss_pct}, drawdown {assessment.drawdown_pct}): a resume now "
            "would be undone by the next evaluation, so it is refused instead of recorded"
        )
    authorization = ResumeAuthorization(
        authorized_by=str(actor_id),
        portfolio_id=portfolio_id,
        from_state=latch,
        to_state=target,
        reason=reason,
    )
    try:
        new_latch = authorize(latch, authorization, assessment, portfolio_id)
    except ValueError as error:  # the pure core's own refusals, verbatim
        raise ResumeRefused(str(error)) from error

    await record_transition(
        session,
        organization_id=scopes.organization_id,
        portfolio_id=portfolio_id,
        from_state=latch,
        to_state=new_latch,
        reason=reason,
        evidence=build_evidence(
            daily_loss_pct=assessment.daily_loss_pct,
            drawdown_pct=assessment.drawdown_pct,
            equity=evidence_state.equity,
            peak_equity=row.peak_equity,
            day_start_equity=row.equity_day_start,
            trading_day=row.trading_day.isoformat() if row.trading_day else None,
            warning_thresholds=(
                limits.kill_switch_warning.daily_loss_pct,
                limits.kill_switch_warning.drawdown_pct,
            ),
            blocked_thresholds=(
                limits.kill_switch_blocked.daily_loss_pct,
                limits.kill_switch_blocked.drawdown_pct,
            ),
            extra={
                "trigger": assessment.trigger,
                "authorized_by": str(actor_id),
                # The durable peak is published above; this is the one the
                # assessment actually used, which is ``max(durable, equity)``
                # whenever the wallet has already climbed past its old peak.
                # Publishing both keeps the evidence from implying a drawdown was
                # measured against a number it was not (Astra, second round).
                "assessed_against_peak_equity": str(evidence_state.peak_equity),
                "evidence_observed_at": evidence_state.as_of.isoformat(),
            },
        ),
        actor_type=ACTOR_USER,
        actor_id=actor_id,
        now=instant,
        publish=publish,
    )
    return ResumeOutcome(
        portfolio_id=portfolio_id,
        from_state=latch,
        to_state=new_latch,
        actor_id=actor_id,
        scopes=EffectiveKillSwitch(
            portfolio_id=portfolio_id,
            organization_id=scopes.organization_id,
            system=scopes.system,
            organization=scopes.organization,
            portfolio=new_latch,
        ),
        assessment=assessment,
    )


async def _latched_since(session: AsyncSession, portfolio_id: uuid.UUID) -> datetime:
    """When the wallet entered the state it is being resumed from.

    Evidence older than this instant proves nothing: it describes the wallet
    *before* the block, and the block happened because of what came after
    (Astra, review of this diff — snapshot 20.000 at 12:00:00, block at
    12:00:30 on 19.500, resume at 12:00:31 citing the 12:00:00 point).
    """
    transition = await latest_transition(session, portfolio_id)
    if transition is None:
        raise ResumeRefused(
            "this wallet has no kill switch history, so there is no moment for the evidence of "
            "a recovery to come after"
        )
    return ensure_utc(transition.created_at)


def _anchored(
    state: PortfolioState,
    row: PersistedRiskState,
    portfolio_id: uuid.UUID,
    now: datetime,
    blocked_at: datetime,
) -> PortfolioState:
    """The caller's state, re-anchored on the **durable** peak and day opening.

    A resume "não redefine pico nem perdas", and a caller-supplied state was the
    way round it: hand in a state whose peak equals the equity and a 9 % drawdown
    reads as zero (Astra, first round). The two numbers a resume must not move are
    therefore taken from the locked row and nowhere else.

    The same function applies the conditions that make an equity *evidence* at all
    to **both** sources — the caller's state and the curve — because the second
    round found the caller's state skipping three of them: it must belong to this
    wallet, not be stamped in the future, be strictly newer than the move being
    resumed, and carry complete marks.
    """
    if state.portfolio_id != portfolio_id:
        raise ResumeRefused(
            f"the state offered as evidence belongs to portfolio {state.portfolio_id}, "
            f"not {portfolio_id}"
        )
    if state.as_of > now:
        raise ResumeRefused(
            "the state offered as evidence is stamped in the future: a patrimony that has "
            "not happened yet is not proof of a recovery"
        )
    if (now - state.as_of).total_seconds() > RESUME_EVIDENCE_MAX_AGE_S:
        raise ResumeRefused(
            "the state offered as evidence was taken too long before this act to show the "
            "trigger stopped biting"
        )
    if state.as_of <= blocked_at:
        raise ResumeRefused(
            "the state offered as evidence is not newer than the kill switch move being "
            "resumed: it describes the wallet before the block, which is not evidence of "
            "a recovery"
        )
    if not state.marks_complete:
        raise ResumeRefused(
            "the state offered as evidence has incomplete marks: an equity that is a "
            "guess cannot show the trigger stopped biting"
        )
    if row.equity_day_start is None or row.trading_day_start_utc is None:
        raise ResumeRefused(
            "the daily reference could not be rebuilt, so the day's loss is unknown: a resume "
            "cannot show the trigger stopped biting"
        )
    if row.trading_day_start_utc != sao_paulo_day_start_utc(now):
        raise ResumeRefused(
            "the persisted daily reference belongs to another trading day: evaluate the wallet "
            "before resuming it, so the day's loss is measured against today's opening"
        )
    return state.model_copy(
        update={
            "peak_equity": max(row.peak_equity, state.equity),
            "day_start_equity": row.equity_day_start,
        }
    )


async def _from_curve(
    session: AsyncSession, row: PersistedRiskState, now: datetime, blocked_at: datetime
) -> PortfolioState:
    """The wallet as the durable equity curve describes it, or a refusal.

    Pinned to the operational 1m resolution and to points that have already
    happened (:mod:`hunter_core.risk.curve`), fresh within
    :data:`RESUME_EVIDENCE_MAX_AGE_S`, and **taken after the block**.
    """
    observation = await latest_observation(session, row.portfolio_id, not_after=now)
    if observation is None:
        raise ResumeRefused(
            "there is no equity observation for this wallet: a resume is refused rather than "
            "granted on an equity nobody measured"
        )
    age = now - ensure_utc(observation.observed_at)
    if age > timedelta(seconds=RESUME_EVIDENCE_MAX_AGE_S):
        raise ResumeRefused(
            f"the newest equity observation is {int(age.total_seconds())}s old (limit "
            f"{RESUME_EVIDENCE_MAX_AGE_S}s): a resume on a stale equity is not a proof of recovery"
        )
    if ensure_utc(observation.observed_at) <= blocked_at:
        raise ResumeRefused(
            "the newest equity observation is not newer than the kill switch move being "
            "resumed: it describes the wallet before the block, which is not evidence of "
            "a recovery. Equal timestamps count as before — two readings of the same "
            "cycle are not a sequence"
        )
    if row.equity_day_start is None or row.trading_day_start_utc is None:
        raise ResumeRefused(
            "the daily reference could not be rebuilt, so the day's loss is unknown: a resume "
            "cannot show the trigger stopped biting"
        )
    return PortfolioState(
        portfolio_id=row.portfolio_id,
        as_of=now,
        equity=observation.equity,
        cash=observation.cash if observation.cash is not None else observation.equity,
        peak_equity=max(row.peak_equity, observation.equity),
        day_start_equity=row.equity_day_start,
        day_start_utc=sao_paulo_day_start_utc(now),
    )
