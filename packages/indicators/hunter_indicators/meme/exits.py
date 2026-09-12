"""The exit rules of a curve position, as pure functions (moved out of
:mod:`hunter_indicators.meme.rules` in T4.10 for the 350-line budget; that
module re-exports every name here, so ``rules:evaluate_exit`` is still the
``code_ref`` of every seeded rule set).

Registered the way a feature is (``key``, ``version``, ``parameters``,
``description``, ``inputs``): changing a threshold is a **new version**, never an
edit, because a rule set that changed meaning silently would make two runs of
an EXP-M* incomparable.

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
5. ``line_broken`` (T4.10, EXP-M2) — the market cap closed **below the support
   line** for ``line_break_snapshots`` consecutive snapshots. The streak is
   counted by the caller against ``meme_features_1m.support_line_sol``
   projected to each snapshot's instant; ``None`` means no line exists for the
   position and the decision says ``support_line_unknown`` — a rule set that
   watches the line and has none is blind, not safe;
6. ``target_multiple`` — the ROI Everton asked for;
7. ``trailing_from_peak`` — drawdown from the highest mark-to-curve seen;
8. ``time_stop`` — the horizon.

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
    "EXIT_INPUTS",
    "ExitDecision",
    "ExitRules",
    "ExitState",
    "evaluate_exit",
    "hit_curve_event",
    "hit_line_break",
    "hit_max_loss",
    "hit_target",
    "hit_time_stop",
    "hit_trailing",
]

HUNDRED: Final = Decimal(100)
EXIT_INPUTS: Final = (
    "paper_wallet.mark_to_curve",
    "paper_wallet.position.peak_mark_sol",
    "meme_tokens.completed_at",
    "meme_tokens.migrated_at",
    "meme_features_1m.creator_sold",
    "meme_features_1m.support_line_sol",
)


@dataclass(frozen=True, slots=True)
class ExitRules:
    """One registered exit rule set, thresholds and the event switches."""

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
    exit_on_line_break: bool = False
    """T4.10: sell when the market cap closes below the support line for
    ``line_break_snapshots`` snapshots in a row. Off by default — EXP-M1's
    frozen set never watched a line and must keep not watching one."""
    line_break_snapshots: int = 2
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
        if self.line_break_snapshots < 1:
            raise ValueError("line_break_snapshots must be at least 1")

    def as_parameters(self) -> Mapping[str, str]:
        """The line rule is listed only when it is watched — EXP-M1's registered
        exits must read today exactly as they did the day they were frozen."""
        parameters = {
            "target_multiple": str(self.target_multiple),
            "trailing_drawdown_pct": str(self.trailing_drawdown_pct),
            "time_stop_s": str(self.time_stop_s),
            "max_loss_pct": str(self.max_loss_pct),
            "exit_on_curve_complete": str(self.exit_on_curve_complete),
            "exit_on_migration": str(self.exit_on_migration),
            "exit_on_creator_dump": str(self.exit_on_creator_dump),
        }
        if self.exit_on_line_break:
            parameters["exit_on_line_break"] = "True"
            parameters["line_break_snapshots"] = str(self.line_break_snapshots)
        return parameters


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
    below_support_streak: int | None = None
    """Consecutive snapshots (this one included) whose market cap closed below
    the support line projected to their instant; ``None`` = no line is known
    for this position (``line_reason`` on the row says why)."""


@dataclass(frozen=True, slots=True)
class ExitDecision:
    """Exit or not, the winning reason, and what the rules could not know."""

    should_exit: bool
    reason: str | None
    unknown: tuple[str, ...]


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


def hit_line_break(state: ExitState, rules: ExitRules) -> bool:
    """The support line was closed below for the declared number of snapshots."""
    if not rules.exit_on_line_break or state.below_support_streak is None:
        return False
    return state.below_support_streak >= rules.line_break_snapshots


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
    if rules.exit_on_line_break and state.below_support_streak is None:
        unknown += ("support_line_unknown",)
    reason: str | None = None
    if state.rug_suspected:
        reason = "rug_signal"
    elif rules.exit_on_creator_dump and state.creator_net_seller:
        reason = "creator_dump"
    elif (event := hit_curve_event(state, rules)) is not None:
        reason = event
    elif hit_max_loss(state, rules):
        reason = "max_loss"
    elif hit_line_break(state, rules):
        reason = "line_broken"
    elif hit_target(state, rules):
        reason = "target_multiple"
    elif hit_trailing(state, rules):
        reason = "trailing_from_peak"
    elif hit_time_stop(state, rules):
        reason = "time_stop"
    return ExitDecision(should_exit=reason is not None, reason=reason, unknown=unknown)
