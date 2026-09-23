"""The entry gate of a curve position, as a pure function — and the home of the
exit rules' names (:mod:`hunter_indicators.meme.exits`, re-exported here so
``hunter_indicators.meme.rules:evaluate_entry+evaluate_exit`` stays the
``code_ref`` of every seeded rule set).

Registered the way a feature is (``key``, ``version``, ``parameters``,
``description``, ``inputs``): changing a threshold is a **new version**, never an
edit, because a rule set that changed meaning silently would make two runs of
an EXP-M* incomparable.

The entry gate answers one question — *may we buy this mint now?* — over a row of
features, and every "no" has a name. Several of those names are about our own
instrument rather than the market: ``progress_unknown``,
``creator_net_seller_unknown``, ``curve_volume_1m_unknown``, ``hype_unknown``,
``snipers_unknown``, ``line_*`` fire when the free sources have not produced the
input yet. Refusing while blind is the decision; reading a missing input as
"nobody sold", "nobody traded" or "the line is fine" is the mistake Astra's
review calls the gravest of the original design.

T4.10 adds the criteria of EXP-M2 (the line: ``higher_lows``, ``breakout_15m``,
``distance_to_support_pct`` in a band) and EXP-M3 (the hype probe:
``hype_score`` floor, ``dev_share`` ceiling — with the brief's one declared
exception, an unknown ``dev_share`` **with a reason** may pass — and a
``snipers`` ceiling). Every new criterion is **off by default**: a gate that does
not ask a question does not refuse over it, so EXP-M1's frozen gate reads
exactly as it did.

T4.16 adds the criteria of EXP-M5 (the flow and the holders), T4.21 the four
switches of its second arm and T4.23 the two floors of arms 3/4 — each off by
default, each documented where it lives: the optional criteria are in
:mod:`hunter_indicators.meme.rules_criteria` and the threshold validation in
:mod:`hunter_indicators.meme.rules_validation` (the 350-line budget); this
module keeps the gate, the features and the precedence of evaluation.

T4.27 adds ``exclude_mayhem`` — **on by default, in every set**: a Mayhem
coin's curve is moved by the agent's virtual SOL, not by demand, so its
``mcap_delta_60s``/``progress_rising`` are not the market speaking
(:mod:`hunter_indicators.meme.executable`). Refuses ``mayhem_curve`` when the
coin is known Mayhem and ``mayhem_unknown`` when the flag was not observed.

T4.52b-2 adds ``max_recent_drawdown_pct`` (EXP-M13, off by default) and moves
the base criteria beside the optional ones in ``rules_criteria`` (the budget).
T4.66 adds EXP-M19's four crowd keys (:mod:`hunter_indicators.meme.rules_crowd`).
T4.80 adds R65's ``max_buys_1m`` (:mod:`hunter_indicators.meme.rules_buys`),
also off by default, and moves ``as_parameters``'s document into
:mod:`hunter_indicators.meme.rules_parameters` (the 350-line budget).
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal
from typing import Final

from hunter_indicators.meme.exits import (
    EXIT_INPUTS,
    ExitDecision,
    ExitRules,
    ExitState,
    evaluate_exit,
    hit_curve_event,
    hit_dead,
    hit_line_break,
    hit_max_loss,
    hit_target,
    hit_time_stop,
    hit_trailing,
)
from hunter_indicators.meme.rules_buys import buys_refusals
from hunter_indicators.meme.rules_criteria import (
    age_refusals,
    creator_refusals,
    drawdown_refusals,
    flow_refusals,
    hype_refusals,
    line_refusals,
    mayhem_refusals,
    participation_pct,
    participation_refusals,
    progress_refusals,
)
from hunter_indicators.meme.rules_crowd import crowd_refusals
from hunter_indicators.meme.rules_parameters import gate_parameters
from hunter_indicators.meme.rules_validation import validate_entry_gate

__all__ = [
    "EXIT_INPUTS",
    "GATE_INPUTS",
    "EntryFeatures",
    "EntryGate",
    "ExitDecision",
    "ExitRules",
    "ExitState",
    "GateDecision",
    "evaluate_entry",
    "evaluate_exit",
    "hit_curve_event",
    "hit_dead",
    "hit_line_break",
    "hit_max_loss",
    "hit_target",
    "hit_time_stop",
    "hit_trailing",
    "participation_pct",
]

HUNDRED: Final = Decimal(100)
GATE_INPUTS: Final = (
    "meme_tokens.created_at",
    "meme_curve_snapshots.real_token_reserves",
    "meme_features_1m.creator_sold",
    "meme_features_1m.curve_volume_1m_sol",
    "meme_features_1m.higher_lows",
    "meme_features_1m.breakout_15m",
    "meme_features_1m.distance_to_support_pct",
    "meme_features_1m.hype_score",
    "meme_features_1m.dev_share",
    "meme_features_1m.snipers",
    "meme_features_1m.top10_share",
    "meme_features_1m.net_sol_flow_1m",
    "meme_features_1m.unique_buyers",
    "meme_features_1m.buys_1m",
    "meme_features_1m.sells_1m",
    "meme_features_1m.holders",
    "meme_features_15s.mcap_delta_60s",
    "meme_features_15s.holders_rising",
    "meme_features_15s.progress_delta_60s",
    "meme_features_15s.holders",
    "meme_features_15s.holders_prev",
    "meme_tokens.mayhem_enabled",
    "meme_curve_snapshots.real_sol_reserves",
    "solana_rpc_ws.trade_event",
)


@dataclass(frozen=True, slots=True)
class EntryGate:
    """One registered entry gate. ``version`` bumps whenever a threshold moves."""

    key: str
    version: int
    description: str
    min_age_s: int
    max_age_s: int
    min_progress_pct: Decimal
    max_progress_pct: Decimal
    max_participation_pct: Decimal
    require_creator_not_net_seller: bool = True
    require_progress: bool = True
    """Off: the progress window is not a criterion and an unknown progress is
    not a refusal (EXP-M3 buys before the denominator of a 30-second-old curve
    is known). On (the default): the window applies and unknown refuses."""
    require_higher_lows: bool = False
    require_breakout_15m: bool = False
    min_distance_to_support_pct: Decimal | None = None
    max_distance_to_support_pct: Decimal | None = None
    """A band on ``(mcap − support) / support``; either bound alone is legal."""
    min_hype_score: Decimal | None = None
    max_dev_share: Decimal | None = None
    dev_share_unknown_allowed: bool = False
    """The brief's one exception to "unknown refuses": ``dev_share ≤ 0,10 ou
    NULL com motivo``. Only meaningful with ``max_dev_share`` set."""
    max_snipers: int | None = None
    min_snipers: int | None = None
    """T4.23 (EXP-M5 arm 3): floor beside ``max_snipers``; unknown still refuses
    by name even with no ceiling set."""
    max_top10_share: Decimal | None = None
    """T4.22 (EXP-M7): ceiling on the top-10 holders' share (fraction); unknown refuses by reason."""
    min_top10_share: Decimal | None = None
    """T4.23 (EXP-M5 arm 4): floor beside ``max_top10_share``, same unknown reason."""
    require_positive_flow: bool = False
    """T4.16 (EXP-M5): ``net_sol_flow_1m > 0`` — or, when the tape is absent
    and the 15-second series speaks, ``mcap_delta_60s > 0``; unknown refuses."""
    min_unique_buyers: int | None = None
    max_sells_to_buys: Decimal | None = None
    """A ceiling on ``sells_1m / buys_1m`` (counts): churn is not demand."""
    require_holders_rising: bool = False
    require_progress_rising: bool = False
    min_holders: int | None = None
    holders_rising_or_flat: bool = False
    creator_unknown_allowed_if_dev_measured: bool = False
    progress_or_mcap_rising: bool = False
    """T4.21 (EXP-M5 arm 2): ``holders_below_min`` under the floor; with
    ``require_holders_rising``, only a **fall** between the two readings
    refuses (``holders_falling``); an unknown creator passes only when
    ``dev_share`` was measured and is within ``max_dev_share`` (a known net
    seller never passes); ``mcap_delta_60s > 0`` stands in for progress rising
    (``progress_not_rising`` only when neither)."""
    exclude_mayhem: bool = True
    """T4.27: refuse a Mayhem coin (``mayhem_curve``) and an unobserved flag
    (``mayhem_unknown``). On in every set; ``False`` is an arm's explicit word."""
    max_recent_drawdown_pct: Decimal | None = None
    recent_drawdown_window_s: int = 60
    recent_drawdown_max_gap_s: int = 30
    """T4.52b-2 (EXP-M13, KB-0118): a **fraction** (``0.50`` = half) the real
    SOL may have lost from its peak of the last ``recent_drawdown_window_s``;
    ``None`` = not a criterion. An observation older than
    ``recent_drawdown_max_gap_s`` is ``recent_drawdown_unknown`` (fail closed)."""
    min_early_retention_pct: Decimal | None = None
    min_early_age_s: int | None = None
    min_new_wallets_30s: int | None = None
    max_quick_flip_share_30s: Decimal | None = None
    """T4.66 (EXP-M19): the crowd (:mod:`hunter_indicators.meme.crowd`) — the
    early wallets' retention (fraction) held for at least so many seconds, a
    floor of new wallets in 30 s, a ceiling (fraction) on quick flips; each
    ``None`` = not a criterion, each unknown refused by name."""
    max_buys_1m: int | None = None
    """T4.80 (R65/KB-0147): a ceiling on the buy **count** of the 60 s ending
    at the decision instant (:mod:`hunter_indicators.meme.rules_buys`) — an
    ``int``, never a decimal. ``None`` = not a criterion; an unmeasured count
    refuses ``buys_1m_unknown``."""
    inputs: tuple[str, ...] = GATE_INPUTS

    def __post_init__(self) -> None:
        """Every threshold check lives in ``rules_validation`` (the 350-line budget)."""
        validate_entry_gate(self)

    def as_parameters(self) -> Mapping[str, str]:
        """Every threshold as a string — what a persisted decomposition stores.

        A criterion the gate does not ask is not listed: EXP-M1's registered
        parameters must read today exactly as they did the day they were frozen.
        The document itself is built in ``rules_parameters`` (the 350-line budget).
        """
        return gate_parameters(self)


@dataclass(frozen=True, slots=True)
class EntryFeatures:
    """One features row at one instant. ``None`` means *not observed*, never zero."""

    mint: str
    age_s: int | None
    progress_pct: Decimal | None
    creator_net_seller: bool | None
    curve_volume_1m_sol: Decimal | None
    intended_size_sol: Decimal
    curve_complete: bool = False
    migrated: bool = False
    higher_lows: bool | None = None
    breakout_15m: bool | None = None
    distance_to_support_pct: Decimal | None = None
    line_reason: str | None = None
    """Why the line columns are ``None`` (``lines.LINE_REASONS``); named in the
    refusal so the heartbeat counts blindness apart from a line that said no."""
    hype_score: Decimal | None = None
    hype_reason: str | None = None
    dev_share: Decimal | None = None
    dev_share_reason: str | None = None
    snipers: int | None = None
    top10_share: Decimal | None = None
    top10_reason: str | None = None
    net_sol_flow_1m: Decimal | None = None
    mcap_delta_60s: Decimal | None = None
    """T4.16: the minute's net SOL flow from the tape, and — on the 15-second
    series — the 60 s market-cap delta the gate reads when the tape is absent."""
    buys_1m: int | None = None
    sells_1m: int | None = None
    unique_buyers_1m: int | None = None
    tape_reason: str | None = None
    """Why the tape columns are ``None`` (``no_trade_feed``, ``not_polled``…),
    named in the refusal so blindness is counted apart from a flow that said no."""
    holders_rising: bool | None = None
    holders_reason: str | None = None
    progress_rising: bool | None = None
    holders: int | None = None
    holders_prev: int | None = None
    """T4.21: the two holders readings behind ``holders_rising`` (floor, "not falling")."""
    is_mayhem: bool | None = None
    """T4.27: the chain's ``is_mayhem_mode`` bit (or the site's agent state,
    ``executable.is_mayhem_curve``); ``None`` = not observed, refused by name."""
    recent_drawdown_pct: Decimal | None = None
    recent_drawdown_peak_age_s: Decimal | None = None
    recent_drawdown_reason: str | None = None
    """T4.52b-2: :func:`hunter_indicators.meme.drawdown.recent_drawdown` —
    the fraction of real SOL lost from the window's peak, that peak's age and
    why both are ``None`` (``no_observation`` / ``stale``)."""
    early_retention_pct: Decimal | None = None
    early_age_s: Decimal | None = None
    new_wallets_30s: int | None = None
    quick_flip_share_30s: Decimal | None = None
    """T4.66 (EXP-M19): :class:`hunter_indicators.meme.crowd.CrowdFeatures` —
    only the event lane fills them; ``None`` elsewhere (refused by name)."""


@dataclass(frozen=True, slots=True)
class GateDecision:
    """Allowed, or the complete list of named refusals in evaluation order."""

    allowed: bool
    refusals: tuple[str, ...]


def evaluate_entry(features: EntryFeatures, gate: EntryGate) -> GateDecision:
    """May we buy this mint now? Pure function of one features row and one gate."""
    refusals: list[str] = []
    if features.intended_size_sol <= 0:
        refusals.append("size_not_positive")
    if features.curve_complete:
        refusals.append("curve_complete")
    if features.migrated:
        refusals.append("already_migrated")
    refusals.extend(mayhem_refusals(features, gate))
    refusals.extend(age_refusals(features, gate))
    refusals.extend(progress_refusals(features, gate))
    refusals.extend(creator_refusals(features, gate))
    refusals.extend(participation_refusals(features, gate))
    refusals.extend(line_refusals(features, gate))
    refusals.extend(hype_refusals(features, gate))
    refusals.extend(flow_refusals(features, gate))
    refusals.extend(drawdown_refusals(features, gate))
    refusals.extend(crowd_refusals(features, gate))
    refusals.extend(buys_refusals(features, gate))
    return GateDecision(allowed=not refusals, refusals=tuple(refusals))
