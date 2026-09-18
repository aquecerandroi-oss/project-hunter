"""T4.61b/T4.61c — the conviction ladder's numbers (``ConvictionConfig``) and
Everton's flag ``MEME_CONVICTION_SIZING`` (default **off**).

Every number is an env override, none of them policy of capital: the cap stays
``MEME_MAX_SOL_PER_TRADE`` and the floor stays ``MEME_MIN_TRADE_SOL`` (T4.61c,
``hunter_risk_meme.limits``) — the ladder only ever goes **down** from the cap.
Unreadable or out of range ⇒ the default: tuning, not authorization (T4.28h's
two families); the boot is never refused by a ladder number.

T4.61c removed ``MEME_CONVICTION_PEAK_UNKNOWN_MULT``: a curve whose fall cannot
be judged is refused (``entry_after_drop_unknown``), not discounted (§8 — the
one clean edge fails closed). The variable, if still set, is ignored.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from hunter_core.execution.meme.gates import parse_flag

__all__ = ["ENV_CONVICTION_SIZING", "ConvictionConfig"]

ENV_CONVICTION_SIZING = "MEME_CONVICTION_SIZING"
"""``off`` (default) | ``on``. Everton's flag: only ``on`` evaluates the ladder."""

_ZERO = Decimal(0)
_ONE = Decimal(1)


def _decimal_in(
    env: Mapping[str, str], name: str, default: Decimal, *, low: Decimal, high: Decimal
) -> Decimal:
    """``low < value <= high`` (``low`` excluded so a multiplier is never ``0``
    and a threshold is never degenerate)."""
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
            "floor": str(self.floor),
            "evidence_max_age_s": self.evidence_max_age_s,
        }
