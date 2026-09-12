"""Value objects of the Lab loop: a rule set as the engine reads it, a bet in
flight and the shape a fill writes — plus, re-exported from
:mod:`hunter_meme_worker.lab_values` (the snapshot, the quote, the wallet state
and the exit shape) and :mod:`hunter_meme_worker.lab_params` (the effective
parameters of a bet, since T4.11).

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

T4.11 (EXP-M4, the moonshot arms) adds ``exit_on_migration`` (``false`` = hold
through the migration and mark on the PumpSwap pool's tape), ``trailing_arm_x``
(trailing armed only after that multiple) and the ``dead`` exit
(``exit_on_dead``, ``dead_stale_s``, ``dead_mark_pct``) — again optional, so
``meme_paper_v0``/``trendline_v0``/``hype_probe_v0`` keep selling on migration.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any

from hunter_indicators.meme.rules import EntryGate
from hunter_meme_worker.lab_params import (
    DEFAULT_DEAD_MARK_PCT,
    DEFAULT_DEAD_STALE_S,
    REFUSAL_EXCEEDS_MAX_SOL_PER_BET,
    REFUSAL_SIZE_NOT_POSITIVE,
    EffectiveParams,
    bool_or,
    decimal_of,
    decimal_or,
    effective_params,
    int_or,
    optional_decimal,
    suggested_extras,
)
from hunter_meme_worker.lab_values import (
    LEGS,
    MARK_CURVE,
    MARK_POOL_TAPE,
    MARK_SOURCES,
    BetExit,
    Snapshot,
    SolUsd,
    WalletState,
    money_str,
    optional_money_str,
)

__all__ = [
    "CLOCKS",
    "LEGS",
    "MARK_CURVE",
    "MARK_POOL_TAPE",
    "MARK_SOURCES",
    "REFUSAL_EXCEEDS_MAX_SOL_PER_BET",
    "REFUSAL_SIZE_NOT_POSITIVE",
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
        min_distance_to_support_pct=optional_decimal(params.get("min_distance_to_support_pct")),
        max_distance_to_support_pct=optional_decimal(params.get("max_distance_to_support_pct")),
        min_hype_score=optional_decimal(params.get("min_hype_score")),
        max_dev_share=optional_decimal(params.get("max_dev_share")),
        dev_share_unknown_allowed=bool(params.get("dev_share_unknown_allowed", False)),
        max_snipers=None if params.get("max_snipers") is None else int(params["max_snipers"]),
        # T4.16 (EXP-M5): the flow and the holders, each absent = not a criterion.
        require_positive_flow=bool(params.get("require_positive_flow", False)),
        min_unique_buyers=(
            None if params.get("min_unique_buyers") is None else int(params["min_unique_buyers"])
        ),
        max_sells_to_buys=optional_decimal(params.get("max_sells_to_buys")),
        require_holders_rising=bool(params.get("require_holders_rising", False)),
        require_progress_rising=bool(params.get("require_progress_rising", False)),
        # T4.21 (EXP-M5 arm 2): four switches, off unless the set says so.
        min_holders=None if params.get("min_holders") is None else int(params["min_holders"]),
        holders_rising_or_flat=bool(params.get("holders_rising_or_flat", False)),
        creator_unknown_allowed_if_dev_measured=bool(
            params.get("creator_unknown_allowed_if_dev_measured", False)
        ),
        progress_or_mcap_rising=bool(params.get("progress_or_mcap_rising", False)),
    )


CLOCKS: tuple[str, ...] = ("1m", "15s")
"""``params.clock``: the series a set's gate reads — the closed minute
(``meme_features_1m``, the default and every set frozen before T4.16) or the
15-second series of the young mints (``meme_features_15s``). One clock per
set: a set is never judged twice on the same instant from two series."""


def _clock_of(value: Any) -> str:
    clock = "1m" if value is None else str(value)
    if clock not in CLOCKS:
        raise ValueError(f"unknown clock {clock!r}; one of {CLOCKS}")
    return clock


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
    exit_on_migration: bool = True
    """T4.11: ``False`` = the position survives the migration (EXP-M4)."""
    trailing_arm_x: Decimal | None = None
    exit_on_dead: bool = False
    dead_stale_s: int = DEFAULT_DEAD_STALE_S
    dead_mark_pct: Decimal = DEFAULT_DEAD_MARK_PCT
    clock: str = "1m"
    """T4.16: ``1m`` | ``15s`` (:data:`CLOCKS`) — which series this set's gate reads."""
    pedigree_exclusions: bool = True
    """T4.16 (EXP-M6): the cross-cutting pedigree refusals apply to this set;
    ``false`` is the falsification arm's word, never the default."""
    ttl_s: int | None = None
    """T4.19: how long this set's proposals wait for the desk (``operator/3``:
    180 s, a buy by hand); ``None`` = the loop's ``lab_proposal_ttl_s``."""

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
            scale_size_sol=optional_decimal(params.get("scale_size_sol")),
            scale_gate=None if params.get("scale_gate") is None else str(params["scale_gate"]),
            exit_on_migration=bool_or(params.get("exit_on_migration"), True),
            trailing_arm_x=optional_decimal(params.get("trailing_arm_x")),
            exit_on_dead=bool_or(params.get("exit_on_dead"), False),
            dead_stale_s=int_or(params.get("dead_stale_s"), DEFAULT_DEAD_STALE_S),
            dead_mark_pct=decimal_or(params.get("dead_mark_pct"), DEFAULT_DEAD_MARK_PCT),
            clock=_clock_of(params.get("clock")),
            pedigree_exclusions=bool_or(params.get("pedigree_exclusions"), True),
            ttl_s=None if params.get("ttl_s") is None else int(params["ttl_s"]),
        )

    def suggested(self) -> dict[str, Any]:
        """``meme_proposals.suggested`` — what the desk pre-fills.

        The T4.10/T4.11 keys appear only when they say something: a set that
        scales opens ``probe`` legs (every other set's bets are ``single`` by
        default at the fill), a set that watches the line says so, a set that
        holds through the migration says ``exit_on_migration: false`` — EXP-M1's
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
        suggested.update(suggested_extras(self))
        return suggested


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
    mark_source: str = MARK_CURVE
    """``curve`` while the position is priced on ``meme_curve_snapshots``;
    ``pool_tape`` once a bet that held through the migration is marked on the
    PumpSwap pool's trades (T4.11, ``0029``)."""
    mark_stale_s: int | None = None
    """Seconds between the tick and the last pool trade it could see."""


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
