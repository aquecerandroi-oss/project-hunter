"""The pedigree exclusions (T4.16, EXP-M6 — E2 of the study of the 21 bets of
12/09/2026): a **cross-cutting** refusal applied to every rule set's gate,
before the set's own criteria, over two counts the radar already keeps in
``meme_tokens``:

- ``creator_prior_mints_1h`` — coins the same creator launched in the hour
  before this one (M-P26: "criador em série"; 6 of the 21 bets, all losers);
- ``symbol_dup_24h`` — other coins with the same ticker created in the 24 h
  before this one (M-P3: "clone de ticker"; 6 of 21, all losers).

Registered the way a gate is (``key``, ``version``, ``parameters``,
``description``, ``inputs``): moving a threshold is a new version. **Unknown
refuses, by name** (``creator_unknown``, ``symbol_unknown``): a coin whose
creator the radar never learned is not a coin with a clean pedigree — the
same reading the entry gate gives a missing feed (Astra's MUST-FIX 1).

The two other exclusions the study names — ``post_sibling_rank_at_create > 1``
(M-P33) and "no twitter **and** empty description" — have no column yet
(T4.2g/T4.12 data), so they are **not** criteria of this version; the
pre-registration (``obsidian/05-EXPERIMENTS/EXP-M6-exclusoes-de-pedigree.md``)
says so, and a version that adds them is ``exclusoes_de_pedigree v2``.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Final

__all__ = [
    "PEDIGREE_INPUTS",
    "PEDIGREE_REFUSALS",
    "PEDIGREE_V1",
    "PedigreeFeatures",
    "PedigreeGate",
    "evaluate_pedigree",
]

PEDIGREE_INPUTS: Final = (
    "meme_tokens.creator",
    "meme_tokens.symbol",
    "meme_tokens.created_at",
)
PEDIGREE_REFUSALS: Final = frozenset(
    {"creator_unknown", "creator_serial", "symbol_unknown", "symbol_clone"}
)
"""The closed vocabulary this module can add to a gate's refusals."""


@dataclass(frozen=True, slots=True)
class PedigreeGate:
    """One registered pedigree gate. ``version`` bumps whenever a threshold moves."""

    key: str
    version: int
    description: str
    max_creator_prior_mints_1h: int
    """``creator_prior_mints_1h`` above this refuses ``creator_serial``
    (the study's "≥ 2" is ``max = 1``)."""
    max_symbol_dup_24h: int
    """``symbol_dup_24h`` above this refuses ``symbol_clone`` (the study's
    "≥ 3 moedas com o mesmo símbolo" counts this one: ``max = 2`` others)."""
    creator_window_s: int = 3600
    symbol_window_s: int = 86400
    inputs: tuple[str, ...] = PEDIGREE_INPUTS

    def __post_init__(self) -> None:
        if self.version < 1:
            raise ValueError("version starts at 1")
        if self.max_creator_prior_mints_1h < 0 or self.max_symbol_dup_24h < 0:
            raise ValueError("a pedigree ceiling cannot be negative")
        if self.creator_window_s < 1 or self.symbol_window_s < 1:
            raise ValueError("a pedigree window is at least one second")

    def as_parameters(self) -> Mapping[str, str]:
        return {
            "max_creator_prior_mints_1h": str(self.max_creator_prior_mints_1h),
            "max_symbol_dup_24h": str(self.max_symbol_dup_24h),
            "creator_window_s": str(self.creator_window_s),
            "symbol_window_s": str(self.symbol_window_s),
        }


@dataclass(frozen=True, slots=True)
class PedigreeFeatures:
    """The two counts at proposal time. ``None`` = the identity is unknown."""

    creator_prior_mints_1h: int | None
    symbol_dup_24h: int | None


PEDIGREE_V1: Final = PedigreeGate(
    key="exclusoes_de_pedigree",
    version=1,
    description=(
        "EXP-M6: refuse a creator with 2+ launches in the previous hour and a ticker "
        "with 3+ coins in the previous 24 h; unknown identity refuses."
    ),
    max_creator_prior_mints_1h=1,
    max_symbol_dup_24h=2,
)
"""The study's thresholds, frozen: ``creator_prior_mints_1h ≥ 2`` and
``symbol_dup_24h ≥ 3`` (this coin plus two others)."""


def evaluate_pedigree(features: PedigreeFeatures, gate: PedigreeGate) -> tuple[str, ...]:
    """The named refusals — empty when the pedigree is clean. Pure."""
    refusals: list[str] = []
    if features.creator_prior_mints_1h is None:
        refusals.append("creator_unknown")
    elif features.creator_prior_mints_1h > gate.max_creator_prior_mints_1h:
        refusals.append("creator_serial")
    if features.symbol_dup_24h is None:
        refusals.append("symbol_unknown")
    elif features.symbol_dup_24h > gate.max_symbol_dup_24h:
        refusals.append("symbol_clone")
    return tuple(refusals)
