"""T4.61b — conviction sizing: the buy is a **fraction of the cap** decided by the
evidence the admission already holds, never a number above it.

Until now every real buy was ``min(max_sol_per_trade, proposal.size)`` flat
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

The product is the multiplier; below the **floor** (0,25) the order is refused
``conviction_too_low`` — dust is never sent. ``entry_after_drop`` is a refusal
by design, not a discount: it is the one clean edge and a half-sized bet on a
draining curve is still a bad bet. Unknown evidence is a discount, never a pass
(§8 of the contract: what is not measured does not vouch for the coin).

**Pure.** :func:`evaluate_conviction` takes the evidence and the config and
returns the ladder; nothing here reads a table or the clock. The read that
gathers the evidence is ``conviction_read.py``. Whether the ladder is *applied*
is Everton's flag (``MEME_CONVICTION_SIZING``, default **off**): off, the ladder
is still computed and written into the order's ``admission`` JSON (shadow), and
the size is the flat one of before. Every number is an env override, none of
them policy of capital: the cap stays ``MEME_MAX_SOL_PER_TRADE`` and the floor
stays ``MEME_MIN_TRADE_SOL`` — the ladder only ever goes **down** from the cap.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from decimal import ROUND_DOWN, Decimal
from typing import Any, Final

from hunter_core.execution.meme.gates import parse_flag
from hunter_meme_executor.creator_flow import CHAIN_FLOW_SOURCE, TAPE_FLOW_SOURCE

__all__ = [
    "ENV_CONVICTION_SIZING",
    "REFUSAL_CONVICTION_TOO_LOW",
    "REFUSAL_ENTRY_AFTER_DROP",
    "ConvictionConfig",
    "ConvictionEvidence",
    "ConvictionLadder",
    "Rung",
    "evaluate_conviction",
]

ENV_CONVICTION_SIZING = "MEME_CONVICTION_SIZING"
"""``off`` (default) | ``on``. Everton's flag: only ``on`` changes a size."""
REFUSAL_ENTRY_AFTER_DROP: Final = "entry_after_drop"
REFUSAL_CONVICTION_TOO_LOW: Final = "conviction_too_low"

_ZERO = Decimal(0)
_ONE = Decimal(1)
_LAMPORT = Decimal("0.000000001")


def _quantize(value: Decimal) -> Decimal:
    return max(_ZERO, value).quantize(_LAMPORT, rounding=ROUND_DOWN)


def _decimal_in(
    env: Mapping[str, str], name: str, default: Decimal, *, low: Decimal, high: Decimal
) -> Decimal:
    """``low < value <= high`` (``low`` excluded so a multiplier is never ``0``
    and a threshold is never degenerate). Unreadable or out of range ⇒ the
    default: tuning, not authorization (T4.28h's two families)."""
    raw = (env.get(name) or "").strip()
    if not raw:
        return default
    try:
        value = Decimal(raw)
    except (ArithmeticError, ValueError):
        return default
    return value if low < value <= high else default


def _int_in(env: Mapping[str, str], name: str, default: int, *, low: int) -> int:
    raw = (env.get(name) or "").strip()
    try:
        value = int(raw) if raw else default
    except ValueError:
        return default
    return value if value >= low else default


@dataclass(frozen=True, slots=True)
class ConvictionConfig:
    """The ladder's numbers. Multipliers in ``(0, 1]``, shares as fractions."""

    enabled: bool = False
    tape_only_multiplier: Decimal = Decimal("0.5")
    """``MEME_CONVICTION_TAPE_ONLY_MULT`` — creator flow decided by the tape alone."""
    min_unique_buyers: int = 25
    """``MEME_CONVICTION_MIN_UNIQUE_BUYERS`` — EXP-M10's threshold."""
    buyers_multiplier: Decimal = Decimal("0.5")
    """``MEME_CONVICTION_BUYERS_MULT`` — below the threshold, or unknown."""
    holders_multiplier: Decimal = Decimal("0.5")
    """``MEME_CONVICTION_HOLDERS_MULT`` — holders not rising, or unknown."""
    bundled_max_pct: Decimal = Decimal("0.10")
    """``MEME_CONVICTION_BUNDLED_MAX_PCT`` — fraction; above it the concentration rung fires."""
    top10_max_pct: Decimal = Decimal("0.20")
    """``MEME_CONVICTION_TOP10_MAX_PCT`` — fraction; above it the concentration rung fires."""
    concentration_multiplier: Decimal = Decimal("0.5")
    """``MEME_CONVICTION_CONCENTRATION_MULT``."""
    drop_pct: Decimal = Decimal("0.50")
    """``MEME_CONVICTION_DROP_PCT`` — ``1 − real_sol_now / peak`` at or above this refuses."""
    drop_window_s: int = 60
    """``MEME_CONVICTION_DROP_WINDOW_S`` — the peak is the max of this window (KB-0118: N = 60 s)."""
    peak_unknown_multiplier: Decimal = Decimal("0.5")
    """``MEME_CONVICTION_PEAK_UNKNOWN_MULT`` — no photo of the curve in the window."""
    floor: Decimal = Decimal("0.25")
    """``MEME_CONVICTION_FLOOR`` — a product below this refuses ``conviction_too_low``."""
    evidence_max_age_s: int = 120
    """``MEME_CONVICTION_EVIDENCE_MAX_AGE_S`` — a 15 s row older than this is unknown."""

    @classmethod
    def from_env(cls, env: Mapping[str, str]) -> ConvictionConfig:
        d = cls()
        mult = {"low": _ZERO, "high": _ONE}
        return cls(
            enabled=parse_flag(env.get(ENV_CONVICTION_SIZING)),
            tape_only_multiplier=_decimal_in(
                env, "MEME_CONVICTION_TAPE_ONLY_MULT", d.tape_only_multiplier, **mult
            ),
            min_unique_buyers=_int_in(
                env, "MEME_CONVICTION_MIN_UNIQUE_BUYERS", d.min_unique_buyers, low=0
            ),
            buyers_multiplier=_decimal_in(
                env, "MEME_CONVICTION_BUYERS_MULT", d.buyers_multiplier, **mult
            ),
            holders_multiplier=_decimal_in(
                env, "MEME_CONVICTION_HOLDERS_MULT", d.holders_multiplier, **mult
            ),
            bundled_max_pct=_decimal_in(
                env, "MEME_CONVICTION_BUNDLED_MAX_PCT", d.bundled_max_pct, **mult
            ),
            top10_max_pct=_decimal_in(
                env, "MEME_CONVICTION_TOP10_MAX_PCT", d.top10_max_pct, **mult
            ),
            concentration_multiplier=_decimal_in(
                env, "MEME_CONVICTION_CONCENTRATION_MULT", d.concentration_multiplier, **mult
            ),
            drop_pct=_decimal_in(env, "MEME_CONVICTION_DROP_PCT", d.drop_pct, **mult),
            drop_window_s=_int_in(env, "MEME_CONVICTION_DROP_WINDOW_S", d.drop_window_s, low=15),
            peak_unknown_multiplier=_decimal_in(
                env, "MEME_CONVICTION_PEAK_UNKNOWN_MULT", d.peak_unknown_multiplier, **mult
            ),
            floor=_decimal_in(env, "MEME_CONVICTION_FLOOR", d.floor, **mult),
            evidence_max_age_s=_int_in(
                env, "MEME_CONVICTION_EVIDENCE_MAX_AGE_S", d.evidence_max_age_s, low=1
            ),
        )

    def as_json(self) -> dict[str, Any]:
        return {
            "enabled": self.enabled,
            "tape_only_multiplier": str(self.tape_only_multiplier),
            "min_unique_buyers": self.min_unique_buyers,
            "buyers_multiplier": str(self.buyers_multiplier),
            "holders_multiplier": str(self.holders_multiplier),
            "bundled_max_pct": str(self.bundled_max_pct),
            "top10_max_pct": str(self.top10_max_pct),
            "concentration_multiplier": str(self.concentration_multiplier),
            "drop_pct": str(self.drop_pct),
            "drop_window_s": self.drop_window_s,
            "peak_unknown_multiplier": str(self.peak_unknown_multiplier),
            "floor": str(self.floor),
            "evidence_max_age_s": self.evidence_max_age_s,
        }


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
    real_sol_peak: Decimal | None
    """``max(real_sol_reserves)`` of ``meme_curve_snapshots`` in the drop window, in SOL."""
    peak_points: int = 0


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
    enabled: bool
    rungs: tuple[Rung, ...]
    multiplier: Decimal
    sol_cap: Decimal
    """``min(requested, max_sol_per_trade)`` — what the flat size was."""
    sol_sized: Decimal
    """``quantize(sol_cap × multiplier)``."""
    ladder_refusal: str | None
    """What the ladder says regardless of the flag (shadow included)."""

    @property
    def refusal(self) -> str | None:
        return self.ladder_refusal if self.enabled else None

    @property
    def applied(self) -> bool:
        return self.enabled and self.ladder_refusal is None

    @property
    def requested_sol(self) -> Decimal:
        """The size the engine's proposal carries: sized when applied, the cap otherwise."""
        return self.sol_sized if self.applied else self.sol_cap

    def as_json(self) -> dict[str, Any]:
        return {
            "enabled": self.enabled,
            "applied": self.applied,
            "multiplier": str(self.multiplier),
            "sol_cap": str(self.sol_cap),
            "sol_sized": str(self.sol_sized),
            "sol_requested": str(self.requested_sol),
            "refusal": self.refusal or "",
            "ladder_refusal": self.ladder_refusal or "",
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


def _drop_rung(e: ConvictionEvidence, c: ConvictionConfig) -> Rung:
    if e.real_sol_now is None or e.real_sol_peak is None or e.real_sol_peak <= 0:
        # No peak to compare against is not a drop and not a pass: a discount,
        # and the reason says which input was missing.
        value = f"now={e.real_sol_now} peak={e.real_sol_peak} points={e.peak_points}"
        return Rung("drop", value, c.peak_unknown_multiplier, "peak_unknown")
    drawdown = _ONE - e.real_sol_now / e.real_sol_peak
    value = f"now={e.real_sol_now} peak={e.real_sol_peak} dd={drawdown:.4f} points={e.peak_points}"
    if drawdown >= c.drop_pct:
        return Rung("drop", value, _ZERO, REFUSAL_ENTRY_AFTER_DROP)
    return Rung("drop", value, _ONE, "within_window")


def evaluate_conviction(
    evidence: ConvictionEvidence,
    config: ConvictionConfig,
    *,
    requested_sol: Decimal,
    max_sol_per_trade: Decimal,
    min_trade_sol: Decimal,
) -> ConvictionLadder:
    """Pure: evidence × config → the ladder, its product and its verdict.

    ``sol_cap = min(requested_sol, max_sol_per_trade)`` is the flat size of
    before; the sized budget is ``sol_cap × product``, quantized down to the
    lamport. A drop rung refuses ``entry_after_drop`` before the floor is looked
    at; a product below ``floor`` or a budget below ``min_trade_sol`` refuses
    ``conviction_too_low``. When the flag is off the same ladder is returned with
    ``enabled = False`` so the row still shows what it would have done.
    """
    rungs = (
        _creator_rung(evidence, config),
        _buyers_rung(evidence, config),
        _holders_rung(evidence, config),
        _concentration_rung(evidence, config),
        _drop_rung(evidence, config),
    )
    product = _ONE
    for rung in rungs:
        product *= rung.multiplier
    cap = _quantize(min(requested_sol, max_sol_per_trade))
    sized = _quantize(cap * product)
    refusal: str | None = None
    if any(r.reason == REFUSAL_ENTRY_AFTER_DROP for r in rungs):
        refusal = REFUSAL_ENTRY_AFTER_DROP
    elif product < config.floor or sized < min_trade_sol:
        refusal = REFUSAL_CONVICTION_TOO_LOW
    return ConvictionLadder(
        enabled=config.enabled,
        rungs=rungs,
        multiplier=product,
        sol_cap=cap,
        sol_sized=sized,
        ladder_refusal=refusal,
    )
