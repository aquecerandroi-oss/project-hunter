"""Value objects of the Lab loop: a rule set as the engine reads it, the
effective parameters of a bet, a bet in flight and the shape a fill writes —
plus, re-exported from :mod:`hunter_meme_worker.lab_values`, the snapshot, the
quote, the wallet state and the exit shape.

Everything monetary is ``Decimal`` and every decimal in ``meme_rule_sets.params``
is a JSON **string**, read here with ``Decimal(str(...))`` so a frozen parameter
is the same number on every restart. Every timestamp is timezone-aware UTC. No
dataclass here reads a clock, opens a session or knows a table name — the repo
(``lab_repo.py``) builds them from rows and the engine (``paper_engine.py``)
moves between them.

T4.10 reads the parameters of EXP-M2/EXP-M3 out of the same JSON, every one
optional so the ``0022`` seeds parse exactly as before: the line and hype
criteria of the gate (``require_higher_lows``, ``require_breakout_15m``,
``min/max_distance_to_support_pct``, ``min_hype_score``, ``max_dev_share``,
``dev_share_unknown_allowed``, ``max_snipers``, ``require_progress``), the
"line broken" exit (``exit_on_line_break``, ``line_break_snapshots``) and the
probe → scale second leg (``scale_size_sol``, ``scale_gate`` = the
``name/version`` of the rule set whose gate must be satisfied for the same
mint while the probe is open).
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any

from hunter_indicators.meme.rules import EntryGate, ExitRules
from hunter_meme_worker.lab_values import (
    LEGS,
    BetExit,
    Snapshot,
    SolUsd,
    WalletState,
    money_str,
    optional_money_str,
)

__all__ = [
    "LEGS",
    "BetEntry",
    "BetExit",
    "BetState",
    "EffectiveParams",
    "RuleSetSpec",
    "Snapshot",
    "SolUsd",
    "WalletState",
    "decimal_of",
    "effective_params",
    "money_str",
    "optional_money_str",
]

REFUSAL_EXCEEDS_MAX_SOL_PER_BET = "exceeds_max_sol_per_bet"
REFUSAL_SIZE_NOT_POSITIVE = "size_not_positive"


def decimal_of(value: Any) -> Decimal:
    """``Decimal`` from a JSON string, int or Decimal — never from a float's repr."""
    if isinstance(value, float):
        raise TypeError("a float is not an exact number; params carry decimals as strings")
    return Decimal(str(value))


def _optional_decimal(value: Any) -> Decimal | None:
    return None if value is None else decimal_of(value)


def _decimal_or(value: Any, default: Decimal) -> Decimal:
    """The decision's number when it gave one, else the rule set's — a given
    zero is a given zero, never "absent"."""
    return default if value is None else decimal_of(value)


def _int_or(value: Any, default: int) -> int:
    return default if value is None else int(value)


def _bool_or(value: Any, default: bool) -> bool:
    return default if value is None else bool(value)


def _gate_from_params(name: str, version: str, params: Mapping[str, Any]) -> EntryGate:
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
        min_distance_to_support_pct=_optional_decimal(params.get("min_distance_to_support_pct")),
        max_distance_to_support_pct=_optional_decimal(params.get("max_distance_to_support_pct")),
        min_hype_score=_optional_decimal(params.get("min_hype_score")),
        max_dev_share=_optional_decimal(params.get("max_dev_share")),
        dev_share_unknown_allowed=bool(params.get("dev_share_unknown_allowed", False)),
        max_snipers=None if params.get("max_snipers") is None else int(params["max_snipers"]),
    )


@dataclass(frozen=True, slots=True)
class RuleSetSpec:
    """One ``meme_rule_sets`` row, parsed. The gate and the exits are T4.5's."""

    id: str
    name: str
    version: str
    kind: str
    exp_ref: str | None
    status: str
    code_ref: str
    gate: EntryGate
    size_sol: Decimal
    target_x: Decimal
    trailing_pct: Decimal
    max_hold_s: int
    max_loss_pct: Decimal
    wallet_max_sol: Decimal
    max_sol_per_bet: Decimal
    daily_loss_cap_sol: Decimal
    max_open_positions: int
    max_exposure_per_mint_sol: Decimal
    fee_pct: Decimal
    priority_fee_sol: Decimal
    exit_on_line_break: bool = False
    line_break_snapshots: int = 2
    scale_size_sol: Decimal | None = None
    """EXP-M3: the size of the second leg opened on the same mint while the
    probe is open and ``scale_gate`` is satisfied; ``None`` = this set never
    scales, and its bets are ``single``."""
    scale_gate: str | None = None
    """``name/version`` of the active rule set whose gate confirms the line."""

    @property
    def label(self) -> str:
        return f"{self.name}/{self.version}"

    @property
    def scales(self) -> bool:
        return self.scale_size_sol is not None and self.scale_gate is not None

    @classmethod
    def from_params(
        cls,
        *,
        id: str,
        name: str,
        version: str,
        kind: str,
        exp_ref: str | None,
        status: str,
        code_ref: str,
        params: Mapping[str, Any],
    ) -> RuleSetSpec:
        return cls(
            id=str(id),
            name=name,
            version=version,
            kind=kind,
            exp_ref=exp_ref,
            status=status,
            code_ref=code_ref,
            gate=_gate_from_params(name, version, params),
            size_sol=decimal_of(params["size_sol"]),
            target_x=decimal_of(params["target_x"]),
            trailing_pct=decimal_of(params["trailing_pct"]),
            max_hold_s=int(params["max_hold_s"]),
            max_loss_pct=decimal_of(params.get("max_loss_pct", "100")),
            wallet_max_sol=decimal_of(params["wallet_max_sol"]),
            max_sol_per_bet=decimal_of(params["max_sol_per_bet"]),
            daily_loss_cap_sol=decimal_of(params["daily_loss_cap_sol"]),
            max_open_positions=int(params.get("max_open_positions", 3)),
            max_exposure_per_mint_sol=decimal_of(
                params.get("max_exposure_per_mint_sol", params["max_sol_per_bet"])
            ),
            fee_pct=decimal_of(params.get("fee_pct", "1.75")),
            priority_fee_sol=decimal_of(params.get("priority_fee_sol", "0")),
            exit_on_line_break=bool(params.get("exit_on_line_break", False)),
            line_break_snapshots=int(params.get("line_break_snapshots", 2)),
            scale_size_sol=_optional_decimal(params.get("scale_size_sol")),
            scale_gate=None if params.get("scale_gate") is None else str(params["scale_gate"]),
        )

    def suggested(self) -> dict[str, Any]:
        """``meme_proposals.suggested`` — what the desk pre-fills.

        The T4.10 keys appear only when they say something: a set that scales
        opens ``probe`` legs (every other set's bets are ``single`` by default
        at the fill) and a set that watches the line says so — EXP-M1's
        proposals keep the four keys they always had.
        """
        suggested: dict[str, Any] = {
            "size_sol": money_str(self.size_sol),
            "target_x": money_str(self.target_x),
            "trailing_pct": money_str(self.trailing_pct),
            "max_hold_s": self.max_hold_s,
        }
        if self.exit_on_line_break:
            suggested["exit_on_line_break"] = True
            suggested["line_break_snapshots"] = self.line_break_snapshots
        if self.scales:
            suggested["leg"] = "probe"
        return suggested


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

    def exit_rules(self, key: str = "lab_exit") -> ExitRules:
        return ExitRules(
            key=key,
            version=1,
            description="effective exits of one bet",
            target_multiple=self.target_x,
            trailing_drawdown_pct=self.trailing_pct,
            time_stop_s=self.max_hold_s,
            max_loss_pct=self.max_loss_pct,
            exit_on_line_break=self.exit_on_line_break,
            line_break_snapshots=self.line_break_snapshots,
        )

    def as_json(self) -> dict[str, Any]:
        return {
            "size_sol": money_str(self.size_sol),
            "target_x": money_str(self.target_x),
            "trailing_pct": money_str(self.trailing_pct),
            "max_hold_s": self.max_hold_s,
            "max_loss_pct": money_str(self.max_loss_pct),
            "exit_on_line_break": self.exit_on_line_break,
            "line_break_snapshots": self.line_break_snapshots,
        }

    @classmethod
    def from_json(cls, params: Mapping[str, Any]) -> EffectiveParams:
        """Rows written before T4.10 carry no line keys: they never watched one."""
        return cls(
            size_sol=decimal_of(params["size_sol"]),
            target_x=decimal_of(params["target_x"]),
            trailing_pct=decimal_of(params["trailing_pct"]),
            max_hold_s=int(params["max_hold_s"]),
            max_loss_pct=decimal_of(params["max_loss_pct"]),
            exit_on_line_break=_bool_or(params.get("exit_on_line_break"), False),
            line_break_snapshots=_int_or(params.get("line_break_snapshots"), 2),
        )


def effective_params(spec: RuleSetSpec, decision: Mapping[str, Any]) -> EffectiveParams | str:
    """The decision (operator's or ``suggested``) under the rule set's ceilings.

    The operator may change any of the four; the size may not exceed
    ``max_sol_per_bet`` (refused by name, the contract's
    ``exceeds_max_sol_per_bet``) and the loss floor is never theirs to move.
    """
    size = _optional_decimal(decision.get("size_sol"))
    if size is None:
        size = spec.size_sol
    if size <= 0:
        return REFUSAL_SIZE_NOT_POSITIVE
    if size > spec.max_sol_per_bet:
        return REFUSAL_EXCEEDS_MAX_SOL_PER_BET
    return EffectiveParams(
        size_sol=size,
        target_x=_decimal_or(decision.get("target_x"), spec.target_x),
        trailing_pct=_decimal_or(decision.get("trailing_pct"), spec.trailing_pct),
        max_hold_s=_int_or(decision.get("max_hold_s"), spec.max_hold_s),
        max_loss_pct=spec.max_loss_pct,
        exit_on_line_break=_bool_or(decision.get("exit_on_line_break"), spec.exit_on_line_break),
        line_break_snapshots=_int_or(
            decision.get("line_break_snapshots"), spec.line_break_snapshots
        ),
    )


@dataclass(frozen=True, slots=True)
class BetState:
    """An open bet as the marks and the exits read it."""

    id: str
    proposal_id: str
    rule_set_id: str
    mint: str
    entry_at: datetime
    tokens: Decimal
    sol_spent: Decimal
    initial_risk_sol: Decimal
    params: EffectiveParams
    high_water_x: Decimal
    mark_sol: Decimal | None
    mark_at: datetime | None
    exit_intent: Mapping[str, Any] | None
    fee_pct: Decimal
    priority_fee_sol: Decimal
    leg: str = "single"
    parent_bet_id: str | None = None


@dataclass(frozen=True, slots=True)
class BetEntry:
    """Everything a fill writes into a new ``meme_paper_bets`` row."""

    entry_at: datetime
    entry: dict[str, Any]
    tokens: Decimal
    sol_spent: Decimal
    initial_risk_sol: Decimal
    params: EffectiveParams
    mark_sol: Decimal
    high_water_x: Decimal
    sol_usd_at_entry: Decimal | None
    leg: str = "single"
    parent_bet_id: str | None = None
