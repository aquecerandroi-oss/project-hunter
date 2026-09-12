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

T4.16 adds the criteria of EXP-M5 (the flow and the holders: net SOL flow —
or, on the 15-second series, the 60 s market-cap delta — positive, a floor on
distinct buyers, a ceiling on ``sells / buys``, holders and progress **rising**
over two consecutive readings), off by default like the others. The optional
criteria themselves live in :mod:`hunter_indicators.meme.rules_criteria`
(the 350-line budget); this module keeps the gate, the features and the
precedence of evaluation.

T4.21 adds the four switches of the E1 gate's second arm (EXP-M5 arm 2,
``fluxo_e_holders/2``): a floor on the holders count, "not falling" in place
of "rising", an unknown creator vouched for by a measured ``dev_share``, and
the 60 s market-cap delta as an alternative to progress rising — off by
default, so arm 1 reads exactly as it was frozen.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal, localcontext
from typing import Final

from hunter_core.strategies.numeric import CONTEXT
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
from hunter_indicators.meme.rules_criteria import (
    creator_refusals,
    flow_refusals,
    hype_refusals,
    line_refusals,
)

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
    inputs: tuple[str, ...] = GATE_INPUTS

    def __post_init__(self) -> None:
        if self.version < 1:
            raise ValueError("version starts at 1")
        if self.min_age_s < 0 or self.max_age_s < self.min_age_s:
            raise ValueError("age window must satisfy 0 <= min_age_s <= max_age_s")
        if not 0 <= self.min_progress_pct <= self.max_progress_pct <= HUNDRED:
            raise ValueError("progress window must satisfy 0 <= min <= max <= 100")
        if not 0 < self.max_participation_pct <= HUNDRED:
            raise ValueError("max_participation_pct must be in (0, 100]")
        low, high = self.min_distance_to_support_pct, self.max_distance_to_support_pct
        if low is not None and high is not None and low > high:
            raise ValueError("distance band must satisfy min <= max")
        if self.min_hype_score is not None and not 0 <= self.min_hype_score <= 1:
            raise ValueError("min_hype_score must be in [0, 1]")
        if self.max_dev_share is not None and not 0 <= self.max_dev_share <= 1:
            raise ValueError("max_dev_share must be in [0, 1]")
        if self.max_snipers is not None and self.max_snipers < 0:
            raise ValueError("max_snipers cannot be negative")
        if self.min_unique_buyers is not None and self.min_unique_buyers < 0:
            raise ValueError("min_unique_buyers cannot be negative")
        if self.max_sells_to_buys is not None and self.max_sells_to_buys < 0:
            raise ValueError("max_sells_to_buys cannot be negative")
        if self.min_holders is not None and self.min_holders < 0:
            raise ValueError("min_holders cannot be negative")

    def as_parameters(self) -> Mapping[str, str]:
        """Every threshold as a string — what a persisted decomposition stores.

        A criterion the gate does not ask is not listed: EXP-M1's registered
        parameters must read today exactly as they did the day they were frozen.
        """
        parameters = {
            "min_age_s": str(self.min_age_s),
            "max_age_s": str(self.max_age_s),
            "min_progress_pct": str(self.min_progress_pct),
            "max_progress_pct": str(self.max_progress_pct),
            "max_participation_pct": str(self.max_participation_pct),
            "require_creator_not_net_seller": str(self.require_creator_not_net_seller),
        }
        optional: dict[str, object] = {
            "require_progress": None if self.require_progress else False,
            "require_higher_lows": self.require_higher_lows or None,
            "require_breakout_15m": self.require_breakout_15m or None,
            "min_distance_to_support_pct": self.min_distance_to_support_pct,
            "max_distance_to_support_pct": self.max_distance_to_support_pct,
            "min_hype_score": self.min_hype_score,
            "max_dev_share": self.max_dev_share,
            "dev_share_unknown_allowed": self.dev_share_unknown_allowed or None,
            "max_snipers": self.max_snipers,
            "require_positive_flow": self.require_positive_flow or None,
            "min_unique_buyers": self.min_unique_buyers,
            "max_sells_to_buys": self.max_sells_to_buys,
            "require_holders_rising": self.require_holders_rising or None,
            "require_progress_rising": self.require_progress_rising or None,
            "min_holders": self.min_holders,
            "holders_rising_or_flat": self.holders_rising_or_flat or None,
            "creator_unknown_allowed_if_dev_measured": (
                self.creator_unknown_allowed_if_dev_measured or None
            ),
            "progress_or_mcap_rising": self.progress_or_mcap_rising or None,
        }
        parameters.update({k: str(v) for k, v in optional.items() if v is not None})
        return parameters


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
    """T4.21: the two holders readings behind ``holders_rising`` — the floor
    reads the newest, "not falling" compares the two."""


@dataclass(frozen=True, slots=True)
class GateDecision:
    """Allowed, or the complete list of named refusals in evaluation order."""

    allowed: bool
    refusals: tuple[str, ...]


def participation_pct(size_sol: Decimal, curve_volume_1m_sol: Decimal | None) -> Decimal | None:
    """Our size as a percentage of the last minute of curve volume, or ``None``.

    ``None`` for an unknown **or** zero denominator: a minute with no volume does
    not make our participation 0 %, it makes it unmeasurable.
    """
    if curve_volume_1m_sol is None or curve_volume_1m_sol <= 0:
        return None
    with localcontext(CONTEXT):
        return HUNDRED * size_sol / curve_volume_1m_sol


def _age_refusals(features: EntryFeatures, gate: EntryGate) -> list[str]:
    if features.age_s is None:
        return ["age_unknown"]
    if features.age_s < gate.min_age_s:
        return ["age_below_min"]
    if features.age_s > gate.max_age_s:
        return ["age_above_max"]
    return []


def _progress_refusals(features: EntryFeatures, gate: EntryGate) -> list[str]:
    if not gate.require_progress:
        return []
    if features.progress_pct is None:
        return ["progress_unknown"]
    if features.progress_pct < gate.min_progress_pct:
        return ["progress_below_min"]
    if features.progress_pct > gate.max_progress_pct:
        return ["progress_above_max"]
    return []


def _participation_refusals(features: EntryFeatures, gate: EntryGate) -> list[str]:
    if features.curve_volume_1m_sol is None:
        return ["curve_volume_1m_unknown"]
    if features.curve_volume_1m_sol <= 0:
        return ["curve_volume_1m_zero"]
    share = participation_pct(features.intended_size_sol, features.curve_volume_1m_sol)
    if share is not None and share > gate.max_participation_pct:
        return ["participation_above_cap"]
    return []


def evaluate_entry(features: EntryFeatures, gate: EntryGate) -> GateDecision:
    """May we buy this mint now? Pure function of one features row and one gate."""
    refusals: list[str] = []
    if features.intended_size_sol <= 0:
        refusals.append("size_not_positive")
    if features.curve_complete:
        refusals.append("curve_complete")
    if features.migrated:
        refusals.append("already_migrated")
    refusals.extend(_age_refusals(features, gate))
    refusals.extend(_progress_refusals(features, gate))
    refusals.extend(creator_refusals(features, gate))
    refusals.extend(_participation_refusals(features, gate))
    refusals.extend(line_refusals(features, gate))
    refusals.extend(hype_refusals(features, gate))
    refusals.extend(flow_refusals(features, gate))
    return GateDecision(allowed=not refusals, refusals=tuple(refusals))
