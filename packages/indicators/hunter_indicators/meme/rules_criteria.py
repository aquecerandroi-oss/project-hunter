"""The optional criteria of the entry gate — the line (EXP-M2), the hype
(EXP-M3) and, since T4.16, the **flow and the holders** (EXP-M5) — split out
of :mod:`hunter_indicators.meme.rules` for the 350-line budget. Every function
here answers with named refusals over one :class:`~.rules.EntryFeatures` and
one :class:`~.rules.EntryGate`, and a gate that does not ask a question never
refuses over it.

The flow criteria read what the 21 bets of 12/09 lacked (the study,
``obsidian/03-TRADING/Meme/Estudo-2026-09-12-21-apostas.md`` §1): net demand
instead of churn, ten distinct buyers instead of one to seven holders,
sells at most 0,6 of the buys, holders and progress **rising**. Every one of
them refuses an unknown input by name — a missing tape is not "nobody sold".

T4.21 (EXP-M5 arm 2, the funnel of 12/09 19:1x BRT): a floor on the holders
count, "not falling" in place of "rising" (``holders_falling`` only when the
newest reading is below the previous one), a measured ``dev_share`` vouching
for an unknown creator, and ``mcap_delta_60s > 0`` as an alternative to
progress rising — each behind its own switch, each unknown still refused by
name (one reading is not "flat", it is ``holders_too_few_readings``).
"""

from __future__ import annotations

from decimal import Decimal, localcontext
from typing import TYPE_CHECKING

from hunter_core.strategies.numeric import CONTEXT

if TYPE_CHECKING:
    from hunter_indicators.meme.rules import EntryFeatures, EntryGate

__all__ = ["creator_refusals", "flow_refusals", "hype_refusals", "line_refusals"]


def _dev_share_vouches(features: EntryFeatures, gate: EntryGate) -> bool:
    """T4.21: an unknown creator passes **only** when the gate says so, the
    dev's share was measured and it is within ``max_dev_share`` — a missing
    ``dev_share`` vouches for nothing, and a known seller is never asked."""
    return (
        gate.creator_unknown_allowed_if_dev_measured
        and gate.max_dev_share is not None
        and features.dev_share is not None
        and features.dev_share <= gate.max_dev_share
    )


def creator_refusals(features: EntryFeatures, gate: EntryGate) -> list[str]:
    """Off means the feature is not a criterion at all — the falsification arm.

    On (the default) refuses both a known net seller and an unknown one: a gate
    that let the unknown through would be reading a missing feed as "the dev did
    not sell", which is the confusion Astra's MUST-FIX 1 names. T4.21's one
    declared exception: a measured ``dev_share`` within the ceiling vouches
    for an unknown creator — never for a known seller.
    """
    if not gate.require_creator_not_net_seller:
        return []
    if features.creator_net_seller is None:
        return [] if _dev_share_vouches(features, gate) else ["creator_net_seller_unknown"]
    return ["creator_is_net_seller"] if features.creator_net_seller else []


def line_refusals(features: EntryFeatures, gate: EntryGate) -> list[str]:
    """EXP-M2: the line must exist, its lows must rise, the previous window's
    high must be taken out and the price must sit in the band above support."""
    asks_line = (
        gate.require_higher_lows
        or gate.require_breakout_15m
        or gate.min_distance_to_support_pct is not None
        or gate.max_distance_to_support_pct is not None
    )
    if not asks_line:
        return []
    if features.higher_lows is None or features.distance_to_support_pct is None:
        return [f"line_{features.line_reason or 'unknown'}"]
    refusals: list[str] = []
    if gate.require_higher_lows and not features.higher_lows:
        refusals.append("no_higher_lows")
    if gate.require_breakout_15m:
        if features.breakout_15m is None:
            refusals.append("breakout_unknown")
        elif not features.breakout_15m:
            refusals.append("no_breakout")
    low, high = gate.min_distance_to_support_pct, gate.max_distance_to_support_pct
    if low is not None and features.distance_to_support_pct < low:
        refusals.append("distance_below_min")
    if high is not None and features.distance_to_support_pct > high:
        refusals.append("distance_above_max")
    return refusals


def hype_refusals(features: EntryFeatures, gate: EntryGate) -> list[str]:
    """EXP-M3: the documented score floor, the dev's share and the snipers."""
    refusals: list[str] = []
    if gate.min_hype_score is not None:
        if features.hype_score is None:
            refusals.append(f"hype_{features.hype_reason or 'unknown'}")
        elif features.hype_score < gate.min_hype_score:
            refusals.append("hype_below_min")
    if gate.max_dev_share is not None:
        if features.dev_share is None:
            if not (gate.dev_share_unknown_allowed and features.dev_share_reason):
                refusals.append("dev_share_unknown")
        elif features.dev_share > gate.max_dev_share:
            refusals.append("dev_share_above_max")
    if gate.max_snipers is not None:
        if features.snipers is None:
            refusals.append("snipers_unknown")
        elif features.snipers > gate.max_snipers:
            refusals.append("snipers_above_max")
    return refusals


def _flow_positive(features: EntryFeatures) -> bool | None:
    """``net_sol_flow_1m > 0`` when the tape spoke; else ``mcap_delta_60s > 0``
    when the 15-second series did (the brief's "ou"); else unknown."""
    if features.net_sol_flow_1m is not None:
        return features.net_sol_flow_1m > 0
    if features.mcap_delta_60s is not None:
        return features.mcap_delta_60s > 0
    return None


def _sells_to_buys(features: EntryFeatures, ceiling: Decimal) -> str | None:
    if features.buys_1m is None or features.sells_1m is None:
        return "sells_ratio_unknown"
    if features.buys_1m == 0:
        return "no_buys"
    with localcontext(CONTEXT):
        ratio = Decimal(features.sells_1m) / Decimal(features.buys_1m)
    return "sells_ratio_above_max" if ratio > ceiling else None


def _holders_unknown(features: EntryFeatures) -> str:
    return f"holders_{features.holders_reason or 'unknown'}"


def _holders_trend_refusal(features: EntryFeatures, gate: EntryGate) -> str | None:
    """``holders_not_rising`` — or, with ``holders_rising_or_flat``,
    ``holders_falling`` only when the newest reading is below the previous
    one; a trend without its two readings cannot tell flat from falling."""
    if features.holders_rising is None:
        return _holders_unknown(features)
    if features.holders_rising:
        return None
    if not gate.holders_rising_or_flat:
        return "holders_not_rising"
    if features.holders is None or features.holders_prev is None:
        return _holders_unknown(features)
    return "holders_falling" if features.holders < features.holders_prev else None


def _holders_refusals(features: EntryFeatures, gate: EntryGate) -> list[str]:
    """The floor on the count and the trend, an unknown named once."""
    refusals: list[str] = []
    if gate.min_holders is not None:
        if features.holders is None:
            refusals.append(_holders_unknown(features))
        elif features.holders < gate.min_holders:
            refusals.append("holders_below_min")
    if gate.require_holders_rising:
        refusal = _holders_trend_refusal(features, gate)
        if refusal is not None and refusal not in refusals:
            refusals.append(refusal)
    return refusals


def _progress_trend_refusal(features: EntryFeatures, gate: EntryGate) -> str | None:
    """Progress rising — or, with ``progress_or_mcap_rising``, the 60 s
    market-cap delta positive; ``progress_not_rising`` when a measured input
    said no and nothing said yes, ``progress_trend_unknown`` when nothing spoke."""
    if features.progress_rising:
        return None
    delta = features.mcap_delta_60s if gate.progress_or_mcap_rising else None
    if delta is not None and delta > 0:
        return None
    if features.progress_rising is None and delta is None:
        return "progress_trend_unknown"
    return "progress_not_rising"


def flow_refusals(features: EntryFeatures, gate: EntryGate) -> list[str]:
    """EXP-M5: net demand, distinct buyers, the sells/buys ceiling, holders and
    progress rising — each unknown refused by name."""
    refusals: list[str] = []
    if gate.require_positive_flow:
        positive = _flow_positive(features)
        if positive is None:
            refusals.append(f"flow_{features.tape_reason or 'unknown'}")
        elif not positive:
            refusals.append("flow_not_positive")
    if gate.min_unique_buyers is not None:
        if features.unique_buyers_1m is None:
            refusals.append("buyers_unknown")
        elif features.unique_buyers_1m < gate.min_unique_buyers:
            refusals.append("buyers_below_min")
    if gate.max_sells_to_buys is not None:
        refusal = _sells_to_buys(features, gate.max_sells_to_buys)
        if refusal is not None:
            refusals.append(refusal)
    refusals.extend(_holders_refusals(features, gate))
    if gate.require_progress_rising:
        refusal = _progress_trend_refusal(features, gate)
        if refusal is not None:
            refusals.append(refusal)
    return refusals
