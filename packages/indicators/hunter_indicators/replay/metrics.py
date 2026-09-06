"""The Lab's metrics, by the names the plan gave them (SHADOW-LAB.md §9).

Four different questions that are routinely collapsed into one "win rate":

- *taxa de alvo entre toques resolvidos* = ``target / (target + stop)``. Only
  resolved touches; an expiry or an invalidation is neither;
- *taxa de lucro líquido* = evaluable closings with ``R_net > 0`` over evaluable
  closings. Expiries and invalidations with a known result **do** count here;
- *expectancy líquida hipotética em R* = the mean ``R_net`` of that same
  population;
- *PF* = sum of positive ``R_net`` over the absolute sum of the negative ones,
  reported **with its denominator**, and ``None`` with a reason when there were
  no losses (an infinite profit factor is not a number to publish).

Everything is ``Decimal``; an outcome whose ``R_net`` could not be established
(funding unknown) is counted as *unevaluable*, never as zero.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal

__all__ = ["LabMetrics", "lab_metrics"]

_TARGET = "target"
_STOP = "stop"


@dataclass(frozen=True, slots=True)
class LabMetrics:
    """The named metrics of one arm, with every denominator visible."""

    total: int
    resolved_touches: int
    targets: int
    stops: int
    target_rate_among_resolved: Decimal | None
    target_rate_reason: str | None
    evaluable: int
    unevaluable: int
    net_wins: int
    net_win_rate: Decimal | None
    expectancy_r: Decimal | None
    sum_r: Decimal | None
    profit_factor: Decimal | None
    profit_factor_denominator: Decimal | None
    profit_factor_reason: str | None


def lab_metrics(outcomes: Sequence[tuple[str, Decimal | None]]) -> LabMetrics:
    """Aggregate ``(result, R_net)`` rows of one arm."""
    targets = sum(1 for result, _ in outcomes if result == _TARGET)
    stops = sum(1 for result, _ in outcomes if result == _STOP)
    resolved = targets + stops
    evaluable = [r for _result, r in outcomes if r is not None]
    positives = [r for r in evaluable if r > 0]
    negatives = [r for r in evaluable if r < 0]
    losses = -sum(negatives, start=Decimal(0))
    gains = sum(positives, start=Decimal(0))
    total_r = sum(evaluable, start=Decimal(0))
    return LabMetrics(
        total=len(outcomes),
        resolved_touches=resolved,
        targets=targets,
        stops=stops,
        target_rate_among_resolved=(
            None if resolved == 0 else Decimal(targets) / Decimal(resolved)
        ),
        target_rate_reason=None if resolved else "no_resolved_touches",
        evaluable=len(evaluable),
        unevaluable=len(outcomes) - len(evaluable),
        net_wins=len(positives),
        net_win_rate=(None if not evaluable else Decimal(len(positives)) / Decimal(len(evaluable))),
        expectancy_r=(None if not evaluable else total_r / Decimal(len(evaluable))),
        sum_r=(None if not evaluable else total_r),
        profit_factor=(None if losses == 0 else gains / losses),
        profit_factor_denominator=(None if not evaluable else losses),
        profit_factor_reason=(
            "no_evaluable_outcomes" if not evaluable else ("no_losses" if losses == 0 else None)
        ),
    )
