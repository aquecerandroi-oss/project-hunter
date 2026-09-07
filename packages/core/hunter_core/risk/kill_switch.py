"""The durable kill switch: the latch, and the evaluation that moves it.

``hunter_risk.kill_switch`` decides; this decides *and remembers*. Escalation is
arithmetic and automatic, de-escalation is an act (:mod:`hunter_core.risk.resume`)
— and both write under the wallet's lock row (``portfolio_risk_state``, PK
``portfolio_id``), which DATABASE.md §18.7 makes the single serialisation point
for everything touching a wallet.

Three shortcuts this module refuses, each because a review found it:

1. **The wallet's latch is never the *effective* state.** It follows the
   automatic assessment alone; copying the effective state would bake an
   organization-wide block into the wallet and outlive the org's own resume
   (Astra, T3.6 review).
2. **The caller's peak and day reference never win over the persisted ones.**
   A caller that read the peak a second earlier would understate the drawdown
   exactly when the peak just moved.
3. **A wallet that cannot be marked keeps its latch.** No equity means no
   automatic ladder — inventing one is the midnight equity §5 forbids.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import update

from hunter_core.db.models.paper_wallet import PortfolioRiskState
from hunter_core.domain.enums import KillSwitchState
from hunter_core.domain.types import ensure_utc
from hunter_core.risk.curve import day_opening_observation
from hunter_core.risk.daily import (
    DayReference,
    PersistedRiskState,
    next_peak,
    resolve_day_reference,
)
from hunter_core.risk.scopes import EffectiveKillSwitch, effective_state, load_locked_state
from hunter_core.risk.transitions import (
    ACTOR_SYSTEM,
    ACTOR_USER,
    build_evidence,
    latest_transition,
    record_transition,
)
from hunter_risk import PAPER_V1, PortfolioState, RiskLimits, sao_paulo_day_start_utc
from hunter_risk.kill_switch import (
    KillSwitchAssessment,
    KillSwitchInputs,
    assess,
    most_restrictive,
)

if TYPE_CHECKING:
    from datetime import datetime

    from sqlalchemy.ext.asyncio import AsyncSession

__all__ = ["STATE_MAX_AGE_S", "KillSwitchEvaluation", "evaluate_and_persist"]


@dataclass(frozen=True, slots=True)
class KillSwitchEvaluation:
    """What one evaluation concluded, and what it wrote."""

    portfolio_id: uuid.UUID
    previous: KillSwitchState
    latched: KillSwitchState
    automatic: KillSwitchState | None
    """``None`` when the daily reference could not be rebuilt."""
    scopes: EffectiveKillSwitch
    reference: DayReference
    peak_equity: Decimal
    daily_loss_pct: Decimal | None
    drawdown_pct: Decimal | None
    changed: bool
    reason: str

    @property
    def effective(self) -> KillSwitchState:
        return self.scopes.effective


async def evaluate_and_persist(
    session: AsyncSession,
    portfolio_id: uuid.UUID,
    state: PortfolioState | None,
    now: datetime,
    *,
    limits: RiskLimits = PAPER_V1,
    system: KillSwitchState | None = None,
    publish: bool = False,
) -> KillSwitchEvaluation:
    """Assess, then persist the day reference, the peak and any audited move.

    All in the caller's transaction and under the wallet's lock, so the state the
    workers read and the history a human reads cannot disagree. ``state`` is
    optional because ``None`` is how a caller says "this wallet could not be
    marked": forcing it to invent an equity is the one thing §5 forbids, and a
    wallet with no measurable patrimony keeps its latch and its protections.
    """
    instant = ensure_utc(now)
    row = await load_locked_state(session, portfolio_id)
    usable = _usable_state(state, portfolio_id, instant)
    equity = usable.equity if usable is not None else None
    opening = await day_opening_observation(session, portfolio_id, sao_paulo_day_start_utc(instant))
    reference = resolve_day_reference(row, opening=opening, now=instant)
    peak, peak_at, raised = (
        next_peak(row, equity=equity, now=instant)
        if equity is not None
        else (row.peak_equity, row.peak_equity_at, False)
    )
    await _persist_row(session, portfolio_id, reference, peak, peak_at, write_peak=raised)
    scopes = await effective_state(session, portfolio_id, system=system)
    assessment = _assess(usable, reference, peak, limits, scopes)
    return await _apply(
        session, row, scopes, assessment, reference, peak, limits, instant, usable, publish
    )


STATE_MAX_AGE_S = 60
"""How far ``state.as_of`` may sit from the instant of the evaluation.

A caller holding a state from 23:59 and evaluating it at 00:00:30 would have the
engine assess a patrimony that is already stale — and stamp the *current* instant
on the conclusion (Astra, review of this diff). One sampling cadence is the same
tolerance the peak declares for itself.
"""


def _usable_state(
    state: PortfolioState | None, portfolio_id: uuid.UUID, now: datetime
) -> PortfolioState | None:
    """The state, if it may be assessed at all — otherwise ``None``, which latches.

    Refusing here rather than raising is deliberate for the two *degraded* cases
    (stale, or marks incomplete): they are conditions of the wallet, not bugs of
    the caller, and the answer to both is the same as having no state at all —
    keep the latch, block entries by missing input, keep the protections. A state
    belonging to **another wallet** is a caller defect and still raises.
    """
    if state is None:
        return None
    if state.portfolio_id != portfolio_id:
        raise ValueError(
            f"state belongs to portfolio {state.portfolio_id}, not {portfolio_id}: evaluating "
            "one wallet against another's equity would stamp the wrong latch"
        )
    # Directional, not ``abs``: a state stamped ahead of the evaluation is not
    # "fresh", it is a patrimony that has not happened (Astra, second round).
    if state.as_of > now or (now - state.as_of).total_seconds() > STATE_MAX_AGE_S:
        return None
    if not state.marks_complete:
        return None
    return state


def _assess(
    state: PortfolioState | None,
    reference: DayReference,
    peak: Decimal,
    limits: RiskLimits,
    scopes: EffectiveKillSwitch,
) -> KillSwitchAssessment | None:
    """The automatic ladder, measured against the **persisted** anchor and peak."""
    anchor = reference.equity_day_start
    if state is None or anchor is None or anchor <= 0:
        return None
    durable = state.model_copy(
        update={"peak_equity": max(peak, state.equity), "day_start_equity": anchor}
    )
    inputs = KillSwitchInputs(
        system=scopes.system, organization=scopes.organization, portfolio=scopes.portfolio
    )
    return assess(durable, limits, inputs)


async def _persist_row(
    session: AsyncSession,
    portfolio_id: uuid.UUID,
    reference: DayReference,
    peak: Decimal,
    peak_at: datetime,
    *,
    write_peak: bool,
) -> None:
    """Write the day reference and the peak. The peak is only ever raised."""
    values: dict[str, object] = {}
    if reference.writes:
        values |= {
            "trading_day": reference.trading_day,
            "trading_day_start_utc": reference.day_start_utc,
            "equity_day_start": reference.equity_day_start,
            "day_reference_observed_at": reference.observed_at,
        }
    if write_peak:
        values |= {"peak_equity": peak, "peak_equity_at": peak_at}
    if values:
        await session.execute(
            update(PortfolioRiskState)
            .where(PortfolioRiskState.portfolio_id == portfolio_id)
            .values(**values)
        )


async def _apply(
    session: AsyncSession,
    row: PersistedRiskState,
    scopes: EffectiveKillSwitch,
    assessment: KillSwitchAssessment | None,
    reference: DayReference,
    peak: Decimal,
    limits: RiskLimits,
    now: datetime,
    state: PortfolioState | None,
    publish: bool,
) -> KillSwitchEvaluation:
    """Move the latch if the ladder says so — up always, down only at the turn."""
    latch = scopes.portfolio
    target, reason = _target(latch, assessment, reference)
    if target is not latch and target is KillSwitchState.ACTIVE:
        previous = await latest_transition(session, row.portfolio_id)
        if previous is not None and previous.actor_type == ACTOR_USER:
            target, reason = latch, "a WARNING written by a person does not clear itself"
    changed = target is not latch
    if changed:
        await record_transition(
            session,
            organization_id=row.organization_id,
            portfolio_id=row.portfolio_id,
            from_state=latch,
            to_state=target,
            reason=reason,
            evidence=build_evidence(
                daily_loss_pct=assessment.daily_loss_pct if assessment else None,
                drawdown_pct=assessment.drawdown_pct if assessment else None,
                equity=state.equity if state else None,
                peak_equity=peak,
                day_start_equity=reference.equity_day_start,
                trading_day=reference.trading_day.isoformat(),
                warning_thresholds=(
                    limits.kill_switch_warning.daily_loss_pct,
                    limits.kill_switch_warning.drawdown_pct,
                ),
                blocked_thresholds=(
                    limits.kill_switch_blocked.daily_loss_pct,
                    limits.kill_switch_blocked.drawdown_pct,
                ),
                extra={
                    "trigger": assessment.trigger if assessment else None,
                    "day_reference_anchored_on": (
                        reference.anchored_on.isoformat() if reference.anchored_on else None
                    ),
                },
            ),
            actor_type=ACTOR_SYSTEM,
            actor_id=None,
            now=now,
            publish=publish,
        )
    return KillSwitchEvaluation(
        portfolio_id=row.portfolio_id,
        previous=latch,
        latched=target,
        automatic=assessment.automatic if assessment else None,
        scopes=EffectiveKillSwitch(
            portfolio_id=scopes.portfolio_id,
            organization_id=scopes.organization_id,
            system=scopes.system,
            organization=scopes.organization,
            portfolio=target,
        ),
        reference=reference,
        peak_equity=peak,
        daily_loss_pct=assessment.daily_loss_pct if assessment else None,
        drawdown_pct=assessment.drawdown_pct if assessment else None,
        changed=changed,
        reason=reason,
    )


def _target(
    latch: KillSwitchState, assessment: KillSwitchAssessment | None, reference: DayReference
) -> tuple[KillSwitchState, str]:
    """Where the latch should stand, and the sentence that says why."""
    if assessment is None:
        return latch, f"daily reference unavailable ({reference.reason.value}): latch preserved"
    automatic = assessment.automatic
    if (
        reference.rolled
        and latch is KillSwitchState.WARNING
        and automatic is KillSwitchState.ACTIVE
    ):
        return KillSwitchState.ACTIVE, "new trading day with both warning triggers cleared"
    return most_restrictive(latch, automatic), (
        f"automatic assessment {automatic.value} (trigger {assessment.trigger})"
    )
