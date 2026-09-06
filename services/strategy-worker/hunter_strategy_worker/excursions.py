"""Honest MFE/MAE — SHADOW-LAB.md "Decisão conjunta" §5.

OHLC says *where* a bar went, never *when*, and a tracking that has not ended
has not shown its extremes yet. So the canonical ``mfe``/``mae`` are **null**
unless three things hold at once, and the partial answer lives here with its
bounds and its coverage instead of a confident number nobody can defend:

1. the tracking is **terminal** — a censored or still-open tracking has an
   unknown tail, and any extreme could be in it, so its upper bound is ``null``
   (unbounded), not "the largest one seen so far";
2. the bars that *are* known cover the whole position — no hole;
3. the exit bar is not ambiguous. Bars that ended with the tracking still open
   are *complete*: their extremes happened entirely while the position was on.
   The bar an intrabar exit happened in is not: its high and low may have come
   before or after the exit, so it only ever raises the upper bound.

Two more rules the reviews forced, each fixing a number that looked certain:

- **``mfe_ts``/``mae_ts`` are always ``null``.** Knowing the value of a bar's
  high does not locate it in the minute. What *is* known is the bar, and that
  goes to ``mfe_bar``/``mae_bar`` as a window, never as an instant (Astra,
  S2 diff review, must-fix 2).
- the excursion is measured against the **observed** price, not the synthetic
  exit. On a favourable gap the trade is credited at ``target1`` while the
  market opened higher; the higher price is a real excursion the position lived
  through, and capping it there would understate it (must-fix 4).

A proven touch is a lower bound: exiting at ``target1`` proves the favourable
excursion reached it, exiting at the stop proves the adverse one did. With no
complete bars there is no partial reading at all: ``null``, never a fabricated
zero. MAE is always a positive magnitude.

Guiding scenario of the plan: entry 100, stop 99, target 102, one bar with low
98 and high 103 -> ``mfe = null``, ``bounds.mfe = [0, 3]``, ``ambiguous``.
"""

from __future__ import annotations

from decimal import Decimal, localcontext
from typing import TYPE_CHECKING, Any

from hunter_core.domain.enums import OutcomeResult, ShadowTrackingState
from hunter_core.strategies.numeric import CONTEXT

if TYPE_CHECKING:
    from hunter_strategy_worker.walker import Progress, TrackingPlan

METHOD = "ohlc_complete_bars_v1"
UNIT = "price"
_ZERO = Decimal(0)
_MINUTE_S = 60

__all__ = ["METHOD", "UNIT", "build_excursions"]


def _positive(value: Decimal) -> Decimal:
    return value if value > _ZERO else _ZERO


def _bars_total(progress: Progress) -> int | None:
    """How many 1m bars the position spans, or ``None`` when that is unknown.

    A censored or still-open tracking has no end yet, so "how many bars it
    lasted" has no answer — reporting the bars seen as the total would present
    partial coverage as full coverage (Astra, S2 diff review, must-fix 3).
    """
    if progress.tracking_state is not ShadowTrackingState.TERMINAL:
        return None
    first, last = progress.first_bar_open, progress.window_last_open
    if first is None or last is None:
        return 0
    return int((last - first).total_seconds()) // _MINUTE_S + 1


def _unavailable(reason: str) -> dict[str, Any]:
    return {
        "unit": UNIT,
        "method": METHOD,
        "available": False,
        "reason": reason,
        "coverage": {"bars_known": 0, "bars_total": 0},
        "mfe": None,
        "mae": None,
        "mfe_ts": None,
        "mae_ts": None,
        "mfe_bar": None,
        "mae_bar": None,
        "mfe_complete_bars": None,
        "mae_complete_bars": None,
        "bounds": {"mfe": None, "mae": None},
        "bar_windows": None,
        "ambiguous": False,
        "initial_risk": None,
        "reference_price": None,
    }


def build_excursions(progress: Progress, plan: TrackingPlan) -> dict[str, Any]:
    """The ``signal_outcomes.meta.excursions`` object for ``progress``."""
    entry = progress.entry
    if entry is None:
        return _unavailable(progress.no_entry_reason or "no_entry")
    ended = progress.tracking_state is ShadowTrackingState.TERMINAL
    with localcontext(CONTEXT):
        mfe_complete = (
            None if progress.complete_high is None else _positive(progress.complete_high - entry)
        )
        mae_complete = (
            None if progress.complete_low is None else _positive(entry - progress.complete_low)
        )
        low_mfe = mfe_complete if mfe_complete is not None else _ZERO
        low_mae = mae_complete if mae_complete is not None else _ZERO
        high_mfe: Decimal | None = low_mfe
        high_mae: Decimal | None = low_mae

        if ended and progress.exit_at_open:
            observed = progress.exit_observed or progress.exit_base
            if observed is not None:
                low_mfe = max(low_mfe, _positive(observed - entry))
                low_mae = max(low_mae, _positive(entry - observed))
            high_mfe, high_mae = low_mfe, low_mae
        elif ended and progress.exit_base is not None:
            if progress.result is OutcomeResult.TARGET:
                low_mfe = max(low_mfe, _positive(plan.target1 - entry))
            if progress.result is OutcomeResult.STOP:
                low_mae = max(low_mae, _positive(entry - plan.stop))
            bar_high, bar_low = progress.exit_bar_high, progress.exit_bar_low
            high_mfe = max(low_mfe, _positive(bar_high - entry)) if bar_high is not None else None
            high_mae = max(low_mae, _positive(entry - bar_low)) if bar_low is not None else None
        else:
            # Not terminal: the rest of the trade has not happened (or cannot be
            # recovered), and any extreme could be in it. Unbounded above.
            high_mfe = high_mae = None

        determined_mfe = high_mfe is not None and high_mfe == low_mfe
        determined_mae = high_mae is not None and high_mae == low_mae
        initial_risk = entry - plan.stop

    return {
        "unit": UNIT,
        "method": METHOD,
        "available": True,
        "coverage": {
            "bars_known": progress.bars_in_position,
            "bars_total": _bars_total(progress),
        },
        "mfe": low_mfe if determined_mfe else None,
        "mae": low_mae if determined_mae else None,
        "mfe_ts": None,
        "mae_ts": None,
        "mfe_bar": progress.complete_high_ts,
        "mae_bar": progress.complete_low_ts,
        "mfe_complete_bars": mfe_complete,
        "mae_complete_bars": mae_complete,
        "bounds": {"mfe": [low_mfe, high_mfe], "mae": [low_mae, high_mae]},
        "bar_windows": {
            "first_open": progress.first_bar_open,
            "last_open": progress.window_last_open,
            "exit_bar_open": progress.exit_bar_open,
        },
        "ambiguous": not (determined_mfe and determined_mae),
        "initial_risk": initial_risk,
        "reference_price": plan.reference_price,
    }
