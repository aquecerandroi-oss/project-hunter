"""The effective parameters of one bet — the numbers it actually runs on —
split out of :mod:`hunter_meme_worker.lab_models` in T4.11 for the 350-line
budget (that module re-exports every name here, so callers did not move).

Every decimal in ``meme_rule_sets.params`` / ``meme_proposals.decision`` is a
JSON **string**, read with :func:`decimal_of` so a frozen parameter is the same
number on every restart; a float is refused, never rounded.

T4.11 adds, each optional so every row written before parses exactly as it
did: ``exit_on_migration`` (``False`` = hold through completion and migration,
marked on the pool's tape; the frozen sets keep ``True``), ``trailing_arm_x``
(the trailing rule disarmed until the peak reaches this multiple — "trailing
50 % só depois de 3×"), and the ``dead`` exit (``exit_on_dead``,
``dead_stale_s``, ``dead_mark_pct``: the tape silent for that long **and** the
mark at or below that share of the cost).
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal
from typing import TYPE_CHECKING, Any

from hunter_indicators.meme.rules import ExitRules
from hunter_meme_worker.lab_values import money_str, optional_money_str

if TYPE_CHECKING:
    from hunter_meme_worker.lab_models import RuleSetSpec

__all__ = [
    "REFUSAL_EXCEEDS_MAX_SOL_PER_BET",
    "REFUSAL_SIZE_NOT_POSITIVE",
    "EffectiveParams",
    "decimal_of",
    "effective_params",
]

REFUSAL_EXCEEDS_MAX_SOL_PER_BET = "exceeds_max_sol_per_bet"
REFUSAL_SIZE_NOT_POSITIVE = "size_not_positive"

DEFAULT_DEAD_STALE_S = 900
DEFAULT_DEAD_MARK_PCT = Decimal(50)


def decimal_of(value: Any) -> Decimal:
    """``Decimal`` from a JSON string, int or Decimal — never from a float's repr."""
    if isinstance(value, float):
        raise TypeError("a float is not an exact number; params carry decimals as strings")
    return Decimal(str(value))


def optional_decimal(value: Any) -> Decimal | None:
    return None if value is None else decimal_of(value)


def decimal_or(value: Any, default: Decimal) -> Decimal:
    """The decision's number when it gave one, else the rule set's — a given
    zero is a given zero, never "absent"."""
    return default if value is None else decimal_of(value)


def int_or(value: Any, default: int) -> int:
    return default if value is None else int(value)


def bool_or(value: Any, default: bool) -> bool:
    return default if value is None else bool(value)


@dataclass(frozen=True, slots=True)
class EffectiveParams:
    """The numbers a bet actually runs on, plus the rule set's own floor."""

    size_sol: Decimal
    target_x: Decimal
    trailing_pct: Decimal
    max_hold_s: int
    max_loss_pct: Decimal
    exit_on_line_break: bool = False
    line_break_snapshots: int = 2
    exit_on_migration: bool = True
    """T4.11: ``False`` holds through the curve's completion **and** its
    migration (one switch — completion precedes migration, and a set that
    holds through one must hold through the other); the position is then
    marked on the PumpSwap pool's tape (``lab_bets_pool.py``)."""
    trailing_arm_x: Decimal | None = None
    exit_on_dead: bool = False
    dead_stale_s: int = DEFAULT_DEAD_STALE_S
    dead_mark_pct: Decimal = DEFAULT_DEAD_MARK_PCT

    def exit_rules(self, key: str = "lab_exit") -> ExitRules:
        return ExitRules(
            key=key,
            version=1,
            description="effective exits of one bet",
            target_multiple=self.target_x,
            trailing_drawdown_pct=self.trailing_pct,
            time_stop_s=self.max_hold_s,
            max_loss_pct=self.max_loss_pct,
            exit_on_curve_complete=self.exit_on_migration,
            exit_on_migration=self.exit_on_migration,
            exit_on_line_break=self.exit_on_line_break,
            line_break_snapshots=self.line_break_snapshots,
            trailing_arm_multiple=self.trailing_arm_x,
            exit_on_dead=self.exit_on_dead,
            dead_stale_s=self.dead_stale_s,
            dead_mark_pct=self.dead_mark_pct,
        )

    def as_json(self) -> dict[str, Any]:
        """``meme_paper_bets.params``. The T4.11 keys appear only when they say
        something, so a bet of a frozen set reads exactly as it did before."""
        params: dict[str, Any] = {
            "size_sol": money_str(self.size_sol),
            "target_x": money_str(self.target_x),
            "trailing_pct": money_str(self.trailing_pct),
            "max_hold_s": self.max_hold_s,
            "max_loss_pct": money_str(self.max_loss_pct),
            "exit_on_line_break": self.exit_on_line_break,
            "line_break_snapshots": self.line_break_snapshots,
        }
        if not self.exit_on_migration:
            params["exit_on_migration"] = False
        if self.trailing_arm_x is not None:
            params["trailing_arm_x"] = money_str(self.trailing_arm_x)
        if self.exit_on_dead:
            params["exit_on_dead"] = True
            params["dead_stale_s"] = self.dead_stale_s
            params["dead_mark_pct"] = money_str(self.dead_mark_pct)
        return params

    @classmethod
    def from_json(cls, params: Mapping[str, Any]) -> EffectiveParams:
        """Rows written before T4.10/T4.11 carry none of the optional keys:
        they never watched a line, always sold on migration, never armed."""
        return cls(
            size_sol=decimal_of(params["size_sol"]),
            target_x=decimal_of(params["target_x"]),
            trailing_pct=decimal_of(params["trailing_pct"]),
            max_hold_s=int(params["max_hold_s"]),
            max_loss_pct=decimal_of(params["max_loss_pct"]),
            exit_on_line_break=bool_or(params.get("exit_on_line_break"), False),
            line_break_snapshots=int_or(params.get("line_break_snapshots"), 2),
            exit_on_migration=bool_or(params.get("exit_on_migration"), True),
            trailing_arm_x=optional_decimal(params.get("trailing_arm_x")),
            exit_on_dead=bool_or(params.get("exit_on_dead"), False),
            dead_stale_s=int_or(params.get("dead_stale_s"), DEFAULT_DEAD_STALE_S),
            dead_mark_pct=decimal_or(params.get("dead_mark_pct"), DEFAULT_DEAD_MARK_PCT),
        )


def effective_params(spec: RuleSetSpec, decision: Mapping[str, Any]) -> EffectiveParams | str:
    """The decision (operator's or ``suggested``) under the rule set's ceilings.

    The operator may change any of the four (``max_hold_s`` included — 7 200 s
    is a number, not a ceiling); the size may not exceed ``max_sol_per_bet``
    (refused by name, the contract's ``exceeds_max_sol_per_bet``) and the loss
    floor is never theirs to move. The T4.11 switches follow the decision when
    it names them and the rule set otherwise.
    """
    size = optional_decimal(decision.get("size_sol"))
    if size is None:
        size = spec.size_sol
    if size <= 0:
        return REFUSAL_SIZE_NOT_POSITIVE
    if size > spec.max_sol_per_bet:
        return REFUSAL_EXCEEDS_MAX_SOL_PER_BET
    return EffectiveParams(
        size_sol=size,
        target_x=decimal_or(decision.get("target_x"), spec.target_x),
        trailing_pct=decimal_or(decision.get("trailing_pct"), spec.trailing_pct),
        max_hold_s=int_or(decision.get("max_hold_s"), spec.max_hold_s),
        max_loss_pct=spec.max_loss_pct,
        exit_on_line_break=bool_or(decision.get("exit_on_line_break"), spec.exit_on_line_break),
        line_break_snapshots=int_or(
            decision.get("line_break_snapshots"), spec.line_break_snapshots
        ),
        exit_on_migration=bool_or(decision.get("exit_on_migration"), spec.exit_on_migration),
        trailing_arm_x=(
            spec.trailing_arm_x
            if decision.get("trailing_arm_x") is None
            else decimal_of(decision["trailing_arm_x"])
        ),
        exit_on_dead=bool_or(decision.get("exit_on_dead"), spec.exit_on_dead),
        dead_stale_s=int_or(decision.get("dead_stale_s"), spec.dead_stale_s),
        dead_mark_pct=decimal_or(decision.get("dead_mark_pct"), spec.dead_mark_pct),
    )


def suggested_extras(spec: RuleSetSpec) -> dict[str, Any]:
    """The T4.11 keys of ``meme_proposals.suggested`` — only the ones that say
    something, so EXP-M1's proposals keep the four keys they always had."""
    extras: dict[str, Any] = {}
    if not spec.exit_on_migration:
        extras["exit_on_migration"] = False
    if spec.trailing_arm_x is not None:
        extras["trailing_arm_x"] = optional_money_str(spec.trailing_arm_x)
    if spec.exit_on_dead:
        extras["exit_on_dead"] = True
    return extras
