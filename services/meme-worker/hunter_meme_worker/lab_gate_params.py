"""The entry gate of a ``meme_rule_sets`` row, parsed — ``_gate_from_params``,
moved out of :mod:`hunter_meme_worker.lab_models` for the 350-line budget
(T4.66; ``lab_models._gate_from_params`` keeps working as an alias). Every
key beyond T4.5's base is optional: absent = not a criterion, so the ``0022``
seeds parse exactly as they did the day they were frozen. Every decimal in
``params`` is a JSON **string**, read with ``Decimal(str(...))``.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from hunter_indicators.meme.rules import EntryGate
from hunter_meme_worker.lab_params import (
    bool_or,
    decimal_of,
    int_or,
    optional_count,
    optional_decimal,
    optional_int,
)

__all__ = ["gate_from_params"]


def gate_from_params(name: str, version: str, params: Mapping[str, Any]) -> EntryGate:
    """T4.5's gate plus the T4.10 criteria, each absent = not a criterion."""
    return EntryGate(
        key=str(params["gate_key"]),
        version=int(params["gate_version"]),
        description=f"{name}/{version}: {params['gate_key']} v{params['gate_version']}",
        min_age_s=int(params["min_age_s"]),
        max_age_s=int(params["max_age_s"]),
        min_progress_pct=decimal_of(params["min_progress_pct"]),
        max_progress_pct=decimal_of(params["max_progress_pct"]),
        max_participation_pct=decimal_of(params["max_participation_pct"]),
        require_creator_not_net_seller=bool(params.get("require_creator_not_net_seller", True)),
        require_progress=bool(params.get("require_progress", True)),
        require_higher_lows=bool(params.get("require_higher_lows", False)),
        require_breakout_15m=bool(params.get("require_breakout_15m", False)),
        min_distance_to_support_pct=optional_decimal(params.get("min_distance_to_support_pct")),
        max_distance_to_support_pct=optional_decimal(params.get("max_distance_to_support_pct")),
        min_hype_score=optional_decimal(params.get("min_hype_score")),
        max_dev_share=optional_decimal(params.get("max_dev_share")),
        dev_share_unknown_allowed=bool(params.get("dev_share_unknown_allowed", False)),
        max_snipers=optional_int(params.get("max_snipers")),
        # T4.23 (EXP-M5 arms 3/4): floors beside the ceilings, off unless the set says so.
        min_snipers=optional_int(params.get("min_snipers")),
        max_top10_share=optional_decimal(params.get("max_top10_share")),
        min_top10_share=optional_decimal(params.get("min_top10_share")),
        # T4.16 (EXP-M5): the flow and the holders, each absent = not a criterion.
        require_positive_flow=bool(params.get("require_positive_flow", False)),
        min_unique_buyers=optional_int(params.get("min_unique_buyers")),
        max_sells_to_buys=optional_decimal(params.get("max_sells_to_buys")),
        require_holders_rising=bool(params.get("require_holders_rising", False)),
        require_progress_rising=bool(params.get("require_progress_rising", False)),
        # T4.21 (EXP-M5 arm 2): four switches, off unless the set says so.
        min_holders=optional_int(params.get("min_holders")),
        holders_rising_or_flat=bool(params.get("holders_rising_or_flat", False)),
        creator_unknown_allowed_if_dev_measured=bool(
            params.get("creator_unknown_allowed_if_dev_measured", False)
        ),
        progress_or_mcap_rising=bool(params.get("progress_or_mcap_rising", False)),
        # T4.27: on unless the set says ``false`` — no arm wants Mayhem today.
        exclude_mayhem=bool_or(params.get("exclude_mayhem"), True),
        # T4.52b-2 (EXP-M13): the recent-drawdown guard, off unless the set names it.
        max_recent_drawdown_pct=optional_decimal(params.get("max_recent_drawdown_pct")),
        recent_drawdown_window_s=int_or(params.get("recent_drawdown_window_s"), 60),
        recent_drawdown_max_gap_s=int_or(params.get("recent_drawdown_max_gap_s"), 30),
        # T4.66 (EXP-M19): the crowd behind the rise, off unless the set names a key.
        min_early_retention_pct=optional_decimal(params.get("min_early_retention_pct")),
        min_early_age_s=optional_int(params.get("min_early_age_s")),
        min_new_wallets_30s=optional_int(params.get("min_new_wallets_30s")),
        max_quick_flip_share_30s=optional_decimal(params.get("max_quick_flip_share_30s")),
        # T4.80 (R65/KB-0147): the buy-count ceiling of the judged minute, off
        # unless the set names it. A **count**, so a decimal is refused here
        # rather than truncated by ``int()`` — see ``optional_count``.
        max_buys_1m=optional_count("max_buys_1m", params.get("max_buys_1m")),
    )
