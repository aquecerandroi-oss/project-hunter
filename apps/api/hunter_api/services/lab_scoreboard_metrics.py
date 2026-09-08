"""Pure ``Decimal`` math the scoreboard needs beyond ``lab_summary_metrics.py``
— no IO, no float. T3.18: ``worst_streak``, ``max_drawdown_r`` and the
mechanical verdict rule are new to this brief; everything else (``is_evaluable``,
``rate``, ``expectancy``, ``profit_factor``, ``sum_of``, ``touch_counts``) is
reused as-is from ``lab_summary_metrics.py`` by ``services/lab_scoreboard.py`` —
the brief's "reuse the plantão's definitions, do not invent new ones".

T3.18d: ``compute_verdict`` no longer implements the mechanical rule itself —
it delegates to ``hunter_indicators.replication.stats.verdict_from_values``,
the same function ``scoreboard_verdict`` calls for the replication report.
Two packages agreeing on a rule by test vigilance instead of by construction
is exactly what let the scoreboard and the replication report disagree on the
same population once (Astra, 2026-09-08, MEDIUM; T3.18c review).
"""

from __future__ import annotations

from decimal import Decimal
from typing import Literal, cast

from hunter_api.services.lab_summary_metrics import quantize4
from hunter_indicators.replication import verdict_from_values

__all__ = ["Verdict", "compute_verdict", "max_drawdown_r", "worst_streak"]

Verdict = Literal["inconclusivo", "validada", "reprovada"]


def worst_streak(ordered_r: list[Decimal]) -> int:
    """Longest run of consecutive net-losing outcomes (``R_net < 0``), in the
    order given (caller sorts by ``exit_ts``). ``0`` when there is no losing
    streak at all (empty series or every outcome breaks even or wins).
    """
    longest = current = 0
    for value in ordered_r:
        if value < 0:
            current += 1
            longest = max(longest, current)
        else:
            current = 0
    return longest


def max_drawdown_r(ordered_r: list[Decimal]) -> Decimal:
    """Max peak-to-trough drop of the cumulative-R curve, in R (never
    negative — a drawdown is a magnitude). ``0`` when the series never falls
    below its running peak (including the empty series: no curve, no drop).
    """
    peak = Decimal(0)
    cumulative = Decimal(0)
    worst = Decimal(0)
    for value in ordered_r:
        cumulative += value
        peak = max(peak, cumulative)
        worst = max(worst, peak - cumulative)
    return quantize4(worst)


def compute_verdict(
    *,
    mature: bool,
    expectancy_r: Decimal | None,
    profit_factor: Decimal | None,
    pf_reason: str | None,
) -> Verdict:
    """SHADOW-LAB.md's mechanical rule (brief T3.18, item 1), delegated to
    ``hunter_indicators.replication.stats.verdict_from_values`` (T3.18d):

    - not mature (< 100 evaluable outcomes or < 30 distinct days) ->
      ``inconclusivo``, regardless of the numbers;
    - mature and ``expectancy_r > 0`` and ``profit_factor > 1`` ->
      ``validada``;
    - mature, anything else -> ``reprovada``.

    ``profit_factor`` is ``None`` with ``pf_reason == "no_losses"`` when the
    version has zero losing outcomes (Σ losses = 0): the ratio is undefined
    in the strict sense but trivially "greater than 1" — a losing side of
    zero cannot make the version fail this rule. ``pf_reason == "no_sample"``
    (empty population) cannot occur here: maturity already requires >= 100
    outcomes with a known ``r_multiple``, so the profit-factor sample is
    never empty when ``mature`` is ``True``. The same holds for
    ``expectancy_r``, which is never ``None`` when ``mature`` is ``True``.

    ``pf_reason`` speaks this module's vocabulary (``"no_losses"``, from
    ``lab_summary_metrics.profit_factor``), not the pure package's
    (``PF_NO_LOSSES == "sem_perdas"``) — translating the string into the
    boolean ``verdict_from_values`` expects is this function's whole job now.
    """
    result = verdict_from_values(
        mature=mature,
        expectancy_r=expectancy_r,
        profit_factor=profit_factor,
        no_losses=pf_reason == "no_losses",
    )
    return cast(Verdict, result)
