"""The hype score of a coin too young to have a line (T4.10, EXP-M3 — "os que não
tiver [linha] você vai deixar já semi-comprado por causa do hype").

A **documented** weighted average in ``[0, 1]``, frozen here as ``hype_score_v1``:

| component | raw input | normalized | weight |
|---|---|---|---|
| ``buys_1m`` | ``meme_features_1m.buys_1m`` | ``min(buys, 30) / 30`` | 0,35 |
| ``unique_buyers_1m`` | ``meme_features_1m.unique_buyers`` | ``min(buyers, 20) / 20`` | 0,25 |
| ``board`` | best 0-based position on the ``movers``/``new`` boards this minute | top-10 → 1, top-50 → 0,5, else 0 | 0,20 |
| ``has_social`` | the board entry's ``has_social`` | 1 if true, else 0 | 0,10 |
| ``snipers_low`` | ``meme_features_1m.snipers`` | 1 if ``snipers <= 2``, else 0 | 0,10 |

``score = Σ weight × normalized``. The full decomposition (``raw``,
``normalized``, ``weight``, ``contribution`` per component) travels with the
number, the way an opportunity score persists its decomposition (PIPELINE §5):
a reader must be able to say which component made a 0,63.

**Absence is named, never zeroed silently.** The score exists only when at
least one of the two sources — the tape (``swap-api``) and the boards
(``/ws/trenches``) — spoke about the mint in this minute. With neither the
score is ``None`` and ``hype_reason = no_tape_no_board``; with exactly one it is
computed with the other source's components at zero and ``hype_reason =
partial``, which is the brief's own rule and the reason ``partial`` sits next to
a non-null score. A missing ``snipers`` reading contributes 0 (an unknown
sniper count is not "few snipers"); a missing ``has_social`` contributes 0.

Everything is ``Decimal``: the score is persisted as ``numeric(9, 6)`` and a
gate compares it to a frozen threshold.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_HALF_EVEN, Decimal, localcontext
from typing import Final

from hunter_core.domain.enums import FeatureCategory
from hunter_core.strategies.numeric import CONTEXT
from hunter_indicators.features.definitions import FeatureDefinition

__all__ = [
    "BOARD_TOP_10",
    "BOARD_TOP_50",
    "BUYERS_CAP",
    "BUYS_CAP",
    "HYPE_DEFINITION",
    "HYPE_REASONS",
    "NO_TAPE_NO_BOARD",
    "PARTIAL",
    "SNIPERS_LOW_MAX",
    "WEIGHTS",
    "HypeComponent",
    "HypeInputs",
    "HypeScore",
    "hype_score",
]

BUYS_CAP: Final = 30
BUYERS_CAP: Final = 20
BOARD_TOP_10: Final = 10
BOARD_TOP_50: Final = 50
SNIPERS_LOW_MAX: Final = 2
WEIGHTS: Final[dict[str, Decimal]] = {
    "buys_1m": Decimal("0.35"),
    "unique_buyers_1m": Decimal("0.25"),
    "board": Decimal("0.20"),
    "has_social": Decimal("0.10"),
    "snipers_low": Decimal("0.10"),
}
"""The brief's five weights; they sum to one, and ``test_meme_hype.py`` says so."""

NO_TAPE_NO_BOARD: Final = "no_tape_no_board"
PARTIAL: Final = "partial"
HYPE_REASONS: Final = frozenset({NO_TAPE_NO_BOARD, PARTIAL})

_SIX = Decimal("0.000001")
_ONE = Decimal(1)
_ZERO = Decimal(0)
_HALF = Decimal("0.5")

HYPE_DEFINITION: Final = FeatureDefinition(
    key="hype_score",
    version=1,
    category=FeatureCategory.MICROSTRUCTURE,
    inputs=(
        "meme_features_1m.buys_1m",
        "meme_features_1m.unique_buyers",
        "meme_board_observations.position",
        "meme_board_observations.has_social",
        "meme_features_1m.snipers",
    ),
    description=(
        "Weighted average in [0, 1] of the minute's buys, unique buyers, board standing "
        "(movers/new), social presence and low sniper count; NULL with a reason when "
        "neither the tape nor the boards spoke."
    ),
    params={
        "weights": {name: str(weight) for name, weight in WEIGHTS.items()},
        "buys_cap": BUYS_CAP,
        "buyers_cap": BUYERS_CAP,
        "board_top_10": BOARD_TOP_10,
        "board_top_50": BOARD_TOP_50,
        "snipers_low_max": SNIPERS_LOW_MAX,
    },
)


@dataclass(frozen=True, slots=True)
class HypeInputs:
    """What one minute says about one mint. ``None`` is *not observed*."""

    buys_1m: int | None
    unique_buyers_1m: int | None
    board_position: int | None
    """Best (lowest) 0-based position across ``movers`` and ``new`` this minute;
    ``None`` when the mint sat on neither."""
    has_social: bool | None
    snipers: int | None
    tape_present: bool
    """The tape of this mint was pulled for this minute (a zero is a stated zero)."""
    board_present: bool
    """A board row of this mint exists for this minute (any board)."""


@dataclass(frozen=True, slots=True)
class HypeComponent:
    name: str
    raw: str | None
    normalized: Decimal
    weight: Decimal
    contribution: Decimal


@dataclass(frozen=True, slots=True)
class HypeScore:
    score: Decimal | None
    reason: str | None
    components: tuple[HypeComponent, ...]

    def as_json(self) -> dict[str, object]:
        """The decomposition, strings for every decimal — what a proposal's
        ``reasons`` carries."""
        return {
            "score": None if self.score is None else str(self.score),
            "reason": self.reason,
            "components": [
                {
                    "name": c.name,
                    "raw": c.raw,
                    "normalized": str(c.normalized),
                    "weight": str(c.weight),
                    "contribution": str(c.contribution),
                }
                for c in self.components
            ],
        }


def _capped(value: int | None, cap: int) -> Decimal:
    if value is None or value <= 0:
        return _ZERO
    with localcontext(CONTEXT):
        return min(Decimal(value), Decimal(cap)) / Decimal(cap)


def _board(position: int | None) -> Decimal:
    if position is None or position < 0:
        return _ZERO
    if position < BOARD_TOP_10:
        return _ONE
    return _HALF if position < BOARD_TOP_50 else _ZERO


def _normalized(inputs: HypeInputs) -> dict[str, tuple[str | None, Decimal]]:
    return {
        "buys_1m": (_raw(inputs.buys_1m), _capped(inputs.buys_1m, BUYS_CAP)),
        "unique_buyers_1m": (
            _raw(inputs.unique_buyers_1m),
            _capped(inputs.unique_buyers_1m, BUYERS_CAP),
        ),
        "board": (_raw(inputs.board_position), _board(inputs.board_position)),
        "has_social": (_raw(inputs.has_social), _ONE if inputs.has_social else _ZERO),
        "snipers_low": (
            _raw(inputs.snipers),
            _ONE if inputs.snipers is not None and inputs.snipers <= SNIPERS_LOW_MAX else _ZERO,
        ),
    }


def _raw(value: object) -> str | None:
    return None if value is None else str(value)


def hype_score(inputs: HypeInputs) -> HypeScore:
    """The documented score, its reason and its decomposition. Pure."""
    components: list[HypeComponent] = []
    total = _ZERO
    with localcontext(CONTEXT):
        for name, (raw, normalized) in _normalized(inputs).items():
            weight = WEIGHTS[name]
            contribution = (weight * normalized).quantize(_SIX, rounding=ROUND_HALF_EVEN)
            components.append(HypeComponent(name, raw, normalized, weight, contribution))
            total += contribution
    if not inputs.tape_present and not inputs.board_present:
        return HypeScore(score=None, reason=NO_TAPE_NO_BOARD, components=tuple(components))
    reason = None if inputs.tape_present and inputs.board_present else PARTIAL
    score = min(max(total, _ZERO), _ONE).quantize(_SIX, rounding=ROUND_HALF_EVEN)
    return HypeScore(score=score, reason=reason, components=tuple(components))
