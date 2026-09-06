"""Turning a declared policy into the arm the production walker will fold.

Three of the eight policies are *only* a different tracking plan (``INV-B`` has
no invalidation level, ``INV-E`` has a lower one, ``TGT-3``/``TGT-4.5`` have a
farther target) — the walker runs unchanged over them. Two more need a
predicate the plan cannot express (``INV-C``, ``EXIT-CHAN``); they carry an
observer and the engine hands its verdict to the walker as a pending
invalidation.

Every level goes through :func:`~hunter_strategy_worker.levels.to_db_scale`
before it is used, exactly as the decision path does, so an arm and the base
compare numbers at the same scale.

What is never rebuilt here: the stop, the entry bar, the horizon and the costs.
They come from the frozen record; an arm that moved them would not be paired
with the base any more.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from decimal import Decimal
from typing import TYPE_CHECKING

from hunter_core.domain.enums import Timeframe
from hunter_indicators.replay.observers import ChannelObserver, ConsecutiveCloseObserver
from hunter_indicators.replay.policies import (
    ExitPolicy,
    InvalidationRule,
    TargetRule,
    buffered_level,
    no_target_level,
)
from hunter_strategy_worker.levels import to_db_scale

if TYPE_CHECKING:
    from hunter_strategy_worker.replay.load import ReplayCase
    from hunter_strategy_worker.walker import TrackingPlan

__all__ = ["ArmNotBuildable", "ArmSpec", "build_arm"]


class ArmNotBuildable(Exception):
    """The frozen record does not carry what this policy needs.

    Raised, never silently downgraded to the base: an arm that quietly fell back
    to another rule would be reported as evidence about a policy it never ran.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


@dataclass(frozen=True, slots=True)
class ArmSpec:
    """One policy bound to one frozen entry."""

    policy: ExitPolicy
    plan: TrackingPlan
    consecutive: ConsecutiveCloseObserver | None = None
    channel: ChannelObserver | None = None
    channel_timeframe: Timeframe | None = None
    sentinel: Decimal | None = None
    """The unreachable target of a no-target arm, or ``None``."""


def _target(case: ReplayCase, policy: ExitPolicy) -> tuple[Decimal, Decimal | None]:
    """``(target1, sentinel)`` for the arm."""
    if policy.target is TargetRule.AS_DECIDED:
        return case.plan.target1, None
    if policy.target is TargetRule.TARGET2:
        if len(case.targets) < 2:
            raise ArmNotBuildable("target2_missing")
        return to_db_scale(case.targets[1]), None
    if policy.target is TargetRule.TARGET3:
        if len(case.targets) < 3:
            raise ArmNotBuildable("target3_missing")
        return to_db_scale(case.targets[2]), None
    reference = case.plan.reference_price
    if reference is None:
        raise ArmNotBuildable("reference_price_missing")
    sentinel = to_db_scale(no_target_level(reference))
    return sentinel, sentinel


def _invalidation(
    case: ReplayCase, policy: ExitPolicy
) -> tuple[Decimal | None, Timeframe | None, ConsecutiveCloseObserver | None]:
    """``(native level, native timeframe, observer)`` for the arm."""
    level, timeframe = case.plan.invalidation_level, case.plan.invalidation_timeframe
    if policy.invalidation is InvalidationRule.AS_DECIDED:
        return level, timeframe, None
    if policy.invalidation is InvalidationRule.NONE:
        return None, None, None
    if policy.invalidation is InvalidationRule.TWO_CLOSES:
        if level is None or timeframe is None:
            return None, None, None
        required = int(policy.parameters["required_closes"])
        observer = ConsecutiveCloseObserver(level=level, timeframe=timeframe, required=required)
        # The native observation is switched off precisely because this policy
        # *replaces* it; leaving it on would fire on the first close.
        return None, None, observer
    if level is None or timeframe is None:
        return None, None, None
    if case.atr0 is None:
        raise ArmNotBuildable("atr0_missing")
    buffer_atr = Decimal(policy.parameters["buffer_atr"])
    return to_db_scale(buffered_level(level, case.atr0, buffer_atr)), timeframe, None


def build_arm(case: ReplayCase, policy: ExitPolicy) -> ArmSpec:
    """The arm ``policy`` runs over ``case``, or :class:`ArmNotBuildable`."""
    target1, sentinel = _target(case, policy)
    level, timeframe, consecutive = _invalidation(case, policy)
    plan = replace(
        case.plan,
        target1=target1,
        invalidation_level=level,
        invalidation_timeframe=timeframe,
    )
    channel = None if policy.channel is None else ChannelObserver(lookback=policy.channel.lookback)
    return ArmSpec(
        policy=policy,
        plan=plan,
        consecutive=consecutive,
        channel=channel,
        channel_timeframe=None if policy.channel is None else policy.channel.timeframe,
        sentinel=sentinel,
    )
