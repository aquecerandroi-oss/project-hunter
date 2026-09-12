"""Value objects of the Lab loop: a rule set as the engine reads it, a snapshot,
a quote, a wallet state, a bet in flight and the two shapes a bet is written in.

Everything monetary is ``Decimal`` and every decimal in ``meme_rule_sets.params``
is a JSON **string**, read here with ``Decimal(str(...))`` so a frozen parameter
is the same number on every restart. Every timestamp is timezone-aware UTC. No
dataclass here reads a clock, opens a session or knows a table name — the repo
(``lab_repo.py``) builds them from rows and the engine (``paper_engine.py``)
moves between them.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Any

from hunter_indicators.meme.curve import CurveReserves
from hunter_indicators.meme.rules import EntryGate, ExitRules

__all__ = [
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


def money_str(value: Decimal) -> str:
    """A ``Decimal`` as plain digits — never ``0E-10`` or ``5E+1`` and never the
    28-digit tail of the arithmetic context: ``format(v, "f")`` writes every
    digit, trailing zeros after the point are dropped (the ``decimal_plain``
    rule of the API schemas, applied at write time so a row reads as it was
    meant)."""
    text = format(value, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text or "0"


def optional_money_str(value: Decimal | None) -> str | None:
    return None if value is None else money_str(value)


def _decimal_or(value: Any, default: Decimal) -> Decimal:
    """The decision's number when it gave one, else the rule set's — a given
    zero is a given zero, never "absent"."""
    return default if value is None else decimal_of(value)


def _int_or(value: Any, default: int) -> int:
    return default if value is None else int(value)


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
        gate = EntryGate(
            key=str(params["gate_key"]),
            version=int(params["gate_version"]),
            description=f"{name}/{version}: {params['gate_key']} v{params['gate_version']}",
            min_age_s=int(params["min_age_s"]),
            max_age_s=int(params["max_age_s"]),
            min_progress_pct=decimal_of(params["min_progress_pct"]),
            max_progress_pct=decimal_of(params["max_progress_pct"]),
            max_participation_pct=decimal_of(params["max_participation_pct"]),
            require_creator_not_net_seller=bool(params.get("require_creator_not_net_seller", True)),
        )
        return cls(
            id=str(id),
            name=name,
            version=version,
            kind=kind,
            exp_ref=exp_ref,
            status=status,
            code_ref=code_ref,
            gate=gate,
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
        )

    def suggested(self) -> dict[str, Any]:
        """``meme_proposals.suggested`` — what the desk pre-fills."""
        return {
            "size_sol": money_str(self.size_sol),
            "target_x": money_str(self.target_x),
            "trailing_pct": money_str(self.trailing_pct),
            "max_hold_s": self.max_hold_s,
        }


@dataclass(frozen=True, slots=True)
class EffectiveParams:
    """The four numbers a bet actually runs on, plus the rule set's own floor."""

    size_sol: Decimal
    target_x: Decimal
    trailing_pct: Decimal
    max_hold_s: int
    max_loss_pct: Decimal

    def exit_rules(self, key: str = "lab_exit") -> ExitRules:
        return ExitRules(
            key=key,
            version=1,
            description="effective exits of one bet",
            target_multiple=self.target_x,
            trailing_drawdown_pct=self.trailing_pct,
            time_stop_s=self.max_hold_s,
            max_loss_pct=self.max_loss_pct,
        )

    def as_json(self) -> dict[str, Any]:
        return {
            "size_sol": money_str(self.size_sol),
            "target_x": money_str(self.target_x),
            "trailing_pct": money_str(self.trailing_pct),
            "max_hold_s": self.max_hold_s,
            "max_loss_pct": money_str(self.max_loss_pct),
        }

    @classmethod
    def from_json(cls, params: Mapping[str, Any]) -> EffectiveParams:
        return cls(
            size_sol=decimal_of(params["size_sol"]),
            target_x=decimal_of(params["target_x"]),
            trailing_pct=decimal_of(params["trailing_pct"]),
            max_hold_s=int(params["max_hold_s"]),
            max_loss_pct=decimal_of(params["max_loss_pct"]),
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
    )


@dataclass(frozen=True, slots=True)
class Snapshot:
    """One ``meme_curve_snapshots`` row as the engine prices against it."""

    mint: str
    observed_at: datetime
    source: str
    reserves: CurveReserves
    real_sol_reserves: Decimal
    total_supply: Decimal
    complete: bool
    mcap_sol: Decimal | None = None

    def as_json(self) -> dict[str, Any]:
        return {
            "observed_at": self.observed_at.isoformat(),
            "source": self.source,
            "virtual_sol_reserves": money_str(self.reserves.virtual_sol_reserves),
            "virtual_token_reserves": money_str(self.reserves.virtual_token_reserves),
            "real_sol_reserves": money_str(self.real_sol_reserves),
            "real_token_reserves": optional_money_str(self.reserves.real_token_reserves),
            "complete": self.complete,
            "mcap_sol": optional_money_str(self.mcap_sol),
        }


@dataclass(frozen=True, slots=True)
class SolUsd:
    """An observed SOL/USD quote — source and instants travel with the number."""

    price_usd: Decimal
    source: str
    as_of: datetime
    observed_at: datetime
    stale: bool

    def as_json(self) -> dict[str, Any]:
        return {
            "price_usd": money_str(self.price_usd),
            "source": self.source,
            "as_of": self.as_of.isoformat(),
            "observed_at": self.observed_at.isoformat(),
            "stale": self.stale,
        }


@dataclass(frozen=True, slots=True)
class WalletState:
    """The paper wallet of one rule set, derived from ``meme_paper_bets`` alone."""

    balance_sol: Decimal
    """``wallet_max_sol + Σ closed pnl − Σ open sol_spent``: a restart is not a reset."""
    open_positions: int
    realized_today_sol: Decimal
    """Closed PnL of the Brasília day — what ``daily_loss_cap_sol`` measures."""
    exposure_by_mint: Mapping[str, Decimal] = field(default_factory=dict[str, Decimal])


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


@dataclass(frozen=True, slots=True)
class BetExit:
    """Everything a sale (or a rug without a snapshot) writes when closing."""

    exit_at: datetime
    exit: dict[str, Any]
    pnl_sol: Decimal
    r_multiple: Decimal
    sol_usd_at_exit: Decimal | None
