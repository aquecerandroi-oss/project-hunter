"""The entry gate and the exit rules of a curve position, as pure functions.

Registered the way a feature is (``key``, ``version``, ``parameters``,
``description``, ``inputs``): changing a threshold is a **new version**, never an
edit, because a rule set that changed meaning silently would make two runs of
EXP-M1 incomparable.

The entry gate answers one question — *may we buy this mint now?* — over a row of
features, and every "no" has a name. Three of those names are about our own
instrument rather than the market: ``progress_unknown``,
``creator_net_seller_unknown`` and ``curve_volume_1m_unknown`` fire when the free
sources have not produced the input yet (T4.2 leaves exactly these columns null
with a reason). Refusing while blind is the decision; reading a missing input as
"nobody sold" or "nobody traded" is the mistake Astra's review calls the gravest
of the original design.

The exit side is a declared precedence, evaluated in this order:

1. ``rug_signal`` — placeholder: no detector exists, so ``rug_suspected`` is
   ``None`` in production today and the decision says ``rug_signal_unknown``
   out loud instead of behaving as if a rug had been ruled out;
2. ``creator_dump`` — the creator turned net seller (``docs/RISK_ENGINE_MEME.md``
   §6). Unknown is ``creator_dump_unknown``, never "the dev did not sell";
3. ``migrated`` / ``curve_complete`` — the curve stops being the venue;
4. ``max_loss`` — the floor against the cost basis. It is an exit rule, **not**
   the risk of the position: on a curve the risk is everything we paid
   (``docs/RISK_ENGINE_MEME.md`` §5), because the sell may not find a buyer;
5. ``target_multiple`` — the ROI Everton asked for;
6. ``trailing_from_peak`` — drawdown from the highest mark-to-curve seen;
7. ``time_stop`` — the horizon.

Marks are always the honest mark-to-curve (what a full sell would net now, fees
included), so ``target_multiple = 2`` means "a full exit would double what we
paid", not "the marginal price doubled".
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal, localcontext
from typing import Final

from hunter_core.strategies.numeric import CONTEXT

__all__ = [
    "EntryFeatures",
    "EntryGate",
    "ExitDecision",
    "ExitRules",
    "ExitState",
    "GateDecision",
    "evaluate_entry",
    "evaluate_exit",
    "hit_curve_event",
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
)
EXIT_INPUTS: Final = (
    "paper_wallet.mark_to_curve",
    "paper_wallet.position.peak_mark_sol",
    "meme_tokens.completed_at",
    "meme_tokens.migrated_at",
    "meme_features_1m.creator_sold",
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

    def as_parameters(self) -> Mapping[str, str]:
        """Every threshold as a string — what a persisted decomposition stores."""
        return {
            "min_age_s": str(self.min_age_s),
            "max_age_s": str(self.max_age_s),
            "min_progress_pct": str(self.min_progress_pct),
            "max_progress_pct": str(self.max_progress_pct),
            "max_participation_pct": str(self.max_participation_pct),
            "require_creator_not_net_seller": str(self.require_creator_not_net_seller),
        }


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


@dataclass(frozen=True, slots=True)
class GateDecision:
    """Allowed, or the complete list of named refusals in evaluation order."""

    allowed: bool
    refusals: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ExitRules:
    """One registered exit rule set, thresholds and the two event switches."""

    key: str
    version: int
    description: str
    target_multiple: Decimal
    trailing_drawdown_pct: Decimal
    time_stop_s: int
    max_loss_pct: Decimal
    exit_on_curve_complete: bool = True
    exit_on_migration: bool = True
    exit_on_creator_dump: bool = True
    inputs: tuple[str, ...] = EXIT_INPUTS

    def __post_init__(self) -> None:
        if self.version < 1:
            raise ValueError("version starts at 1")
        if self.target_multiple <= 1:
            raise ValueError("target_multiple must be greater than 1")
        if not 0 < self.trailing_drawdown_pct < HUNDRED:
            raise ValueError("trailing_drawdown_pct must be in (0, 100)")
        if not 0 < self.max_loss_pct <= HUNDRED:
            raise ValueError("max_loss_pct must be in (0, 100]")
        if self.time_stop_s < 1:
            raise ValueError("time_stop_s must be at least 1 second")

    def as_parameters(self) -> Mapping[str, str]:
        return {
            "target_multiple": str(self.target_multiple),
            "trailing_drawdown_pct": str(self.trailing_drawdown_pct),
            "time_stop_s": str(self.time_stop_s),
            "max_loss_pct": str(self.max_loss_pct),
            "exit_on_curve_complete": str(self.exit_on_curve_complete),
            "exit_on_migration": str(self.exit_on_migration),
            "exit_on_creator_dump": str(self.exit_on_creator_dump),
        }


@dataclass(frozen=True, slots=True)
class ExitState:
    """What the exit rules read: honest marks, the peak, the clock, the events."""

    mark_sol: Decimal
    """Mark-to-curve: SOL a full sell would net **now**, fees included."""
    cost_basis_sol: Decimal
    peak_mark_sol: Decimal
    held_s: int
    curve_complete: bool = False
    migrated: bool = False
    rug_suspected: bool | None = None
    """``None`` = no detector has looked. Named in the decision, never assumed."""
    creator_net_seller: bool | None = None
    """The creator dump of ``RISK_ENGINE_MEME`` §6; ``None`` = no trade feed."""


@dataclass(frozen=True, slots=True)
class ExitDecision:
    """Exit or not, the winning reason, and what the rules could not know."""

    should_exit: bool
    reason: str | None
    unknown: tuple[str, ...]


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
    if features.progress_pct is None:
        return ["progress_unknown"]
    if features.progress_pct < gate.min_progress_pct:
        return ["progress_below_min"]
    if features.progress_pct > gate.max_progress_pct:
        return ["progress_above_max"]
    return []


def _creator_refusals(features: EntryFeatures, gate: EntryGate) -> list[str]:
    """Off means the feature is not a criterion at all — the falsification arm.

    On (the default) refuses both a known net seller and an unknown one: a gate
    that let the unknown through would be reading a missing feed as "the dev did
    not sell", which is the confusion Astra's MUST-FIX 1 names.
    """
    if not gate.require_creator_not_net_seller:
        return []
    if features.creator_net_seller is None:
        return ["creator_net_seller_unknown"]
    return ["creator_is_net_seller"] if features.creator_net_seller else []


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
    refusals.extend(_creator_refusals(features, gate))
    refusals.extend(_participation_refusals(features, gate))
    return GateDecision(allowed=not refusals, refusals=tuple(refusals))


def hit_curve_event(state: ExitState, rules: ExitRules) -> str | None:
    """``migrated`` or ``curve_complete`` when the rule set watches for them."""
    if rules.exit_on_migration and state.migrated:
        return "migrated"
    if rules.exit_on_curve_complete and state.curve_complete:
        return "curve_complete"
    return None


def hit_max_loss(state: ExitState, rules: ExitRules) -> bool:
    """Mark at or below the declared floor against the cost basis."""
    with localcontext(CONTEXT):
        floor = state.cost_basis_sol * (HUNDRED - rules.max_loss_pct) / HUNDRED
        return state.mark_sol <= floor


def hit_target(state: ExitState, rules: ExitRules) -> bool:
    """Mark at or above ``target_multiple`` times everything we paid."""
    with localcontext(CONTEXT):
        return state.mark_sol >= state.cost_basis_sol * rules.target_multiple


def hit_trailing(state: ExitState, rules: ExitRules) -> bool:
    """Mark fell ``trailing_drawdown_pct`` from the highest mark seen since entry."""
    with localcontext(CONTEXT):
        trigger = state.peak_mark_sol * (HUNDRED - rules.trailing_drawdown_pct) / HUNDRED
        return state.mark_sol <= trigger


def hit_time_stop(state: ExitState, rules: ExitRules) -> bool:
    """Held for at least the declared horizon."""
    return state.held_s >= rules.time_stop_s


def evaluate_exit(state: ExitState, rules: ExitRules) -> ExitDecision:
    """Should we sell now? The precedence is the module docstring's list."""
    unknown: tuple[str, ...] = ()
    if state.rug_suspected is None:
        unknown += ("rug_signal_unknown",)
    if rules.exit_on_creator_dump and state.creator_net_seller is None:
        unknown += ("creator_dump_unknown",)
    reason: str | None = None
    if state.rug_suspected:
        reason = "rug_signal"
    elif rules.exit_on_creator_dump and state.creator_net_seller:
        reason = "creator_dump"
    elif (event := hit_curve_event(state, rules)) is not None:
        reason = event
    elif hit_max_loss(state, rules):
        reason = "max_loss"
    elif hit_target(state, rules):
        reason = "target_multiple"
    elif hit_trailing(state, rules):
        reason = "trailing_from_peak"
    elif hit_time_stop(state, rules):
        reason = "time_stop"
    return ExitDecision(should_exit=reason is not None, reason=reason, unknown=unknown)
