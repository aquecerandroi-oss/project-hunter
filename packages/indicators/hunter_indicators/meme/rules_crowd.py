"""EXP-M19's crowd criteria of the entry gate (T4.66) — the readings of
:mod:`hunter_indicators.meme.crowd` judged against four optional keys, each
off by default, each unknown refused by name (a feed that has not covered the
window is not "nobody flipped"):

- ``min_early_retention_pct`` (a **fraction**, ``0.70`` = the early wallets
  still hold 70 % of what they bought) → ``early_retention_below_min``;
- ``min_early_age_s`` (the retention must have lasted) → ``early_age_below_min``;
- ``min_new_wallets_30s`` → ``new_wallets_below_min``;
- ``max_quick_flip_share_30s`` (a fraction of the window's trades) →
  ``quick_flip_above_max`` (strict: a share **above** the ceiling refuses).

The retention and the age are one measurement (the early set), so they share
one unknown, ``early_retention_unknown``, emitted once when either criterion is
on and the set was not measured. Split out of ``rules_criteria`` for the
350-line budget, evaluated last by ``evaluate_entry``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from hunter_indicators.meme.rules import EntryFeatures, EntryGate

__all__ = ["crowd_refusals"]


def crowd_refusals(features: EntryFeatures, gate: EntryGate) -> list[str]:
    """EXP-M19 (T4.66): the four crowd criteria, each only when the gate asks."""
    refusals: list[str] = []
    asks_early = gate.min_early_retention_pct is not None or gate.min_early_age_s is not None
    if asks_early:
        if features.early_retention_pct is None or features.early_age_s is None:
            refusals.append("early_retention_unknown")
        else:
            if (
                gate.min_early_retention_pct is not None
                and features.early_retention_pct < gate.min_early_retention_pct
            ):
                refusals.append("early_retention_below_min")
            if gate.min_early_age_s is not None and features.early_age_s < gate.min_early_age_s:
                refusals.append("early_age_below_min")
    if gate.min_new_wallets_30s is not None:
        if features.new_wallets_30s is None:
            refusals.append("new_wallets_unknown")
        elif features.new_wallets_30s < gate.min_new_wallets_30s:
            refusals.append("new_wallets_below_min")
    if gate.max_quick_flip_share_30s is not None:
        if features.quick_flip_share_30s is None:
            refusals.append("quick_flip_unknown")
        elif features.quick_flip_share_30s > gate.max_quick_flip_share_30s:
            refusals.append("quick_flip_above_max")
    return refusals
