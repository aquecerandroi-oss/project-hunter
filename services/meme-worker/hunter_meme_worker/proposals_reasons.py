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

from hunter_indicators.meme.pedigree_e2b import E2B_V1
from hunter_indicators.meme.rules import EntryFeatures, participation_pct
from hunter_meme_worker.absorb_rules import absorb_reason_block
from hunter_meme_worker.lab_models import RuleSetSpec, money_str, optional_money_str

if TYPE_CHECKING:
    from hunter_indicators.meme.event_gate import EventFeatures
    from hunter_indicators.meme.identity import IdentityFeatures
    from hunter_indicators.meme.pedigree import PedigreeFeatures, PedigreeGate
    from hunter_indicators.meme.pedigree_e2b import E2bFeatures
    from hunter_meme_worker.absorb import AbsorbFeatures

__all__ = ["gate_reasons"]


def gate_reasons(
    features: EntryFeatures,
    spec: RuleSetSpec,
    *,
    pedigree: PedigreeFeatures | None = None,
    pedigree_gate: PedigreeGate | None = None,
    series: str | None = None,
    identity: IdentityFeatures | None = None,
    event: EventFeatures | None = None,
    e2b: E2bFeatures | None = None,
    absorb: AbsorbFeatures | None = None,
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
        or gate.max_buys_1m is not None  # T4.80: the ceiling belongs beside the count
    )
    if asks_flow:
        flow: dict[str, Any] = {
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
        if gate.max_buys_1m is not None:
            # T4.80: only when the set asks it — a frozen decomposition keeps
            # exactly the keys it was written with.
            flow["max_buys_1m"] = gate.max_buys_1m
        reasons.append(flow)
    if pedigree is not None and pedigree_gate is not None:
        reasons.append(
            {
                "feature": "pedigree",
                "rule": f"{pedigree_gate.key}/{pedigree_gate.version}",
                "creator_prior_mints_1h": pedigree.creator_prior_mints_1h,
                "symbol_dup_24h": pedigree.symbol_dup_24h,
                "max_creator_prior_mints_1h": pedigree_gate.max_creator_prior_mints_1h,
                "max_symbol_dup_24h": pedigree_gate.max_symbol_dup_24h,
                # T4.24 (EXP-M6, braço 2): recorded whenever the pedigree block
                # is, regardless of whether this set applies the exclusion.
                "creator_prior_dump_count": pedigree.creator_prior_dump_count,
                "creator_prior_dead_count": pedigree.creator_prior_dead_count,
            }
        )
    # T4.31 (EXP-M9): the E2-b decomposition — the two legs, the guard and the
    # frozen thresholds — only for the set that turns the criterion on.
    if e2b is not None and spec.pedigree_e2b:
        reasons.append(
            {
                "feature": "pedigree_e2b",
                "rule": f"{E2B_V1.key}/{E2B_V1.version}",
                "top_buyer_share": optional_money_str(e2b.top_buyer_share),
                "buyers": e2b.buyers,
                "fill_seconds": e2b.fill_seconds,
                "tape_reason": e2b.tape_reason,
                **E2B_V1.as_parameters(),
            }
        )
    # T4.26 (EXP-M8): like every other optional criterion, the block is
    # recorded only when the set actually asks the question — a set that does
    # not read ``require_twitter``/``require_event`` keeps its frozen
    # decomposition exactly as it was (EXP-M1's own invariant).
    if identity is not None and spec.require_twitter:
        reasons.append(
            {
                "feature": "identity",
                "has_twitter": identity.has_twitter,
                "twitter_kind": identity.twitter_kind,
                "twitter_post_age_s": identity.twitter_post_age_s,
                "twitter_reuse_count": identity.twitter_reuse_count,
                "has_website": identity.has_website,
                "has_telegram": identity.has_telegram,
                "description_len": identity.description_len,
            }
        )
    # T4.27: Mayhem is excluded by default, but a frozen set's decomposition must read
    # exactly as the day it was frozen (EXP-M1's invariant) — the block appears only when
    # the set spells ``exclude_mayhem`` out in its params.
    if spec.declares_mayhem:
        reasons.append(
            {"feature": "mayhem", "is_mayhem": features.is_mayhem, "excluded": gate.exclude_mayhem}
        )
    if event is not None and spec.require_event:
        reasons.append(
            {
                "feature": "event",
                "kind": event.kind,
                "confidence": event.confidence,
                "title": event.title,
                "source": event.source,
                "observed_at": None if event.observed_at is None else event.observed_at.isoformat(),
                "match_kind": event.match_kind,
            }
        )
    # T4.79 (EXP-M22): the absorption block, only for a set that asks.
    if spec.require_absorb_confirmed or spec.require_absorb_sell_seen:
        reasons.append(absorb_reason_block(absorb))
    return reasons
