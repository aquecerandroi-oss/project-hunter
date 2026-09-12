"""The inputs and the outputs of a curve replay: snapshots in, outcomes out.

``CurveSnapshot`` is deliberately *not* a T4.2 row object: this package must not
depend on a schema another task is still writing, so the bridge is
:func:`snapshot_from_mapping`, a pure reader of a plain mapping. Feed it a
``NormalizedCurveState.model_dump()``, a ``meme_curve_snapshots`` row or a hand
written dict — what it refuses to do is invent a field that was not there. An
absent ``real_token_reserves`` stays ``None`` and the entry gate then refuses
``progress_unknown``, which is the honest reading of a launch nobody measured.

The outcome shape is the Lab's: entry, exit, reason, R and holding time, plus the
day the entry belongs to, because the day is the block the confidence interval
resamples (``.claude/state/exp-drafts/t362b/blocos90.py``, [[KB-0010]]).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any, Literal

from hunter_indicators.meme.curve import CurveReserves
from hunter_indicators.meme.models import LedgerEvent, PaperWalletLimits, require_utc
from hunter_indicators.meme.rules import EntryGate, ExitRules

__all__ = [
    "CurveSnapshot",
    "MintOutcome",
    "MintSeries",
    "ReplayPlan",
    "ReplayResult",
    "SkippedMint",
    "snapshot_from_mapping",
]

Axis = Literal["r_multiple", "pnl_sol"]


@dataclass(frozen=True, slots=True)
class CurveSnapshot:
    """One observation of one curve. ``None`` is "not observed", never zero."""

    mint: str
    observed_at: datetime
    reserves: CurveReserves
    curve_volume_1m_sol: Decimal | None = None
    creator_net_seller: bool | None = None
    rug_suspected: bool | None = None
    migrated: bool = False

    def __post_init__(self) -> None:
        require_utc(self.observed_at, "observed_at")


def snapshot_from_mapping(row: Mapping[str, Any]) -> CurveSnapshot:
    """Build a snapshot from a plain mapping, inventing nothing that is absent."""
    reserves = CurveReserves(
        virtual_sol_reserves=Decimal(str(row["virtual_sol_reserves"])),
        virtual_token_reserves=Decimal(str(row["virtual_token_reserves"])),
        real_token_reserves=_optional_decimal(row.get("real_token_reserves")),
        initial_real_token_reserves=_optional_decimal(row.get("initial_real_token_reserves")),
        complete=bool(row.get("complete", False)),
    )
    observed_at = row["observed_at"]
    if not isinstance(observed_at, datetime):
        observed_at = datetime.fromisoformat(str(observed_at))
    return CurveSnapshot(
        mint=str(row["mint"]),
        observed_at=observed_at,
        reserves=reserves,
        curve_volume_1m_sol=_optional_decimal(row.get("curve_volume_1m_sol")),
        creator_net_seller=_optional_bool(row.get("creator_net_seller")),
        rug_suspected=_optional_bool(row.get("rug_suspected")),
        migrated=bool(row.get("migrated", False)),
    )


def _optional_decimal(value: Any) -> Decimal | None:
    return None if value is None else Decimal(str(value))


def _optional_bool(value: Any) -> bool | None:
    return None if value is None else bool(value)


@dataclass(frozen=True, slots=True)
class MintSeries:
    """Every snapshot of one mint, in order, with the creation instant for age."""

    mint: str
    created_at: datetime
    snapshots: tuple[CurveSnapshot, ...]

    def __post_init__(self) -> None:
        require_utc(self.created_at, "created_at")
        if not self.snapshots:
            raise ValueError("a series needs at least one snapshot")
        previous: datetime | None = None
        for snapshot in self.snapshots:
            if snapshot.mint != self.mint:
                raise ValueError("every snapshot of a series belongs to the same mint")
            if previous is not None and snapshot.observed_at <= previous:
                raise ValueError("snapshots must be strictly increasing in observed_at")
            previous = snapshot.observed_at
        if self.snapshots[0].observed_at < self.created_at:
            raise ValueError("a snapshot cannot be older than the token")


@dataclass(frozen=True, slots=True)
class ReplayPlan:
    """One frozen experiment arm: the gate, the exits, the caps and the size."""

    gate: EntryGate
    exits: ExitRules
    limits: PaperWalletLimits
    size_sol: Decimal
    priority_fee_sol: Decimal
    opening_balance_sol: Decimal
    max_loss_cap_sol: Decimal | None = None
    """Risk doctrine cap on the loss of one position, when the doctrine sets one.
    The initial risk of R is ``min(cost * max_loss_pct, this)`` — never a stop
    distance in price, because a curve has no book to place a stop in."""

    def __post_init__(self) -> None:
        if self.size_sol <= 0:
            raise ValueError("size_sol must be positive")
        if self.priority_fee_sol < 0:
            raise ValueError("priority_fee_sol cannot be negative")
        if self.opening_balance_sol <= 0:
            raise ValueError("opening_balance_sol must be positive")
        if self.max_loss_cap_sol is not None and self.max_loss_cap_sol <= 0:
            raise ValueError("max_loss_cap_sol must be positive when set")


@dataclass(frozen=True, slots=True)
class MintOutcome:
    """One trade of one mint, in the shape the Lab reads."""

    mint: str
    day: str
    decision_index: int
    entry_index: int
    entry_ts: datetime
    entry_size_sol: Decimal
    """Everything that left the wallet at entry: curve cost, fee and priority fee."""
    tokens: Decimal
    slippage_tokens: Decimal
    """Tokens the decision snapshot would have bought minus the tokens the fill
    bought: the concurrency slippage, measured instead of assumed."""
    entry_price_sol: Decimal
    exit_index: int | None
    exit_ts: datetime | None
    exit_reason: str
    unfilled_exit_reason: str | None
    exit_proceeds_sol: Decimal | None
    mark_at_exit_sol: Decimal | None
    peak_mark_sol: Decimal
    pnl_sol: Decimal
    initial_risk_sol: Decimal
    r_multiple: Decimal
    holding_s: int
    closed: bool
    unknown: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class SkippedMint:
    """A mint that never traded, and the named reasons why."""

    mint: str
    reason: str
    refusals: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ReplayResult:
    """Everything one run produced: outcomes, skips and the wallet's ledger."""

    outcomes: tuple[MintOutcome, ...]
    skipped: tuple[SkippedMint, ...]
    ledger: tuple[LedgerEvent, ...]

    @property
    def total_pnl_sol(self) -> Decimal:
        return sum((o.pnl_sol for o in self.outcomes), start=Decimal(0))

    def day_blocks(self, axis: Axis = "r_multiple") -> tuple[list[str], list[float]]:
        """``(days, values)`` for the day-block bootstrap of the Lab.

        Floats, not ``Decimal``: the bootstrap is NumPy over a window in memory
        and nothing here is money being persisted (PIPELINE §9).
        """
        values: list[float] = [float(getattr(outcome, axis)) for outcome in self.outcomes]
        return [outcome.day for outcome in self.outcomes], values


def outcomes_of(results: Sequence[MintOutcome | SkippedMint]) -> tuple[MintOutcome, ...]:
    """The outcomes of a mixed run, in order."""
    return tuple(r for r in results if isinstance(r, MintOutcome))
