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

**T4.24 (EXP-M6, braço 2) adds a second, independent check** —
``evaluate_repeat_dumper`` — over two counts our own database can already
answer, not a bump of ``PEDIGREE_V1`` (its thresholds are frozen):
``creator_prior_dump_count`` (coins the same creator launched before, in
**any** window, where the creator sold — by the tape, by the chain watch or
by one of our own bets exiting ``creator_dump``) and
``creator_prior_dead_count`` (of those, how many died in their first 30
minutes; ``None`` per coin without a series is not counted either way). A
rule set opts in with ``params.pedigree_repeat_dumper: true`` — off by
default, exactly like a falsification arm's own word for
``pedigree_exclusions``.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Final

__all__ = [
    "PEDIGREE_INPUTS",
    "PEDIGREE_REFUSALS",
    "PEDIGREE_V1",
    "REPEAT_DUMPER_INPUTS",
    "REPEAT_DUMPER_REFUSAL",
    "PedigreeFeatures",
    "PedigreeGate",
    "evaluate_pedigree",
    "evaluate_repeat_dumper",
]

PEDIGREE_INPUTS: Final = (
    "meme_tokens.creator",
    "meme_tokens.symbol",
    "meme_tokens.created_at",
)
REPEAT_DUMPER_INPUTS: Final = (
    "meme_features_1m.creator_sold",
    "meme_paper_bets.creator_sold_seen_at",
    "meme_paper_bets.exit->>'reason'",
)
"""T4.24: what ``creator_prior_dump_count`` is read from — our own database,
never a third-party field."""
PEDIGREE_REFUSALS: Final = frozenset(
    {
        "creator_unknown",
        "creator_serial",
        "symbol_unknown",
        "symbol_clone",
        "creator_repeat_dumper",
    }
)
"""The closed vocabulary this module can add to a gate's refusals."""
REPEAT_DUMPER_REFUSAL: Final = "creator_repeat_dumper"


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
    """The counts at proposal time. ``None`` = the identity is unknown."""

    creator_prior_mints_1h: int | None
    symbol_dup_24h: int | None
    creator_prior_dump_count: int | None = None
    """T4.24: prior coins of the same creator (any window) where the creator
    sold, by our own database (see :data:`REPEAT_DUMPER_INPUTS`). ``None``
    only when the creator or its creation time is unknown — the same
    condition that already makes :func:`evaluate_pedigree` refuse
    ``creator_unknown``."""
    creator_prior_dead_count: int | None = None
    """T4.24: of the coins counted above, how many fell under 20 % of their
    own peak inside their first 30 minutes — diagnostic only, never a
    refusal; a coin with no series in that window is not counted either way."""


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


def evaluate_repeat_dumper(features: PedigreeFeatures) -> tuple[str, ...]:
    """T4.24 (EXP-M6, braço 2): refuse a creator with at least one prior dump
    in **our own** database. Pure, and independent of :data:`PEDIGREE_V1` —
    the caller applies it only when the rule set's own
    ``pedigree_repeat_dumper`` switch is on. An unknown count (``None``)
    refuses nothing here: whenever this check runs beside
    :func:`evaluate_pedigree` (T4.24's only wiring), that one already refuses
    the same row by name (``creator_unknown``)."""
    if features.creator_prior_dump_count is None:
        return ()
    return (REPEAT_DUMPER_REFUSAL,) if features.creator_prior_dump_count >= 1 else ()
