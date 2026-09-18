"""T4.61b/T4.61c — conviction sizing: the buy is a **fraction of the cap** decided
by the evidence the admission already holds, never a number above it.

Until T4.61b every real buy was ``min(max_sol_per_trade, proposal.size)`` flat
(0,28 SOL on 18/09/2026). Everton: "usa a inteligência que já adquirimos e opera
agora com o dinheiro que temos; pode variar os valores da entrada". The ladder
below is that intelligence, rung by rung, each one a measurement with its KB:

| rung | evidence | multiplier | why |
|---|---|---|---|
| ``creator`` | ``creator_verdict.decided_by`` is the tape alone | × 0,5 | the tape lags 20–40 s (COVER, R56 §3.2); the chain-clean read keeps 1,0 |
| ``buyers`` | ``unique_buyers_60s < 25`` or unknown | × 0,5 | EXP-M10: +0,09 R above 25 |
| ``holders`` | ``holders_rising`` false or unknown | × 0,5 | KB-0108: holders falling is the death signature |
| ``concentration`` | ``bundled_share > 10 %`` or ``top10_share > 20 %`` | × 0,5 | halfway to the caps (20 % / 25 %) — KB-0103's "one wallet pays a fifth" |
| ``drop`` | fresh ``real_sol`` ≥ 50 % below the 60 s peak | **refuse** ``entry_after_drop`` | KB-0118: −0,305 R in 73 bets; R56: 6 of 7 real buys were this cell |
| | fewer than two photos in the window, or the read failed | **refuse** ``entry_after_drop_unknown`` | T4.61c: one photo after the fall reads as "no fall" (review A2) — the edge fails closed |

The ``drop`` rung is the registered feature ``recent_drawdown_pct`` v1
(``hunter_indicators.meme.drawdown``, EXP-M13) folded over the stored photos of
the window **plus** the admission's own ``confirmed`` read as the newest point —
one definition, three lanes (event, 15 s, executor). The product is the
multiplier; below the **floor** (0,25) the order is refused ``conviction_too_low``.
Unknown evidence is a discount, never a pass (§8 of the contract).

**Pure.** :func:`evaluate_conviction` takes the evidence, the config and the
instant, and returns the ladder; nothing here reads a table or the clock. The
read is ``conviction_read.py``; the verdict goes **into** the engine as
``MemeConviction`` (T4.61c: check 26 and the ``conviction`` ceiling of §5), so a
refusal is ``approved = false`` by construction and a discount binds by its own
name. The dust floor (``conviction_too_small``) is the engine's, against
``MEME_MIN_TRADE_SOL``. Off (``MEME_CONVICTION_SIZING``, the default) the ladder
is not evaluated at all: no read, no rung, the flat size of before.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import ROUND_DOWN, Decimal
from typing import Any, Final

from hunter_indicators.meme.drawdown import (
    NO_OBSERVATION,
    TOO_FEW_POINTS,
    ReservePoint,
    recent_drawdown,
)
from hunter_meme_executor.conviction_config import ENV_CONVICTION_SIZING, ConvictionConfig
from hunter_meme_executor.creator_flow import CHAIN_FLOW_SOURCE, TAPE_FLOW_SOURCE
from hunter_risk_meme import MemeConviction
from hunter_risk_meme.conviction import (
    CONVICTION_TOO_LOW,
    ENTRY_AFTER_DROP,
    ENTRY_AFTER_DROP_UNKNOWN,
)

__all__ = [
    "ENV_CONVICTION_SIZING",
    "LADDER_OFF",
    "REFUSAL_CONVICTION_TOO_LOW",
    "REFUSAL_ENTRY_AFTER_DROP",
    "REFUSAL_ENTRY_AFTER_DROP_UNKNOWN",
    "ConvictionConfig",
    "ConvictionEvidence",
    "ConvictionLadder",
    "Rung",
    "evaluate_conviction",
]

REFUSAL_ENTRY_AFTER_DROP: Final = ENTRY_AFTER_DROP
REFUSAL_ENTRY_AFTER_DROP_UNKNOWN: Final = ENTRY_AFTER_DROP_UNKNOWN
REFUSAL_CONVICTION_TOO_LOW: Final = CONVICTION_TOO_LOW

LADDER_OFF: Final[dict[str, Any]] = {"enabled": False, "evaluated": False}
"""What ``admission.conviction`` carries when the flag is off: nothing was read."""

_ZERO = Decimal(0)
_ONE = Decimal(1)
_LAMPORT = Decimal("0.000000001")


def _quantize(value: Decimal) -> Decimal:
    return max(_ZERO, value).quantize(_LAMPORT, rounding=ROUND_DOWN)


@dataclass(frozen=True, slots=True)
class ConvictionEvidence:
    """What the ladder judges — every field ``None`` when not measured."""

    creator_decided_by: str | None
    """``creator_verdict.decided_by`` of this admission (``creator_flow.py``)."""
    unique_buyers_60s: int | None
    holders_rising: bool | None
    evidence_as_of: datetime | None
    """The 15 s row's ``as_of`` the two fields above came from."""
    bundled_share_pct: Decimal | None
    top10_share_pct: Decimal | None
    real_sol_now: Decimal | None
    """The admission's own ``confirmed`` curve read, in SOL."""
    curve_points: tuple[ReservePoint, ...] = ()
    """``meme_curve_snapshots`` of the drop window (real SOL in SOL), as stored."""
    read_failed: str | None = None
    """The series read raised (its error type): the drop cannot be judged."""


@dataclass(frozen=True, slots=True)
class Rung:
    name: str
    value: str
    """What was observed, as text (``""`` when unknown)."""
    multiplier: Decimal
    reason: str

    def as_json(self) -> dict[str, str]:
        return {
            "name": self.name,
            "value": self.value,
            "multiplier": str(self.multiplier),
            "reason": self.reason,
        }


@dataclass(frozen=True, slots=True)
class ConvictionLadder:
    rungs: tuple[Rung, ...]
    multiplier: Decimal
    sol_cap: Decimal
    """``min(requested, max_sol_per_trade)`` — what the flat size was."""
    sol_sized: Decimal
    """``quantize(sol_cap × multiplier)`` — the ``conviction`` ceiling of §5."""
    refusal: str | None
    """``entry_after_drop`` | ``entry_after_drop_unknown`` | ``conviction_too_low`` | ``None``."""

    def to_input(self) -> MemeConviction:
        """The verdict the engine receives (check 26 + the ceiling)."""
        detail = ";".join(f"{r.name}={r.reason}" for r in self.rungs)
        return MemeConviction(
            enabled=True,
            multiplier=self.multiplier,
            sol_sized=self.sol_sized,
            refusal=self.refusal,
            detail=detail,
        )

    def as_json(self) -> dict[str, Any]:
        return {
            "enabled": True,
            "evaluated": True,
            "multiplier": str(self.multiplier),
            "sol_cap": str(self.sol_cap),
            "sol_sized": str(self.sol_sized),
            "refusal": self.refusal or "",
            "rungs": [r.as_json() for r in self.rungs],
        }


def _creator_rung(e: ConvictionEvidence, c: ConvictionConfig) -> Rung:
    who = e.creator_decided_by or ""
    if who == CHAIN_FLOW_SOURCE:
        return Rung("creator", who, _ONE, "chain_clean")
    if who == TAPE_FLOW_SOURCE:
        return Rung("creator", who, c.tape_only_multiplier, "tape_only")
    # Nobody spoke (only admissible under T4.28h's allowance) or a seller (the
    # engine refuses ``creator_net_seller`` anyway): never a full-size bet.
    return Rung("creator", who, c.tape_only_multiplier, "unknown" if not who else "not_chain_clean")


def _buyers_rung(e: ConvictionEvidence, c: ConvictionConfig) -> Rung:
    if e.unique_buyers_60s is None:
        return Rung("buyers", "", c.buyers_multiplier, "unknown")
    if e.unique_buyers_60s < c.min_unique_buyers:
        return Rung("buyers", str(e.unique_buyers_60s), c.buyers_multiplier, "below_min")
    return Rung("buyers", str(e.unique_buyers_60s), _ONE, "at_or_above_min")


def _holders_rung(e: ConvictionEvidence, c: ConvictionConfig) -> Rung:
    if e.holders_rising is None:
        return Rung("holders", "", c.holders_multiplier, "unknown")
    if not e.holders_rising:
        return Rung("holders", "false", c.holders_multiplier, "not_rising")
    return Rung("holders", "true", _ONE, "rising")


def _concentration_rung(e: ConvictionEvidence, c: ConvictionConfig) -> Rung:
    value = f"bundled={e.bundled_share_pct} top10={e.top10_share_pct}"
    if e.bundled_share_pct is None or e.top10_share_pct is None:
        return Rung("concentration", value, c.concentration_multiplier, "unknown")
    if e.bundled_share_pct > c.bundled_max_pct or e.top10_share_pct > c.top10_max_pct:
        return Rung("concentration", value, c.concentration_multiplier, "above_half_cap")
    return Rung("concentration", value, _ONE, "within_half_cap")


def _drop_rung(e: ConvictionEvidence, c: ConvictionConfig, as_of: datetime) -> Rung:
    """KB-0118 over the registered fold: the stored photos of the window plus the
    admission's own read as the newest point. Fewer than two stored photos cannot
    say whether anything fell (``too_few_points``, as the 15 s lane names it) —
    a refusal, never a pass and never a discount (T4.61c, review A2)."""
    start = as_of - timedelta(seconds=c.drop_window_s)
    stored = [
        p for p in e.curve_points if p.received_at <= as_of and start <= p.observed_at <= as_of
    ]
    if e.read_failed is not None or e.real_sol_now is None:
        why = f"read_failed:{e.read_failed}" if e.read_failed else "no_curve_read"
        value = f"now={e.real_sol_now} points={len(stored)} {why}"
        return Rung("drop", value, _ZERO, REFUSAL_ENTRY_AFTER_DROP_UNKNOWN)
    if len(stored) < 2:
        why = TOO_FEW_POINTS if stored else NO_OBSERVATION
        value = f"now={e.real_sol_now} points={len(stored)} {why}"
        return Rung("drop", value, _ZERO, REFUSAL_ENTRY_AFTER_DROP_UNKNOWN)
    now_point = ReservePoint(observed_at=as_of, received_at=as_of, real_sol=e.real_sol_now)
    fold = recent_drawdown(
        [*stored, now_point], as_of=as_of, window_s=c.drop_window_s, max_gap_s=c.drop_window_s
    )
    peak = max(p.real_sol for p in stored)
    value = (
        f"now={e.real_sol_now} peak={peak} dd={fold.drawdown_pct} "
        f"peak_age_s={fold.peak_age_s} points={len(stored)}"
    )
    if fold.drawdown_pct is None:  # total by construction (the newest point is now)
        return Rung("drop", f"{value} {fold.reason}", _ZERO, REFUSAL_ENTRY_AFTER_DROP_UNKNOWN)
    if fold.drawdown_pct >= c.drop_pct:
        return Rung("drop", value, _ZERO, REFUSAL_ENTRY_AFTER_DROP)
    return Rung("drop", value, _ONE, "within_window")


def evaluate_conviction(
    evidence: ConvictionEvidence,
    config: ConvictionConfig,
    *,
    requested_sol: Decimal,
    max_sol_per_trade: Decimal,
    as_of: datetime,
) -> ConvictionLadder:
    """Pure: evidence × config × instant → the ladder, its product and its verdict.

    ``sol_cap = min(requested_sol, max_sol_per_trade)`` is the flat size of
    before; the sized budget is ``sol_cap × product``, quantized down to the
    lamport. The drop rung's refusals come first; then a product below ``floor``
    refuses ``conviction_too_low``. Whether the budget is above
    ``min_trade_sol`` is the engine's check (``conviction_too_small``).
    """
    rungs = (
        _creator_rung(evidence, config),
        _buyers_rung(evidence, config),
        _holders_rung(evidence, config),
        _concentration_rung(evidence, config),
        _drop_rung(evidence, config, as_of),
    )
    product = _ONE
    for rung in rungs:
        product *= rung.multiplier
    cap = _quantize(min(requested_sol, max_sol_per_trade))
    sized = _quantize(cap * product)
    drop = rungs[-1].reason
    refusal: str | None = None
    if drop in (REFUSAL_ENTRY_AFTER_DROP, REFUSAL_ENTRY_AFTER_DROP_UNKNOWN):
        refusal = drop
    elif product < config.floor:
        refusal = REFUSAL_CONVICTION_TOO_LOW
    return ConvictionLadder(
        rungs=rungs, multiplier=product, sol_cap=cap, sol_sized=sized, refusal=refusal
    )
