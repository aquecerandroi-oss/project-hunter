"""Validation of one :class:`~hunter_indicators.meme.rules.EntryGate`'s
thresholds — split out of ``rules.py`` for the 350-line budget (T4.23).
``EntryGate.__post_init__`` calls :func:`validate_entry_gate` once and does
nothing else; every failure names the field, exactly as the checks did before
the split.
"""

from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING, Final

if TYPE_CHECKING:
    from hunter_indicators.meme.rules import EntryGate

__all__ = ["validate_entry_gate"]

_HUNDRED: Final = Decimal(100)


def validate_entry_gate(gate: EntryGate) -> None:
    if gate.version < 1:
        raise ValueError("version starts at 1")
    if gate.min_age_s < 0 or gate.max_age_s < gate.min_age_s:
        raise ValueError("age window must satisfy 0 <= min_age_s <= max_age_s")
    if not 0 <= gate.min_progress_pct <= gate.max_progress_pct <= _HUNDRED:
        raise ValueError("progress window must satisfy 0 <= min <= max <= 100")
    if not 0 < gate.max_participation_pct <= _HUNDRED:
        raise ValueError("max_participation_pct must be in (0, 100]")
    low, high = gate.min_distance_to_support_pct, gate.max_distance_to_support_pct
    if low is not None and high is not None and low > high:
        raise ValueError("distance band must satisfy min <= max")
    if gate.min_hype_score is not None and not 0 <= gate.min_hype_score <= 1:
        raise ValueError("min_hype_score must be in [0, 1]")
    if gate.max_dev_share is not None and not 0 <= gate.max_dev_share <= 1:
        raise ValueError("max_dev_share must be in [0, 1]")
    if gate.max_snipers is not None and gate.max_snipers < 0:
        raise ValueError("max_snipers cannot be negative")
    if gate.max_top10_share is not None and not 0 <= gate.max_top10_share <= 1:
        raise ValueError("max_top10_share must be in [0, 1]")
    if gate.min_unique_buyers is not None and gate.min_unique_buyers < 0:
        raise ValueError("min_unique_buyers cannot be negative")
    if gate.max_sells_to_buys is not None and gate.max_sells_to_buys < 0:
        raise ValueError("max_sells_to_buys cannot be negative")
    if gate.min_holders is not None and gate.min_holders < 0:
        raise ValueError("min_holders cannot be negative")
    _validate_sniper_band(gate)
    _validate_top10_band(gate)


def _validate_sniper_band(gate: EntryGate) -> None:
    """T4.23 (EXP-M5 arm 3): a floor beside ``max_snipers``, never above it."""
    if gate.min_snipers is None:
        return
    if gate.min_snipers < 0:
        raise ValueError("min_snipers cannot be negative")
    if gate.max_snipers is not None and gate.min_snipers > gate.max_snipers:
        raise ValueError("min_snipers must be <= max_snipers")


def _validate_top10_band(gate: EntryGate) -> None:
    """T4.23 (EXP-M5 arm 4): a floor beside ``max_top10_share``, never above it."""
    if gate.min_top10_share is None:
        return
    if not 0 <= gate.min_top10_share <= 1:
        raise ValueError("min_top10_share must be in [0, 1]")
    if gate.max_top10_share is not None and gate.min_top10_share > gate.max_top10_share:
        raise ValueError("min_top10_share must be <= max_top10_share")
