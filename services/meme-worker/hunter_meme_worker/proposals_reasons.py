"""``meme_proposals.reasons`` — which rule fired and the value of every
feature it read: the decomposition of a proposal (split from
:mod:`hunter_meme_worker.proposals` in T4.16 for the 350-line budget; that
module re-exports :func:`gate_reasons`).

Every block after the first is listed **only when the gate asked for it**,
so an EXP-M1 proposal's ``reasons`` read exactly as they did the day the set
was frozen: the line (T4.10), the hype (T4.10), the flow and the holders
(T4.16, EXP-M5), the pedigree (T4.16, EXP-M6 — cross-cutting, listed whenever
the set applies it) and the series the row came from (only for the 15-second
clock).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from hunter_indicators.meme.rules import EntryFeatures, participation_pct
from hunter_meme_worker.lab_models import RuleSetSpec, money_str, optional_money_str

if TYPE_CHECKING:
    from hunter_indicators.meme.pedigree import PedigreeFeatures, PedigreeGate

__all__ = ["gate_reasons"]


def gate_reasons(
    features: EntryFeatures,
    spec: RuleSetSpec,
    *,
    pedigree: PedigreeFeatures | None = None,
    pedigree_gate: PedigreeGate | None = None,
    series: str | None = None,
) -> list[dict[str, Any]]:
    """Which rule fired and the value of every feature it read — the decomposition."""
    gate = spec.gate
    share = participation_pct(features.intended_size_sol, features.curve_volume_1m_sol)
    progress = features.progress_pct
    rule: dict[str, Any] = {"rule": f"{gate.key}/{gate.version}"}
    if series is not None:
        rule["series"] = series
    reasons: list[dict[str, Any]] = [
        rule,
        {"feature": "age_s", "value": features.age_s, "window": [gate.min_age_s, gate.max_age_s]},
        {
            "feature": "curve_progress_pct",
            "value": optional_money_str(progress),
            "window": [money_str(gate.min_progress_pct), money_str(gate.max_progress_pct)],
        },
        {"feature": "creator_net_seller", "value": features.creator_net_seller},
        {
            "feature": "participation_pct",
            "value": optional_money_str(share),
            "cap": money_str(gate.max_participation_pct),
        },
    ]
    if gate.require_higher_lows or gate.require_breakout_15m or gate.max_distance_to_support_pct:
        reasons.append(
            {
                "feature": "line",
                "higher_lows": features.higher_lows,
                "breakout_15m": features.breakout_15m,
                "distance_to_support_pct": optional_money_str(features.distance_to_support_pct),
                "line_reason": features.line_reason,
                "band": [
                    optional_money_str(gate.min_distance_to_support_pct),
                    optional_money_str(gate.max_distance_to_support_pct),
                ],
            }
        )
    if gate.min_hype_score is not None:
        reasons.append(
            {
                "feature": "hype_score",
                "value": optional_money_str(features.hype_score),
                "hype_reason": features.hype_reason,
                "min": money_str(gate.min_hype_score),
                "dev_share": optional_money_str(features.dev_share),
                "dev_share_reason": features.dev_share_reason,
                "snipers": features.snipers,
            }
        )
    asks_flow = (
        gate.require_positive_flow
        or gate.min_unique_buyers is not None
        or gate.max_sells_to_buys is not None
        or gate.require_holders_rising
        or gate.require_progress_rising
    )
    if asks_flow:
        reasons.append(
            {
                "feature": "flow",
                "net_sol_flow_1m": optional_money_str(features.net_sol_flow_1m),
                "mcap_delta_60s": optional_money_str(features.mcap_delta_60s),
                "buys_1m": features.buys_1m,
                "sells_1m": features.sells_1m,
                "unique_buyers_1m": features.unique_buyers_1m,
                "tape_reason": features.tape_reason,
                "holders_rising": features.holders_rising,
                "holders_reason": features.holders_reason,
                "progress_rising": features.progress_rising,
                "min_unique_buyers": gate.min_unique_buyers,
                "max_sells_to_buys": optional_money_str(gate.max_sells_to_buys),
                "snipers": features.snipers,
                "dev_share": optional_money_str(features.dev_share),
            }
        )
    if pedigree is not None and pedigree_gate is not None:
        reasons.append(
            {
                "feature": "pedigree",
                "rule": f"{pedigree_gate.key}/{pedigree_gate.version}",
                "creator_prior_mints_1h": pedigree.creator_prior_mints_1h,
                "symbol_dup_24h": pedigree.symbol_dup_24h,
                "max_creator_prior_mints_1h": pedigree_gate.max_creator_prior_mints_1h,
                "max_symbol_dup_24h": pedigree_gate.max_symbol_dup_24h,
            }
        )
    return reasons
