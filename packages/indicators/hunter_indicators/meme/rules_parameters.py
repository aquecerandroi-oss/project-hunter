"""The registered parameter document of one
:class:`~hunter_indicators.meme.rules.EntryGate` — ``as_parameters``, split out
of ``rules.py`` for the 350-line budget (T4.80, the same move ``rules_validation``
made in T4.23). ``EntryGate.as_parameters`` calls :func:`gate_parameters` and
does nothing else; the document is byte-for-byte what it was before the split.

The contract it keeps: **a criterion the gate does not ask is not listed**, so
EXP-M1's frozen parameters read today exactly as they did the day they were
frozen, and every value is a string (what a persisted decomposition stores).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Mapping

    from hunter_indicators.meme.rules import EntryGate

__all__ = ["gate_parameters"]


def gate_parameters(gate: EntryGate) -> Mapping[str, str]:
    """Every threshold as a string; the optional ones only when set."""
    parameters = {
        "min_age_s": str(gate.min_age_s),
        "max_age_s": str(gate.max_age_s),
        "min_progress_pct": str(gate.min_progress_pct),
        "max_progress_pct": str(gate.max_progress_pct),
        "max_participation_pct": str(gate.max_participation_pct),
        "require_creator_not_net_seller": str(gate.require_creator_not_net_seller),
    }
    optional: dict[str, object] = {
        "require_progress": None if gate.require_progress else False,
        "require_higher_lows": gate.require_higher_lows or None,
        "require_breakout_15m": gate.require_breakout_15m or None,
        "min_distance_to_support_pct": gate.min_distance_to_support_pct,
        "max_distance_to_support_pct": gate.max_distance_to_support_pct,
        "min_hype_score": gate.min_hype_score,
        "max_dev_share": gate.max_dev_share,
        "dev_share_unknown_allowed": gate.dev_share_unknown_allowed or None,
        "max_snipers": gate.max_snipers,
        "min_snipers": gate.min_snipers,
        "max_top10_share": gate.max_top10_share,
        "min_top10_share": gate.min_top10_share,
        "require_positive_flow": gate.require_positive_flow or None,
        "min_unique_buyers": gate.min_unique_buyers,
        "max_sells_to_buys": gate.max_sells_to_buys,
        "require_holders_rising": gate.require_holders_rising or None,
        "require_progress_rising": gate.require_progress_rising or None,
        "min_holders": gate.min_holders,
        "holders_rising_or_flat": gate.holders_rising_or_flat or None,
        "creator_unknown_allowed_if_dev_measured": (
            gate.creator_unknown_allowed_if_dev_measured or None
        ),
        "progress_or_mcap_rising": gate.progress_or_mcap_rising or None,
        "exclude_mayhem": None if gate.exclude_mayhem else False,
        "max_recent_drawdown_pct": gate.max_recent_drawdown_pct,
        "min_early_retention_pct": gate.min_early_retention_pct,
        "min_early_age_s": gate.min_early_age_s,
        "min_new_wallets_30s": gate.min_new_wallets_30s,
        "max_quick_flip_share_30s": gate.max_quick_flip_share_30s,
        # T4.80 (R65/KB-0147): a count, listed only when the set asks it.
        "max_buys_1m": gate.max_buys_1m,
    }
    if gate.max_recent_drawdown_pct is not None:
        optional["recent_drawdown_window_s"] = gate.recent_drawdown_window_s
        optional["recent_drawdown_max_gap_s"] = gate.recent_drawdown_max_gap_s
    parameters.update({k: str(v) for k, v in optional.items() if v is not None})
    return parameters
